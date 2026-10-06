"""Run: python -m unittest discover -s tests -v

These exercise access control and record integrity. Camera/face accuracy still
requires real volunteers, lighting and unknown-person checks on the laptop.
"""
import base64
import csv
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime as RealDateTime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import cv2
import numpy as np
from jinja2 import DictLoader
from werkzeug.security import generate_password_hash

from app import FaceEngine, create_app, db_connect


def jpeg_data(image=None):
    if image is None:
        image = np.zeros((300, 300, 3), dtype=np.uint8)
    success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert success
    return "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")


class AttendanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "long-test-password-2026"
        cls.password_hash = generate_password_hash(cls.password)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name)
        self.app = create_app({
            "TESTING": True, "DATA_DIR": self.data_dir,
            "SECRET_KEY": "test-only-" + "s" * 48,
            "ADMIN_USERNAME": "teacher", "ADMIN_PASSWORD_HASH": self.password_hash,
        })
        self.app.jinja_loader = DictLoader({
            "login.html": '<input name="csrf_token" value="{{ csrf_token }}">{{ error or "" }}',
            "index.html": "Dashboard", "scan.html": "Scan", "enroll.html": "Enroll", "qr.html": "QR",
        })
        self.client = self.app.test_client()
        self.login(self.client)

    def tearDown(self):
        self.temp.cleanup()

    def login(self, client):
        client.get("/login")
        with client.session_transaction() as session:
            csrf = session["csrf_token"]
        response = client.post("/login", data={"username": "teacher", "password": self.password, "csrf_token": csrf})
        self.assertEqual(response.status_code, 302)
        return client.get("/api/state").get_json()["csrf_token"]

    def csrf(self, client=None):
        return (client or self.client).get("/api/state").get_json()["csrf_token"]

    def post(self, url, payload, client=None):
        client = client or self.client
        return client.post(url, json=payload, headers={"X-CSRF-Token": self.csrf(client)})

    def add(self, code="A001", name="Asha", consent=True):
        response = self.post("/api/students", {"student_code": code, "name": name, "face_consent": consent})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["student_id"]

    def qr_image(self, student_id):
        png = self.client.get(f"/api/students/{student_id}/qr.png").data
        return jpeg_data(cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR))

    def test_authentication_and_csrf_required(self):
        stranger = self.app.test_client()
        self.assertEqual(stranger.get("/api/state").status_code, 401)
        self.assertEqual(stranger.get("/api/attendance.csv").status_code, 401)
        self.assertEqual(stranger.get("/api/audit.csv").status_code, 401)
        self.assertEqual(stranger.get("/api/students/1/qr.png").status_code, 401)
        self.assertEqual(self.client.post("/api/students", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/students", json={}, headers={"X-CSRF-Token": "invalid-\u2603"}).status_code, 403)
        self.assertEqual(stranger.get("/health").get_json(), {"status": "ok"})

    def test_login_csrf_and_attempt_throttling(self):
        stranger = self.app.test_client()
        self.assertEqual(stranger.post("/login", data={"username": "teacher", "password": self.password}).status_code, 403)
        with stranger.session_transaction() as session:
            csrf = session["csrf_token"]
        for _ in range(5):
            response = stranger.post("/login", data={"username": "unknown-\u2603", "password": "wrong", "csrf_token": csrf})
            self.assertEqual(response.status_code, 401)
        response = stranger.post("/login", data={"username": "teacher", "password": self.password, "csrf_token": csrf})
        self.assertEqual(response.status_code, 429)

    def test_qr_duplicate_and_cross_method_uniqueness(self):
        student_id = self.add()
        image = self.qr_image(student_id)
        response = self.post("/api/scan/qr", {"image": image})
        self.assertEqual(response.get_json()["status"], "marked")
        response = self.post("/api/scan/qr", {"image": image})
        self.assertEqual(response.get_json()["status"], "duplicate")
        engine = self.app.extensions["face_engine"]
        engine.predict = lambda _image: (student_id, 10.0, "stub-model")
        for expected in ("progress", "progress", "duplicate"):
            response = self.post("/api/scan/face", {"image": jpeg_data()})
            self.assertEqual(response.get_json()["status"], expected)
        state = self.client.get("/api/state").get_json()
        self.assertEqual(len(state["attendance_today"]), 1)
        self.assertEqual(state["attendance_today"][0]["method"], "qr")
        # The first method must also survive in the opposite order.
        second = self.add("A002", "Bina")
        engine.predict = lambda _image: (second, 10.0, "stub-model")
        for expected in ("progress", "progress", "marked"):
            response = self.post("/api/scan/face", {"image": jpeg_data()})
            self.assertEqual(response.get_json()["status"], expected)
        response = self.post("/api/scan/qr", {"image": self.qr_image(second)})
        self.assertEqual(response.get_json()["status"], "duplicate")
        self.assertEqual(response.get_json()["attendance"]["method"], "face")

    def test_unknown_and_mismatched_face_reset_stability(self):
        first = self.add()
        second = self.add("A002", "Bina")
        engine = self.app.extensions["face_engine"]
        engine.predict = lambda _image: (first, 10.0, "v1")
        self.assertEqual(self.post("/api/scan/face", {"image": jpeg_data()}).get_json()["count"], 1)
        engine.predict = lambda _image: (None, 100.0, "v1")
        self.assertEqual(self.post("/api/scan/face", {"image": jpeg_data()}).get_json()["error"], "unknown_face")
        engine.predict = lambda _image: (first, 10.0, "v1")
        self.assertEqual(self.post("/api/scan/face", {"image": jpeg_data()}).get_json()["count"], 1)
        engine.predict = lambda _image: (second, 10.0, "v1")
        self.assertEqual(self.post("/api/scan/face", {"image": jpeg_data()}).get_json()["count"], 1)
        self.assertEqual(len(self.client.get("/api/state").get_json()["attendance_today"]), 0)

    def test_deactivation_and_qr_rotation(self):
        student_id = self.add()
        old_qr = self.qr_image(student_id)
        self.assertEqual(self.post(f"/api/students/{student_id}/qr/revoke", {}).status_code, 200)
        self.assertEqual(self.post("/api/scan/qr", {"image": old_qr}).status_code, 400)
        current_qr = self.qr_image(student_id)
        self.assertEqual(self.post(f"/api/students/{student_id}/active", {"active": False}).status_code, 200)
        self.assertEqual(self.post("/api/scan/qr", {"image": current_qr}).status_code, 400)
        self.assertEqual(self.client.get(f"/api/students/{student_id}/qr.png").status_code, 404)
        engine = self.app.extensions["face_engine"]
        engine.predict = lambda _image: (student_id, 10.0, "stub-model")
        self.assertEqual(self.post("/api/scan/face", {"image": jpeg_data()}).status_code, 400)

    def test_face_samples_require_consent_and_minimum(self):
        student_id = self.add(consent=False)
        self.assertEqual(self.post(f"/api/students/{student_id}/face-samples", {"image": jpeg_data()}).status_code, 400)
        student_id = self.add("A002", "Bina", consent=True)
        engine = self.app.extensions["face_engine"]
        engine.crop = lambda _image: np.full((160, 160), 80, np.uint8)
        self.assertEqual(self.post(f"/api/students/{student_id}/face-samples", {"image": jpeg_data()}).get_json()["count"], 1)
        self.assertEqual(self.post("/api/train", {}).status_code, 400)
        for _ in range(19):
            self.assertEqual(self.post(f"/api/students/{student_id}/face-samples", {"image": jpeg_data()}).status_code, 200)
        response = self.post("/api/train", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["trained_students"], 1)
        self.assertTrue(self.client.get("/api/state").get_json()["model"]["ready"])
        self.assertIsNotNone(FaceEngine(self.data_dir, 65).model)
        model_path = self.data_dir / "model.yml"
        model_path.write_bytes(model_path.read_bytes() + b"\n# modified after training\n")
        self.assertIsNone(FaceEngine(self.data_dir, 65).model)
        self.post(f"/api/students/{student_id}/face-samples", {"image": jpeg_data()})
        self.assertFalse(self.client.get("/api/state").get_json()["model"]["ready"])

    def test_manual_correction_retains_audit_and_csv_protection(self):
        student_id = self.add(name='=HYPERLINK("https://example.invalid")')
        self.assertEqual(self.post("/api/attendance/manual", {"student_id": student_id, "reason": ""}).status_code, 400)
        response = self.post("/api/attendance/manual", {"student_id": student_id, "reason": "Teacher observed student"})
        self.assertEqual(response.get_json()["status"], "marked")
        row_id = response.get_json()["attendance"]["id"]
        exported = self.client.get("/api/attendance.csv").data.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(exported)))
        self.assertTrue(rows[1][2].startswith("'="))
        self.assertEqual(self.post(f"/api/attendance/{row_id}/void", {"reason": "Wrong student selected"}).status_code, 200)
        self.assertEqual(len(self.client.get("/api/state").get_json()["attendance_today"]), 0)
        with closing(db_connect(self.data_dir)) as connection:
            audit = connection.execute("SELECT action,details FROM audit ORDER BY id").fetchall()
        self.assertEqual([row["action"] for row in audit], ["manual_mark", "void_mark"])
        self.assertIn("manual", audit[1]["details"])
        self.assertEqual(self.client.get("/api/audit.csv").status_code, 200)

    def test_concurrent_attempts_create_one_daily_row(self):
        student_id = self.add()
        clients = [self.app.test_client(), self.app.test_client()]
        tokens = [self.login(client) for client in clients]
        def mark(index):
            return clients[index].post("/api/attendance/manual", json={"student_id": student_id, "reason": "Concurrent integrity check"},
                                       headers={"X-CSRF-Token": tokens[index]}).get_json()["status"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(mark, [0, 1]))
        self.assertEqual(sorted(results), ["duplicate", "marked"])
        self.assertEqual(len(self.client.get("/api/state").get_json()["attendance_today"]), 1)

    def test_image_payload_limits_and_validation(self):
        self.assertEqual(self.post("/api/scan/qr", {"image": "data:image/jpeg;base64,!!!"}).status_code, 400)
        self.assertEqual(self.post("/api/scan/qr", {"image": "data:image/png;base64,AAAA"}).status_code, 400)
        self.assertEqual(self.post("/api/scan/qr", {"image": "x" * (2 * 1024 * 1024)}).status_code, 413)
        self.assertEqual(self.post("/api/students", {"student_code": "../../x", "name": "X"}).status_code, 400)

    def test_face_crop_rejects_no_face_and_multiple_faces(self):
        engine = self.app.extensions["face_engine"]
        image = np.zeros((300, 300, 3), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, "No clear face"):
            engine.crop(image)
        class TwoFaces:
            def detectMultiScale(self, *_args, **_kwargs):
                return np.array([[20, 20, 80, 80], [120, 20, 80, 80]])
        engine.detector = TwoFaces()
        with self.assertRaisesRegex(ValueError, "Only one face"):
            engine.crop(image)

    def test_daily_uniqueness_resets_at_ist_midnight(self):
        student_id = self.add()
        before = RealDateTime(2026, 10, 4, 23, 59, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
        after = RealDateTime(2026, 10, 5, 0, 0, 1, tzinfo=ZoneInfo("Asia/Kolkata"))
        with patch("app.datetime") as clock:
            clock.now.return_value = before
            first = self.post("/api/attendance/manual", {"student_id": student_id, "reason": "Observed before midnight"}).get_json()
            repeat = self.post("/api/attendance/manual", {"student_id": student_id, "reason": "Retry before midnight"}).get_json()
            self.assertEqual((first["status"], repeat["status"]), ("marked", "duplicate"))
            self.assertEqual(first["attendance"]["day"], "2026-10-04")
            clock.now.return_value = after
            second = self.post("/api/attendance/manual", {"student_id": student_id, "reason": "Observed after midnight"}).get_json()
            repeat = self.post("/api/attendance/manual", {"student_id": student_id, "reason": "Retry after midnight"}).get_json()
            self.assertEqual((second["status"], repeat["status"]), ("marked", "duplicate"))
            self.assertEqual(second["attendance"]["day"], "2026-10-05")
        with closing(db_connect(self.data_dir)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM attendance").fetchone()[0], 2)

    def test_unsafe_threshold_is_rejected(self):
        for threshold in (float("nan"), float("inf"), -1, 0, "not-a-number"):
            with self.subTest(threshold=threshold), self.assertRaisesRegex(RuntimeError, "finite positive"):
                create_app({"TESTING": True, "DATA_DIR": self.data_dir,
                            "SECRET_KEY": "s" * 64, "ADMIN_PASSWORD_HASH": self.password_hash,
                            "FACE_THRESHOLD": threshold})

    def test_large_jpeg_header_rejected_before_opencv_decode(self):
        large = jpeg_data(np.zeros((100, 2001, 3), dtype=np.uint8))
        with patch("app.cv2.imdecode") as decode:
            response = self.post("/api/scan/qr", {"image": large})
            self.assertEqual(response.status_code, 400)
            self.assertIn("1920", response.get_json()["message"])
            decode.assert_not_called()
        # A tiny compressed payload can advertise billions of pixels. Mutate
        # JPEG SOF dimensions without allocating that image in the test.
        forged = bytearray(base64.b64decode(jpeg_data().split(",", 1)[1]))
        start_of_frame = forged.index(b"\xff\xc0")
        forged[start_of_frame + 5:start_of_frame + 9] = b"\xff\xff\xff\xff"
        forged_image = "data:image/jpeg;base64," + base64.b64encode(forged).decode("ascii")
        with patch("app.cv2.imdecode") as decode:
            self.assertEqual(self.post("/api/scan/qr", {"image": forged_image}).status_code, 400)
            decode.assert_not_called()
        # A PNG with a misleading JPEG data URL must also fail before decoding.
        success, png = cv2.imencode(".png", np.zeros((30, 30, 3), np.uint8))
        self.assertTrue(success)
        wrong_format = "data:image/jpeg;base64," + base64.b64encode(png).decode("ascii")
        with patch("app.cv2.imdecode") as decode:
            self.assertEqual(self.post("/api/scan/qr", {"image": wrong_format}).status_code, 400)
            decode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
