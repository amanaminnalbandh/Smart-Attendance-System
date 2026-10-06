"use strict";

(() => {
  const page = document.body.dataset.page;
  const statusBox = document.getElementById("page-status");
  let csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  let appState = null;
  let camera = null;

  function showStatus(message, kind = "") {
    if (!statusBox) return;
    statusBox.hidden = false;
    statusBox.className = `status ${kind}`;
    statusBox.textContent = String(message);
  }

  async function api(path, payload, signal) {
    const options = {
      credentials: "same-origin",
      cache: "no-store",
      signal
    };

    if (payload !== undefined) {
      options.method = "POST";
      options.headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken
      };
      options.body = JSON.stringify(payload);
    }

    const response = await fetch(path, options);

    const data = await response.json().catch(() => ({
      ok: false,
      message: "The server returned an invalid response. Check the server terminal."
    }));

    if (response.status === 401) {
      camera?.stop();
      window.location.assign("/login");
      throw new Error("Your session has expired. Log in again.");
    }

    if (!response.ok || data.ok === false) {
      const error = new Error(
        data.message || data.error || "The request could not be completed."
      );

      error.httpStatus = response.status;
      error.code = data.error;
      throw error;
    }

    return data;
  }

  async function loadState() {
    appState = await api("/api/state");

    if (appState.csrf_token) {
      csrfToken = appState.csrf_token;
    }

    return appState;
  }

  function element(tag, value, className) {
    const node = document.createElement(tag);

    if (value !== undefined) {
      node.textContent = String(value);
    }

    if (className) {
      node.className = className;
    }

    return node;
  }

  function cell(row, content) {
    const td = element("td");

    if (content instanceof Node) {
      td.append(content);
    } else {
      td.textContent = String(content ?? "");
    }

    row.append(td);
    return td;
  }

  function studentLabel(student) {
    const holder = element("div");

    holder.append(
      element("span", student.name, "name"),
      element("span", student.student_code, "subtext")
    );

    return holder;
  }

  function actionLink(label, href) {
    const link = element("a", label, "button secondary small");
    link.href = href;
    return link;
  }

  function actionButton(label, className, handler) {
    const button = element("button", label, className);
    button.type = "button";

    button.addEventListener("click", async () => {
      button.disabled = true;

      try {
        await handler();
      } catch (error) {
        showStatus(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });

    return button;
  }

  function emptyTable(body, columns, message) {
    const row = element("tr");
    const td = cell(row, message);

    td.colSpan = columns;
    td.className = "empty";
    body.append(row);
  }

  async function updateDashboard() {
    const state = await loadState();
    const students = Array.isArray(state.students) ? state.students : [];
    const active = students.filter(student => student.active);

    document.getElementById("active-count").textContent = String(active.length);

    const model = state.model || {};

    document.getElementById("model-label").textContent =
      model.ready ? "Ready" : "Training needed";

    document.getElementById("model-note").textContent =
      model.ready
        ? `${model.trained_students || 0} students trained`
        : "Collect samples, then press Train model";

    document.getElementById("min-samples").textContent =
      String(model.min_samples || 20);

    const studentsBody = document.getElementById("students-body");
    studentsBody.textContent = "";

    for (const student of students) {
      const row = element("tr");

      cell(row, studentLabel(student));

      cell(
        row,
        element(
          "span",
          student.active ? "Active" : "Inactive",
          `badge ${student.active ? "good" : "bad"}`
        )
      );

      const face = element("div");

      face.append(
        element("span", `${student.face_samples || 0} saved`, "name"),
        element(
          "span",
          student.face_consent
            ? "Consent recorded"
            : "QR only · No face consent",
          "subtext"
        )
      );

      cell(row, face);

      const actions = element("div", undefined, "actions");

      if (student.active && student.face_consent) {
        actions.append(
          actionLink(
            "Face samples",
            `/enroll/${encodeURIComponent(student.id)}`
          )
        );
      }

      if (student.active && student.qr_ready) {
        actions.append(
          actionLink(
            "QR card",
            `/qr/${encodeURIComponent(student.id)}`
          )
        );
      }

      if (student.active) {
        actions.append(
          actionButton("Reissue QR", "secondary small", async () => {
            const result = await api(
              `/api/students/${encodeURIComponent(student.id)}/qr/revoke`,
              {}
            );

            await updateDashboard();

            showStatus(
              result.message ||
                "The new QR is ready. The old card is now invalid.",
              "success"
            );
          })
        );
      }

      actions.append(
        actionButton(
          student.active ? "Deactivate" : "Activate",
          student.active ? "danger small" : "secondary small",
          async () => {
            const result = await api(
              `/api/students/${encodeURIComponent(student.id)}/active`,
              { active: !student.active }
            );

            await updateDashboard();

            showStatus(
              result.message ||
                "Student status updated. Retrain the face model.",
              "success"
            );
          }
        )
      );

      cell(row, actions);
      studentsBody.append(row);
    }

    if (!students.length) {
      emptyTable(
        studentsBody,
        4,
        "No students yet. Add your first student using the form above."
      );
    }

    const selection = document.getElementById("manual-student");
    const previousValue = selection.value;

    selection.textContent = "";

    const placeholder = element("option", "Select a student");
    placeholder.value = "";
    selection.append(placeholder);

    for (const student of active) {
      const option = element(
        "option",
        `${student.name} · ${student.student_code}`
      );

      option.value = String(student.id);
      selection.append(option);
    }

    selection.value = previousValue;

    // session.js updates attendance counts and the subject register.
    window.dispatchEvent(new Event("attendance:refresh"));
  }

  function bindForm(form, handler) {
    form.addEventListener("submit", async event => {
      event.preventDefault();

      const button = form.querySelector('button[type="submit"]');
      button.disabled = true;

      try {
        await handler();
      } catch (error) {
        showStatus(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });
  }

  function bindDashboard() {
    const studentForm = document.getElementById("student-form");

    bindForm(studentForm, async () => {
      const name = document.getElementById("student-name").value.trim();
      const studentCode =
        document.getElementById("student-code").value.trim();

      if (!name || !studentCode) {
        throw new Error("Enter both the name and roll number or ID.");
      }

      const result = await api("/api/students", {
        name,
        student_code: studentCode,
        face_consent: document.getElementById("face-consent").checked
      });

      studentForm.reset();
      await updateDashboard();

      showStatus(
        result.message ||
          "Student added. The QR card is ready; collect face samples if consent has been recorded.",
        "success"
      );
    });

    bindForm(document.getElementById("manual-form"), async () => {
      const studentId =
        document.getElementById("manual-student").value;

      const reason =
        document.getElementById("manual-reason").value.trim();

      if (!studentId || reason.length < 5) {
        throw new Error(
          "Select a student and enter a reason of at least 5 characters."
        );
      }

      const result = await api("/api/attendance/manual", {
        student_id: Number(studentId),
        reason
      });

      document.getElementById("manual-reason").value = "";

      await updateDashboard();

      showStatus(
        result.message ||
          "Manual attendance recorded after teacher verification.",
        "success"
      );
    });

    document.getElementById("refresh-button").addEventListener(
      "click",
      async () => {
        try {
          await updateDashboard();
          showStatus("Dashboard refreshed.", "success");
        } catch (error) {
          showStatus(error.message, "error");
        }
      }
    );

    const trainButton = document.getElementById("train-button");

    trainButton.addEventListener("click", async () => {
      trainButton.disabled = true;
      showStatus("Training the face model. Please wait…");

      try {
        const result = await api("/api/train", {});

        await updateDashboard();

        showStatus(
          result.message ||
            "The face model is ready. You can use the live scanner.",
          "success"
        );
      } catch (error) {
        showStatus(error.message, "error");
      } finally {
        trainButton.disabled = false;
      }
    });
  }

  function cameraError(error) {
    if (
      error.name === "NotAllowedError" ||
      error.name === "SecurityError"
    ) {
      return "Camera permission denied. Allow camera access in the address bar, then press Start again. Open the page on localhost or HTTPS.";
    }

    if (
      error.name === "NotFoundError" ||
      error.name === "DevicesNotFoundError"
    ) {
      return "No webcam found. Check that a webcam is connected. Without a camera, use verified manual attendance on the dashboard.";
    }

    if (
      error.name === "NotReadableError" ||
      error.name === "TrackStartError"
    ) {
      return "Another app is using the camera. Close other camera or meeting apps, then press Start again.";
    }

    return (
      error.message ||
      "The camera could not start. Check browser permissions and the webcam."
    );
  }

  class CameraSession {
    constructor(onFrame, interval) {
      this.video = document.getElementById("camera-video");
      this.placeholder = document.getElementById("camera-placeholder");
      this.startButton = document.getElementById("camera-start");
      this.stopButton = document.getElementById("camera-stop");
      this.onFrame = onFrame;
      this.interval = interval;
      this.running = false;
      this.stream = null;
      this.timer = null;
      this.controller = null;
      this.generation = 0;
      this.pageExited = false;
      this.canvas = document.createElement("canvas");

      this.startButton.addEventListener("click", () => this.start());

      this.stopButton.addEventListener("click", () => {
        this.stop();
        showStatus("The camera is off. Press Start to resume.");
      });

      window.addEventListener("pagehide", () => {
        this.pageExited = true;
        this.stop();
      });

      window.addEventListener("beforeunload", () => {
        this.pageExited = true;
        this.stop();
      });
    }

    async start() {
      if (this.running) return;

      const startGeneration = this.generation;
      this.startButton.disabled = true;

      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error(
            "Camera access is unavailable. Open the page on localhost or HTTPS in a current version of Chrome or Edge."
          );
        }

        const acquiredStream =
          await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: "user",
              width: { ideal: 640 },
              height: { ideal: 480 }
            },
            audio: false
          });

        if (
          this.pageExited ||
          startGeneration !== this.generation
        ) {
          acquiredStream.getTracks().forEach(track => track.stop());
          return;
        }

        this.stream = acquiredStream;

        acquiredStream.getVideoTracks().forEach(track => {
          track.addEventListener("ended", () => {
            if (this.stream !== acquiredStream) return;

            this.stop();

            showStatus(
              "The camera connection ended. Check the webcam and permissions, then press Start again.",
              "warning"
            );
          });
        });

        this.video.srcObject = this.stream;
        await this.video.play();

        if (
          this.pageExited ||
          startGeneration !== this.generation
        ) {
          acquiredStream.getTracks().forEach(track => track.stop());
          return;
        }

        this.running = true;
        this.generation += 1;
        this.startedAt = Date.now();
        this.placeholder.hidden = true;
        this.stopButton.disabled = false;

        showStatus(
          page === "enroll"
            ? "The camera is on. Keep only one face in the frame; accepted samples will be saved."
            : "The camera is on. Scanning…"
        );

        this.schedule(250);
      } catch (error) {
        if (startGeneration !== this.generation) return;

        this.stop();
        showStatus(cameraError(error), "error");
      }
    }

    schedule(delay) {
      const generation = this.generation;

      if (this.running) {
        this.timer = window.setTimeout(
          () => this.frame(generation),
          delay
        );
      }
    }

    isCurrent(generation) {
      return this.running && generation === this.generation;
    }

    capture() {
      const width = this.video.videoWidth;
      const height = this.video.videoHeight;

      if (!width || !height) return null;

      const scale = Math.min(640 / width, 480 / height, 1);

      this.canvas.width = Math.max(1, Math.floor(width * scale));
      this.canvas.height = Math.max(1, Math.floor(height * scale));

      this.canvas.getContext("2d").drawImage(
        this.video,
        0,
        0,
        this.canvas.width,
        this.canvas.height
      );

      return this.canvas.toDataURL("image/jpeg", 0.75);
    }

    async frame(generation) {
      if (!this.isCurrent(generation)) return;

      const elapsed = Date.now() - this.startedAt;

      // Enrollment 2-minute limit.
      if (page === "enroll" && elapsed > 120000) {
        this.stop();

        showStatus(
          "The 2-minute limit has been reached. Only accepted samples were saved. If fewer than 20 were saved, adjust the lighting and restart enrollment.",
          "warning"
        );

        return;
      }

      // Scanner 45-minute timeout and countdown.
      if (page === "scan") {
        const timeLimit = 2700000;

        if (elapsed > timeLimit) {
          this.stop();

          showStatus(
            "Scanner paused after 45 minutes of continuous use for security and battery saving. Press Start to resume.",
            "warning"
          );

          return;
        } else {
          const timerDisplay =
            document.getElementById("time-remaining");

          if (timerDisplay) {
            const timeLeft =
              Math.floor((timeLimit - elapsed) / 1000);

            const minutes = Math.floor(timeLeft / 60)
              .toString()
              .padStart(2, "0");

            const seconds = (timeLeft % 60)
              .toString()
              .padStart(2, "0");

            timerDisplay.textContent =
              `Time left before pause: ${minutes}:${seconds}`;
          }
        }
      }

      const image = this.capture();

      if (!image) {
        this.schedule(300);
        return;
      }

      const controller = new AbortController();
      this.controller = controller;

      const timeout =
        window.setTimeout(() => controller.abort(), 25000);

      try {
        await this.onFrame(image, controller.signal, generation);
      } catch (error) {
        if (!this.isCurrent(generation)) return;

        if (error.name === "AbortError") {
          showStatus(
            "The server took too long to respond. Stop the camera and check the server.",
            "warning"
          );
        } else {
          showStatus(
            error.message,
            error.httpStatus === 400 ? "warning" : "error"
          );
        }

        if ([401, 403].includes(error.httpStatus)) {
          this.stop();
        }
      } finally {
        window.clearTimeout(timeout);

        if (this.controller === controller) {
          this.controller = null;
        }

        if (this.isCurrent(generation)) {
          this.schedule(this.interval);
        }
      }
    }

    stop() {
      this.running = false;
      this.generation += 1;

      window.clearTimeout(this.timer);
      this.controller?.abort();

      if (this.stream) {
        this.stream.getTracks().forEach(track => track.stop());
      }

      this.stream = null;
      this.video.srcObject = null;
      this.placeholder.hidden = false;
      this.startButton.disabled = false;
      this.stopButton.disabled = true;

      if (page === "scan") {
        const timerDisplay =
          document.getElementById("time-remaining");

        if (timerDisplay) {
          timerDisplay.textContent = "";
        }
      }
    }
  }

  function showScanResult(result) {
    const kind =
      result.status === "marked"
        ? "success"
        : result.status === "duplicate"
          ? "warning"
          : "";

    showStatus(result.message || "Scan complete.", kind);
  }

  async function imageFileData(file) {
    if (!file || !["image/png", "image/jpeg"].includes(file.type)) {
      throw new Error("Select a PNG or JPEG image.");
    }

    if (file.size > 5 * 1024 * 1024) {
      throw new Error("The image must be no larger than 5 MB.");
    }

    const source = URL.createObjectURL(file);

    try {
      const image = new Image();
      image.src = source;

      await image.decode();

      const scale = Math.min(
        640 / image.naturalWidth,
        480 / image.naturalHeight,
        1
      );

      const canvas = document.createElement("canvas");

      canvas.width = Math.max(
        1,
        Math.floor(image.naturalWidth * scale)
      );

      canvas.height = Math.max(
        1,
        Math.floor(image.naturalHeight * scale)
      );

      const context = canvas.getContext("2d");

      context.fillStyle = "white";
      context.fillRect(0, 0, canvas.width, canvas.height);

      context.drawImage(
        image,
        0,
        0,
        canvas.width,
        canvas.height
      );

      return canvas.toDataURL("image/jpeg", 0.75);
    } finally {
      URL.revokeObjectURL(source);
    }
  }

  function bindScanner() {
    const mode =
      document.body.dataset.mode === "qr" ? "qr" : "face";

    camera = new CameraSession(
      async (image, signal, generation) => {
        const result = await api(
          `/api/scan/${mode}`,
          { image },
          signal
        );

        if (camera.isCurrent(generation)) {
          showScanResult(result);
        }
      },
      900
    );

    if (mode === "face" && !appState.model?.ready) {
      camera.startButton.disabled = true;

      showStatus(
        "The face model is not ready. Collect student samples on the dashboard, then press Train model. The QR scanner works without face training.",
        "warning"
      );
    }

    const uploadForm =
      document.getElementById("qr-upload-form");

    if (uploadForm) {
      bindForm(uploadForm, async () => {
        camera.stop();
        showStatus("Checking the QR image…");

        const image = await imageFileData(
          document.getElementById("qr-upload").files[0]
        );

        const result =
          await api("/api/scan/qr", { image });

        showStatus(
          `${result.message || "QR check complete."}\nDemo image scan: this does not prove the person is physically present.`,
          result.status === "marked" ? "success" : "warning"
        );
      });
    }
  }

  async function bindEnrollment() {
    const studentId = document.body.dataset.studentId;

    const student = appState.students.find(
      item => String(item.id) === String(studentId)
    );

    if (!student) {
      throw new Error(
        "Student not found. Reopen the enrollment page from the dashboard."
      );
    }

    document.getElementById("enroll-name").textContent =
      `${student.name}: face samples`;

    document.getElementById("enroll-description").textContent =
      `${student.student_code} · Only this student should face the camera.`;

    const updateProgress = count => {
      document.getElementById("sample-count").textContent =
        `${count} / 25`;

      document.getElementById("sample-progress").value =
        Math.min(count, 25);
    };

    const savedCount = Number(student.face_samples || 0);
    updateProgress(savedCount);

    if (!student.active || !student.face_consent) {
      showStatus(
        "Face enrollment requires an active student with recorded face consent. QR attendance is available without face enrollment.",
        "error"
      );

      return;
    }

    camera = new CameraSession(
      async (image, signal, generation) => {
        const result = await api(
          `/api/students/${encodeURIComponent(studentId)}/face-samples`,
          { image },
          signal
        );

        if (!camera.isCurrent(generation)) return;

        const count = Number(result.count);

        if (!Number.isFinite(count)) {
          throw new Error(
            "The server did not return a sample count. Refresh the dashboard to check saved samples."
          );
        }

        updateProgress(count);

        if (count >= 25) {
          camera.stop();
          camera.startButton.disabled = true;

          showStatus(
            `${count} accepted samples saved. Press Train model on the dashboard.`,
            "success"
          );
        } else {
          showStatus(
            result.message ||
              `Sample accepted. ${count} / 25 saved.`,
            "success"
          );
        }
      },
      450
    );

    if (savedCount >= 25) {
      camera.startButton.disabled = true;

      showStatus(
        `${savedCount} samples are already saved. Train the model on the dashboard.`,
        "success"
      );
    } else {
      camera.startButton.disabled = false;
      showStatus("Consent recorded. Press Start enrollment.");
    }
  }

  function bindQr() {
    const studentId = document.body.dataset.studentId;

    const student = appState.students.find(
      item => String(item.id) === String(studentId)
    );

    if (!student || !student.active || !student.qr_ready) {
      throw new Error(
        "No active QR card found. Check the student's status or reissue the QR from the dashboard."
      );
    }

    document.getElementById("qr-name").textContent =
      student.name;

    document.getElementById("qr-code").textContent =
      student.student_code;

    document.getElementById("qr-active").textContent =
      "Private student card · Active";

    const image = document.getElementById("qr-image");

    image.addEventListener("load", () => {
      document.getElementById("print-button").disabled = false;
    });

    image.addEventListener("error", () => {
      showStatus(
        "The QR image could not load. Check your login and the student's status.",
        "error"
      );
    });

    image.src =
      `/api/students/${encodeURIComponent(studentId)}/qr.png`;

    document.getElementById("qr-card").hidden = false;

    document.getElementById("print-button").addEventListener(
      "click",
      () => window.print()
    );
  }

  const logout = document.getElementById("logout-button");

  logout?.addEventListener("click", async () => {
    camera?.stop();
    logout.disabled = true;

    try {
      await api("/logout", {});
      window.location.assign("/login");
    } catch (error) {
      showStatus(error.message, "error");
      logout.disabled = false;
    }
  });

  async function init() {
    if (page === "dashboard") {
      bindDashboard();
      await updateDashboard();
    } else {
      await loadState();

      if (page === "scan") {
        bindScanner();
      }

      if (page === "enroll") {
        await bindEnrollment();
      }

      if (page === "qr") {
        bindQr();
      }
    }
  }

  init().catch(error => showStatus(error.message, "error"));
})();