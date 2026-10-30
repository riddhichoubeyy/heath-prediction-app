
"""Streamlit front end for the Health Prediction App."""

from datetime import datetime

import pandas as pd
import streamlit as st

import ai_service
import database
import validation


BLOOD_FIELDS = ("glucose", "haemoglobin", "cholesterol")


# --------------------------------------------------
# PAGE DESIGN AND CSS
# --------------------------------------------------

PAGE_CSS = """
<style>

/* Main background */
.stApp {
    background: linear-gradient(
        135deg,
        #eef5fb 0%,
        #f8fbff 55%,
        #eaf2fa 100%
    );
    color: #18324b;
}

/* Main page width */
.block-container {
    max-width: 1250px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}

/* Headings */
h1, h2, h3, h4 {
    color: #173b5e !important;
    font-weight: 750 !important;
}

/* Normal text */
.stApp p,
.stApp label,
.stApp [data-testid="stMarkdownContainer"] {
    color: #344b60;
}

[data-testid="stCaptionContainer"] p {
    color: #60788d !important;
}

/* Dashboard metric cards */
div[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #d9e6f1;
    border-radius: 18px;
    padding: 22px 20px;
    box-shadow: 0 5px 18px rgba(30, 70, 110, 0.07);
}

div[data-testid="stMetricLabel"],
div[data-testid="stMetricLabel"] * {
    color: #58738c !important;
    font-weight: 600 !important;
}

div[data-testid="stMetricValue"],
div[data-testid="stMetricValue"] * {
    color: #16466d !important;
    font-weight: 800 !important;
}

/* Text, number and date input fields */
.stTextInput input,
.stNumberInput input,
.stDateInput input,
.stTextArea textarea {
    background: #ffffff !important;
    color: #18324b !important;
    border: 1px solid #cbdbea !important;
    border-radius: 10px !important;
    min-height: 44px;
}

/* Input labels */
.stTextInput label,
.stNumberInput label,
.stDateInput label,
.stTextArea label,
.stSelectbox label {
    color: #294b68 !important;
    font-weight: 600 !important;
}

/* Placeholder text */
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: #91a3b3 !important;
}

/* Dropdowns */
.stSelectbox div[data-baseweb="select"] > div {
    background: #ffffff !important;
    color: #18324b !important;
    border-radius: 10px !important;
    border-color: #cbdbea !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 12px;
    border-bottom: 1px solid #d5e2ee;
}

.stTabs [data-baseweb="tab"] {
    color: #365a78 !important;
    font-weight: 650;
    padding: 12px 18px;
}

.stTabs [aria-selected="true"] {
    color: #087eae !important;
}

/* Forms and expanders */
div[data-testid="stForm"],
div[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #d9e6f1;
    border-radius: 16px;
    padding: 18px;
    box-shadow: 0 5px 18px rgba(30, 70, 110, 0.05);
}

/* Buttons */
.stButton button,
.stFormSubmitButton button {
    background: #087eae !important;
    color: #ffffff !important;
    border: 0 !important;
    border-radius: 10px !important;
    padding: 10px 22px !important;
    font-weight: 650 !important;
    transition: 0.2s ease;
}

.stButton button:hover,
.stFormSubmitButton button:hover {
    background: #06658e !important;
    color: #ffffff !important;
    box-shadow: 0 4px 12px rgba(8, 126, 174, 0.2);
}

/* Data table */
div[data-testid="stDataFrame"],
div[data-testid="stTable"] {
    background: #ffffff;
    border: 1px solid #d9e6f1;
    border-radius: 14px;
    overflow: hidden;
}

/* Alerts */
div[data-testid="stAlert"] {
    border-radius: 12px;
}

/* Separators */
hr {
    border-color: #dce7f0 !important;
}

</style>
"""


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def show_flash():
    """Show a one-time message after a page rerun."""

    flash = st.session_state.pop("flash", None)

    if flash:
        kind, message = flash

        if kind == "success":
            st.success(message)
        else:
            st.error(message)


def display_date(iso_date):
    """Convert database date into display date."""

    return datetime.strptime(
        iso_date,
        validation.DB_DATE_FORMAT
    ).strftime(validation.DISPLAY_DATE_FORMAT)


def format_number(value):
    """Format numbers without unnecessary decimal zeros."""

    return f"{value:.10g}"


def show_errors(errors):
    """Display validation errors."""

    st.error(
        "The record could not be saved because of the following problem(s):"
    )

    for message in errors:
        st.markdown(f"- {message}")


# --------------------------------------------------
# CREATE PATIENT RECORD
# --------------------------------------------------

def handle_create(
    name,
    dob,
    email,
    glucose,
    haemoglobin,
    cholesterol
):
    """Validate, generate AI remarks and save the patient."""

    record, errors = validation.validate_patient(
        name,
        dob,
        email,
        glucose,
        haemoglobin,
        cholesterol
    )

    if errors:
        show_errors(errors)
        return

    try:
        with st.spinner("Generating AI assessment..."):

            remarks = ai_service.generate_remarks(
                record["glucose"],
                record["haemoglobin"],
                record["cholesterol"]
            )

    except ai_service.AIServiceError as exc:

        st.error(
            f"AI assessment failed, so nothing was saved. {exc} "
            "Click the button again to retry."
        )

        return

    new_id = database.create_patient(record, remarks)

    st.session_state["add_form_version"] = (
        st.session_state.get("add_form_version", 0) + 1
    )

    st.session_state["flash"] = (
        "success",
        f"Record saved for {record['full_name']} (ID {new_id})."
    )

    st.rerun()


# --------------------------------------------------
# UPDATE PATIENT RECORD
# --------------------------------------------------

def handle_update(
    existing,
    name,
    dob,
    email,
    glucose,
    haemoglobin,
    cholesterol
):
    """Update patient information and AI remarks if needed."""

    record, errors = validation.validate_patient(
        name,
        dob,
        email,
        glucose,
        haemoglobin,
        cholesterol
    )

    if errors:
        show_errors(errors)
        return

    blood_changed = any(
        record[field] != existing[field]
        for field in BLOOD_FIELDS
    )

    remarks = existing["remarks"]

    if blood_changed:

        try:
            with st.spinner(
                "Blood values changed - regenerating AI assessment..."
            ):

                remarks = ai_service.generate_remarks(
                    record["glucose"],
                    record["haemoglobin"],
                    record["cholesterol"]
                )

        except ai_service.AIServiceError as exc:

            st.error(
                f"AI assessment failed, so the record was not updated. "
                f"{exc} Click the button again to retry."
            )

            return

    database.update_patient(
        existing["id"],
        record,
        remarks
    )

    note = (
        " AI remarks were regenerated."
        if blood_changed
        else " AI was not called (blood values unchanged)."
    )

    st.session_state["flash"] = (
        "success",
        f"Record ID {existing['id']} updated." + note
    )

    st.rerun()


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

def render_dashboard():
    """Display patient statistics."""

    patients = database.get_all_patients()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "📋 Total records",
        len(patients)
    )

    if patients:

        frame = pd.DataFrame(patients)

        col2.metric(
            "🩸 Avg glucose",
            f"{frame['glucose'].mean():.1f} mg/dL"
        )

        col3.metric(
            "🧬 Avg haemoglobin",
            f"{frame['haemoglobin'].mean():.1f} g/dL"
        )

        col4.metric(
            "❤️ Avg cholesterol",
            f"{frame['cholesterol'].mean():.1f} mg/dL"
        )

    else:

        col2.metric("🩸 Avg glucose", "No data")
        col3.metric("🧬 Avg haemoglobin", "No data")
        col4.metric("❤️ Avg cholesterol", "No data")


# --------------------------------------------------
# ADD RECORD TAB
# --------------------------------------------------

def render_add_tab():

    st.subheader("➕ Add patient record")

    st.caption(
        "Date of Birth accepts dd/mm/yyyy or dd.mm.yyyy."
    )

    form_version = st.session_state.setdefault(
        "add_form_version",
        0
    )

    with st.form(f"add_form_{form_version}"):

        name = st.text_input("Full Name")

        dob = st.text_input(
            "Date of Birth (dd/mm/yyyy)"
        )

        email = st.text_input("Email Address")

        col1, col2, col3 = st.columns(3)

        glucose = col1.text_input(
            "Glucose (mg/dL)"
        )

        haemoglobin = col2.text_input(
            "Haemoglobin (g/dL)"
        )

        cholesterol = col3.text_input(
            "Cholesterol (mg/dL)"
        )

        submitted = st.form_submit_button(
            "Validate and save",
            type="primary"
        )

    if submitted:

        handle_create(
            name,
            dob,
            email,
            glucose,
            haemoglobin,
            cholesterol
        )


# --------------------------------------------------
# VIEW ALL RECORDS TAB
# --------------------------------------------------

def render_records_tab():

    st.subheader("📊 All patient records")

    patients = database.get_all_patients()

    if not patients:

        st.info(
            "No records yet. Add one in the 'Add Record' tab."
        )

        return

    frame = pd.DataFrame(patients)

    frame["date_of_birth"] = (
        frame["date_of_birth"].apply(display_date)
    )

    frame = frame.rename(
        columns={
            "id": "ID",
            "full_name": "Full Name",
            "date_of_birth": "Date of Birth",
            "email": "Email",
            "glucose": "Glucose",
            "haemoglobin": "Haemoglobin",
            "cholesterol": "Cholesterol",
            "remarks": "Remarks (AI-generated)"
        }
    )

    st.dataframe(
        frame,
        hide_index=True,
        column_config={
            "Remarks (AI-generated)": (
                st.column_config.TextColumn(
                    width="large"
                )
            )
        }
    )

    with st.expander("Read the full AI remarks"):

        for patient in patients:

            st.markdown(
                f"**ID {patient['id']} - "
                f"{patient['full_name']}**"
            )

            st.write(patient["remarks"])

    st.caption(
        "Remarks are informational risk assessments generated by an AI "
        "service, not medical diagnoses."
    )


# --------------------------------------------------
# EDIT AND DELETE RECORD TAB
# --------------------------------------------------

def render_edit_delete_tab():

    st.subheader("✏️ Edit or delete a record")

    patients = database.get_all_patients()

    if not patients:

        st.info("No records available.")

        return

    labels = {
        patient["id"]: (
            f"ID {patient['id']} - "
            f"{patient['full_name']} "
            f"({patient['email']})"
        )
        for patient in patients
    }

    patient_id = st.selectbox(
        "Select a record",
        list(labels),
        format_func=labels.get
    )

    patient = database.get_patient(patient_id)

    st.markdown("**Current AI remarks**")

    st.info(patient["remarks"])

    st.caption(
        "Informational risk assessment only, "
        "not a medical diagnosis."
    )

    with st.form(
        f"edit_form_{patient_id}_{patient['email']}"
    ):

        name = st.text_input(
            "Full Name",
            patient["full_name"]
        )

        dob = st.text_input(
            "Date of Birth (dd/mm/yyyy)",
            display_date(patient["date_of_birth"])
        )

        email = st.text_input(
            "Email Address",
            patient["email"]
        )

        col1, col2, col3 = st.columns(3)

        glucose = col1.text_input(
            "Glucose (mg/dL)",
            format_number(patient["glucose"])
        )

        haemoglobin = col2.text_input(
            "Haemoglobin (g/dL)",
            format_number(patient["haemoglobin"])
        )

        cholesterol = col3.text_input(
            "Cholesterol (mg/dL)",
            format_number(patient["cholesterol"])
        )

        update_clicked = st.form_submit_button(
            "Update record",
            type="primary"
        )

    if update_clicked:

        handle_update(
            patient,
            name,
            dob,
            email,
            glucose,
            haemoglobin,
            cholesterol
        )

    st.divider()

    st.markdown("**Delete this record**")

    if st.button(
        "Delete record",
        key=f"delete_{patient_id}"
    ):

        st.session_state["confirm_delete_id"] = patient_id

    if (
        st.session_state.get("confirm_delete_id")
        == patient_id
    ):

        st.warning(
            f"Are you sure you want to permanently delete "
            f"{patient['full_name']} (ID {patient_id})?"
        )

        yes_col, no_col, _ = st.columns([1, 1, 4])

        if yes_col.button(
            "Yes, delete",
            type="primary",
            key=f"confirm_{patient_id}"
        ):

            database.delete_patient(patient_id)

            st.session_state.pop(
                "confirm_delete_id",
                None
            )

            st.session_state["flash"] = (
                "success",
                f"Record ID {patient_id} was deleted."
            )

            st.rerun()

        if no_col.button(
            "Cancel",
            key=f"cancel_{patient_id}"
        ):

            st.session_state.pop(
                "confirm_delete_id",
                None
            )

            st.rerun()


# --------------------------------------------------
# MAIN APPLICATION
# --------------------------------------------------

def main():

    st.set_page_config(
        page_title="Health Prediction App",
        page_icon="🩺",
        layout="wide"
    )

    database.init_db()

    st.markdown(
        PAGE_CSS,
        unsafe_allow_html=True
    )

    st.title("🩺 Health Prediction App")

    st.write(
        "Store patient blood test results and get an informational "
        "AI risk assessment for each record. This is a software "
        "demonstration, not a medical diagnosis tool."
    )

    show_flash()

    render_dashboard()

    tab_add, tab_view, tab_edit = st.tabs(
        [
            "➕ Add Record",
            "📊 View Records",
            "✏️ Edit / Delete"
        ]
    )

    with tab_add:
        render_add_tab()

    with tab_view:
        render_records_tab()

    with tab_edit:
        render_edit_delete_tab()


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    main()
