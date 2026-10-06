(() => {

  "use strict";


  const byId = (id) =>
    document.getElementById(id);


  let csrfToken = "";

  let currentSession = null;

  let cameraStream = null;

  let scanTimer = null;

  let requestRunning = false;

  let successLocked = false;


  const page =
    byId("scanner-page");


  if (!page) {
    return;
  }


  const mode =
    page.dataset.mode === "qr"
      ? "qr"
      : "face";


  const video =
    byId("scanner-video");


  const canvas =
    byId("scanner-canvas");


  const startButton =
    byId("start-camera-button");


  const stopButton =
    byId("stop-camera-button");


  /* ======================================
     API
  ====================================== */

  async function api(
    url,
    options = {}
  ) {

    const headers = {
      ...(options.headers || {})
    };


    if (
      options.method &&
      options.method !== "GET"
    ) {

      if (!csrfToken) {

        throw new Error(
          "Security token is not ready."
        );

      }


      headers["X-CSRF-Token"] =
        csrfToken;


      headers["Content-Type"] =
        "application/json";

    }


    const response =
      await fetch(
        url,
        {
          ...options,

          credentials:
            "same-origin",

          headers
        }
      );


    let data;


    try {

      data =
        await response.json();

    } catch (error) {

      throw new Error(
        "Server returned an invalid response."
      );

    }


    if (!response.ok) {

      const apiError =
        new Error(
          data.message ||
          `Request failed (${response.status}).`
        );


      apiError.data =
        data;


      apiError.status =
        response.status;


      throw apiError;

    }


    return data;

  }



  /* ======================================
     STATUS BOX
  ====================================== */

  function showStatus(
    message,
    type = "info"
  ) {

    const box =
      byId("scan-status");


    const text =
      byId("scan-status-text");


    const icon =
      byId("scan-status-icon");


    if (
      !box ||
      !text ||
      !icon
    ) {
      return;
    }


    box.className =
      `scan-result scan-result-${type}`;


    text.textContent =
      message;


    if (
      type === "success"
    ) {

      icon.textContent =
        "✓";

    } else if (
      type === "error"
    ) {

      icon.textContent =
        "×";

    } else if (
      type === "warning"
    ) {

      icon.textContent =
        "!";

    } else {

      icon.textContent =
        "•";

    }

  }



  /* ======================================
     SUCCESS INFORMATION
  ====================================== */

  function showSuccessDetails(
    data
  ) {

    const details =
      byId(
        "scan-success-details"
      );


    if (!details) {
      return;
    }


    byId(
      "success-student"
    ).textContent =
      data.name || "Student";


    byId(
      "success-subject"
    ).textContent =
      data.subject ||
      data.subject_name ||
      (
        currentSession
          ? currentSession.subject_name
          : "—"
      );


    byId(
      "success-method"
    ).textContent =
      mode === "qr"
        ? "QR"
        : "Face";


    details.hidden =
      false;

  }



  function hideSuccessDetails() {

    const details =
      byId(
        "scan-success-details"
      );


    if (details) {

      details.hidden =
        true;

    }

  }



  /* ======================================
     PAGE MODE
  ====================================== */

  function configureMode() {

    const title =
      byId(
        "scanner-title"
      );


    const heading =
      byId(
        "camera-heading"
      );


    const description =
      byId(
        "camera-description"
      );


    if (
      mode === "qr"
    ) {

      title.textContent =
        "QR Attendance Scanner";


      heading.textContent =
        "QR Camera Scanner";


      description.textContent =
        "Hold the student's QR card clearly in front of the camera.";


      byId(
        "qr-help"
      ).hidden =
        false;


      byId(
        "face-help"
      ).hidden =
        true;


    } else {

      title.textContent =
        "Face Attendance Scanner";


      heading.textContent =
        "Face Camera Scanner";


      description.textContent =
        "Keep one registered student clearly visible in front of the camera.";


      byId(
        "qr-help"
      ).hidden =
        true;


      byId(
        "face-help"
      ).hidden =
        false;

    }

  }



  /* ======================================
     CURRENT SUBJECT SESSION
  ====================================== */

  function renderSession() {

    const badge =
      byId(
        "scanner-session-badge"
      );


    const info =
      byId(
        "scanner-session-info"
      );


    if (
      !currentSession
    ) {

      badge.textContent =
        "Scanner Closed";


      info.innerHTML =
        "<strong>No active subject session.</strong><br>" +
        "Go back to the dashboard and start a subject session first.";


      startButton.disabled =
        true;


      stopCamera();


      return;

    }


    badge.textContent =
      "Scanner Active";


    info.innerHTML =
      "<strong>Subject:</strong> " +
      currentSession.subject_name +

      "<br><strong>Session ends:</strong> " +
      formatDateTime(
        currentSession.expires_at
      );


    startButton.disabled =
      false;

  }



  function formatDateTime(
    value
  ) {

    if (!value) {

      return "—";

    }


    const date =
      new Date(value);


    if (
      Number.isNaN(
        date.getTime()
      )
    ) {

      return value;

    }


    return date.toLocaleString();

  }



  async function loadState() {

    try {

      const data =
        await api(
          "/api/state"
        );


      csrfToken =
        data.csrf_token || "";


      currentSession =
        data.current_session || null;


      renderSession();


      if (
        currentSession
      ) {

        showStatus(
          `Ready to scan for ${currentSession.subject_name}.`,
          "info"
        );

      } else {

        showStatus(
          "No active subject session. Start a session from the dashboard first.",
          "error"
        );

      }


    } catch (error) {

      showStatus(
        error.message,
        "error"
      );

    }

  }



  /* ======================================
     CAMERA
  ====================================== */

  async function startCamera() {

    if (
      !currentSession
    ) {

      showStatus(
        "Start a subject attendance session first.",
        "error"
      );


      return;

    }


    if (cameraStream) {

      return;

    }


    successLocked =
      false;


    hideSuccessDetails();


    try {

      cameraStream =
        await navigator.mediaDevices.getUserMedia(
          {
            video: {
              facingMode:
                "user",

              width: {
                ideal: 1280
              },

              height: {
                ideal: 720
              }
            },

            audio:
              false
          }
        );


      video.srcObject =
        cameraStream;


      await video.play();


      startButton.disabled =
        true;


      stopButton.disabled =
        false;


      showStatus(
        mode === "qr"
          ? "Camera ready. Show the student's QR code."
          : "Camera ready. Keep one registered face in the frame.",
        "info"
      );


      beginScanning();


    } catch (error) {

      console.error(
        error
      );


      showStatus(
        "Camera could not start. Allow camera permission and try again.",
        "error"
      );

    }

  }



  function stopCamera() {

    if (
      scanTimer
    ) {

      clearInterval(
        scanTimer
      );


      scanTimer =
        null;

    }


    if (
      cameraStream
    ) {

      cameraStream
        .getTracks()
        .forEach(
          (track) =>
            track.stop()
        );


      cameraStream =
        null;

    }


    if (
      video
    ) {

      video.srcObject =
        null;

    }


    if (
      startButton
    ) {

      startButton.disabled =
        !currentSession;

    }


    if (
      stopButton
    ) {

      stopButton.disabled =
        true;

    }

  }



  /* ======================================
     CAMERA FRAME
  ====================================== */

  function captureImage() {

    if (
      !video.videoWidth ||
      !video.videoHeight
    ) {

      return null;

    }


    const maxWidth =
      960;


    const scale =
      Math.min(
        1,
        maxWidth /
        video.videoWidth
      );


    canvas.width =
      Math.round(
        video.videoWidth *
        scale
      );


    canvas.height =
      Math.round(
        video.videoHeight *
        scale
      );


    const context =
      canvas.getContext(
        "2d"
      );


    context.drawImage(
      video,
      0,
      0,
      canvas.width,
      canvas.height
    );


    return canvas.toDataURL(
      "image/jpeg",
      0.82
    );

  }



  /* ======================================
     SCANNER
  ====================================== */

  function beginScanning() {

    if (
      scanTimer
    ) {

      clearInterval(
        scanTimer
      );

    }


    scanTimer =
      window.setInterval(
        scanFrame,
        mode === "face"
          ? 900
          : 700
      );


    scanFrame();

  }



  async function scanFrame() {

    if (
      requestRunning ||
      successLocked ||
      !cameraStream ||
      !currentSession
    ) {

      return;

    }


    const image =
      captureImage();


    if (!image) {

      return;

    }


    requestRunning =
      true;


    try {

      const endpoint =
        mode === "qr"
          ? "/api/scan/qr"
          : "/api/scan/face";


      const data =
        await api(
          endpoint,
          {
            method:
              "POST",

            body:
              JSON.stringify({
                image
              })
          }
        );


      /* FACE 1/3, 2/3 */

      if (
        data.status ===
        "progress"
      ) {

        showStatus(
          data.message ||
          "Hold still...",
          "info"
        );


        return;

      }


      /* SUCCESS OR DUPLICATE */

      if (
        data.status ===
          "marked" ||
        data.status ===
          "duplicate"
      ) {

        successLocked =
          true;


        const subject =
          data.subject ||
          (
            currentSession
              ? currentSession.subject_name
              : ""
          );


        if (
          data.status ===
          "marked"
        ) {

          showStatus(
            `Attendance marked successfully for ${data.name || "student"}${subject ? ` — ${subject}` : ""}.`,
            "success"
          );

        } else {

          showStatus(
            `${data.name || "Student"} is already marked for ${subject || "this session"}.`,
            "success"
          );

        }


        showSuccessDetails(
          data
        );


        window.setTimeout(
          () => {

            successLocked =
              false;


            hideSuccessDetails();


            showStatus(
              mode === "qr"
                ? "Ready for the next QR code."
                : "Ready for the next student.",
              "info"
            );

          },
          3500
        );

      }


    } catch (error) {

      const data =
        error.data || {};


      const errorCode =
        data.error || "";


      /* NORMAL QR SEARCHING */

      if (
        mode === "qr" &&
        (
          errorCode ===
            "invalid_request" ||
          String(
            data.message || ""
          ).includes(
            "No readable QR"
          )
        )
      ) {

        showStatus(
          "No readable QR found. Move the QR closer and keep it still.",
          "warning"
        );


      /* UNKNOWN FACE */

      } else if (
        errorCode ===
        "unknown_face"
      ) {

        showStatus(
          data.message ||
          "Unknown face. Try better lighting.",
          "warning"
        );


      /* SESSION ENDED */

      } else if (
        String(
          data.message || ""
        ).toLowerCase().includes(
          "session"
        )
      ) {

        showStatus(
          data.message ||
          "Attendance session has ended.",
          "error"
        );


        currentSession =
          null;


        renderSession();


      } else {

        showStatus(
          data.message ||
          error.message ||
          "Scan failed.",
          "warning"
        );

      }


    } finally {

      requestRunning =
        false;

    }

  }



  /* ======================================
     BUTTONS
  ====================================== */

  startButton.addEventListener(
    "click",
    startCamera
  );


  stopButton.addEventListener(
    "click",
    () => {

      stopCamera();


      if (
        currentSession
      ) {

        showStatus(
          "Camera stopped.",
          "info"
        );

      }

    }
  );



  /* ======================================
     START PAGE
  ====================================== */

  configureMode();

  loadState();


  window.addEventListener(
    "beforeunload",
    stopCamera
  );


})();