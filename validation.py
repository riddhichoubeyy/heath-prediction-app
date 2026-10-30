"""Input validation for patient records.

Every validator returns (clean_value, error_message). If the input is valid,
error_message is None. Nothing is silently corrected: invalid input always
produces an error.
"""
import re
from datetime import date, datetime

# Simple, readable email pattern: something@something.tld
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")

# Both dd/mm/yyyy (required format) and dd.mm.yyyy (used in the test data).
DATE_FORMATS = ("%d/%m/%Y", "%d.%m.%Y")
MIN_BIRTH_YEAR = 1900

DB_DATE_FORMAT = "%Y-%m-%d"
DISPLAY_DATE_FORMAT = "%d/%m/%Y"


def validate_name(value):
    name = (value or "").strip()
    if not name:
        return None, "Full Name cannot be empty."
    return name, None


def validate_email(value):
    email = (value or "").strip()
    if not email:
        return None, "Email cannot be empty."
    if not EMAIL_PATTERN.match(email):
        return None, f"Email '{email}' is not a valid format (expected name@domain.com)."
    return email, None


def validate_date_of_birth(value):
    """Accepts dd/mm/yyyy or dd.mm.yyyy and returns an ISO date string (yyyy-mm-dd)."""
    text = (value or "").strip()
    if not text:
        return None, "Date of Birth cannot be empty."

    parsed = None
    for fmt in DATE_FORMATS:
        try:
            # strptime rejects impossible dates such as 31.11.2001
            parsed = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue

    if parsed is None:
        return None, (f"Date of Birth '{text}' is not a valid calendar date "
                      "(use dd/mm/yyyy or dd.mm.yyyy, and make sure the day exists in that month).")
    if parsed > date.today():
        return None, f"Date of Birth '{text}' is in the future."
    if parsed.year < MIN_BIRTH_YEAR:
        return None, f"Date of Birth '{text}' is not plausible (year must be {MIN_BIRTH_YEAR} or later)."
    return parsed.strftime(DB_DATE_FORMAT), None


def validate_blood_value(value, label):
    text = str(value if value is not None else "").strip()
    if not text:
        return None, f"{label} cannot be empty."
    try:
        number = float(text)
    except ValueError:
        return None, f"{label} must be a number (got '{text}')."
    if number != number or number in (float("inf"), float("-inf")):
        return None, f"{label} must be a finite number."
    if number <= 0:
        return None, f"{label} must be greater than zero."
    return number, None


def validate_patient(name, dob, email, glucose, haemoglobin, cholesterol):
    """Validate all fields. Returns (clean_dict, errors_list)."""
    checks = {
        "full_name": validate_name(name),
        "date_of_birth": validate_date_of_birth(dob),
        "email": validate_email(email),
        "glucose": validate_blood_value(glucose, "Glucose"),
        "haemoglobin": validate_blood_value(haemoglobin, "Haemoglobin"),
        "cholesterol": validate_blood_value(cholesterol, "Cholesterol"),
    }
    clean = {}
    errors = []
    for field, (value, error) in checks.items():
        if error:
            errors.append(error)
        else:
            clean[field] = value
    return clean, errors
