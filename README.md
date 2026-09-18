# Patient Case-Taking Software

A simple academic prototype web application built with **Flask** and **SQLite**
that demonstrates user authentication, role-based access control, and file
upload/viewing for two types of users: **Patients** and **Doctors**.

> This is a college assignment prototype. It is **not** a real healthcare
> product and should not be used to store real patient data.

---

## 1. Features

- Patient & Doctor registration with role selection
- Secure, session-based login (passwords hashed with Werkzeug)
- Patient dashboard: edit basic profile info, upload/view/delete medical records
- Doctor dashboard: view list of patients, open a patient's profile and records
- Role-based access control (patients and doctors cannot access each other's
  pages) and per-record ownership checks (one patient cannot view another
  patient's files, even by editing the URL)
- SQLite database, created automatically on first run

---

## 2. Project Structure

```
patient-case-taking/
├── app.py                     # Main Flask application (routes, auth, DB)
├── requirements.txt           # Python dependencies
├── README.md
├── uploads/                   # Uploaded medical record files are stored here
├── templates/                 # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── patient_dashboard.html
│   ├── edit_profile.html
│   ├── doctor_dashboard.html
│   ├── patient_view.html
│   └── error.html
└── static/
    ├── css/style.css
    └── js/script.js
```

`patient_case_taking.db` (the SQLite database file) is created automatically
the first time you run the app — it is not included in this folder.

---

## 3. Setup Instructions (Windows)

Open PowerShell inside the `patient-case-taking` folder and run:

```powershell
python -m venv venv
```

```powershell
venv\Scripts\activate
```

```powershell
pip install -r requirements.txt
```

```powershell
python app.py
```

You should see output similar to:

```
 * Running on http://127.0.0.1:5000
```

Open your browser and go to:

```
http://127.0.0.1:5000
```

### How the database is created

The first time `app.py` runs, it calls `init_db()`, which uses
`CREATE TABLE IF NOT EXISTS` statements to create `patient_case_taking.db`
and its three tables (`users`, `patient_profiles`, `medical_records`) if they
don't already exist. You do not need to create the database manually.

To start completely fresh, just stop the app, delete
`patient_case_taking.db`, and run `python app.py` again.

---

## 4. Testing Procedure

### Test 1 — Patient flow
1. Go to **Create Account**, register as a **Patient**.
2. Log in with that account.
3. On the Patient Dashboard, click **Edit Profile** and fill in basic info.
4. Click **Upload Medical Record** and upload a PDF or image.
5. Confirm the file appears in **My Uploaded Records**.
6. Click **Open** to view it in the browser.
7. Click **Delete** to remove it, and confirm it's gone.
8. Click **Logout**.

### Test 2 — Doctor flow
1. Register a second account as a **Doctor**.
2. Log in with the doctor account.
3. On the Doctor Dashboard, confirm the patient from Test 1 is listed.
4. Click **View Profile** for that patient.
5. Confirm their basic information and uploaded records are visible.
6. Click **Open** on a record to view it.

### Test 3 — Security checks
- Log out, then try visiting `/patient/dashboard` or `/doctor/dashboard`
  directly — you should be redirected to the login page.
- Log in as a patient and try visiting `/doctor/dashboard` — you should see
  an "Access denied" page (HTTP 403).
- Log in as a doctor and try to `POST` to a patient's upload/delete URL —
  blocked (403).
- Create two patient accounts, upload a file as Patient A, note its record
  ID from the URL, then log in as Patient B and try to open
  `/records/<that id>/view` — you should get a 403 Access Denied page.

---

## 5. How It Works (Explanation)

**1. Registration** — `POST /register` validates the form (all fields
filled, passwords match, minimum length, unique email), then hashes the
password and inserts a new row into the `users` table. If the role is
`patient`, an empty row is also created in `patient_profiles`.

**2. Password hashing** — Passwords are never stored as plain text.
`generate_password_hash()` (Werkzeug) turns the password into a salted hash
before it's saved. `check_password_hash()` compares a login attempt against
that stored hash — the original password is never recoverable from it.

**3. Login verification** — `POST /login` looks up the user by email, then
calls `check_password_hash(stored_hash, submitted_password)`. If it matches,
the login succeeds; otherwise a generic "Invalid email or password" message
is shown (so attackers can't tell whether the email exists).

**4. Sessions** — On successful login, Flask's `session` (a signed cookie,
protected by `app.config["SECRET_KEY"]`) stores `user_id`, `full_name`, and
`role`. Every protected route checks `session["user_id"]` to confirm the
user is logged in, and `session["role"]` to confirm they have the right
role. `session.clear()` on logout removes all of this.

**5. Patient/Doctor roles** — The `role` column on `users` is either
`'patient'` or `'doctor'`. The `role_required(role)` decorator wraps each
route and checks `session["role"]` before allowing access — e.g.
`/doctor/dashboard` is wrapped with `role_required("doctor")`.

**6. SQLite storage** — Three tables: `users` (login + role info),
`patient_profiles` (one row per patient, linked by `user_id`), and
`medical_records` (one row per uploaded file, linked by `patient_id`).
Foreign keys tie records back to the correct patient.

**7. File uploads** — `POST /patient/records/upload` checks the file
extension against an allow-list (`pdf`, `png`, `jpg`, `jpeg`), runs the
filename through `secure_filename()` to strip anything dangerous, prefixes
it with the user's ID and a timestamp to keep it unique, and saves it into
the local `uploads/` folder. A matching row is inserted into
`medical_records` with the original filename, stored filename, file type,
and upload date.

**8. Doctors viewing records** — Doctors have a read-only route,
`/doctor/patient/<id>`, that looks up any user with `role='patient'` and
shows their profile plus all rows from `medical_records` where
`patient_id` matches. There is no delete or upload route for doctors.

**9. Preventing unauthorized access** — Two layers:
   - **Role checks** (`role_required`) stop a patient from loading doctor
     pages and vice versa, even by typing the URL directly.
   - **Ownership checks** (in `view_record` and `delete_record`) compare
     `record["patient_id"]` against `session["user_id"]` before allowing
     access — so even a logged-in patient can't view or delete another
     patient's record by changing the ID in the URL. A mismatch returns
     HTTP 403 (Forbidden).

**10. Purpose of each file**
   - `app.py` — all routes, database setup, authentication, and
     authorization logic.
   - `templates/base.html` — shared layout (navbar, flash messages, footer)
     that every other page extends.
   - `templates/index.html` — public landing page.
   - `templates/login.html` / `register.html` — auth forms.
   - `templates/patient_dashboard.html` — patient's own info, upload form,
     and record list.
   - `templates/edit_profile.html` — form to update patient medical info.
   - `templates/doctor_dashboard.html` — list of all patients for a doctor.
   - `templates/patient_view.html` — read-only view of one patient, shown
     to doctors.
   - `templates/error.html` — shown for 403/404/413 errors.
   - `static/css/style.css` — all styling (no frameworks).
   - `static/js/script.js` — small UX helpers (auto-hide flash messages,
     basic "did you pick a file?" check before upload).
