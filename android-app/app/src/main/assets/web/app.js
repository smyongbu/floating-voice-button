(() => {
  "use strict";

  const native = window.NativeApp;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const state = {
    recognition: {
      active: false,
      capturing: false,
      phase: "idle",
      status: "正在检查本地模型…",
      text: ""
    },
    settings: {
      engine: "local_dual",
      overlayEnabled: false,
      overlayTextEnabled: true,
      overlayOpacity: 72,
      overlaySize: 64,
      overlayPermission: false,
      microphonePermission: false
    },
    resources: [],
    history: [],
    version: "",
    page: "recording",
    engineMode: null,
    historyQuery: "",
    historyVisibleCount: 40
  };

  const elements = {
    pages: [...document.querySelectorAll(".page")],
    navItems: [...document.querySelectorAll(".nav-item")],
    statusText: document.getElementById("statusText"),
    recordButton: document.getElementById("recordButton"),
    recordButtonText: document.getElementById("recordButtonText"),
    cancelButton: document.getElementById("cancelButton"),
    transcriptText: document.getElementById("transcriptText"),
    recognitionAnnouncement: document.getElementById("recognitionAnnouncement"),
    copyTranscriptButton: document.getElementById("copyTranscriptButton"),
    resourceNotice: document.getElementById("resourceNotice"),
    activeModelsButton: document.getElementById("activeModelsButton"),
    activeModelsTitle: document.getElementById("activeModelsTitle"),
    activeModelsDetail: document.getElementById("activeModelsDetail"),
    historyCount: document.getElementById("historyCount"),
    historySearch: document.getElementById("historySearch"),
    copyAllHistoryButton: document.getElementById("copyAllHistoryButton"),
    historyEmpty: document.getElementById("historyEmpty"),
    historyList: document.getElementById("historyList"),
    loadMoreHistory: document.getElementById("loadMoreHistory"),
    clearHistoryButton: document.getElementById("clearHistoryButton"),
    engineInputs: [...document.querySelectorAll('input[name="engine"]')],
    engineModeButtons: [...document.querySelectorAll(".engine-mode-switch [data-engine-mode]")],
    engineCards: [...document.querySelectorAll(".engine-card[data-engine-mode]")],
    resourceList: document.getElementById("resourceList"),
    resourceAnnouncement: document.getElementById("resourceAnnouncement"),
    overlaySwitch: document.getElementById("overlaySwitch"),
    overlayStatus: document.getElementById("overlayStatus"),
    overlayTextSwitch: document.getElementById("overlayTextSwitch"),
    overlayOpacity: document.getElementById("overlayOpacity"),
    overlayOpacityValue: document.getElementById("overlayOpacityValue"),
    overlaySize: document.getElementById("overlaySize"),
    overlaySizeValue: document.getElementById("overlaySizeValue"),
    overlayPreview: document.getElementById("overlayPreview"),
    overlayPreviewText: document.getElementById("overlayPreviewText"),
    overlayPreviewOrb: document.getElementById("overlayPreviewOrb"),
    overlayWaveform: document.getElementById("overlayWaveform"),
    overlayWaveFront: document.getElementById("overlayWaveFront"),
    overlayWaveMiddle: document.getElementById("overlayWaveMiddle"),
    overlayWaveBack: document.getElementById("overlayWaveBack"),
    copyDiagnosticsButton: document.getElementById("copyDiagnosticsButton"),
    versionText: document.getElementById("versionText"),
    confirmDialog: document.getElementById("confirmDialog"),
    confirmMessage: document.getElementById("confirmMessage"),
    confirmCancel: document.getElementById("confirmCancel"),
    confirmAccept: document.getElementById("confirmAccept"),
    toast: document.getElementById("toast"),
    waveShell: document.getElementById("waveShell"),
    waveFront: document.getElementById("waveFront"),
    waveMiddle: document.getElementById("waveMiddle"),
    waveBack: document.getElementById("waveBack")
  };

  let confirmAction = null;
  let confirmReturnFocus = null;
  let toastTimer = 0;
  let previousRecognitionActive = false;
  let previewRecordingTimer = 0;
  let previewLevelTimer = 0;
  let overlayPreviewRecording = false;
  const resourceCards = new Map();

  function buildSmoothWavePath(width, centerY, amplitude, cycles, phase, count = 48) {
    const points = [];
    for (let index = 0; index <= count; index += 1) {
      const ratio = index / count;
      const envelope = Math.pow(Math.sin(Math.PI * ratio), 1.65);
      const harmonic = Math.sin(ratio * Math.PI * 2 * cycles + phase);
      const detail = Math.sin(ratio * Math.PI * 2 * (cycles * 1.9) - phase * 0.6) * 0.17;
      points.push({
        x: ratio * width,
        y: centerY + (harmonic + detail) * amplitude * envelope
      });
    }
    let path = `M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
    for (let index = 1; index < points.length - 1; index += 1) {
      const current = points[index];
      const next = points[index + 1];
      const midX = (current.x + next.x) / 2;
      const midY = (current.y + next.y) / 2;
      path += ` Q${current.x.toFixed(1)} ${current.y.toFixed(1)} ${midX.toFixed(1)} ${midY.toFixed(1)}`;
    }
    const last = points[points.length - 1];
    return `${path} L${last.x.toFixed(1)} ${last.y.toFixed(1)}`;
  }

  class SmoothWaveform {
    constructor() {
      this.active = false;
      this.target = 0;
      this.level = 0;
      this.phase = 0;
      this.frame = 0;
      this.lastTime = 0;
      this.render();
    }

    setActive(active) {
      this.active = active;
      elements.waveShell.dataset.active = String(active);
      if (!active) this.target = 0;
      if (reducedMotion.matches || !this.isVisible()) {
        this.level = active ? Math.max(this.level, 0.08) : 0;
        this.render();
        this.stopIfIdle();
      } else {
        this.start();
      }
    }

    setLevel(raw) {
      const normalized = Math.max(0, Math.min(1, Number(raw) || 0));
      this.target = this.active ? Math.min(1, Math.sqrt(normalized) * 0.92 + 0.035) : 0;
      if (reducedMotion.matches) {
        this.level += (this.target - this.level) * 0.55;
        this.render();
      } else if (this.isVisible()) {
        this.start();
      }
    }

    isVisible() {
      return state.page === "recording" && !document.hidden;
    }

    refreshVisibility() {
      if (this.isVisible() && !reducedMotion.matches) this.start();
      else if (this.frame) {
        cancelAnimationFrame(this.frame);
        this.frame = 0;
      }
    }

    start() {
      if (this.frame || !this.isVisible()) return;
      this.lastTime = performance.now();
      this.frame = requestAnimationFrame((time) => this.tick(time));
    }

    tick(time) {
      if (!this.isVisible()) {
        this.frame = 0;
        return;
      }
      const delta = Math.min(40, Math.max(0, time - this.lastTime));
      this.lastTime = time;
      this.level += (this.target - this.level) * (this.active ? 0.16 : 0.11);
      if (this.active) this.phase += delta * (0.00155 + this.level * 0.0011);
      this.render();
      if (this.active || Math.abs(this.level - this.target) > 0.003) {
        this.frame = requestAnimationFrame((next) => this.tick(next));
      } else {
        this.stopIfIdle();
      }
    }

    stopIfIdle() {
      if (this.frame) cancelAnimationFrame(this.frame);
      this.frame = 0;
      if (!this.active) {
        this.level = 0;
        this.render();
      }
    }

    render() {
      const baseAmplitude = this.active ? 3 : 1.2;
      const amplitude = baseAmplitude + this.level * 33;
      elements.waveBack.setAttribute("d", this.path(amplitude * 0.43, 2.9, -this.phase * 0.82));
      elements.waveMiddle.setAttribute("d", this.path(amplitude * 0.68, 1.82, this.phase * 0.64 + 0.7));
      elements.waveFront.setAttribute("d", this.path(amplitude, 2.25, this.phase));
    }

    path(amplitude, cycles, phase) {
      return buildSmoothWavePath(360, 56, amplitude, cycles, phase);
    }
  }

  class CompactWaveform {
    constructor() {
      this.active = false;
      this.target = 0.08;
      this.level = 0.08;
      this.targetSpeed = 0.012;
      this.speed = 0.012;
      this.phase = 0;
      this.frame = 0;
      this.lastTime = 0;
      this.lastLevelAt = 0;
      elements.overlayWaveform.dataset.active = "false";
      elements.overlayWaveform.dataset.motion = "paused";
      this.render();
    }

    setActive(active) {
      this.active = active;
      elements.overlayWaveform.dataset.active = String(active);
      this.target = active ? 0.42 : 0.08;
      this.level = active ? 0.42 : 0.08;
      this.targetSpeed = active ? 0.065 : 0.012;
      this.speed = active ? 0.065 : 0.012;
      this.lastLevelAt = active ? performance.now() : 0;
      if (reducedMotion.matches || !this.isVisible()) {
        if (this.frame) cancelAnimationFrame(this.frame);
        this.frame = 0;
        this.level = active ? 0.42 : 0.08;
        this.render();
        this.updateMotionState();
        return;
      }
      this.start();
    }

    setLevel(raw) {
      const normalized = Math.max(0, Math.min(1, Number(raw) || 0));
      if (!this.active) return;
      const now = performance.now();
      const voice = Math.pow(normalized, 0.65);
      const brightness = 0.5 + Math.sin(now * 0.0037) * 0.18;
      this.target = 0.1 + 0.78 * voice;
      this.targetSpeed = 0.045 + 0.055 * voice + 0.035 * brightness * voice;
      this.lastLevelAt = now;
      if (reducedMotion.matches || !this.isVisible()) return;
      this.start();
    }

    isVisible() {
      return state.page === "settings" && !document.hidden;
    }

    updateMotionState() {
      elements.overlayWaveform.dataset.motion = this.frame ? "running" : "paused";
    }

    refreshVisibility() {
      if (this.isVisible() && !reducedMotion.matches) {
        this.start();
      } else {
        if (this.frame) cancelAnimationFrame(this.frame);
        this.frame = 0;
        this.render();
        this.updateMotionState();
      }
    }

    refreshMotionPreference() {
      if (reducedMotion.matches) {
        if (this.frame) cancelAnimationFrame(this.frame);
        this.frame = 0;
        this.level = this.active ? 0.42 : 0.08;
        this.render();
        this.updateMotionState();
        return;
      }
      this.refreshVisibility();
    }

    start() {
      if (this.frame || !this.isVisible() || reducedMotion.matches) {
        this.updateMotionState();
        return;
      }
      this.lastTime = performance.now();
      this.frame = requestAnimationFrame((time) => this.tick(time));
      this.updateMotionState();
    }

    tick(time) {
      if (!this.isVisible() || reducedMotion.matches) {
        this.frame = 0;
        this.updateMotionState();
        return;
      }
      const delta = Math.min(40, Math.max(0, time - this.lastTime));
      this.lastTime = time;
      if (this.active) {
        if (time - this.lastLevelAt > 420) {
          const voice = Math.max(0, Math.min(1, 0.5 + Math.sin(time * 0.0058) * 0.28 + Math.sin(time * 0.0091 + 1.2) * 0.18));
          const brightness = 0.5 + Math.sin(time * 0.0037 + 0.8) * 0.18;
          this.target = 0.1 + 0.78 * voice;
          this.targetSpeed = 0.045 + 0.055 * voice + 0.035 * brightness * voice;
        }
        const elapsedSeconds = delta / 1000;
        const timeConstant = this.target > this.level ? 0.045 : 0.22;
        const smoothing = 1 - Math.exp(-elapsedSeconds / timeConstant);
        const speedSmoothing = 1 - Math.exp(-elapsedSeconds / 0.14);
        this.level += (this.target - this.level) * smoothing;
        this.speed += (this.targetSpeed - this.speed) * speedSmoothing;
      } else {
        this.target = 0.08;
        this.level = 0.08;
        this.targetSpeed = 0.012;
        this.speed = 0.012;
      }
      this.phase += delta * (0.0022 + this.speed * 0.0255);
      this.render();
      this.frame = requestAnimationFrame((next) => this.tick(next));
    }

    render() {
      const amplitude = 2 + this.level * 18.5;
      elements.overlayWaveBack.setAttribute("d", buildSmoothWavePath(120, 36, amplitude * 0.43, 2.9, -this.phase * 0.82, 36));
      elements.overlayWaveMiddle.setAttribute("d", buildSmoothWavePath(120, 36, amplitude * 0.68, 1.82, this.phase * 0.64 + 0.7, 36));
      elements.overlayWaveFront.setAttribute("d", buildSmoothWavePath(120, 36, amplitude, 2.25, this.phase, 36));
    }
  }

  const waveform = new SmoothWaveform();
  const overlayWaveform = new CompactWaveform();

  function callNative(method, ...args) {
    if (!native || typeof native[method] !== "function") {
      return runPreviewAction(method, args);
    }
    try {
      return native[method](...args);
    } catch (_) {
      showToast("操作没有完成，请重试。")
      return undefined;
    }
  }

  function runPreviewAction(method, args) {
    const resourceById = (id) => state.resources.find((item) => item.id === id);
    if (["ready", "setCurrentPage"].includes(method)) return undefined;
    if (method === "setEngine") {
      state.settings.engine = String(args[0] || "local_dual");
      renderSettings();
      renderRecognition();
      showToast("预览：识别方案已切换");
      return undefined;
    }
    if (method === "toggleRecognition") {
      if (state.recognition.active) {
        window.clearTimeout(previewRecordingTimer);
        window.clearInterval(previewLevelTimer);
        state.recognition = { active: true, capturing: false, phase: "processing", status: "正在使用所选模型校正文字…", text: state.recognition.text };
        renderRecognition();
        previewRecordingTimer = window.setTimeout(() => {
          state.recognition = { active: false, capturing: false, phase: "idle", status: "识别完成", text: "你好，这是独立网页预览生成的中英文 mixed speech 示例。" };
          state.history.unshift({ id: Date.now(), text: state.recognition.text, createdAt: new Date().toISOString().replace("T", " ").slice(0, 19), engine: state.settings.engine });
          renderAll();
        }, 1100);
      } else {
        state.recognition = { active: true, capturing: false, phase: "preparing", status: "正在准备本地模型…", text: "" };
        renderRecognition();
        previewRecordingTimer = window.setTimeout(() => {
          state.recognition = { active: true, capturing: true, phase: "listening", status: "正在本地实时识别…", text: "你好，这是独立网页预览" };
          renderRecognition();
          previewLevelTimer = window.setInterval(() => waveform.setLevel(0.12 + Math.random() * 0.75), 110);
        }, 650);
      }
      return undefined;
    }
    if (method === "cancelRecognition") {
      window.clearTimeout(previewRecordingTimer);
      window.clearInterval(previewLevelTimer);
      state.recognition = { active: false, capturing: false, phase: "idle", status: "本次识别已取消", text: "" };
      renderRecognition();
      return undefined;
    }
    if (method === "downloadResource") {
      const resource = resourceById(String(args[0]));
      if (!resource) return undefined;
      resource.status = "downloading";
      resource.presentBytes = Math.max(resource.presentBytes, Math.round(resource.totalBytes * 0.36));
      resource.speedBytesPerSecond = 5242880;
      resource.etaSeconds = Math.round((resource.totalBytes - resource.presentBytes) / resource.speedBytesPerSecond);
      renderResources();
      showToast("预览：已模拟开始下载");
      return undefined;
    }
    if (method === "pauseResource") {
      const resource = resourceById(String(args[0]));
      if (resource) { resource.status = "paused"; resource.speedBytesPerSecond = 0; renderResources(); }
      return undefined;
    }
    if (method === "verifyResource") { showToast("预览：模型校验通过"); return undefined; }
    if (method === "deleteResource") {
      const resource = resourceById(String(args[0]));
      if (resource) { resource.status = "missing"; resource.presentBytes = 0; resource.installedBytes = 0; renderResources(); renderRecognition(); }
      return undefined;
    }
    if (method === "deleteHistory") {
      state.history = state.history.filter((item) => Number(item.id) !== Number(args[0]));
      renderHistory();
      return undefined;
    }
    if (method === "clearHistory") { state.history = []; renderHistory(); return undefined; }
    if (method === "copyText" || method === "copyHistory" || method === "copyAllHistory" || method === "copyDiagnostics") { showToast("预览：已模拟复制"); return undefined; }
    if (method === "setOverlayEnabled") { state.settings.overlayEnabled = Boolean(args[0]); state.settings.overlayPermission = true; renderSettings(); return undefined; }
    if (method === "setOverlayTextEnabled") { state.settings.overlayTextEnabled = Boolean(args[0]); renderSettings(); return undefined; }
    if (method === "setOverlayOpacity") { state.settings.overlayOpacity = Number(args[0]); renderSettings(); return undefined; }
    if (method === "setOverlaySize") { state.settings.overlaySize = Number(args[0]); renderSettings(); return undefined; }
    showToast("当前操作仅在正式 App 中生效");
    return undefined;
  }

  function loadInitialState() {
    if (native && typeof native.getInitialState === "function") {
      try {
        return JSON.parse(native.getInitialState());
      } catch (_) {
        return null;
      }
    }
    return {
      recognition: { active: false, capturing: false, phase: "idle", status: "双语实时与整段校正模型已就绪", text: "" },
      settings: state.settings,
      resources: [
        { id: "zipformer-bilingual", name: "Zipformer｜中英双语实时模型", purpose: "边说边显示中文、英文和中英混说结果", version: "2024-03-20-exp32-int8", totalBytes: 60142871, presentBytes: 60142871, installedBytes: 60142871, status: "available", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 11717148672, errorMessage: "" },
        { id: "paraformer", name: "Paraformer｜中英双语整段校正模型", purpose: "停止后重新校正完整句子，改善长句连贯度", version: "2024-03-09-small-int8", totalBytes: 81904027, presentBytes: 81904027, installedBytes: 81904027, status: "available", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 11717148672, errorMessage: "" },
        { id: "qwen3-asr-0.6b-int8", name: "Qwen3-ASR 0.6B INT8 高质量校正模型", purpose: "停止后高质量校正中英文和中英混说；下载较大、处理较慢", version: "2026-03-25-int8", totalBytes: 987015347, presentBytes: 0, installedBytes: 0, status: "missing", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 0, errorMessage: "" }
      ],
      history: [
        { id: 3, text: "你好，今天测试一下中文和 English 混合识别。", createdAt: "2026-08-18 18:42:00", engine: "local_dual" },
        { id: 2, text: "Please create a new note and copy this sentence.", createdAt: "2026-08-18 17:16:00", engine: "local_dual_qwen" },
        { id: 1, text: "这是一条较长的模拟历史记录，用于检查卡片换行、复制按钮和删除按钮在窄屏幕上的排版。", createdAt: "2026-08-18 16:03:00", engine: "local_zipformer" }
      ],
      version: "独立 UI 预览"
    };
  }

  function applyFullState(next) {
    if (!next) return;
    if (next.recognition) state.recognition = next.recognition;
    if (next.settings) state.settings = next.settings;
    if (Array.isArray(next.resources)) state.resources = next.resources;
    if (Array.isArray(next.history)) state.history = next.history;
    if (typeof next.version === "string") state.version = next.version;
    renderAll();
    if (["recording", "history", "settings"].includes(next.page) && next.page !== state.page) {
      navigate(next.page);
    }
  }

  function receive(payload) {
    let event;
    try {
      event = typeof payload === "string" ? JSON.parse(payload) : payload;
    } catch (_) {
      return;
    }
    if (!event || typeof event.type !== "string") return;
    switch (event.type) {
      case "fullState":
        applyFullState(event.state);
        break;
      case "recognition":
        state.recognition = event.recognition || state.recognition;
        renderRecognition();
        break;
      case "audioLevel":
        waveform.setLevel(event.level);
        overlayWaveform.setLevel(event.level);
        break;
      case "history": {
        const previousNewest = newestHistoryKey(state.history);
        const previousCount = state.history.length;
        state.history = Array.isArray(event.history) ? event.history : [];
        const hasNewRecord = state.history.length >= previousCount
          && newestHistoryKey(state.history) !== previousNewest;
        renderHistory({
          scrollToLatest: state.page === "history" && hasNewRecord,
          preserveScroll: state.page === "history" && !hasNewRecord,
        });
        break;
      }
      case "settings":
        state.settings = event.settings || state.settings;
        renderSettings();
        renderRecognition();
        break;
      case "resources":
        state.resources = Array.isArray(event.resources) ? event.resources : [];
        renderResources();
        renderRecognition();
        break;
      case "toast":
        showToast(String(event.message || ""));
        break;
      case "navigate":
        navigate(event.page);
        break;
      default:
        break;
    }
  }

  function renderAll() {
    renderRecognition();
    renderHistory();
    renderSettings();
    renderResources();
  }

  function renderRecognition() {
    const recognition = state.recognition;
    const phase = recognition.phase || "idle";
    const active = Boolean(recognition.active);
    const capturing = Boolean(recognition.capturing);
    const text = typeof recognition.text === "string" ? recognition.text : "";
    elements.statusText.textContent = recognition.status || "准备就绪";
    elements.recordButton.dataset.active = String(active);
    elements.recordButton.disabled = active && phase === "processing";
    elements.recordButtonText.textContent = active ? (phase === "processing" ? "正在整理文字" : "停止识别") : "开始识别";
    elements.cancelButton.classList.toggle("is-hidden", !active);
    elements.transcriptText.textContent = text || "识别文字会显示在这里";
    elements.transcriptText.classList.toggle("is-placeholder", !text);
    if (previousRecognitionActive && !active) {
      elements.recognitionAnnouncement.textContent = text ? "识别完成，文字已保存。" : "本次识别已结束。";
    }
    previousRecognitionActive = active;
    waveform.setActive(capturing);
    elements.resourceNotice.classList.toggle("is-hidden", !hasMissingRequiredResources());
    const modelCopy = {
      local_dual: ["Zipformer ＋ Paraformer", "2 套模型 · 实时出字，停止后分段校正"],
      local_dual_qwen: ["Zipformer ＋ Qwen3-ASR", "2 套模型 · 实时出字，停止后高质量校正"],
      local_zipformer: ["仅 Zipformer", "1 套模型 · 只做实时识别"],
      local_paraformer: ["仅 Paraformer", "1 套模型 · 停止后生成全文"],
      local_qwen: ["仅 Qwen3-ASR", "1 套模型 · 停止后高质量生成全文"]
    }[state.settings.engine] || ["正在读取模型", "请稍候"];
    elements.activeModelsTitle.textContent = modelCopy[0];
    elements.activeModelsDetail.textContent = modelCopy[1];
  }

  function renderHistory({ scrollToLatest = false, preserveScroll = false } = {}) {
    const previousHeight = preserveScroll ? document.documentElement.scrollHeight : 0;
    const previousTop = preserveScroll ? window.scrollY : 0;
    const query = state.historyQuery.trim().toLocaleLowerCase("zh-CN");
    const filtered = state.history
      .filter((item) => String(item.text || "").toLocaleLowerCase("zh-CN").includes(query))
      .sort((left, right) => historySortValue(right) - historySortValue(left));
    const visible = filtered.slice(0, state.historyVisibleCount).reverse();
    elements.historyCount.textContent = `${state.history.length} 条记录`;
    elements.clearHistoryButton.disabled = state.history.length === 0;
    elements.copyAllHistoryButton.disabled = state.history.length === 0;
    elements.historyEmpty.classList.toggle("is-hidden", filtered.length > 0);
    elements.historyList.replaceChildren(...visible.map(createHistoryCard));
    elements.loadMoreHistory.classList.toggle("is-hidden", visible.length >= filtered.length);
    if (scrollToLatest && state.page === "history") scrollHistoryToLatest();
    else if (preserveScroll && state.page === "history") {
      window.requestAnimationFrame(() => {
        const addedHeight = document.documentElement.scrollHeight - previousHeight;
        window.scrollTo({ top: Math.max(0, previousTop + addedHeight), behavior: "auto" });
      });
    }
  }

  function historySortValue(item) {
    const timestamp = Date.parse(String(item?.createdAt || "").replace(" ", "T"));
    return Number.isFinite(timestamp) ? timestamp : Number(item?.id) || 0;
  }

  function newestHistoryKey(items) {
    const newest = [...items].sort((left, right) => historySortValue(right) - historySortValue(left))[0];
    return newest ? `${historySortValue(newest)}:${newest.id}` : "";
  }

  function scrollHistoryToLatest() {
    window.requestAnimationFrame(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "auto" }));
  }

  function createHistoryCard(item) {
    const card = document.createElement("article");
    card.className = "history-card";
    const text = document.createElement("p");
    text.className = "history-text";
    text.textContent = String(item.text || "");
    const meta = document.createElement("p");
    meta.className = "history-meta";
    meta.textContent = `${formatDate(item.createdAt)}　${engineName(item.engine)}`;
    const copy = iconActionButton("复制", "copy", () => callNative("copyHistory", Number(item.id)));
    copy.classList.add("history-copy");
    const footer = document.createElement("div");
    footer.className = "history-footer";
    footer.append(meta, copy);
    const remove = iconActionButton("删除", "close", () => {
      openConfirm("删除这条识别记录？删除后无法恢复。", "确认删除", () => callNative("deleteHistory", Number(item.id)));
    });
    remove.classList.add("history-remove");
    const copyCard = () => callNative("copyHistory", Number(item.id));
    card.addEventListener("click", copyCard);
    [copy, remove].forEach((button) => button.addEventListener("click", (event) => event.stopPropagation()));
    card.append(remove, text, footer);
    return card;
  }

  function iconActionButton(label, icon, action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-icon-action";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.innerHTML = icon === "copy"
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"></path></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"></path></svg>';
    button.addEventListener("click", action);
    return button;
  }

  function renderSettings() {
    if (!state.engineMode) {
      state.engineMode = ["local_dual", "local_dual_qwen"].includes(state.settings.engine) ? "correction" : "recognition";
    }
    renderEngineMode();
    elements.engineInputs.forEach((input) => {
      input.checked = input.value === state.settings.engine;
    });
    elements.overlaySwitch.checked = Boolean(state.settings.overlayEnabled);
    elements.overlayTextSwitch.checked = state.settings.overlayTextEnabled !== false;
    const opacity = Math.min(100, Math.max(35, Number(state.settings.overlayOpacity) || 72));
    elements.overlayOpacity.value = String(opacity);
    elements.overlayOpacityValue.value = `${opacity}%`;
    elements.overlayPreview.style.setProperty("--overlay-demo-opacity", String(opacity / 100));
    const overlaySize = Math.min(88, Math.max(48, Number(state.settings.overlaySize) || 64));
    elements.overlaySize.value = String(overlaySize);
    elements.overlaySizeValue.value = `${overlaySize} dp`;
    elements.overlayPreview.style.setProperty("--overlay-demo-size", `${overlaySize}px`);
    elements.overlayPreview.dataset.overlaySizeDp = String(overlaySize);
    elements.overlayPreviewText.classList.toggle("is-hidden", state.settings.overlayTextEnabled === false);
    elements.overlayStatus.textContent = state.settings.overlayEnabled
      ? "悬浮小球已开启；点击开始或停止识别，长按可关闭。"
      : state.settings.overlayPermission
        ? "权限已允许，开启后可在其他应用上方识别。"
        : "首次开启时需要允许显示在其他应用上层。";
    elements.versionText.textContent = state.version ? `悬浮语音按钮 ${state.version}` : "";
  }

  function renderEngineMode() {
    elements.engineModeButtons.forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.engineMode === state.engineMode));
    });
    elements.engineCards.forEach((card) => {
      card.hidden = card.dataset.engineMode !== state.engineMode;
    });
  }

  function renderResources() {
    const activeIds = new Set(state.resources.map((resource) => resource.id));
    resourceCards.forEach((record, id) => {
      if (!activeIds.has(id)) {
        record.card.remove();
        resourceCards.delete(id);
      }
    });
    state.resources.forEach((resource, index) => {
      let record = resourceCards.get(resource.id);
      if (!record) {
        record = createResourceCard(resource);
        resourceCards.set(resource.id, record);
      }
      updateResourceCard(record, resource);
      const current = elements.resourceList.children[index];
      if (current !== record.card) elements.resourceList.insertBefore(record.card, current || null);
    });
  }

  function createResourceCard(resource) {
    const card = document.createElement("article");
    card.className = "resource-card";
    const header = document.createElement("div");
    header.className = "resource-card-header";
    const heading = document.createElement("div");
    const title = document.createElement("h3");
    const purpose = document.createElement("p");
    heading.append(title, purpose);
    const status = document.createElement("span");
    header.append(heading);

    const progress = document.createElement("progress");
    progress.className = "resource-progress";
    progress.max = 1;

    const stats = document.createElement("div");
    stats.className = "resource-stats";
    const amount = document.createElement("span");
    const speed = document.createElement("span");
    const space = document.createElement("span");
    stats.append(amount, speed, space);

    const footer = document.createElement("div");
    footer.className = "resource-card-footer";
    const error = document.createElement("p");
    error.className = "resource-error is-hidden";
    card.append(header, progress, stats, error, footer);
    return { card, header, title, purpose, status, progress, amount, speed, space, error, footer, actionKey: "", statusValue: "" };
  }

  function updateResourceCard(record, resource) {
    record.title.textContent = resource.name;
    record.purpose.textContent = resource.purpose;
    record.status.className = `resource-state-label${resource.status === "available" ? " is-available" : resource.status === "error" ? " is-error" : ""}`;
    record.status.textContent = resourceStatusName(resource.status);
    record.progress.value = resource.totalBytes > 0 ? Math.min(1, resource.presentBytes / resource.totalBytes) : 0;
    record.progress.setAttribute("aria-label", `${resource.name}下载进度`);
    record.amount.textContent = resource.status === "available"
      ? `已占 ${formatBytes(resource.installedBytes)}`
      : `${formatBytes(resource.presentBytes)} / ${formatBytes(resource.totalBytes)}`;
    record.speed.textContent = resource.speedBytesPerSecond > 0
      ? `${formatBytes(resource.speedBytesPerSecond)}/秒 · ${formatEta(resource.etaSeconds)}`
      : `版本 ${resource.version}`;
    record.space.textContent = resource.freeBytes > 0 ? `手机可用 ${formatBytes(resource.freeBytes)}` : "正在读取可用空间";
    record.error.textContent = resource.errorMessage || "";
    record.error.classList.toggle("is-hidden", !resource.errorMessage);

    const actionKey = resource.status;
    if (record.actionKey !== actionKey) {
      record.status.remove();
      record.footer.replaceChildren();
      if (["downloading", "pausing"].includes(resource.status)) {
        record.header.append(record.status);
        record.footer.append(resourceButton(resource.status === "pausing" ? "正在暂停" : "暂停下载", () => callNative("pauseResource", resource.id), false, resource.status === "pausing"));
      } else if (resource.status === "verifying") {
        record.header.append(record.status);
        record.footer.append(resourceButton("正在校验完整性", () => {}, false, true));
      } else if (resource.status === "available") {
        record.footer.append(resourceButton("校验模型", () => callNative("verifyResource", resource.id)));
        record.footer.append(resourceButton("删除模型", () => {
          openConfirm(`删除“${resource.name}”？之后仍可重新下载，应用本身不会被删除。`, "确认删除", () => callNative("deleteResource", resource.id));
        }, true));
      } else {
        if (resource.status !== "missing") record.header.append(record.status);
        const label = resource.status === "paused" ? "继续下载" : resource.status === "error" ? "重试下载" : "下载模型";
        record.footer.append(resourceButton(label, () => callNative("downloadResource", resource.id)));
      }
      record.actionKey = actionKey;
    }
    if (record.statusValue && record.statusValue !== resource.status && ["available", "paused", "error"].includes(resource.status)) {
      elements.resourceAnnouncement.textContent = `${resource.name}：${resourceStatusName(resource.status)}。`;
    }
    record.statusValue = resource.status;
  }

  function resourceButton(label, action, danger = false, disabled = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `resource-action${danger ? " is-danger" : ""}`;
    button.textContent = label;
    button.disabled = disabled;
    button.addEventListener("click", action);
    return button;
  }

  function navigate(page) {
    if (!["recording", "history", "settings"].includes(page) || state.page === page) return;
    state.page = page;
    state.historyVisibleCount = 40;
    elements.pages.forEach((section) => {
      const active = section.dataset.page === page;
      section.hidden = !active;
      section.classList.toggle("is-active", active);
      if (active) {
        section.setAttribute("tabindex", "-1");
        section.focus({ preventScroll: true });
        if (page === "history") scrollHistoryToLatest();
        else window.scrollTo(0, 0);
      }
    });
    elements.navItems.forEach((item) => {
      const active = item.dataset.target === page;
      item.classList.toggle("is-active", active);
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    callNative("setCurrentPage", page);
    waveform.refreshVisibility();
    overlayWaveform.refreshVisibility();
  }

  function openConfirm(message, acceptLabel, action) {
    confirmAction = action;
    confirmReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    elements.confirmMessage.textContent = message;
    elements.confirmAccept.textContent = acceptLabel;
    elements.confirmDialog.showModal();
    elements.confirmCancel.focus();
  }

  function closeConfirm() {
    confirmAction = null;
    if (elements.confirmDialog.open) elements.confirmDialog.close();
    const target = confirmReturnFocus;
    confirmReturnFocus = null;
    if (target?.isConnected) target.focus();
  }

  function handleBack() {
    if (elements.confirmDialog.open) {
      closeConfirm();
      return true;
    }
    if (state.page !== "recording") {
      navigate("recording");
      return true;
    }
    return false;
  }

  function showToast(message) {
    if (!message) return;
    window.clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 3200);
  }

  function hasMissingRequiredResources() {
    const requirements = {
      local_dual: ["zipformer-bilingual", "paraformer"],
      local_dual_qwen: ["zipformer-bilingual", "qwen3-asr-0.6b-int8"],
      local_zipformer: ["zipformer-bilingual"],
      local_paraformer: ["paraformer"],
      local_qwen: ["qwen3-asr-0.6b-int8"]
    }[state.settings.engine] || [];
    return requirements.some((id) => !state.resources.some((item) => item.id === id && item.status === "available"));
  }

  function resourceStatusName(status) {
    return {
      available: "已安装",
      downloading: "下载中",
      pausing: "暂停中",
      paused: "已暂停",
      verifying: "校验中",
      error: "需要重试",
      missing: "未安装"
    }[status] || "未安装";
  }

  function engineName(engine) {
    return {
      local_dual: "实时＋校正",
      local_dual_qwen: "实时＋Qwen 校正",
      local_zipformer: "仅实时",
      local_paraformer: "仅整段",
      local_qwen: "仅 Qwen"
    }[engine] || "未知方式";
  }

  function formatDate(raw) {
    if (!raw) return "时间未知";
    const date = new Date(`${String(raw).replace(" ", "T")}Z`);
    if (Number.isNaN(date.getTime())) return String(raw);
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    }).format(date);
  }

  function formatBytes(bytes) {
    const value = Math.max(0, Number(bytes) || 0);
    if (value < 1024) return `${Math.round(value)} 字节`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / 1024 / 1024).toFixed(1)} MB`;
  }

  function formatEta(seconds) {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    if (value < 60) return `约 ${Math.max(1, value)} 秒`;
    if (value < 3600) return `约 ${Math.ceil(value / 60)} 分钟`;
    return `约 ${Math.ceil(value / 3600)} 小时`;
  }

  elements.navItems.forEach((item) => item.addEventListener("click", () => navigate(item.dataset.target)));
  elements.recordButton.addEventListener("click", () => callNative("toggleRecognition"));
  elements.cancelButton.addEventListener("click", () => callNative("cancelRecognition"));
  elements.copyTranscriptButton.addEventListener("click", () => callNative("copyText", state.recognition.text || ""));
  elements.resourceNotice.addEventListener("click", () => navigate("settings"));
  elements.activeModelsButton.addEventListener("click", () => navigate("settings"));
  elements.historySearch.addEventListener("input", (event) => {
    state.historyQuery = event.target.value || "";
    state.historyVisibleCount = 40;
    renderHistory();
  });
  elements.copyAllHistoryButton.addEventListener("click", () => {
    if (state.history.length) callNative("copyAllHistory");
  });
  elements.loadMoreHistory.addEventListener("click", () => {
    state.historyVisibleCount += 40;
    renderHistory({ preserveScroll: true });
  });
  elements.clearHistoryButton.addEventListener("click", () => {
    if (!state.history.length) return;
    openConfirm("清空全部识别记录？所有记录都会从这台手机中永久删除。", "确认清空", () => callNative("clearHistory"));
  });
  elements.engineInputs.forEach((input) => input.addEventListener("change", () => {
    if (input.checked) callNative("setEngine", input.value);
  }));
  elements.engineModeButtons.forEach((button) => button.addEventListener("click", () => {
    state.engineMode = button.dataset.engineMode;
    renderEngineMode();
  }));
  elements.overlaySwitch.addEventListener("change", () => {
    const enabled = elements.overlaySwitch.checked;
    elements.overlaySwitch.disabled = true;
    callNative("setOverlayEnabled", enabled);
    window.setTimeout(() => { elements.overlaySwitch.disabled = false; }, 500);
  });
  elements.overlayTextSwitch.addEventListener("change", () => {
    elements.overlayPreviewText.classList.toggle("is-hidden", !elements.overlayTextSwitch.checked);
    callNative("setOverlayTextEnabled", elements.overlayTextSwitch.checked);
  });
  elements.overlayOpacity.addEventListener("input", () => {
    elements.overlayOpacityValue.value = `${elements.overlayOpacity.value}%`;
    elements.overlayPreview.style.setProperty("--overlay-demo-opacity", String(Number(elements.overlayOpacity.value) / 100));
  });
  elements.overlayOpacity.addEventListener("change", () => {
    callNative("setOverlayOpacity", Number(elements.overlayOpacity.value));
  });
  elements.overlaySize.addEventListener("input", () => {
    const size = Number(elements.overlaySize.value);
    elements.overlaySizeValue.value = `${size} dp`;
    elements.overlayPreview.style.setProperty("--overlay-demo-size", `${size}px`);
    elements.overlayPreview.dataset.overlaySizeDp = String(size);
  });
  elements.overlaySize.addEventListener("change", () => {
    callNative("setOverlaySize", Number(elements.overlaySize.value));
  });

  elements.overlayPreviewOrb.addEventListener("click", () => {
    overlayPreviewRecording = !overlayPreviewRecording;
    overlayWaveform.setActive(overlayPreviewRecording);
    elements.overlayPreviewOrb.classList.toggle("is-recording", overlayPreviewRecording);
    elements.overlayPreviewOrb.setAttribute("aria-pressed", String(overlayPreviewRecording));
    elements.overlayPreviewOrb.setAttribute(
      "aria-label",
      overlayPreviewRecording ? "悬浮球正在录音，点击停止录音" : "悬浮球当前为待机，点击开始录音"
    );
    elements.overlayPreviewText.textContent = overlayPreviewRecording
      ? "正在识别：你好，今天测试一下中英文混合识别。"
      : "待机：点击悬浮球开始识别。";
  });
  elements.copyDiagnosticsButton.addEventListener("click", () => callNative("copyDiagnostics"));
  elements.confirmCancel.addEventListener("click", closeConfirm);
  elements.confirmAccept.addEventListener("click", () => {
    const action = confirmAction;
    closeConfirm();
    if (typeof action === "function") action();
  });
  elements.confirmDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeConfirm();
  });
  reducedMotion.addEventListener?.("change", () => {
    waveform.setActive(state.recognition.capturing);
    overlayWaveform.refreshMotionPreference();
  });
  document.addEventListener("visibilitychange", () => {
    waveform.refreshVisibility();
    overlayWaveform.refreshVisibility();
  });

  window.VoiceApp = { receive, handleBack };
  applyFullState(loadInitialState());
  callNative("ready");
})();
