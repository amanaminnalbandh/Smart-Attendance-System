# Verification — English revision, 05 October 2026

This revision translates the interface and documentation into English. It keeps application APIs, the database schema, dependency versions and the bundled face-detector source unchanged. Existing records do not require migration.

## Previously completed checks — 04 October 2026

All 13 backend automated tests passed on Windows with Python 3.12.14 and the pinned local requirements. Tests covered daily uniqueness across face and QR in both orders, concurrent requests, the IST midnight boundary, credentials and CSRF, QR revocation, active status, image bounds, unsafe thresholds, manual correction auditing, CSV text safety and face-model integrity.

Real OpenCV QR decoding, blank-face rejection and LBPH training, saving and reloading were exercised. Identity and match-stability behavior used mocked face predictions; these checks do not establish real recognition accuracy or liveness.

Actual Flask/Jinja HTML routes, CSS, JavaScript and QR PNG passed a response/render smoke check. A local browser test verified login, sample student registration and saved manual attendance. JavaScript syntax passed.

## English revision checks — 05 October 2026

All 13 existing backend tests were rerun on 05 October 2026 using the pinned wheels and Python 3.12.14 on Windows: 13 passed in 9.714 seconds. No additional tests were added for the translation.

The English interface also passed actual Flask/Jinja template and response smoke checks on 05 October 2026. JavaScript syntax passed. These checks do not establish real camera performance or validate cloud hosting.

## Limits and source package

Real laptop webcam permissions, face-recognition accuracy, room lighting, anti-spoofing and internet hosting have not been validated. Cloud requirements describe an optional deployment path, not a deployed service.

The source archive contains no setup credentials, student database, enrolled student faces or trained personal model. The bundled pretrained Haar detector is an official OpenCV asset with its embedded license retained. It is a general face detector, not a student identity model.
