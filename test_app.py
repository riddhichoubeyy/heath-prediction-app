
"""Automated checks for validation, SQLite CRUD, the AI client and UI handlers.

The real Gemini API is never called here: requests.post is replaced with fakes.
The UI handlers in app.py are tested with a stand-in for the streamlit module.
"""

import importlib
import inspect
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

import ai_service
import database
import validation

PROJECT_DIR = Path(__file__).parent

# The 10 assignment records, exactly as supplied.
TEST_DATA = [
    (1, "Robyn Pears", "28.01.1960", "robyn@gmail.com", "232", "13.5", "180"),
    (2, "John Hunter", "10.12.1990", "hunter@gmail", "94", "15", "200"),
    (3, "Darryl Tim", "12.11.1993", "timd@smh.com.au", "240", "18.6", "326"),
    (4, "Peter Larry", "31.11.2001", "Larry@hotmail.com", "88", "11.5", "165"),
    (5, "Sam Kerr", "09.12.2006", "sam@news.com.au", "198", "8.9", "192"),
    (6, "Robyn Pears", "28.01.1960", "robyn@gmail.com", "232", "13.5", "180"),
    (7, "Madison XI", "12.09.1998", "madison@hotmail.com", "85", "7.6", "163"),
    (8, "Kris Wu", "19.10.2030", "Kris.wu.gmail.com", "79", "16.5", "197"),
    (9, "Tenille Singh", "30.11.1991", "Tenille@yahoo.com", "101", "15", "310"),
    (10, "Prem Kumar", "28.04.1990", "prem@telstra.com", "155", "12.5", "265"),
]

VALID_TESTS = [1, 3, 5, 6, 7, 9, 10]
EXPECTED_ERRORS = {2: 1, 4: 1, 8: 2}


def fields_of(test_number):
    """Return the six form values for one supplied test record."""
    return TEST_DATA[test_number - 1][1:]


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    database.init_db()


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def interactions_body(text="Looks typical."):
    """Create a successful response in the Gemini Interactions API format."""
    return {
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {"type": "text", "text": text}
                ]
            }
        ]
    }


# ---------------------------------------------------------------- validation


def test_supplied_records_expected_error_counts():
    for number, *form_values in TEST_DATA:
        _, errors = validation.validate_patient(*form_values)
        assert len(errors) == EXPECTED_ERRORS.get(number, 0), (number, errors)


def test_exactly_seven_valid_and_three_rejected():
    valid = [
        number
        for number, *form_values in TEST_DATA
        if not validation.validate_patient(*form_values)[1]
    ]
    assert valid == VALID_TESTS


def test_error_messages_identify_the_problem():
    _, e2 = validation.validate_patient(*fields_of(2))
    _, e4 = validation.validate_patient(*fields_of(4))
    _, e8 = validation.validate_patient(*fields_of(8))

    assert "Email" in e2[0]
    assert "valid calendar date" in e4[0]
    assert any("future" in error for error in e8)
    assert any("Email" in error for error in e8)


@pytest.mark.parametrize("email", [
    "robyn@gmail.com",
    "timd@smh.com.au",
    "a.b+c@sub.example.org",
    "x_y@domain.io",
])
def test_valid_emails(email):
    assert validation.validate_email(email) == (email, None)


@pytest.mark.parametrize("email", [
    "",
    "   ",
    "hunter@gmail",
    "Kris.wu.gmail.com",
    "@gmail.com",
    "name@.com",
    "name@domain.",
    "na me@domain.com",
    "name@@domain.com",
    "name@domain.c",
])
def test_invalid_emails(email):
    assert validation.validate_email(email)[1] is not None


@pytest.mark.parametrize("text,iso", [
    ("28/01/1960", "1960-01-28"),
    ("28.01.1960", "1960-01-28"),
    ("29.02.2000", "2000-02-29"),
    ("01.01.1900", "1900-01-01"),
])
def test_valid_dates(text, iso):
    assert validation.validate_date_of_birth(text) == (iso, None)


@pytest.mark.parametrize("text", [
    "",
    "  ",
    "abc",
    "31.11.2001",
    "30.02.2000",
    "29.02.2001",
    "00.01.2000",
    "32.01.2000",
    "10.13.2000",
    "28-01-1960",
    "28/01.1960",
    "1960-01-28",
    "28.01.60",
    "28.01.1960 extra",
])
def test_invalid_dates(text):
    value, error = validation.validate_date_of_birth(text)
    assert value is None and error is not None


def test_future_dates_rejected_but_today_accepted():
    today = date.today()
    tomorrow = today + timedelta(days=1)

    assert validation.validate_date_of_birth(
        today.strftime("%d/%m/%Y")
    )[1] is None

    _, error = validation.validate_date_of_birth(
        tomorrow.strftime("%d/%m/%Y")
    )
    assert "future" in error


def test_implausibly_old_date_rejected():
    assert validation.validate_date_of_birth("01.01.1899")[1] is not None


@pytest.mark.parametrize("value", [
    "232",
    "13.5",
    " 180 ",
    "0.1",
    "1e2",
])
def test_valid_blood_values(value):
    number, error = validation.validate_blood_value(value, "Glucose")
    assert error is None and number == float(value)


@pytest.mark.parametrize("value", [
    "",
    "  ",
    None,
    "abc",
    "12,5",
    "0",
    "-5",
    "nan",
    "inf",
    "-inf",
    "1 2",
])
def test_invalid_blood_values(value):
    number, error = validation.validate_blood_value(value, "Glucose")
    assert number is None and error is not None


def test_blood_error_names_the_field():
    error = validation.validate_blood_value("abc", "Haemoglobin")[1]
    assert "Haemoglobin" in error


@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_name_rejected(value):
    assert validation.validate_name(value)[1] is not None


def test_all_empty_fields_report_six_errors():
    _, errors = validation.validate_patient("", "", "", "", "", "")
    assert len(errors) == 6


def test_validation_does_not_alter_values():
    record, errors = validation.validate_patient(
        "Mary  Jane",
        "09.12.2006",
        "Sam@News.com.au",
        "198",
        "8.9",
        "192",
    )

    assert errors == []
    assert record["full_name"] == "Mary  Jane"
    assert record["email"] == "Sam@News.com.au"
    assert (
        record["glucose"],
        record["haemoglobin"],
        record["cholesterol"],
    ) == (198.0, 8.9, 192.0)
    assert record["date_of_birth"] == "2006-12-09"


# ------------------------------------------------------------------ database


def test_crud_and_duplicates(temp_db):
    ids = {}

    for number, *form_values in TEST_DATA:
        record, errors = validation.validate_patient(*form_values)

        if not errors:
            ids[number] = database.create_patient(record, "remark")

    saved = database.get_all_patients()

    assert len(saved) == 7
    assert ids[1] != ids[6]
    assert [p["full_name"] for p in saved].count("Robyn Pears") == 2

    record, _ = validation.validate_patient(*fields_of(3))
    record["email"] = "gokul@infocare.com"

    assert database.update_patient(ids[3], record, "remark")
    assert database.get_patient(ids[3])["email"] == "gokul@infocare.com"

    assert database.delete_patient(ids[1])
    assert database.get_patient(ids[1]) is None
    assert len(database.get_all_patients()) == 6
    assert database.get_patient(ids[6]) is not None


def test_stored_values_round_trip(temp_db):
    record, _ = validation.validate_patient(*fields_of(1))
    new_id = database.create_patient(record, "AI text")

    stored = database.get_patient(new_id)

    assert stored == {
        "id": new_id,
        "full_name": "Robyn Pears",
        "date_of_birth": "1960-01-28",
        "email": "robyn@gmail.com",
        "glucose": 232.0,
        "haemoglobin": 13.5,
        "cholesterol": 180.0,
        "remarks": "AI text",
    }


def test_missing_record_operations(temp_db):
    record, _ = validation.validate_patient(*fields_of(1))

    assert database.get_patient(999) is None
    assert database.update_patient(999, record, "x") is False
    assert database.delete_patient(999) is False


def test_sql_text_is_stored_literally(temp_db):
    record, _ = validation.validate_patient(
        "Robert'); DROP TABLE patients;--",
        "01.01.1990",
        "a@b.com",
        "90",
        "14",
        "180",
    )

    database.create_patient(record, "remark")

    assert database.get_all_patients()[0]["full_name"] == (
        "Robert'); DROP TABLE patients;--"
    )


def test_records_persist_across_processes(tmp_path):
    env = {
        **os.environ,
        "DB_PATH": str(tmp_path / "persist.db"),
    }

    write_code = (
        "import database, validation\n"
        "database.init_db()\n"
        "record, _ = validation.validate_patient("
        "'Ann Lee', '01.01.1990', 'ann@x.com', '90', '14', '180')\n"
        "database.create_patient(record, 'saved remark')\n"
    )

    read_code = (
        "import database; "
        "print([p['remarks'] for p in database.get_all_patients()])"
    )

    subprocess.run(
        [sys.executable, "-c", write_code],
        env=env,
        cwd=PROJECT_DIR,
        check=True,
    )

    result = subprocess.run(
        [sys.executable, "-c", read_code],
        env=env,
        cwd=PROJECT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "['saved remark']"


# ---------------------------------------------------------------- AI service


def test_default_model_is_gemini_3_1_flash_lite(monkeypatch):
    assert ai_service.DEFAULT_MODEL == "gemini-3.1-flash-lite"

    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    with patch(
        "ai_service.requests.post",
        return_value=FakeResponse(200, interactions_body()),
    ) as post:
        ai_service.generate_remarks(90, 14, 180)

    assert post.call_args.args[0] == ai_service.API_URL
    assert post.call_args.kwargs["json"]["model"] == "gemini-3.1-flash-lite"


def test_model_is_configurable_and_blank_uses_default(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setenv("GEMINI_MODEL", "my-custom-model")

    with patch(
        "ai_service.requests.post",
        return_value=FakeResponse(200, interactions_body()),
    ) as post:
        ai_service.generate_remarks(90, 14, 180)

    assert post.call_args.kwargs["json"]["model"] == "my-custom-model"

    monkeypatch.setenv("GEMINI_MODEL", "   ")

    with patch(
        "ai_service.requests.post",
        return_value=FakeResponse(200, interactions_body()),
    ) as post:
        ai_service.generate_remarks(90, 14, 180)

    assert post.call_args.kwargs["json"]["model"] == ai_service.DEFAULT_MODEL


def test_request_format(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key-123")

    with patch(
        "ai_service.requests.post",
        return_value=FakeResponse(200, interactions_body()),
    ) as post:
        ai_service.generate_remarks(232.0, 13.5, 180.0)

    kwargs = post.call_args.kwargs

    assert kwargs["headers"]["x-goog-api-key"] == "secret-key-123"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert "secret-key-123" not in post.call_args.args[0]
    assert kwargs["timeout"] == ai_service.TIMEOUT_SECONDS

    assert kwargs["json"]["model"] == ai_service.DEFAULT_MODEL
    assert kwargs["json"]["store"] is False
    assert isinstance(kwargs["json"]["input"], str)
    assert set(kwargs["json"]) == {"model", "input", "store"}


def test_only_blood_values_are_sent(monkeypatch):
    assert list(inspect.signature(ai_service.generate_remarks).parameters) == [
        "glucose",
        "haemoglobin",
        "cholesterol",
    ]

    monkeypatch.setenv("GEMINI_API_KEY", "dummy")

    with patch(
        "ai_service.requests.post",
        return_value=FakeResponse(200, interactions_body()),
    ) as post:
        ai_service.generate_remarks(232.0, 13.5, 180.0)

    prompt = post.call_args.kwargs["json"]["input"]

    assert "Glucose: 232.0" in prompt
    assert "Haemoglobin: 13.5" in prompt
    assert "Cholesterol: 180.0" in prompt
    assert "@" not in prompt
    assert post.call_args.kwargs["json"]["store"] is False


def test_prompt_asks_for_informational_not_diagnosis():
    prompt = ai_service._build_prompt(90, 14, 180)

    assert "not a diagnosis" in prompt
    assert "not a medical diagnosis" in prompt


def test_successful_response_text_is_returned_trimmed(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")

    with patch(
        "ai_service.requests.post",
        return_value=FakeResponse(200, interactions_body(" Looks typical. ")),
    ):
        assert ai_service.generate_remarks(90, 14, 180) == "Looks typical."


def test_multiple_parts_are_joined_and_thought_parts_skipped(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")

    body = {
        "status": "completed",
        "steps": [
            {
                "type": "thought",
                "content": [
                    {"type": "text", "text": "internal reasoning"}
                ],
            },
            {
                "type": "model_output",
                "content": [
                    {"type": "text", "text": "Part one. "},
                    {"type": "text", "text": "Part two."},
                ],
            },
        ],
    }

    with patch(
        "ai_service.requests.post",
        return_value=FakeResponse(200, body),
    ):
        assert ai_service.generate_remarks(90, 14, 180) == (
            "Part one. \nPart two."
        )


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with patch("ai_service.requests.post") as post:
        with pytest.raises(
            ai_service.AIServiceError,
            match="GEMINI_API_KEY",
        ):
            ai_service.generate_remarks(90, 14, 180)

    post.assert_not_called()


def test_blank_api_key_counts_as_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")

    with pytest.raises(
        ai_service.AIServiceError,
        match="GEMINI_API_KEY",
    ):
        ai_service.generate_remarks(90, 14, 180)


@pytest.mark.parametrize(
    "response,expected",
    [
        (
            FakeResponse(400, {"error": {"message": "API key not valid"}}),
            "HTTP 400.*API key not valid",
        ),
        (
            FakeResponse(401, {"error": {"message": "Unauthorized"}}),
            "HTTP 401",
        ),
        (
            FakeResponse(403, {"error": {"message": "Forbidden"}}),
            "HTTP 403",
        ),
        (
            FakeResponse(404, {"error": {"message": "Model not found"}}),
            "HTTP 404",
        ),
        (
            FakeResponse(429, {"error": {"message": "Rate limit exceeded"}}),
            "HTTP 429",
        ),
        (
            FakeResponse(500, {"error": {"message": "Server error"}}),
            "HTTP 500",
        ),
        (
            FakeResponse(503, {"error": {"message": "High demand"}}),
            "HTTP 503",
        ),
        (
            FakeResponse(418, {"error": {"message": "Unexpected error"}}),
            "HTTP 418",
        ),
        (
            FakeResponse(200, {"unexpected": 1}),
            "did not complete",
        ),
        (
            FakeResponse(200, None),
            "unexpected response",
        ),
        (
            FakeResponse(200, ["not", "a", "dict"]),
            "unexpected response",
        ),
        (
            FakeResponse(200, {"status": "completed", "steps": None}),
            "unexpected response",
        ),
        (
            FakeResponse(
                200,
                {
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": ["bad"],
                        }
                    ],
                },
            ),
            "unexpected response",
        ),
        (
            FakeResponse(200, {"status": "completed", "steps": []}),
            "empty assessment",
        ),
        (
            FakeResponse(200, interactions_body("")),
            "empty assessment",
        ),
        (
            FakeResponse(200, interactions_body("   ")),
            "empty assessment",
        ),
        (
            FakeResponse(200, {"status": "in_progress", "steps": []}),
            "did not complete",
        ),
    ],
)
def test_ai_error_responses(monkeypatch, response, expected):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")

    with patch("ai_service.time.sleep"):
        with patch(
            "ai_service.requests.post",
            return_value=response,
        ):
            with pytest.raises(
                ai_service.AIServiceError,
                match=expected,
            ):
                ai_service.generate_remarks(90, 14, 180)


def test_ai_timeout(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")

    with patch("ai_service.time.sleep"):
        with patch(
            "ai_service.requests.post",
            side_effect=requests.exceptions.Timeout,
        ):
            with pytest.raises(
                ai_service.AIServiceError,
                match="timed out",
            ):
                ai_service.generate_remarks(90, 14, 180)


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.ConnectionError,
        requests.exceptions.SSLError,
        requests.exceptions.RequestException,
    ],
)
def test_ai_connection_failures(monkeypatch, error):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")

    with patch(
        "ai_service.requests.post",
        side_effect=error,
    ):
        with pytest.raises(
            ai_service.AIServiceError,
            match="Could not connect",
        ):
            ai_service.generate_remarks(90, 14, 180)


def test_error_messages_never_contain_the_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key-123")

    failures = [
        FakeResponse(403, {"error": {"message": "Forbidden"}}),
        FakeResponse(404, {"error": {"message": "Not found"}}),
        FakeResponse(429, {"error": {"message": "Rate limit"}}),
        FakeResponse(500, {"error": {"message": "Server error"}}),
    ]

    with patch("ai_service.time.sleep"):
        for response in failures:
            with patch(
                "ai_service.requests.post",
                return_value=response,
            ):
                with pytest.raises(ai_service.AIServiceError) as info:
                    ai_service.generate_remarks(90, 14, 180)

            assert "secret-key-123" not in str(info.value)


# ------------------------------------------- UI handlers (streamlit replaced)


@pytest.fixture
def ui(temp_db, monkeypatch):
    """Import app.py against fake Streamlit and AI service modules."""

    fake_st = MagicMock()
    fake_st.session_state = {}

    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    sys.modules.pop("app", None)

    app = importlib.import_module("app")

    calls = []

    def fake_generate_remarks(glucose, haemoglobin, cholesterol):
        calls.append((glucose, haemoglobin, cholesterol))
        return f"AI remark #{len(calls)}"

    monkeypatch.setattr(
        app.ai_service,
        "generate_remarks",
        fake_generate_remarks,
    )

    yield app, fake_st, calls

    sys.modules.pop("app", None)


def create_all_supplied_records(app):
    for number, *form_values in TEST_DATA:
        app.handle_create(*form_values)


def test_create_flow_with_all_ten_supplied_records(ui):
    app, fake_st, calls = ui

    create_all_supplied_records(app)

    saved = database.get_all_patients()

    assert len(saved) == 7
    assert [p["full_name"] for p in saved] == [
        "Robyn Pears",
        "Darryl Tim",
        "Sam Kerr",
        "Robyn Pears",
        "Madison XI",
        "Tenille Singh",
        "Prem Kumar",
    ]

    assert len(calls) == 7
    assert fake_st.error.call_count == 3
    assert [p["remarks"] for p in saved] == [
        f"AI remark #{i}" for i in range(1, 8)
    ]
    assert calls[0] == (232.0, 13.5, 180.0)


def test_invalid_record_is_validated_before_the_api_is_called(ui):
    app, fake_st, calls = ui

    app.handle_create(*fields_of(2))

    assert calls == []
    assert database.get_all_patients() == []

    shown = " ".join(
        str(call) for call in fake_st.markdown.call_args_list
    )
    assert "hunter@gmail" in shown


def test_ai_failure_on_create_saves_nothing_and_allows_retry(
    ui,
    monkeypatch,
):
    app, fake_st, calls = ui

    def failing(*args):
        raise ai_service.AIServiceError(
            "The AI service timed out. Please try again."
        )

    monkeypatch.setattr(
        app.ai_service,
        "generate_remarks",
        failing,
    )

    app.handle_create(*fields_of(1))

    assert database.get_all_patients() == []
    assert "nothing was saved" in fake_st.error.call_args.args[0]
    assert "retry" in fake_st.error.call_args.args[0]

    monkeypatch.setattr(
        app.ai_service,
        "generate_remarks",
        lambda *args: "AI remark after retry",
    )

    app.handle_create(*fields_of(1))

    saved = database.get_all_patients()

    assert len(saved) == 1
    assert saved[0]["remarks"] == "AI remark after retry"


def test_email_only_update_does_not_call_the_ai(ui):
    app, fake_st, calls = ui

    app.handle_create(*fields_of(3))
    existing = database.get_all_patients()[0]

    assert len(calls) == 1

    app.handle_update(
        existing,
        "Darryl Tim",
        "12.11.1993",
        "gokul@infocare.com",
        app.format_number(existing["glucose"]),
        app.format_number(existing["haemoglobin"]),
        app.format_number(existing["cholesterol"]),
    )

    assert len(calls) == 1

    updated = database.get_patient(existing["id"])

    assert updated["email"] == "gokul@infocare.com"
    assert updated["remarks"] == existing["remarks"]
    assert "AI was not called" in fake_st.session_state["flash"][1]


def test_unchanged_form_values_round_trip_without_ai_call(ui):
    app, fake_st, calls = ui

    app.handle_create(
        "Odd Values",
        "01.01.1990",
        "odd@x.com",
        "123456.789",
        "0.1",
        "1234567.5",
    )

    existing = database.get_all_patients()[0]

    app.handle_update(
        existing,
        "Odd Values",
        "01/01/1990",
        "new@x.com",
        app.format_number(existing["glucose"]),
        app.format_number(existing["haemoglobin"]),
        app.format_number(existing["cholesterol"]),
    )

    assert len(calls) == 1


@pytest.mark.parametrize(
    "field_index,new_value",
    [
        (3, "250"),
        (4, "14.2"),
        (5, "300"),
    ],
)
def test_blood_value_update_regenerates_the_remark(
    ui,
    field_index,
    new_value,
):
    app, fake_st, calls = ui

    app.handle_create(*fields_of(3))
    existing = database.get_all_patients()[0]

    form = [
        existing["full_name"],
        "12.11.1993",
        existing["email"],
        app.format_number(existing["glucose"]),
        app.format_number(existing["haemoglobin"]),
        app.format_number(existing["cholesterol"]),
    ]

    form[field_index] = new_value

    app.handle_update(existing, *form)

    assert len(calls) == 2
    assert calls[1][field_index - 3] == float(new_value)
    assert (
        database.get_patient(existing["id"])["remarks"]
        == "AI remark #2"
    )
    assert "regenerated" in fake_st.session_state["flash"][1]


def test_invalid_update_changes_nothing_and_skips_the_ai(ui):
    app, fake_st, calls = ui

    app.handle_create(*fields_of(3))
    existing = database.get_all_patients()[0]

    app.handle_update(
        existing,
        "Darryl Tim",
        "12.11.1993",
        "not-an-email",
        "999",
        "18.6",
        "326",
    )

    assert len(calls) == 1
    assert database.get_patient(existing["id"]) == existing


def test_ai_failure_on_update_leaves_record_unchanged(ui, monkeypatch):
    app, fake_st, calls = ui

    app.handle_create(*fields_of(3))
    existing = database.get_all_patients()[0]

    def failing(*args):
        raise ai_service.AIServiceError("rate limit")

    monkeypatch.setattr(
        app.ai_service,
        "generate_remarks",
        failing,
    )

    app.handle_update(
        existing,
        "Darryl Tim",
        "12.11.1993",
        "gokul@infocare.com",
        "999",
        "18.6",
        "326",
    )

    assert database.get_patient(existing["id"]) == existing
    assert "was not updated" in fake_st.error.call_args.args[0]


def test_full_crud_demonstration_sequence(ui):
    app, fake_st, calls = ui

    create_all_supplied_records(app)

    assert len(database.get_all_patients()) == 7

    target = database.get_all_patients()[1]

    app.handle_update(
        target,
        target["full_name"],
        "12.11.1993",
        "gokul@infocare.com",
        app.format_number(target["glucose"]),
        app.format_number(target["haemoglobin"]),
        app.format_number(target["cholesterol"]),
    )

    doomed = database.get_all_patients()[4]

    assert database.delete_patient(doomed["id"])

    remaining = database.get_all_patients()

    assert len(remaining) == 6
    assert doomed["id"] not in [p["id"] for p in remaining]
    assert "gokul@infocare.com" in [p["email"] for p in remaining]
