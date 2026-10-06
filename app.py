"""Laptop-only attendance teaching prototype: local browser camera + private SQLite.



LBPH is a demonstration recognizer, not a liveness or anti-spoofing system. Never

base a consequential decision on a face match without human review.

"""

import base64

import binascii

import csv

import hashlib

import hmac

import io

import json

import os

import re

import secrets

import sqlite3

import threading

import time

from contextlib import closing

from datetime import datetime, timedelta

from functools import wraps

from pathlib import Path

from zoneinfo import ZoneInfo



import cv2

import numpy as np

import qrcode

from PIL import Image, UnidentifiedImageError

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

from werkzeug.security import check_password_hash





BASE_DIR = Path(__file__).resolve().parent

IST = ZoneInfo("Asia/Kolkata")

MIN_SAMPLES = 20
MAX_SAMPLES = 60

SESSION_DURATION_MINUTES = 60

DEFAULT_SUBJECTS = (
    "Java",
    "Python",
    "Cloud Computing",
    "Data Science",
    "DBMS",
    "Computer Networks",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    face_consent INTEGER NOT NULL DEFAULT 0,
    qr_token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);

CREATE TABLE IF NOT EXISTS class_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ended_at TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_class_session
ON class_sessions(active)
WHERE active = 1;

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    session_id INTEGER NOT NULL REFERENCES class_sessions(id),
    day TEXT NOT NULL,
    marked_at TEXT NOT NULL,
    method TEXT NOT NULL CHECK(method IN ('face','qr','manual')),
    UNIQUE(student_id, session_id)
);

CREATE INDEX IF NOT EXISTS attendance_session_idx
ON attendance(session_id);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    admin_username TEXT NOT NULL,
    student_id INTEGER,
    attendance_id INTEGER,
    reason TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""



def db_connect(data_dir):

    connection = sqlite3.connect(str(Path(data_dir) / "attendance.sqlite3"), timeout=10)

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    connection.execute("PRAGMA busy_timeout = 10000")

    return connection





def init_db(data_dir):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "faces").mkdir(exist_ok=True)

    with closing(db_connect(data_dir)) as connection:
        existing = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='attendance'"
        ).fetchone()

        if existing is not None:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(attendance)").fetchall()
            }

            # Old project schema had no session_id and allowed one mark per day.
            # Preserve it as a backup table, then create the new session-based table.
            if "session_id" not in columns:
                stamp = datetime.now(IST).strftime("%Y%m%d%H%M%S")
                backup_name = f"attendance_legacy_{stamp}"
                connection.execute(
                    f'ALTER TABLE attendance RENAME TO "{backup_name}"'
                )

        connection.executescript(SCHEMA)

        for order, subject_name in enumerate(DEFAULT_SUBJECTS, start=1):
            connection.execute(
                "INSERT OR IGNORE INTO subjects(name,sort_order,active) VALUES(?,?,1)",
                (subject_name, order),
            )

        connection.commit()



class FaceEngine:

    """One process owns the model. A lock serializes OpenCV and sample mutation."""



    def __init__(self, data_dir, threshold):

        self.data_dir = Path(data_dir)

        self.threshold = float(threshold)

        self.lock = threading.RLock()

        # Some OpenCV wheels omit cascade XML assets. Ship the official model

        # with this project; the package path remains a fallback for old copies.

        cascade_path = BASE_DIR / "assets" / "haarcascade_frontalface_default.xml"

        if not cascade_path.is_file():

            package_data = getattr(getattr(cv2, "data", None), "haarcascades", None)

            if package_data:

                cascade_path = Path(package_data) / "haarcascade_frontalface_default.xml"

        detector_error = "Face detector is missing or invalid. Restore assets/haarcascade_frontalface_default.xml from the project ZIP."

        if not cascade_path.is_file():

            raise RuntimeError(detector_error)

        self.detector = cv2.CascadeClassifier(str(cascade_path))

        if self.detector.empty():

            raise RuntimeError(detector_error)

        self.model = None

        self.labels = set()

        self.version = secrets.token_hex(8)

        self.load()



    def invalidate(self):

        with self.lock:

            self.model = None

            self.labels = set()

            self.version = secrets.token_hex(8)

            for filename in ("model.yml", "model-meta.json"):

                (self.data_dir / filename).unlink(missing_ok=True)



    def load(self):

        model_path = self.data_dir / "model.yml"

        meta_path = self.data_dir / "model-meta.json"

        if not model_path.is_file() or not meta_path.is_file():

            return

        try:

            meta = json.loads(meta_path.read_text(encoding="utf-8"))

            checksum = hashlib.sha256(model_path.read_bytes()).hexdigest()

            expected = meta["sha256"]

            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or not hmac.compare_digest(checksum, expected):

                return

            model = cv2.face.LBPHFaceRecognizer_create()

            model.read(str(model_path))

            self.labels = {int(value) for value in meta["labels"]}

            self.model = model

            self.version = str(meta["version"])

        except (ValueError, TypeError, KeyError, OSError, cv2.error):

            self.model = None

            self.labels = set()



    def crop(self, image):

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        height, width = gray.shape

        # Downscale only for detection, then map the box to the original image.

        scale = min(1.0, 800.0 / max(height, width))

        detection_image = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray

        faces = self.detector.detectMultiScale(

            detection_image, scaleFactor=1.1, minNeighbors=6, minSize=(70, 70)

        )

        if len(faces) == 0:

            raise ValueError("No clear face found. Face the camera in good light.")

        if len(faces) != 1:

            raise ValueError("Only one face is allowed in the camera frame.")

        x, y, width, height = (int(value / scale) for value in faces[0])

        cropped = gray[y:y + height, x:x + width]

        if cropped.size == 0:

            raise ValueError("Face could not be cropped. Try again.")

        return cv2.equalizeHist(cv2.resize(cropped, (160, 160)))



    def sample_count(self, student_id):

        return len(list((self.data_dir / "faces" / str(int(student_id))).glob("*.png")))



    def add_sample(self, student_id, image):

        with self.lock:

            face = self.crop(image)

            folder = self.data_dir / "faces" / str(int(student_id))

            folder.mkdir(exist_ok=True)

            count = self.sample_count(student_id)

            if count >= MAX_SAMPLES:

                raise ValueError("Maximum 60 samples reached for this student.")

            output = folder / f"{secrets.token_hex(12)}.png"

            if not cv2.imwrite(str(output), face):

                raise ValueError("The face sample could not be saved.")

            self.invalidate()

            return count + 1



    def train(self, students):

        with self.lock:

            faces, labels, included = [], [], []

            for student in students:

                if not student["active"] or not student["face_consent"]:

                    continue

                files = sorted((self.data_dir / "faces" / str(student["id"])).glob("*.png"))

                if not files:

                    continue

                if len(files) < MIN_SAMPLES:

                    raise ValueError(f"{student['name']} has {len(files)} samples; collect at least {MIN_SAMPLES}.")

                valid = []

                for file in files:

                    face = cv2.imread(str(file), cv2.IMREAD_GRAYSCALE)

                    if face is not None and face.shape == (160, 160):

                        valid.append(face)

                if len(valid) < MIN_SAMPLES:

                    raise ValueError(f"{student['name']} needs at least {MIN_SAMPLES} valid samples.")

                faces.extend(valid)

                labels.extend([student["id"]] * len(valid))

                included.append(student["id"])

            if not faces:

                raise ValueError("Collect at least 20 consented samples for a student before training.")

            model = cv2.face.LBPHFaceRecognizer_create()

            model.train(faces, np.array(labels, dtype=np.int32))

            version = secrets.token_hex(8)

            model_temp = self.data_dir / f"model-{version}.tmp.yml"

            meta_temp = self.data_dir / f"model-meta-{version}.tmp.json"

            try:

                model.write(str(model_temp))

                checksum = hashlib.sha256(model_temp.read_bytes()).hexdigest()

                meta_temp.write_text(json.dumps({"labels": included, "version": version, "sha256": checksum}),

                                     encoding="utf-8")

                # A crash between these replacements leaves a checksum mismatch:

                # next startup refuses the pair and asks for fresh training.

                os.replace(model_temp, self.data_dir / "model.yml")

                os.replace(meta_temp, self.data_dir / "model-meta.json")

            finally:

                for temporary in (model_temp, meta_temp):

                    try:

                        temporary.unlink(missing_ok=True)

                    except OSError:

                        pass

            self.model, self.labels, self.version = model, set(included), version

            return included



    def predict(self, image):

        with self.lock:

            if self.model is None:

                raise ValueError("Train the face model first.")

            cropped = self.crop(image)

            label, distance = self.model.predict(cropped)

            if int(label) not in self.labels or not np.isfinite(distance) or distance > self.threshold:

                return None, float(distance), self.version

            return int(label), float(distance), self.version





def create_app(config_override=None):

    config_override = config_override or {}

    data_dir = Path(config_override.get("DATA_DIR", os.environ.get(

        "SMART_ATTENDANCE_DATA_DIR", BASE_DIR / "data"

    ))).resolve()

    config_path = data_dir / "config.json"

    stored = {}

    if config_path.is_file():

        try:

            stored = json.loads(config_path.read_text(encoding="utf-8"))

        except (OSError, ValueError) as exc:

            raise RuntimeError("Cannot read private config.json. Check the data folder.") from exc

    env_secret = os.environ.get("SMART_ATTENDANCE_SECRET")

    env_hash = os.environ.get("SMART_ATTENDANCE_ADMIN_HASH")

    if env_secret or env_hash:

        if not env_secret or not env_hash or len(env_secret) < 32 or not env_hash.startswith("scrypt:"):

            raise RuntimeError("Cloud setup needs a secret of at least 32 characters and a scrypt admin hash.")

        stored.update(secret_key=env_secret, password_hash=env_hash,

                      admin_username=os.environ.get("SMART_ATTENDANCE_ADMIN_USER", "admin"))

    if config_override.get("TESTING"):

        stored.update(secret_key=config_override.get("SECRET_KEY"),

                      password_hash=config_override.get("ADMIN_PASSWORD_HASH"),

                      admin_username=config_override.get("ADMIN_USERNAME", "admin"))

    if not all(stored.get(key) for key in ("secret_key", "password_hash", "admin_username")):

        raise RuntimeError("First run: execute python setup_project.py to set your own admin password.")

    try:

        threshold = float(config_override.get("FACE_THRESHOLD", os.environ.get(

            "FACE_THRESHOLD", stored.get("face_threshold", 65)

        )))

    except (ValueError, TypeError) as exc:

        raise RuntimeError("FACE_THRESHOLD must be a finite positive number.") from exc

    if not np.isfinite(threshold) or threshold <= 0:

        raise RuntimeError("FACE_THRESHOLD must be a finite positive number.")

    init_db(data_dir)

    app = Flask(__name__)

    app.config.update(

        SECRET_KEY=stored["secret_key"], DATA_DIR=data_dir,

        ADMIN_USERNAME=stored["admin_username"], ADMIN_PASSWORD_HASH=stored["password_hash"],

        MAX_CONTENT_LENGTH=2 * 1024 * 1024,

        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",

        SESSION_COOKIE_SECURE=os.environ.get("SECURE_COOKIE") == "1",

        PERMANENT_SESSION_LIFETIME=8 * 60 * 60,

        FACE_THRESHOLD=threshold,

    )

    app.config.update(config_override)

    app.config["FACE_THRESHOLD"] = threshold

    if os.environ.get("TRUST_PROXY") == "1":

        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    engine = FaceEngine(data_dir, app.config["FACE_THRESHOLD"])

    app.extensions["face_engine"] = engine

    app.extensions["login_attempts"] = {}

    throttle_lock = threading.Lock()

    scan_lock = threading.Lock()

    # Server-side progress avoids relying on a client-writable match count.

    face_progress = {}

    app.extensions["face_progress"] = face_progress



    def now():

        return datetime.now(IST)



    def db():

        return db_connect(data_dir)



    def failure(message, code=400, error="invalid_request"):

        return jsonify(ok=False, message=message, error=error), code



    def csrf_token():

        if "csrf_token" not in session:

            session["csrf_token"] = secrets.token_urlsafe(32)

        return session["csrf_token"]



    def authenticated(function):

        @wraps(function)

        def wrapped(*args, **kwargs):

            if not session.get("admin_logged_in"):

                if request.path.startswith("/api/") or request.is_json:

                    return failure("Please log in again.", 401, "authentication_required")

                return redirect(url_for("login"))

            return function(*args, **kwargs)

        return wrapped



    @app.before_request

    def protect_mutations():

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:

            expected = session.get("csrf_token", "")

            actual = request.headers.get("X-CSRF-Token", "") or request.form.get("csrf_token", "")

            if not expected or not hmac.compare_digest(str(expected).encode("utf-8"), str(actual).encode("utf-8")):

                if request.path == "/login":

                    return render_template("login.html", csrf_token=csrf_token(),

                                           error="Page expired. Please try again."), 403

                return failure("Page expired. Refresh and try again.", 403, "csrf_failed")



    @app.after_request

    def security_headers(response):

        response.headers["X-Content-Type-Options"] = "nosniff"

        response.headers["X-Frame-Options"] = "DENY"

        response.headers["Referrer-Policy"] = "same-origin"

        response.headers["Permissions-Policy"] = "camera=(self), microphone=()"

        response.headers["Content-Security-Policy"] = (

            "default-src 'self'; script-src 'self'; style-src 'self'; "

            "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "

            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"

        )

        if request.path.startswith("/api/") or request.path in {"/", "/login", "/scan"}:

            response.headers["Cache-Control"] = "no-store"

        return response



    @app.errorhandler(413)

    def too_large(_error):

        return failure("Image/request is too large. Use the built-in camera capture.", 413, "request_too_large")



    @app.errorhandler(404)

    def not_found(_error):

        if request.path.startswith("/api/"):

            return failure("Item not found.", 404, "not_found")

        return "Page not found", 404



    def body():

        value = request.get_json(silent=True)

        if not isinstance(value, dict):

            raise ValueError("A JSON object is required.")

        return value



    def decode_image(payload):

        encoded = payload.get("image")

        if not isinstance(encoded, str) or not encoded.startswith("data:image/jpeg;base64,"):

            raise ValueError("Use a JPEG camera capture.")

        try:

            raw = base64.b64decode(encoded.split(",", 1)[1], validate=True)

        except (binascii.Error, ValueError) as exc:

            raise ValueError("Invalid camera image.") from exc

        if len(raw) > 1_500_000 or len(raw) < 10:

            raise ValueError("Camera image is empty or too large.")

        # Read the compressed header before allocating a decoded OpenCV bitmap.

        try:

            with Image.open(io.BytesIO(raw)) as header:

                if header.format != "JPEG":

                    raise ValueError("Camera image must be JPEG format.")

                width, height = header.size

                if not 1 <= width <= 1920 or not 1 <= height <= 1920:

                    raise ValueError("Camera image must be at most 1920 pixels on each side.")

                header.verify()

        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:

            raise ValueError("Camera image could not be read safely.") from exc

        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)

        if image is None or image.size == 0:

            raise ValueError("Camera image could not be read.")

        if image.shape[0] > 1920 or image.shape[1] > 1920:

            raise ValueError("Camera image must be at most 1920 pixels on each side.")

        return image



    def get_student(student_id):

        with closing(db()) as connection:

            return connection.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()



    def require_active_student(student_id, consent=False):

        student = get_student(student_id)

        if student is None or not student["active"]:

            raise ValueError("Student is missing or inactive.")

        if consent and not student["face_consent"]:

            raise ValueError("Explicit face enrollment consent is required.")

        return student



    def audit(connection, action, student_id, attendance_id, reason, details):

        connection.execute(

            "INSERT INTO audit(action,admin_username,student_id,attendance_id,reason,details,created_at) VALUES(?,?,?,?,?,?,?)",

            (action, app.config["ADMIN_USERNAME"], student_id, attendance_id, reason,

             json.dumps(details, ensure_ascii=False), now().isoformat(timespec="seconds")),

        )



    def expire_finished_sessions(connection):
        current_iso = now().isoformat(timespec="seconds")
        connection.execute(
            "UPDATE class_sessions "
            "SET active=0, ended_at=COALESCE(ended_at, expires_at) "
            "WHERE active=1 AND expires_at<=?",
            (current_iso,),
        )

    def active_class_session(connection):
        expire_finished_sessions(connection)
        return connection.execute(
            "SELECT cs.id,cs.subject_id,sub.name AS subject_name,"
            "cs.started_at,cs.expires_at,cs.ended_at,cs.active "
            "FROM class_sessions cs "
            "JOIN subjects sub ON sub.id=cs.subject_id "
            "WHERE cs.active=1 "
            "ORDER BY cs.id DESC LIMIT 1"
        ).fetchone()

    def session_dict(row):
        if row is None:
            return None

        value = dict(row)
        value["active"] = bool(value["active"])

        try:
            remaining = int(
                (datetime.fromisoformat(value["expires_at"]) - now()).total_seconds()
            )
        except (ValueError, TypeError):
            remaining = 0

        value["seconds_remaining"] = max(0, remaining)
        return value

    def require_active_class_session(connection, expected_session_id=None):
        class_session = active_class_session(connection)

        if class_session is None:
            raise ValueError(
                "No active subject session. Teacher must start a 1-hour session first."
            )

        if (
            expected_session_id is not None
            and class_session["id"] != expected_session_id
        ):
            raise ValueError(
                "The attendance session changed or expired. Reopen the scanner."
            )

        return class_session

    def record_attendance(
        student_id,
        method,
        reason=None,
        expected_qr_token=None,
        expected_session_id=None,
    ):
        moment = now()
        day = moment.date().isoformat()
        marked_at = moment.isoformat(timespec="seconds")

        with closing(db()) as connection:
            connection.execute("BEGIN IMMEDIATE")

            class_session = require_active_class_session(
                connection,
                expected_session_id=expected_session_id,
            )

            student = connection.execute(
                "SELECT * FROM students WHERE id = ?",
                (student_id,),
            ).fetchone()

            if student is None or not student["active"]:
                connection.rollback()
                raise ValueError("Student is missing or inactive.")

            if method == "face" and not student["face_consent"]:
                connection.rollback()
                raise ValueError("Face consent is required.")

            if method == "qr" and not hmac.compare_digest(
                student["qr_token"], expected_qr_token or ""
            ):
                connection.rollback()
                raise ValueError("This QR was revoked. Download the new QR.")

            cursor = connection.execute(
                "INSERT OR IGNORE INTO attendance"
                "(student_id,session_id,day,marked_at,method) VALUES(?,?,?,?,?)",
                (
                    student_id,
                    class_session["id"],
                    day,
                    marked_at,
                    method,
                ),
            )

            inserted = cursor.rowcount == 1

            row = connection.execute(
                "SELECT a.id,a.student_id,a.session_id,a.day,a.marked_at,a.method,"
                "sub.name AS subject_name "
                "FROM attendance a "
                "JOIN class_sessions cs ON cs.id=a.session_id "
                "JOIN subjects sub ON sub.id=cs.subject_id "
                "WHERE a.student_id=? AND a.session_id=?",
                (student_id, class_session["id"]),
            ).fetchone()

            if inserted and method == "manual":
                audit(
                    connection,
                    "manual_mark",
                    student_id,
                    row["id"],
                    reason,
                    dict(row),
                )

            connection.commit()

        status = "marked" if inserted else "duplicate"

        if inserted:
            message = (
                f"Attendance marked for {student['name']} "
                f"in {class_session['subject_name']}."
            )
        else:
            message = (
                f"{student['name']} is already marked in this "
                f"{class_session['subject_name']} session."
            )

        return jsonify(
            ok=True,
            status=status,
            message=message,
            student_id=student_id,
            name=student["name"],
            subject=class_session["subject_name"],
            session_id=class_session["id"],
            attendance=dict(row),
        )



    @app.get("/health")

    def health():

        return jsonify(status="ok")



    @app.route("/login", methods=["GET", "POST"])

    def login():

        if request.method == "GET":

            if session.get("admin_logged_in"):

                return redirect(url_for("index"))

            return render_template("login.html", csrf_token=csrf_token(), error=None)

        username = request.form.get("username", "")

        password = request.form.get("password", "")

        key = request.remote_addr or "local"

        moment = time.monotonic()

        with throttle_lock:

            attempts = app.extensions["login_attempts"]

            # Expire unrelated entries too so this memory map stays bounded.

            for address in list(attempts):

                if moment - attempts[address]["last"] > 15 * 60:

                    del attempts[address]

            attempt = attempts.get(key, {"count": 0, "last": moment})

            if attempt["count"] >= 5 and moment - attempt["last"] < 15 * 60:

                return render_template("login.html", csrf_token=csrf_token(),

                                       error="Too many attempts. Try again after 15 minutes."), 429

        matched = hmac.compare_digest(username.encode("utf-8"), str(app.config["ADMIN_USERNAME"]).encode("utf-8")) and check_password_hash(

            app.config["ADMIN_PASSWORD_HASH"], password

        )

        if not matched:

            with throttle_lock:

                previous = attempts.get(key, {"count": 0})

                attempts[key] = {"count": previous["count"] + 1, "last": moment}

            return render_template("login.html", csrf_token=csrf_token(),

                                   error="Username or password is incorrect."), 401

        with throttle_lock:

            attempts.pop(key, None)

        session.clear()

        session["admin_logged_in"] = True

        session["scan_id"] = secrets.token_urlsafe(24)

        session.permanent = True

        csrf_token()

        return redirect(url_for("index"))



    @app.post("/logout")

    @authenticated

    def logout():

        with scan_lock:

            face_progress.pop(session.get("scan_id"), None)

        session.clear()

        return jsonify(ok=True, message="Logged out.")



    @app.get("/")

    @authenticated

    def index():

        return render_template("index.html", csrf_token=csrf_token())


    @app.get("/sessions")
    @authenticated
    def sessions_page():
        return render_template("sessions.html", csrf_token=csrf_token())



    @app.get("/scan")

    @authenticated

    def scan_page():

        mode = request.args.get("mode", "face")

        if mode not in {"face", "qr"}:

            mode = "face"

        return render_template("scan.html", csrf_token=csrf_token(), mode=mode)



    @app.get("/enroll/<int:student_id>")

    @authenticated

    def enroll_page(student_id):

        if get_student(student_id) is None:

            return "Student not found", 404

        return render_template("enroll.html", csrf_token=csrf_token(), student_id=student_id)



    @app.get("/qr/<int:student_id>")

    @authenticated

    def qr_page(student_id):

        if get_student(student_id) is None:

            return "Student not found", 404

        return render_template("qr.html", csrf_token=csrf_token(), student_id=student_id)



    @app.get("/api/state")
    @authenticated
    def state():
        today = now().date().isoformat()

        with closing(db()) as connection:
            students = connection.execute(
                "SELECT id,student_code,name,active,face_consent "
                "FROM students ORDER BY active DESC,id"
            ).fetchall()

            subjects = connection.execute(
                "SELECT id,name,sort_order,active "
                "FROM subjects WHERE active=1 ORDER BY sort_order"
            ).fetchall()

            current = active_class_session(connection)

            attendance = connection.execute(
                "SELECT a.id,a.student_id,a.session_id,s.student_code,s.name,"
                "sub.name AS subject_name,a.day,a.marked_at,a.method,"
                "cs.started_at AS session_started_at,"
                "cs.expires_at AS session_expires_at "
                "FROM attendance a "
                "JOIN students s ON s.id=a.student_id "
                "JOIN class_sessions cs ON cs.id=a.session_id "
                "JOIN subjects sub ON sub.id=cs.subject_id "
                "WHERE a.day=? "
                "ORDER BY a.marked_at DESC,a.id DESC",
                (today,),
            ).fetchall()

            connection.commit()

        rows = []
        for student in students:
            value = dict(student)
            value.update(
                active=bool(value["active"]),
                face_consent=bool(value["face_consent"]),
                face_samples=engine.sample_count(value["id"]),
                qr_ready=bool(value["active"]),
            )
            rows.append(value)

        return jsonify(
            csrf_token=csrf_token(),
            students=rows,
            subjects=[dict(row) for row in subjects],
            current_session=session_dict(current),
            attendance_today=[dict(row) for row in attendance],
            today=today,
            model={
                "ready": engine.model is not None,
                "trained_students": len(engine.labels),
                "threshold": engine.threshold,
                "min_samples": MIN_SAMPLES,
            },
            settings={
                "timezone": "Asia/Kolkata",
                "session_duration_minutes": SESSION_DURATION_MINUTES,
            },
        )

    @app.get("/api/sessions/current")
    @authenticated
    def current_session_api():
        with closing(db()) as connection:
            current = active_class_session(connection)
            connection.commit()

        return jsonify(
            ok=True,
            current_session=session_dict(current),
            session_duration_minutes=SESSION_DURATION_MINUTES,
        )

    @app.post("/api/sessions/start")
    @authenticated
    def start_session():
        try:
            payload = body()
            subject_id = payload.get("subject_id")

            if not isinstance(subject_id, int) or isinstance(subject_id, bool):
                raise ValueError("Select a valid subject.")

            started = now()
            expires = started + timedelta(minutes=SESSION_DURATION_MINUTES)

            with closing(db()) as connection:
                connection.execute("BEGIN IMMEDIATE")

                existing = active_class_session(connection)
                if existing is not None:
                    connection.rollback()
                    return failure(
                        f"{existing['subject_name']} session is already active.",
                        409,
                        "session_already_active",
                    )

                subject = connection.execute(
                    "SELECT id,name FROM subjects WHERE id=? AND active=1",
                    (subject_id,),
                ).fetchone()

                if subject is None:
                    connection.rollback()
                    raise ValueError("Selected subject was not found.")

                cursor = connection.execute(
                    "INSERT INTO class_sessions"
                    "(subject_id,started_at,expires_at,active) VALUES(?,?,?,1)",
                    (
                        subject_id,
                        started.isoformat(timespec="seconds"),
                        expires.isoformat(timespec="seconds"),
                    ),
                )
                session_id = cursor.lastrowid

                audit(
                    connection,
                    "session_start",
                    None,
                    None,
                    "Teacher started a 1-hour attendance session",
                    {
                        "session_id": session_id,
                        "subject_id": subject_id,
                        "subject": subject["name"],
                        "started_at": started.isoformat(timespec="seconds"),
                        "expires_at": expires.isoformat(timespec="seconds"),
                    },
                )

                connection.commit()

                current = connection.execute(
                    "SELECT cs.id,cs.subject_id,sub.name AS subject_name,"
                    "cs.started_at,cs.expires_at,cs.ended_at,cs.active "
                    "FROM class_sessions cs "
                    "JOIN subjects sub ON sub.id=cs.subject_id "
                    "WHERE cs.id=?",
                    (session_id,),
                ).fetchone()

            return jsonify(
                ok=True,
                message=(
                    f"{subject['name']} session started. "
                    f"Scanner will close automatically after 60 minutes."
                ),
                current_session=session_dict(current),
            ), 201

        except ValueError as exc:
            return failure(str(exc))
        except sqlite3.IntegrityError:
            return failure(
                "Another subject session is already active.",
                409,
                "session_already_active",
            )

    @app.post("/api/sessions/<int:session_id>/end")
    @authenticated
    def end_session(session_id):
        with closing(db()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            expire_finished_sessions(connection)

            row = connection.execute(
                "SELECT cs.id,cs.subject_id,sub.name AS subject_name,"
                "cs.started_at,cs.expires_at,cs.ended_at,cs.active "
                "FROM class_sessions cs "
                "JOIN subjects sub ON sub.id=cs.subject_id "
                "WHERE cs.id=?",
                (session_id,),
            ).fetchone()

            if row is None:
                connection.rollback()
                return failure("Session not found.", 404, "not_found")

            if not row["active"]:
                connection.commit()
                return jsonify(
                    ok=True,
                    message="Session is already closed.",
                    current_session=None,
                )

            ended_at = now().isoformat(timespec="seconds")
            connection.execute(
                "UPDATE class_sessions SET active=0,ended_at=? WHERE id=?",
                (ended_at, session_id),
            )

            audit(
                connection,
                "session_end",
                None,
                None,
                "Teacher ended the attendance session",
                {
                    "session_id": session_id,
                    "subject_id": row["subject_id"],
                    "subject": row["subject_name"],
                    "ended_at": ended_at,
                },
            )

            connection.commit()

        with scan_lock:
            face_progress.clear()

        return jsonify(
            ok=True,
            message=f"{row['subject_name']} session ended. Scanner is closed.",
            current_session=None,
        )



    @app.post("/api/students")

    @authenticated

    def add_student():

        try:

            payload = body()

            code, name = payload.get("student_code"), payload.get("name")

            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,63}", code.strip()):

                raise ValueError("Student code: use 1–64 letters, numbers, dot, slash, dash or underscore.")

            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or any(ord(c) < 32 for c in name):

                raise ValueError("Name must be 1–100 characters without control characters.")

            consent = payload.get("face_consent", False)

            if not isinstance(consent, bool):

                raise ValueError("Face consent must be true or false.")

            with closing(db()) as connection:

                cursor = connection.execute(

                    "INSERT INTO students(student_code,name,face_consent,qr_token,created_at) VALUES(?,?,?,?,?)",

                    (code.strip(), name.strip(), int(consent), secrets.token_urlsafe(32), now().isoformat(timespec="seconds")),

                )

                connection.commit()

                student_id = cursor.lastrowid

            return jsonify(ok=True, message="Student added. Keep their QR private.", student_id=student_id), 201

        except ValueError as exc:

            return failure(str(exc))

        except sqlite3.IntegrityError:

            return failure("That student code already exists.", 409, "duplicate_student_code")



    @app.post("/api/students/<int:student_id>/active")

    @authenticated

    def set_active(student_id):

        try:

            active = body().get("active")

            if not isinstance(active, bool):

                raise ValueError("Active must be true or false.")

            if get_student(student_id) is None:

                return failure("Student not found.", 404, "not_found")

            with engine.lock:

                with closing(db()) as connection:

                    connection.execute("UPDATE students SET active=?,qr_token=? WHERE id=?",

                                       (int(active), secrets.token_urlsafe(32), student_id))

                    audit(connection, "activate" if active else "deactivate", student_id, None,

                          "Teacher changed student status", {"active": active})

                    connection.commit()

                engine.invalidate()

            return jsonify(ok=True, message="Student status changed. Retrain faces; previous QR has been revoked.")

        except ValueError as exc:

            return failure(str(exc))



    @app.post("/api/students/<int:student_id>/face-samples")

    @authenticated

    def face_sample(student_id):

        try:

            with engine.lock:

                require_active_student(student_id, consent=True)

                count = engine.add_sample(student_id, decode_image(body()))

            return jsonify(ok=True, message=f"Face sample saved ({count}/{MIN_SAMPLES} minimum).",

                           count=count, required=MIN_SAMPLES)

        except (ValueError, cv2.error) as exc:

            return failure(str(exc) if isinstance(exc, ValueError) else "Face capture failed. Try again.")



    @app.post("/api/train")

    @authenticated

    def train():

        try:

            with engine.lock:

                with closing(db()) as connection:

                    students = connection.execute("SELECT * FROM students").fetchall()

                included = engine.train(students)

            message = f"Face model trained for {len(included)} student(s)."

            if len(included) == 1:

                message += " One-person models can accept other people; use two or more identities and test unknown faces."

            return jsonify(ok=True, message=message, trained_students=len(included), ready=True)

        except (ValueError, cv2.error) as exc:

            return failure(str(exc) if isinstance(exc, ValueError) else "Training failed. Check your face samples.")



    @app.post("/api/scan/face")
    @authenticated
    def scan_face():
        scan_id = session.get("scan_id")

        try:
            with closing(db()) as connection:
                current = require_active_class_session(connection)
                connection.commit()
                current_session_id = current["id"]

            with engine.lock:
                label, distance, version = engine.predict(decode_image(body()))

                if label is None:
                    with scan_lock:
                        face_progress.pop(scan_id, None)

                    return failure(
                        "Unknown face. Try better lighting or use the registered QR.",
                        400,
                        "unknown_face",
                    )

                student = require_active_student(label, consent=True)
                moment = time.monotonic()

                with scan_lock:
                    for key in list(face_progress):
                        if moment - face_progress[key]["time"] > 30:
                            face_progress.pop(key, None)

                    previous = face_progress.get(scan_id)
                    same = (
                        previous
                        and previous["id"] == label
                        and previous["version"] == version
                        and previous["session_id"] == current_session_id
                        and moment - previous["time"] <= 4
                    )

                    count = previous["count"] + 1 if same else 1

                    face_progress[scan_id] = {
                        "id": label,
                        "version": version,
                        "session_id": current_session_id,
                        "count": count,
                        "time": moment,
                    }

                    if count < 3:
                        return jsonify(
                            ok=True,
                            status="progress",
                            message=f"Hold still: {student['name']} ({count}/3).",
                            name=student["name"],
                            count=count,
                            required=3,
                            session_id=current_session_id,
                        )

                    face_progress.pop(scan_id, None)

                return record_attendance(
                    label,
                    "face",
                    expected_session_id=current_session_id,
                )

        except (ValueError, cv2.error) as exc:
            with scan_lock:
                face_progress.pop(scan_id, None)

            return failure(
                str(exc)
                if isinstance(exc, ValueError)
                else "Face scan failed. Try again."
            )



    @app.post("/api/scan/qr")

    @authenticated

    def scan_qr():

        try:
            with closing(db()) as connection:
                current = require_active_class_session(connection)
                connection.commit()
                current_session_id = current["id"]

            image = decode_image(body())

            # New detector per call avoids sharing OpenCV mutable state between threads.

            detector = cv2.QRCodeDetector()

            multiple, codes, points, _straight = detector.detectAndDecodeMulti(image)

            if multiple and points is not None and len(points) > 1:

                raise ValueError("Show only one QR code at a time.")

            values = [value for value in codes if value] if multiple else []

            if len(values) > 1:

                raise ValueError("Show only one QR code at a time.")

            if not values:

                value, _points, _straight = detector.detectAndDecode(image)

                if value:

                    values = [value]

            if not values:

                raise ValueError("No readable QR found. Move the QR closer and keep it still.")

            payload = values[0]

            if not payload.startswith("sa1:") or len(payload) > 100:

                raise ValueError("This is not a registered attendance QR.")

            with closing(db()) as connection:

                student = connection.execute("SELECT id FROM students WHERE qr_token=? AND active=1",

                                             (payload[4:],)).fetchone()

            if student is None:

                raise ValueError("QR is invalid, revoked or belongs to an inactive student.")

            return record_attendance(
                student["id"],
                "qr",
                expected_qr_token=payload[4:],
                expected_session_id=current_session_id,
            )

        except (ValueError, cv2.error) as exc:

            return failure(str(exc) if isinstance(exc, ValueError) else "QR scan failed. Try again.")



    @app.get("/api/students/<int:student_id>/qr.png")

    @authenticated

    def student_qr(student_id):

        try:

            student = require_active_student(student_id)

            output = io.BytesIO()

            qrcode.make("sa1:" + student["qr_token"]).save(output, format="PNG")

            response = Response(output.getvalue(), mimetype="image/png")

            response.headers["Content-Disposition"] = f'inline; filename="student-{student_id}-qr.png"'

            return response

        except ValueError as exc:

            return failure(str(exc), 404, "not_found")



    @app.post("/api/students/<int:student_id>/qr/revoke")

    @authenticated

    def revoke_qr(student_id):

        try:

            require_active_student(student_id)

            with closing(db()) as connection:

                connection.execute("UPDATE students SET qr_token=? WHERE id=?", (secrets.token_urlsafe(32), student_id))

                audit(connection, "reissue_qr", student_id, None, "Teacher reissued QR", {})

                connection.commit()

            return jsonify(ok=True, message="Old QR revoked. Download the new QR.")

        except ValueError as exc:

            return failure(str(exc))



    def correction_reason(payload):

        reason = payload.get("reason")

        if not isinstance(reason, str) or not 5 <= len(reason.strip()) <= 500:

            raise ValueError("Enter a reason of 5–500 characters for the audit log.")

        return reason.strip()



    @app.post("/api/attendance/manual")

    @authenticated

    def manual_attendance():

        try:

            payload = body()

            reason = correction_reason(payload)

            student_id = payload.get("student_id")

            if not isinstance(student_id, int) or isinstance(student_id, bool):

                raise ValueError("A student ID is required.")

            return record_attendance(student_id, "manual", reason)

        except ValueError as exc:

            return failure(str(exc))



    @app.post("/api/attendance/<int:attendance_id>/void")

    @authenticated

    def void_attendance(attendance_id):

        try:

            reason = correction_reason(body())

            with closing(db()) as connection:

                connection.execute("BEGIN IMMEDIATE")

                row = connection.execute("SELECT * FROM attendance WHERE id=?", (attendance_id,)).fetchone()

                if row is None:

                    return failure("Attendance entry not found.", 404, "not_found")

                audit(connection, "void_mark", row["student_id"], attendance_id, reason, dict(row))

                connection.execute("DELETE FROM attendance WHERE id=?", (attendance_id,))

                connection.commit()

            return jsonify(ok=True, message="Mark voided with an audit record. Student may be scanned again.")

        except ValueError as exc:

            return failure(str(exc))



    def csv_cell(value):

        value = "" if value is None else str(value)

        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):

            return "'" + value

        return value



    @app.get("/api/attendance.csv")
    @authenticated
    def export_attendance():
        with closing(db()) as connection:
            rows = connection.execute(
                "SELECT a.day,sub.name AS subject,s.student_code,s.name,"
                "cs.started_at,cs.expires_at,a.marked_at,a.method "
                "FROM attendance a "
                "JOIN students s ON s.id=a.student_id "
                "JOIN class_sessions cs ON cs.id=a.session_id "
                "JOIN subjects sub ON sub.id=cs.subject_id "
                "ORDER BY a.day DESC,cs.started_at DESC,a.marked_at DESC"
            ).fetchall()

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "Date (IST)",
            "Subject",
            "Student code",
            "Name",
            "Session started (IST)",
            "Session expires (IST)",
            "Marked at (IST)",
            "Method",
        ])

        for row in rows:
            writer.writerow([csv_cell(value) for value in row])

        return Response(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="attendance.csv"'
            },
        )



    @app.get("/api/audit.csv")

    @authenticated

    def export_audit():

        with closing(db()) as connection:

            rows = connection.execute(

                "SELECT created_at,action,admin_username,student_id,attendance_id,reason,details FROM audit ORDER BY id DESC"

            ).fetchall()

        output = io.StringIO(newline="")

        writer = csv.writer(output)

        writer.writerow(["Timestamp (IST)", "Action", "Admin", "Student ID", "Attendance ID", "Reason", "Saved original entry"])

        for row in rows:

            writer.writerow([csv_cell(value) for value in row])

        return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",

                        headers={"Content-Disposition": 'attachment; filename="attendance-audit.csv"'})



    return app





if __name__ == "__main__":

    from waitress import serve

    application = create_app()

    host = os.environ.get("HOST", "127.0.0.1")

    port = int(os.environ.get("PORT", "8000"))

    print(f"Smart Attendance: http://{host}:{port} (use Ctrl+C to stop)")

    serve(application, host=host, port=port, threads=4)
