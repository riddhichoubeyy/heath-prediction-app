"""SQLite persistence layer. No UI or API code lives here."""
import os
import sqlite3
from contextlib import closing

DB_PATH = os.getenv("DB_PATH") or "patients.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name     TEXT NOT NULL,
                date_of_birth TEXT NOT NULL,
                email         TEXT NOT NULL,
                glucose       REAL NOT NULL,
                haemoglobin   REAL NOT NULL,
                cholesterol   REAL NOT NULL,
                remarks       TEXT NOT NULL
            )
            """
        )


def create_patient(record, remarks):
    """Insert a validated record. Returns the new row id."""
    with closing(_connect()) as conn, conn:
        cursor = conn.execute(
            "INSERT INTO patients (full_name, date_of_birth, email, glucose, "
            "haemoglobin, cholesterol, remarks) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record["full_name"], record["date_of_birth"], record["email"],
             record["glucose"], record["haemoglobin"], record["cholesterol"], remarks),
        )
        return cursor.lastrowid


def get_all_patients():
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM patients ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def get_patient(patient_id):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    return dict(row) if row else None


def update_patient(patient_id, record, remarks):
    with closing(_connect()) as conn, conn:
        cursor = conn.execute(
            "UPDATE patients SET full_name = ?, date_of_birth = ?, email = ?, "
            "glucose = ?, haemoglobin = ?, cholesterol = ?, remarks = ? WHERE id = ?",
            (record["full_name"], record["date_of_birth"], record["email"],
             record["glucose"], record["haemoglobin"], record["cholesterol"],
             remarks, patient_id),
        )
        return cursor.rowcount > 0


def delete_patient(patient_id):
    with closing(_connect()) as conn, conn:
        cursor = conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        return cursor.rowcount > 0
