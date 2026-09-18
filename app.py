"""
Patient Case-Taking Software
------------------------------
A simple Flask web app demonstrating:
- User registration/login (Patient & Doctor roles)
- Session-based authentication
- Password hashing (Werkzeug)
- SQLite database (via sqlite3, no ORM - kept simple for learning)
- File upload/viewing with ownership checks
- Role-based access control

This is an academic prototype only - NOT a real healthcare product.
"""

import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "patient_case_taking.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

app = Flask(__name__)

# In a real project, always set this via an environment variable.
# We fall back to a fixed dev key only so the app is easy to run for class.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Get a SQLite connection for this request (stored on flask.g)."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they do not already exist."""
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('patient', 'doctor')),
            created_at TEXT NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS patient_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            age INTEGER,
            gender TEXT,
            phone TEXT,
            address TEXT,
            blood_group TEXT,
            allergies TEXT,
            medical_conditions TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)

    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Auth / authorization helpers
# ---------------------------------------------------------------------------

def login_required(f):
    """Require any logged-in user (patient or doctor)."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped


def role_required(role):
    """Require the logged-in user to have a specific role."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            if session.get("role") != role:
                # Logged in, but wrong role -> forbidden, not a redirect loop
                return render_template("error.html",
                                        message="You are not authorized to view this page."), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def allowed_file(filename):
    return "." in filename and \
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "")

        # --- Validation ---
        if not full_name or not email or not password or not confirm_password or not role:
            flash("All fields are required.", "error")
            return render_template("register.html", form=request.form)

        if role not in ("patient", "doctor"):
            flash("Please select a valid role.", "error")
            return render_template("register.html", form=request.form)

        if password != confirm_password:
            flash("Password and confirmation do not match.", "error")
            return render_template("register.html", form=request.form)

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("register.html", form=request.form)

        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            flash("An account with this email already exists.", "error")
            return render_template("register.html", form=request.form)

        # --- Create user ---
        password_hash = generate_password_hash(password)
        created_at = datetime.utcnow().isoformat()

        cursor = db.execute(
            """INSERT INTO users (full_name, email, password_hash, role, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (full_name, email, password_hash, role, created_at)
        )
        user_id = cursor.lastrowid

        # If patient, create an (initially empty) profile row too
        if role == "patient":
            db.execute(
                """INSERT INTO patient_profiles (user_id) VALUES (?)""",
                (user_id,)
            )

        db.commit()

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        # Successful login -> create session
        session.clear()
        session["user_id"] = user["id"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]

        if user["role"] == "doctor":
            return redirect(url_for("doctor_dashboard"))
        return redirect(url_for("patient_dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Patient routes
# ---------------------------------------------------------------------------

@app.route("/patient/dashboard")
@role_required("patient")
def patient_dashboard():
    db = get_db()
    user_id = session["user_id"]

    profile = db.execute(
        "SELECT * FROM patient_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()

    records = db.execute(
        """SELECT * FROM medical_records
           WHERE patient_id = ?
           ORDER BY uploaded_at DESC""",
        (user_id,)
    ).fetchall()

    return render_template(
        "patient_dashboard.html",
        profile=profile,
        records=records
    )


@app.route("/patient/profile/edit", methods=["GET", "POST"])
@role_required("patient")
def edit_profile():
    db = get_db()
    user_id = session["user_id"]

    if request.method == "POST":
        age = request.form.get("age", "").strip()
        gender = request.form.get("gender", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        blood_group = request.form.get("blood_group", "").strip()
        allergies = request.form.get("allergies", "").strip()
        medical_conditions = request.form.get("medical_conditions", "").strip()

        # Age should be a number if provided
        age_value = None
        if age:
            try:
                age_value = int(age)
            except ValueError:
                flash("Age must be a number.", "error")
                profile = db.execute(
                    "SELECT * FROM patient_profiles WHERE user_id = ?", (user_id,)
                ).fetchone()
                return render_template("edit_profile.html", profile=profile)

        db.execute(
            """UPDATE patient_profiles
               SET age = ?, gender = ?, phone = ?, address = ?,
                   blood_group = ?, allergies = ?, medical_conditions = ?
               WHERE user_id = ?""",
            (age_value, gender, phone, address, blood_group,
             allergies, medical_conditions, user_id)
        )
        db.commit()

        flash("Profile updated successfully.", "success")
        return redirect(url_for("patient_dashboard"))

    profile = db.execute(
        "SELECT * FROM patient_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    return render_template("edit_profile.html", profile=profile)


@app.route("/patient/records/upload", methods=["POST"])
@role_required("patient")
def upload_record():
    user_id = session["user_id"]

    if "file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("patient_dashboard"))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("patient_dashboard"))

    if not allowed_file(file.filename):
        flash("Invalid file type. Only PDF, PNG, JPG, and JPEG are allowed.", "error")
        return redirect(url_for("patient_dashboard"))

    original_filename = secure_filename(file.filename)
    file_ext = original_filename.rsplit(".", 1)[1].lower()

    # Make the stored filename unique so different patients' files never collide
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    stored_filename = f"user{user_id}_{timestamp}_{original_filename}"

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored_filename)
    file.save(filepath)

    db = get_db()
    db.execute(
        """INSERT INTO medical_records
           (patient_id, original_filename, stored_filename, file_type, uploaded_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, original_filename, stored_filename, file_ext,
         datetime.utcnow().isoformat())
    )
    db.commit()

    flash("File uploaded successfully.", "success")
    return redirect(url_for("patient_dashboard"))


def _get_record_or_403(record_id, requesting_user_id, requesting_role):
    """
    Fetch a medical record and verify the requester is allowed to see it.
    - Patients may only access their OWN records.
    - Doctors may access any patient's records (read-only, enforced at route level).
    Returns the record row, or aborts with 403/404.
    """
    db = get_db()
    record = db.execute(
        "SELECT * FROM medical_records WHERE id = ?", (record_id,)
    ).fetchone()

    if record is None:
        abort(404)

    if requesting_role == "patient" and record["patient_id"] != requesting_user_id:
        # Ownership check: a patient can never view another patient's record,
        # even by guessing/changing the URL.
        abort(403)

    return record


@app.route("/records/<int:record_id>/view")
@login_required
def view_record(record_id):
    record = _get_record_or_403(record_id, session["user_id"], session["role"])
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        record["stored_filename"],
        as_attachment=False
    )


@app.route("/patient/records/<int:record_id>/delete", methods=["POST"])
@role_required("patient")
def delete_record(record_id):
    user_id = session["user_id"]
    db = get_db()

    record = db.execute(
        "SELECT * FROM medical_records WHERE id = ?", (record_id,)
    ).fetchone()

    if record is None:
        abort(404)

    # Ownership check: only the owning patient may delete their own record.
    if record["patient_id"] != user_id:
        abort(403)

    # Remove the physical file if it exists
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], record["stored_filename"])
    if os.path.exists(filepath):
        os.remove(filepath)

    db.execute("DELETE FROM medical_records WHERE id = ?", (record_id,))
    db.commit()

    flash("Record deleted.", "success")
    return redirect(url_for("patient_dashboard"))


# ---------------------------------------------------------------------------
# Doctor routes
# ---------------------------------------------------------------------------

@app.route("/doctor/dashboard")
@role_required("doctor")
def doctor_dashboard():
    db = get_db()
    patients = db.execute(
        "SELECT id, full_name, email FROM users WHERE role = 'patient' ORDER BY full_name"
    ).fetchall()

    return render_template(
        "doctor_dashboard.html",
        patients=patients,
        patient_count=len(patients)
    )


@app.route("/doctor/patient/<int:patient_id>")
@role_required("doctor")
def view_patient(patient_id):
    db = get_db()

    patient = db.execute(
        "SELECT * FROM users WHERE id = ? AND role = 'patient'", (patient_id,)
    ).fetchone()

    if patient is None:
        abort(404)

    profile = db.execute(
        "SELECT * FROM patient_profiles WHERE user_id = ?", (patient_id,)
    ).fetchone()

    records = db.execute(
        """SELECT * FROM medical_records
           WHERE patient_id = ?
           ORDER BY uploaded_at DESC""",
        (patient_id,)
    ).fetchall()

    return render_template(
        "patient_view.html",
        patient=patient,
        profile=profile,
        records=records
    )


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", message="Access denied. You are not authorized to view this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", message="The page or resource you requested was not found."), 404


@app.errorhandler(413)
def file_too_large(e):
    return render_template("error.html", message="File too large. Maximum upload size is 10 MB."), 413


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
