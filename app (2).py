"""Streamlit front end. Delegates validation, storage and AI calls to other modules."""
from datetime import datetime

import pandas as pd
import streamlit as st

import ai_service
import database
import validation

BLOOD_FIELDS = ("glucose", "haemoglobin", "cholesterol")

PAGE_CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
div[data-testid="stMetric"] {background: #f4f6f8; border: 1px solid #e1e5ea;
    padding: 12px 16px; border-radius: 8px;}
</style>
"""


def show_flash():
    """Show a one-off message stored before a rerun."""
    flash = st.session_state.pop("flash", None)
    if flash:
        kind, text = flash
        (st.success if kind == "success" else st.error)(text)


def display_date(iso_date):
    return datetime.strptime(iso_date, validation.DB_DATE_FORMAT).strftime(validation.DISPLAY_DATE_FORMAT)


def format_number(value):
    """Show 232.0 as '232' and 13.5 as '13.5' without losing precision."""
    return f"{value:.10g}"


def show_errors(errors):
    st.error("The record could not be saved because of the following problem(s):")
    for message in errors:
        st.markdown(f"- {message}")


def handle_create(name, dob, email, glucose, haemoglobin, cholesterol):
    """Validate first, then call the AI API, then save. Nothing is saved if either step fails."""
    record, errors = validation.validate_patient(name, dob, email, glucose, haemoglobin, cholesterol)
    if errors:
        show_errors(errors)
        return

    try:
        with st.spinner("Generating AI assessment..."):
            remarks = ai_service.generate_remarks(
                record["glucose"], record["haemoglobin"], record["cholesterol"]
            )
    except ai_service.AIServiceError as exc:
        st.error(f"AI assessment failed, so nothing was saved. {exc} Click the button again to retry.")
        return

    new_id = database.create_patient(record, remarks)
    # A new form key gives the add form empty fields again.
    st.session_state["add_form_version"] = st.session_state.get("add_form_version", 0) + 1
    st.session_state["flash"] = ("success", f"Record saved for {record['full_name']} (ID {new_id}).")
    st.rerun()


def handle_update(existing, name, dob, email, glucose, haemoglobin, cholesterol):
    """Validate, call the AI API only if a blood value changed, then update the record."""
    record, errors = validation.validate_patient(name, dob, email, glucose, haemoglobin, cholesterol)
    if errors:
        show_errors(errors)
        return

    blood_changed = any(record[field] != existing[field] for field in BLOOD_FIELDS)
    remarks = existing["remarks"]
    if blood_changed:
        try:
            with st.spinner("Blood values changed - regenerating AI assessment..."):
                remarks = ai_service.generate_remarks(
                    record["glucose"], record["haemoglobin"], record["cholesterol"]
                )
        except ai_service.AIServiceError as exc:
            st.error(f"AI assessment failed, so the record was not updated. {exc} Click the button again to retry.")
            return

    database.update_patient(existing["id"], record, remarks)
    note = " AI remarks were regenerated." if blood_changed else " AI was not called (blood values unchanged)."
    st.session_state["flash"] = ("success", f"Record ID {existing['id']} updated." + note)
    st.rerun()


def render_dashboard():
    patients = database.get_all_patients()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total records", len(patients))
    if patients:
        frame = pd.DataFrame(patients)
        col2.metric("Avg glucose (mg/dL)", f"{frame['glucose'].mean():.1f}")
        col3.metric("Avg haemoglobin (g/dL)", f"{frame['haemoglobin'].mean():.1f}")
        col4.metric("Avg cholesterol (mg/dL)", f"{frame['cholesterol'].mean():.1f}")
    else:
        for column in (col2, col3, col4):
            column.metric("-", "No data")


def render_add_tab():
    st.subheader("Add patient record")
    st.caption("Date of Birth accepts dd/mm/yyyy or dd.mm.yyyy.")
    form_version = st.session_state.setdefault("add_form_version", 0)

    with st.form(f"add_form_{form_version}"):
        name = st.text_input("Full Name")
        dob = st.text_input("Date of Birth (dd/mm/yyyy)")
        email = st.text_input("Email Address")
        col1, col2, col3 = st.columns(3)
        glucose = col1.text_input("Glucose (mg/dL)")
        haemoglobin = col2.text_input("Haemoglobin (g/dL)")
        cholesterol = col3.text_input("Cholesterol (mg/dL)")
        submitted = st.form_submit_button("Validate and save", type="primary")

    if submitted:
        handle_create(name, dob, email, glucose, haemoglobin, cholesterol)


def render_records_tab():
    st.subheader("All patient records")
    patients = database.get_all_patients()
    if not patients:
        st.info("No records yet. Add one in the 'Add Record' tab.")
        return

    frame = pd.DataFrame(patients)
    frame["date_of_birth"] = frame["date_of_birth"].apply(display_date)
    frame = frame.rename(columns={
        "id": "ID", "full_name": "Full Name", "date_of_birth": "Date of Birth",
        "email": "Email", "glucose": "Glucose", "haemoglobin": "Haemoglobin",
        "cholesterol": "Cholesterol", "remarks": "Remarks (AI-generated)",
    })
    st.dataframe(
        frame,
        hide_index=True,
        column_config={"Remarks (AI-generated)": st.column_config.TextColumn(width="large")},
    )
    with st.expander("Read the full AI remarks"):
        for patient in patients:
            st.markdown(f"**ID {patient['id']} - {patient['full_name']}**")
            st.write(patient["remarks"])
    st.caption("Remarks are informational risk assessments generated by an AI service, not medical diagnoses.")


def render_edit_delete_tab():
    st.subheader("Edit or delete a record")
    patients = database.get_all_patients()
    if not patients:
        st.info("No records available.")
        return

    labels = {p["id"]: f"ID {p['id']} - {p['full_name']} ({p['email']})" for p in patients}
    patient_id = st.selectbox("Select a record", list(labels), format_func=labels.get)
    patient = database.get_patient(patient_id)

    st.markdown("**Current AI remarks**")
    st.info(patient["remarks"])
    st.caption("Informational risk assessment only, not a medical diagnosis.")

    # The key includes the record id and email so the fields reload when another record is selected.
    with st.form(f"edit_form_{patient_id}_{patient['email']}"):
        name = st.text_input("Full Name", patient["full_name"])
        dob = st.text_input("Date of Birth (dd/mm/yyyy)", display_date(patient["date_of_birth"]))
        email = st.text_input("Email Address", patient["email"])
        col1, col2, col3 = st.columns(3)
        glucose = col1.text_input("Glucose (mg/dL)", format_number(patient["glucose"]))
        haemoglobin = col2.text_input("Haemoglobin (g/dL)", format_number(patient["haemoglobin"]))
        cholesterol = col3.text_input("Cholesterol (mg/dL)", format_number(patient["cholesterol"]))
        update_clicked = st.form_submit_button("Update record", type="primary")

    if update_clicked:
        handle_update(patient, name, dob, email, glucose, haemoglobin, cholesterol)

    st.divider()
    st.markdown("**Delete this record**")
    if st.button("Delete record", key=f"delete_{patient_id}"):
        st.session_state["confirm_delete_id"] = patient_id

    if st.session_state.get("confirm_delete_id") == patient_id:
        st.warning(f"Are you sure you want to permanently delete {patient['full_name']} (ID {patient_id})?")
        yes_col, no_col, _ = st.columns([1, 1, 4])
        if yes_col.button("Yes, delete", type="primary", key=f"confirm_{patient_id}"):
            database.delete_patient(patient_id)
            st.session_state.pop("confirm_delete_id", None)
            st.session_state["flash"] = ("success", f"Record ID {patient_id} was deleted.")
            st.rerun()
        if no_col.button("Cancel", key=f"cancel_{patient_id}"):
            st.session_state.pop("confirm_delete_id", None)
            st.rerun()


def main():
    st.set_page_config(page_title="Health Prediction App", page_icon="🩺", layout="wide")
    database.init_db()
    st.markdown(PAGE_CSS, unsafe_allow_html=True)

    st.title("Health Prediction App")
    st.write(
        "Store patient blood test results and get an informational AI risk assessment for each record. "
        "This is a software demonstration, not a medical diagnosis tool."
    )
    show_flash()
    render_dashboard()

    tab_add, tab_view, tab_edit = st.tabs(["Add Record", "View Records", "Edit / Delete"])
    with tab_add:
        render_add_tab()
    with tab_view:
        render_records_tab()
    with tab_edit:
        render_edit_delete_tab()


# Streamlit runs this file as a script, so __name__ is "__main__" there.
# Keeping the UI inside main() lets the tests import the handlers without rendering a page.
if __name__ == "__main__":
    main()
