function byId(id) {
  return document.getElementById(id);
}

function setHidden(element, hidden) {
  if (element) element.hidden = hidden;
}

function mountVoiceRecorder() {
  const start = byId("voice-start");
  if (!start) return () => {};
  const stop = byId("voice-stop");
  const discard = byId("voice-discard");
  const download = byId("voice-download");
  const preview = byId("voice-preview");
  const timer = byId("voice-timer");
  const status = byId("voice-status");
  let recorder;
  let stream;
  let chunks = [];
  let objectUrl;
  let timerId;
  let startedAt = 0;

  const updateTimer = () => {
    const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    timer.textContent = String(Math.floor(elapsed / 60)).padStart(2, "0") + ":" + String(elapsed % 60).padStart(2, "0");
  };
  const clearDownload = () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
    download.removeAttribute("href");
    setHidden(download, true);
    preview.removeAttribute("src");
    setHidden(preview, true);
  };
  const stopStream = () => {
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
  };
  const reset = (message = "Select Start recording when you are ready.") => {
    clearInterval(timerId);
    timerId = null;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    recorder = null;
    stopStream();
    chunks = [];
    timer.textContent = "00:00";
    start.disabled = false;
    stop.disabled = true;
    discard.disabled = true;
    status.textContent = message;
  };

  start.onclick = async () => {
    clearDownload();
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      status.textContent = "Voice recording is not supported by this browser.";
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunks = [];
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        if (!chunks.length) return;
        const blob = new Blob(chunks, { type: recorder?.mimeType || "audio/webm" });
        objectUrl = URL.createObjectURL(blob);
        download.href = objectUrl;
        setHidden(download, false);
        preview.src = objectUrl;
        setHidden(preview, false);
        status.textContent = "Recording ready. Download it before leaving this page.";
        discard.disabled = false;
      };
      recorder.start();
      startedAt = Date.now();
      timerId = setInterval(updateTimer, 500);
      start.disabled = true;
      stop.disabled = false;
      discard.disabled = true;
      status.textContent = "Recording…";
    } catch (error) {
      stopStream();
      status.textContent = error.name === "NotAllowedError" ? "Microphone access was declined." : "Could not start the microphone.";
    }
  };
  stop.onclick = () => {
    if (!recorder || recorder.state === "inactive") return;
    recorder.stop();
    clearInterval(timerId);
    timerId = null;
    stopStream();
    start.disabled = false;
    stop.disabled = true;
    discard.disabled = false;
  };
  discard.onclick = () => { clearDownload(); reset("Recording discarded. Nothing was saved."); };
  const cleanup = () => {
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.ondataavailable = null;
      recorder.stop();
    }
    recorder = null;
    stopStream();
    clearDownload();
  };
  document.addEventListener("student-entertainment-change", event => {
    if (event.detail?.panel !== "voice") cleanup();
  });
  window.addEventListener("pagehide", cleanup, { once: true });
  return cleanup;
}

function mountPhotoBooth() {
  const start = byId("photo-start");
  if (!start) return () => {};
  const take = byId("photo-take");
  const retake = byId("photo-retake");
  const download = byId("photo-download");
  const video = byId("photo-video");
  const canvas = byId("photo-canvas");
  const placeholder = byId("photo-placeholder");
  const status = byId("photo-status");
  let stream;
  let objectUrl;

  const stopCamera = () => {
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
    video.srcObject = null;
    take.disabled = true;
    start.disabled = false;
  };
  const clearPhoto = () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
    download.removeAttribute("href");
    setHidden(download, true);
    setHidden(canvas, true);
  };
  const reset = (message = "Your camera is off.") => {
    stopCamera();
    clearPhoto();
    setHidden(video, true);
    setHidden(placeholder, false);
    retake.disabled = true;
    status.textContent = message;
  };
  start.onclick = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      status.textContent = "Camera access is not supported by this browser.";
      return;
    }
    try {
      clearPhoto();
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
      video.srcObject = stream;
      setHidden(video, false);
      setHidden(placeholder, true);
      start.disabled = true;
      take.disabled = false;
      retake.disabled = true;
      status.textContent = "Camera ready. Take a photo when you are ready.";
    } catch (error) {
      status.textContent = error.name === "NotAllowedError" ? "Camera access was declined." : "Could not start the camera.";
    }
  };
  take.onclick = () => {
    if (!stream || !video.videoWidth) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => {
      if (!blob) return;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = URL.createObjectURL(blob);
      download.href = objectUrl;
      setHidden(download, false);
      setHidden(canvas, false);
      stopCamera();
      setHidden(video, true);
      retake.disabled = false;
      status.textContent = "Photo ready. Download it before leaving this page.";
    }, "image/png");
  };
  retake.onclick = () => start.click();
  const cleanup = () => { stopCamera(); clearPhoto(); };
  document.addEventListener("student-entertainment-change", event => {
    if (event.detail?.panel !== "photo") cleanup();
  });
  window.addEventListener("pagehide", cleanup, { once: true });
  return cleanup;
}

export function mountEntertainmentMedia() {
  const cleanupVoice = mountVoiceRecorder();
  const cleanupPhoto = mountPhotoBooth();
  return () => { cleanupVoice(); cleanupPhoto(); };
}

export function mountEntertainment() {
  const tabs = [...document.querySelectorAll("[data-entertainment-tab]")];
  if (!tabs.length) return;
  const mediaCleanup = mountEntertainmentMedia();
  const panels = tabs.map(tab => document.getElementById(tab.getAttribute("aria-controls")));
  const allowed = new Set(tabs.map(tab => tab.dataset.entertainmentTab));
  const requested = location.hash.slice(1);
  let active = allowed.has(requested) ? requested : "draw";

  function select(name, updateHash = true) {
    active = allowed.has(name) ? name : "games";
    tabs.forEach((tab, index) => {
      const selected = tab.dataset.entertainmentTab === active;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      panels[index].hidden = !selected;
    });
    document.dispatchEvent(new CustomEvent("student-entertainment-change", { detail: { panel: active } }));
    if (updateHash) history.replaceState(null, "", location.pathname + location.search + "#" + active);
  }
  tabs.forEach((tab, index) => {
    tab.onclick = () => select(tab.dataset.entertainmentTab);
    tab.onkeydown = event => {
      let next;
      if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
      if (event.key === "ArrowLeft") next = tabs[(index + tabs.length - 1) % tabs.length];
      if (event.key === "Home") next = tabs[0];
      if (event.key === "End") next = tabs.at(-1);
      if (next) {
        event.preventDefault();
        select(next.dataset.entertainmentTab);
        next.focus();
      }
    };
  });
  select(active, false);
  window.addEventListener("pagehide", mediaCleanup, { once: true });
}
