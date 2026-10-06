(() => {
  "use strict";

  let csrfToken = "";
  let currentSession = null;
  let stateRequestRunning = false;
  let stateRefreshRequested = false;
  let stateGeneration = 0;
  let sessionMutationRunning = false;
  let dashboardState = null;

  const byId = (id) => document.getElementById(id);

  function renderAttendanceCounts() {
    const students = dashboardState?.students || [];

    const activeIds = new Set(
      students
        .filter((student) => student.active)
        .map((student) => String(student.id))
    );

    const selectedSubject = byId("session-subject")?.value;

    const sessionMatches =
      currentSession &&
      String(currentSession.subject_id) === selectedSubject;

    const attendance = dashboardState?.attendance_today || [];

    const presentIds = new Set(
      attendance
        .filter(
          (entry) =>
            sessionMatches &&
            String(entry.session_id) === String(currentSession.id) &&
            activeIds.has(String(entry.student_id))
        )
        .map((entry) => String(entry.student_id))
    );

    if (byId("present-count")) {
      byId("present-count").textContent = String(presentIds.size);
    }

    if (byId("absent-count")) {
      byId("absent-count").textContent = String(
        sessionMatches
          ? Math.max(0, activeIds.size - presentIds.size)
          : 0
      );
    }

    if (byId("today-label")) {
      byId("today-label").textContent = sessionMatches
        ? `${dashboardState?.today || ""} · ${currentSession.subject_name}`
        : "Select a subject and start attendance";
    }
  }

  async function api(url, options = {}) {
    const headers = {
      ...(options.headers || {})
    };

    if (options.method && options.method !== "GET") {
      if (!csrfToken) {
        throw new Error(
          "Security token is not ready. Refresh the page and try again."
        );
      }

      headers["X-CSRF-Token"] = csrfToken;
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(url, {
      ...options,
      credentials: "same-origin",
      headers
    });

    let data;

    try {
      data = await response.json();
    } catch (error) {
      throw new Error("Server returned an invalid response.");
    }

    if (!response.ok) {
      throw new Error(
        data.message || `Request failed (${response.status}).`
      );
    }

    return data;
  }

  function formatDateTime(value) {
    if (!value) return "-";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  }

  function formatTime(value) {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
  }

  function setScannerLinksEnabled(enabled) {
    const links = [
      byId("session-face-scanner"),
      byId("session-qr-scanner")
    ];

    links.forEach((link) => {
      if (!link) return;

      link.style.pointerEvents = enabled ? "auto" : "none";
      link.style.opacity = enabled ? "1" : "0.5";

      link.setAttribute(
        "aria-disabled",
        enabled ? "false" : "true"
      );
    });
  }

  function updateTimer() {
    const timer = byId("session-timer");

    if (!timer) return;

    if (!currentSession) {
      timer.textContent = "--:--";
      return;
    }

    const endTime = new Date(
      currentSession.expires_at
    ).getTime();

    if (Number.isNaN(endTime)) {
      timer.textContent = "--:--";
      return;
    }

    const remaining = Math.max(
      0,
      Math.floor((endTime - Date.now()) / 1000)
    );

    const minutes = String(
      Math.floor(remaining / 60)
    ).padStart(2, "0");

    const seconds = String(
      remaining % 60
    ).padStart(2, "0");

    timer.textContent = `${minutes}:${seconds}`;

    if (remaining <= 0) {
      currentSession = null;

      renderSession();
      renderAttendanceCounts();

      window.setTimeout(loadState, 500);
    }
  }

  function renderSession() {
    const badge = byId("session-badge");
    const info = byId("session-information");
    const startButton = byId("start-session-button");
    const endButton = byId("end-session-button");
    const subjectSelect = byId("session-subject");

    if (
      !badge ||
      !info ||
      !startButton ||
      !endButton ||
      !subjectSelect
    ) {
      return;
    }

    if (!currentSession) {
      badge.textContent = "Scanner Closed";

      info.textContent =
        "No active attendance session. Select a subject and start a 1-hour session.";

      startButton.disabled = false;
      endButton.disabled = true;
      subjectSelect.disabled = false;

      setScannerLinksEnabled(false);
      updateTimer();

      return;
    }

    badge.textContent = "Scanner Active";

    info.innerHTML =
      "<strong>Subject:</strong> " +
      currentSession.subject_name +
      "<br><strong>Started:</strong> " +
      formatDateTime(currentSession.started_at) +
      "<br><strong>Ends:</strong> " +
      formatDateTime(currentSession.expires_at);

    startButton.disabled = true;
    endButton.disabled = false;
    subjectSelect.disabled = true;

    if (currentSession.subject_id) {
      subjectSelect.value = String(
        currentSession.subject_id
      );
    }

    setScannerLinksEnabled(true);
    updateTimer();
  }

  function populateSubjects(subjects) {
    const select = byId("session-subject");

    if (!select) return;

    const previous = select.value;

    select.innerHTML = "";

    if (
      !Array.isArray(subjects) ||
      subjects.length === 0
    ) {
      const option = document.createElement("option");

      option.value = "";
      option.textContent = "No subjects available";

      select.appendChild(option);
      return;
    }

    subjects.forEach((subject) => {
      const option = document.createElement("option");

      option.value = String(subject.id);
      option.textContent = subject.name;

      select.appendChild(option);
    });

    if (previous) {
      select.value = previous;
    }
  }

  function renderAttendance(attendance) {
    const body = byId("attendance-body");

    if (!body) return;

    body.innerHTML = "";

    if (
      !Array.isArray(attendance) ||
      attendance.length === 0
    ) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");

      cell.colSpan = 5;
      cell.className = "empty";

      cell.textContent =
        "No attendance recorded today. Start a subject session and use Face, QR or Manual attendance.";

      row.appendChild(cell);
      body.appendChild(row);

      return;
    }

    attendance.forEach((entry) => {
      const row = document.createElement("tr");

      // Student.
      const studentCell = document.createElement("td");
      const studentName = document.createElement("strong");

      studentName.textContent = entry.name || "Unknown";

      const br = document.createElement("br");
      const studentCode = document.createElement("small");

      studentCode.textContent = entry.student_code || "";

      studentCell.appendChild(studentName);
      studentCell.appendChild(br);
      studentCell.appendChild(studentCode);

      // Subject.
      const subjectCell = document.createElement("td");
      const subjectName = document.createElement("strong");

      subjectName.textContent = entry.subject_name || "—";
      subjectCell.appendChild(subjectName);

      // Time.
      const timeCell = document.createElement("td");

      timeCell.textContent = formatTime(entry.marked_at);

      // Method.
      const methodCell = document.createElement("td");
      const methodBadge = document.createElement("span");

      methodBadge.className = "badge";

      methodBadge.textContent = String(
        entry.method || ""
      ).toUpperCase();

      methodCell.appendChild(methodBadge);

      // Correction.
      const correctionCell = document.createElement("td");
      const voidButton = document.createElement("button");

      voidButton.type = "button";
      voidButton.className = "danger small";
      voidButton.textContent = "Void entry";
      voidButton.dataset.subjectVoid = String(entry.id);

      correctionCell.appendChild(voidButton);

      row.appendChild(studentCell);
      row.appendChild(subjectCell);
      row.appendChild(timeCell);
      row.appendChild(methodCell);
      row.appendChild(correctionCell);

      body.appendChild(row);
    });
  }

  async function loadState() {
    if (stateRequestRunning || sessionMutationRunning) {
      stateRefreshRequested = true;
      return;
    }

    stateRequestRunning = true;
    stateRefreshRequested = false;

    const generation = stateGeneration;

    try {
      const data = await api("/api/state");

      // Ignore responses started before a subject/session change.
      if (
        generation !== stateGeneration ||
        sessionMutationRunning
      ) {
        stateRefreshRequested = true;
        return;
      }

      csrfToken = data.csrf_token || "";

      if (!Array.isArray(data.subjects)) {
        throw new Error(
          'Backend response does not contain "subjects".'
        );
      }

      populateSubjects(data.subjects);

      currentSession = data.current_session || null;
      dashboardState = data;

      renderSession();
      renderAttendanceCounts();

      // Keep previous lectures in today's attendance register.
      renderAttendance(data.attendance_today || []);
    } catch (error) {
      if (
        generation !== stateGeneration ||
        sessionMutationRunning
      ) {
        return;
      }

      console.error(
        "Dashboard session load failed:",
        error
      );

      const info = byId("session-information");

      if (info) {
        info.textContent = error.message;
      }

      setScannerLinksEnabled(false);
    } finally {
      stateRequestRunning = false;

      if (
        stateRefreshRequested &&
        !sessionMutationRunning
      ) {
        loadState();
      }
    }
  }

  async function startSession() {
    if (sessionMutationRunning) return;

    const select = byId("session-subject");
    const subjectId = Number(select.value);

    if (
      !Number.isInteger(subjectId) ||
      subjectId <= 0
    ) {
      alert("Please select a subject.");
      return;
    }

    sessionMutationRunning = true;
    stateGeneration += 1;

    byId("start-session-button").disabled = true;
    byId("end-session-button").disabled = true;

    try {
      const data = await api(
        "/api/sessions/start",
        {
          method: "POST",
          body: JSON.stringify({
            subject_id: subjectId
          })
        }
      );

      currentSession = data.current_session;

      renderSession();
      renderAttendanceCounts();

      if (data.message) {
        alert(data.message);
      }
    } catch (error) {
      alert(error.message);
    } finally {
      sessionMutationRunning = false;

      renderSession();
      await loadState();
    }
  }

  async function endSession() {
    if (
      !currentSession ||
      sessionMutationRunning
    ) {
      return;
    }

    sessionMutationRunning = true;
    stateGeneration += 1;

    byId("start-session-button").disabled = true;
    byId("end-session-button").disabled = true;

    try {
      const data = await api(
        `/api/sessions/${currentSession.id}/end`,
        {
          method: "POST",
          body: JSON.stringify({})
        }
      );

      currentSession = null;

      renderSession();
      renderAttendanceCounts();

      if (data.message) {
        alert(data.message);
      }
    } catch (error) {
      alert(error.message);
    } finally {
      sessionMutationRunning = false;

      renderSession();
      await loadState();
    }
  }

  async function voidAttendance(attendanceId) {
    const reason = window.prompt(
      "Reason for voiding this attendance entry (minimum 5 characters):"
    );

    if (reason === null) return;

    if (reason.trim().length < 5) {
      alert("Reason must contain at least 5 characters.");
      return;
    }

    try {
      const data = await api(
        `/api/attendance/${attendanceId}/void`,
        {
          method: "POST",
          body: JSON.stringify({
            reason: reason.trim()
          })
        }
      );

      if (data.message) {
        alert(data.message);
      }

      await loadState();
    } catch (error) {
      alert(error.message);
    }
  }

  function init() {
    byId("session-subject")?.addEventListener(
      "change",
      () => {
        stateGeneration += 1;

        renderAttendanceCounts();
        loadState();
      }
    );

    // Refresh after manual attendance or student changes in app.js.
    window.addEventListener(
      "attendance:refresh",
      loadState
    );

    const startButton = byId("start-session-button");
    const endButton = byId("end-session-button");

    if (startButton) {
      startButton.addEventListener(
        "click",
        startSession
      );
    }

    if (endButton) {
      endButton.addEventListener(
        "click",
        endSession
      );
    }

    const attendanceBody = byId("attendance-body");

    if (attendanceBody) {
      attendanceBody.addEventListener(
        "click",
        (event) => {
          const button = event.target.closest(
            "[data-subject-void]"
          );

          if (!button) return;

          const attendanceId = Number(
            button.dataset.subjectVoid
          );

          if (
            Number.isInteger(attendanceId) &&
            attendanceId > 0
          ) {
            voidAttendance(attendanceId);
          }
        }
      );
    }

    const refreshButton = byId("refresh-button");

    if (refreshButton) {
      refreshButton.addEventListener(
        "click",
        () => {
          window.setTimeout(loadState, 250);
        }
      );
    }

    setScannerLinksEnabled(false);
    loadState();

    // Update the session timer every second.
    window.setInterval(updateTimer, 1000);

    // Update attendance counts every five seconds.
    window.setInterval(loadState, 5000);

    window.addEventListener("focus", loadState);

    document.addEventListener(
      "visibilitychange",
      () => {
        if (document.visibilityState === "visible") {
          loadState();
        }
      }
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      init
    );
  } else {
    init();
  }
})();