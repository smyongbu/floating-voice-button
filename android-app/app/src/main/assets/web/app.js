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
      text: "",
      finalProcessing: false,
      finalQueueCount: 0,
      finalText: ""
    },
    settings: {
      engine: "local_dual",
      realtimeEngine: "streaming_paraformer",
      finalEngine: "qwen3_asr_17b_q5_k_m",
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
    historyQuery: "",
    historyVisibleCount: 40,
    selectedHistoryIds: new Set()
  };

  const elements = {
    pages: [...document.querySelectorAll(".page")],
    navItems: [...document.querySelectorAll(".nav-item")],
    statusText: document.getElementById("statusText"),
    statusHint: document.getElementById("statusHint"),
    recordButton: document.getElementById("recordButton"),
    recordButtonText: document.getElementById("recordButtonText"),
    cancelButton: document.getElementById("cancelButton"),
    transcriptText: document.getElementById("transcriptText"),
    finalRecognitionStatus: document.getElementById("finalRecognitionStatus"),
    recognitionAnnouncement: document.getElementById("recognitionAnnouncement"),
    copyTranscriptButton: document.getElementById("copyTranscriptButton"),
    resourceNotice: document.getElementById("resourceNotice"),
    realtimeModelButton: document.getElementById("realtimeModelButton"),
    realtimeModelName: document.getElementById("realtimeModelName"),
    realtimeModelProgress: document.getElementById("realtimeModelProgress"),
    finalModelButton: document.getElementById("finalModelButton"),
    finalModelName: document.getElementById("finalModelName"),
    finalModelProgress: document.getElementById("finalModelProgress"),
    historyCount: document.getElementById("historyCount"),
    historySearch: document.getElementById("historySearch"),
    historySelectionBar: document.getElementById("historySelectionBar"),
    historySelectionCount: document.getElementById("historySelectionCount"),
    copySelectedHistoryButton: document.getElementById("copySelectedHistoryButton"),
    deleteSelectedHistoryButton: document.getElementById("deleteSelectedHistoryButton"),
    cancelHistorySelectionButton: document.getElementById("cancelHistorySelectionButton"),
    copyAllHistoryButton: document.getElementById("copyAllHistoryButton"),
    historyEmpty: document.getElementById("historyEmpty"),
    historyEmptyTitle: document.getElementById("historyEmptyTitle"),
    historyEmptyText: document.getElementById("historyEmptyText"),
    historyList: document.getElementById("historyList"),
    loadMoreHistory: document.getElementById("loadMoreHistory"),
    clearHistoryButton: document.getElementById("clearHistoryButton"),
    engineInputs: [...document.querySelectorAll('input[name="realtimeEngine"], input[name="finalEngine"]')],
    openResourceManagerButton: document.getElementById("openResourceManagerButton"),
    resourceManagerDialog: document.getElementById("resourceManagerDialog"),
    closeResourceManagerButton: document.getElementById("closeResourceManagerButton"),
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
    overlayEdgeHint: document.getElementById("overlayEdgeHint"),
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
  let resourceManagerReturnFocus = null;
  let toastTimer = 0;
  let previousRecognitionActive = false;
  let previewRecordingTimer = 0;
  let previewLevelTimer = 0;
  let overlayPreviewRecording = false;
  let overlayPreviewPosition = { x: null, y: null, side: "right" };
  let overlayPreviewDrag = null;
  let suppressOverlayPreviewClick = false;
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
      this.target = 0;
      this.level = 0;
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
      if (!active) {
        this.target = 0;
        this.level = 0;
        if (this.frame) cancelAnimationFrame(this.frame);
        this.frame = 0;
        this.render();
        this.updateMotionState();
        return;
      }
      if (reducedMotion.matches || !this.isVisible()) {
        if (this.frame) cancelAnimationFrame(this.frame);
        this.frame = 0;
        this.level = active ? 0.42 : 0;
        this.render();
        this.updateMotionState();
        return;
      }
      this.start();
    }

    setLevel(raw) {
      const normalized = Math.max(0, Math.min(1, Number(raw) || 0));
      this.target = this.active ? Math.min(1, Math.sqrt(normalized) * 0.86 + 0.06) : 0;
      this.lastLevelAt = performance.now();
      if (!this.active || reducedMotion.matches || !this.isVisible()) return;
      this.start();
    }

    isVisible() {
      return state.page === "settings" && !document.hidden;
    }

    updateMotionState() {
      elements.overlayWaveform.dataset.motion = this.frame ? "running" : "paused";
    }

    refreshVisibility() {
      if (this.active && this.isVisible() && !reducedMotion.matches) {
        this.start();
      } else {
        if (this.frame) cancelAnimationFrame(this.frame);
        this.frame = 0;
        this.render();
        this.updateMotionState();
      }
    }

    refreshMotionPreference() {
      this.setActive(this.active);
    }

    start() {
      if (this.frame || !this.active || !this.isVisible() || reducedMotion.matches) {
        this.updateMotionState();
        return;
      }
      this.lastTime = performance.now();
      this.frame = requestAnimationFrame((time) => this.tick(time));
      this.updateMotionState();
    }

    tick(time) {
      if (!this.active || !this.isVisible() || reducedMotion.matches) {
        this.frame = 0;
        this.updateMotionState();
        return;
      }
      const delta = Math.min(40, Math.max(0, time - this.lastTime));
      this.lastTime = time;
      if (time - this.lastLevelAt > 420) {
        const syntheticLevel = 0.48 + Math.sin(time * 0.0041) * 0.18 + Math.sin(time * 0.0067 + 1.2) * 0.12;
        this.target = Math.max(0.18, Math.min(0.82, syntheticLevel));
      }
      this.level += (this.target - this.level) * 0.14;
      this.phase += delta * (0.0019 + this.level * 0.00125);
      this.render();
      this.frame = requestAnimationFrame((next) => this.tick(next));
    }

    render() {
      const amplitude = this.active ? 2.4 + this.level * 14 : 0.72;
      elements.overlayWaveBack.setAttribute("d", buildSmoothWavePath(120, 36, amplitude * 0.43, 2.9, -this.phase * 0.82, 36));
      elements.overlayWaveMiddle.setAttribute("d", buildSmoothWavePath(120, 36, amplitude * 0.68, 1.82, this.phase * 0.64 + 0.7, 36));
      elements.overlayWaveFront.setAttribute("d", buildSmoothWavePath(120, 36, amplitude, 2.25, this.phase, 36));
    }
  }

  const waveform = new SmoothWaveform();
  const overlayWaveform = new CompactWaveform();
  const modelBridgeMethods = Object.freeze({
    realtimeEngine: "setRealtimeModel",
    finalEngine: "setFinalModel"
  });
  const modelResourceAliases = Object.freeze({
    realtimeEngine: {
      streaming_paraformer: ["streaming-paraformer", "streaming-paraformer-bilingual", "streaming-paraformer-bilingual-zh-en", "paraformer-streaming"],
      zipformer: ["zipformer", "zipformer-bilingual"]
    },
    finalEngine: {
      faster_whisper_small: ["faster-whisper-small", "faster-whisper-small-gguf-q8-0"],
      qwen3_asr_06b_int8: ["qwen3-asr-0.6b-int8", "qwen3-asr-06b-int8"],
      qwen3_asr_17b_q5_k_m: ["qwen3-asr-1.7b-q5-k-m", "qwen3-asr-17b-q5-k-m", "qwen3-asr-1.7b-gguf-q5-k-m"]
    }
  });

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

  function setModelSelection(settingKey, value) {
    const method = modelBridgeMethods[settingKey];
    if (!method) return;
    callNative(method, String(value || ""));
  }

  function runPreviewAction(method, args) {
    const resourceById = (id) => state.resources.find((item) => item.id === id);
    if (["ready", "setCurrentPage"].includes(method)) return undefined;
    if (method === modelBridgeMethods.realtimeEngine || method === modelBridgeMethods.finalEngine) {
      const settingKey = method === modelBridgeMethods.realtimeEngine ? "realtimeEngine" : "finalEngine";
      state.settings[settingKey] = String(args[0] || state.settings[settingKey]);
      renderSettings();
      renderRecognition();
      showToast("预览：识别模型已切换");
      return undefined;
    }
    if (method === "setEngine") {
      state.settings.engine = String(args[0] || "local_dual");
      renderSettings();
      renderRecognition();
      showToast("预览：识别方案已切换");
      return undefined;
    }
    if (method === "toggleRecognition") {
      if (!state.recognition.active && hasMissingRequiredResources()) {
        navigate("settings");
        showToast("请先下载当前方案所需的离线模型");
        return undefined;
      }
      if (state.recognition.active) {
        window.clearTimeout(previewRecordingTimer);
        window.clearInterval(previewLevelTimer);
        state.recognition = {
          active: true,
          capturing: false,
          phase: "processing",
          status: "正在使用最后识别模型整理文字…",
          text: state.recognition.text
        };
        renderRecognition();
        previewRecordingTimer = window.setTimeout(() => {
          const rawText = "我今天要 review this project，然后 update the README and fix the login bug。";
          const id = Date.now();
          state.recognition = { active: false, capturing: false, phase: "idle", status: "识别完成", text: rawText };
          const item = { id, text: rawText, createdAt: new Date().toISOString().replace("T", " ").slice(0, 19), engine: state.settings.finalEngine };
          state.history.unshift(item);
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
      state.selectedHistoryIds.delete(Number(args[0]));
      renderHistory();
      renderSettings();
      return undefined;
    }
    if (method === "clearHistory") { state.history = []; state.selectedHistoryIds.clear(); renderHistory(); renderSettings(); return undefined; }
    if (method === "copyText" || method === "copyHistory" || method === "copyDiagnostics") { showToast("预览：已模拟复制"); return undefined; }
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
      recognition: { active: false, capturing: false, phase: "idle", status: "实时与最后识别模型已就绪", text: "", finalProcessing: false, finalQueueCount: 0, finalText: "" },
      settings: { ...state.settings },
      resources: [
        { id: "streaming-paraformer-bilingual-zh-en", name: "Streaming Paraformer", purpose: "边说边显示中英文识别文字", version: "8e40c432-int8", totalBytes: 237202501, presentBytes: 237202501, installedBytes: 237202501, status: "available", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 11717148672, errorMessage: "" },
        { id: "zipformer-bilingual", name: "Zipformer", purpose: "边说边显示中英文和中英混说识别文字", version: "2024-03-20-exp32-int8", totalBytes: 60142871, presentBytes: 0, installedBytes: 0, status: "missing", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 11717148672, errorMessage: "" },
        { id: "faster-whisper-small-gguf-q8-0", name: "Faster-Whisper Small", purpose: "停止后生成完整的最终识别文字", version: "c0214bd3-q8_0", totalBytes: 269751136, presentBytes: 0, installedBytes: 0, status: "missing", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 11717148672, errorMessage: "" },
        { id: "qwen3-asr-0.6b-int8", name: "Qwen3-ASR 0.6B INT8", purpose: "停止后生成中英文和中英混说最终文字", version: "68818b23-int8", totalBytes: 987015347, presentBytes: 0, installedBytes: 0, status: "missing", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 11717148672, errorMessage: "" },
        { id: "qwen3-asr-1.7b-gguf-q5-k-m", name: "Qwen3-ASR 1.7B Q5_K_M", purpose: "停止后生成高质量的中英文最终识别文字", version: "92282af1-q5_k_m", totalBytes: 1517290464, presentBytes: 1517290464, installedBytes: 1517290464, status: "available", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 11717148672, errorMessage: "" }
      ],
      history: [
        { id: 3, text: "我今天要 review this project，然后 update the README and fix the login bug。", createdAt: "2026-08-20 14:32:00", engine: "qwen3_asr_17b_q5_k_m" },
        { id: 2, text: "Please create a new note and copy this sentence.", createdAt: "2026-08-18 17:16:00", engine: "local_dual_qwen" },
        { id: 1, text: "这是一条较长的模拟历史记录，用于检查卡片换行、复制按钮和删除按钮在窄屏幕上的排版。", createdAt: "2026-08-18 16:03:00", engine: "local_zipformer" }
      ],
      version: "独立 UI 预览"
    };
  }

  function mergeSettings(next) {
    const merged = { ...state.settings, ...(next || {}) };
    if (typeof next?.realtimeModel === "string") merged.realtimeEngine = next.realtimeModel;
    if (typeof next?.finalModel === "string") merged.finalEngine = next.finalModel;
    return merged;
  }

  function applyFullState(next) {
    if (!next) return;
    if (next.recognition) state.recognition = next.recognition;
    if (next.settings) {
      state.settings = mergeSettings(next.settings);
    }
    if (Array.isArray(next.resources)) state.resources = next.resources;
    if (Array.isArray(next.history)) {
      state.history = next.history;
      pruneHistorySelection();
    }
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
      case "history":
        state.history = Array.isArray(event.history) ? event.history : [];
        pruneHistorySelection();
        renderHistory();
        renderSettings();
        renderRecognition();
        if (state.page === "history") scrollHistoryToLatest();
        break;
      case "settings":
        if (event.settings) {
          state.settings = mergeSettings(event.settings);
        }
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
    const backgroundFinalBusy = Boolean(recognition.finalProcessing) || Number(recognition.finalQueueCount || 0) > 0;
    const recognitionText = typeof recognition.text === "string" ? recognition.text : "";
    const finalText = typeof recognition.finalText === "string" ? recognition.finalText : "";
    const text = active ? recognitionText : recognition.finalProcessing ? finalText : recognitionText;
    const missingRequiredResources = hasMissingRequiredResources();
    elements.statusText.textContent = missingRequiredResources && !active
      ? "需要先下载所需离线模型"
      : backgroundFinalBusy && !active
      ? "正在整理上一段文字，可继续识别"
      : recognition.status || "准备就绪";
    elements.statusHint.textContent = {
      preparing: "模型和麦克风准备完成前，请先不要说话",
      listening: "",
      processing: "正在生成最终文字，请稍候",
      idle: active ? "正在准备本轮识别" : ""
    }[phase] || "";
    elements.recordButton.dataset.active = String(active);
    elements.recordButton.disabled = (!active && missingRequiredResources) || (active && phase === "processing");
    elements.recordButtonText.textContent = active
      ? phase === "processing" ? "正在加入队列" : "停止识别"
      : missingRequiredResources ? "请先下载模型" : backgroundFinalBusy ? "继续识别" : "开始识别";
    elements.cancelButton.classList.toggle("is-hidden", !active);
    elements.transcriptText.textContent = text || "识别文字会显示在这里";
    elements.transcriptText.classList.toggle("is-placeholder", !text);
    const queueCount = Number(recognition.finalQueueCount || 0);
    elements.finalRecognitionStatus.textContent = recognition.finalProcessing
      ? queueCount > 0 ? `最后识别中···　排队 ${queueCount} 条` : "最后识别中···"
      : queueCount > 0 ? `等待最后识别　${queueCount} 条` : "";
    elements.finalRecognitionStatus.classList.toggle("is-hidden", !elements.finalRecognitionStatus.textContent);
    if (previousRecognitionActive && !active) {
      elements.recognitionAnnouncement.textContent = text ? "识别完成，文字已保存。" : "本次识别已结束。";
    }
    previousRecognitionActive = active;
    waveform.setActive(capturing);
    elements.resourceNotice.classList.toggle("is-hidden", !missingRequiredResources);
    elements.engineInputs.forEach((input) => { input.disabled = active; });
    const currentRealtimeName = realtimeModelName(state.settings.realtimeEngine);
    const currentFinalName = finalModelName(state.settings.finalEngine);
    elements.realtimeModelName.textContent = currentRealtimeName;
    elements.finalModelName.textContent = currentFinalName;
    const updateModelCard = (button, progressElement, settingKey, modelName) => {
      const resource = selectedModelResource(settingKey);
      const measurable = Boolean(resource && resource.totalBytes > 0 && resource.presentBytes >= 0);
      const progress = measurable ? Math.min(100, Math.max(0, resource.presentBytes / resource.totalBytes * 100)) : 0;
      const resourceLoading = Boolean(resource && ["downloading", "pausing", "verifying"].includes(resource.status));
      const preparing = active && phase === "preparing";
      const loading = resourceLoading || preparing;
      const indeterminate = loading && (!resourceLoading || !measurable);
      const ready = resource?.status === "available";
      button.classList.toggle("is-loading", loading);
      button.classList.toggle("is-indeterminate", indeterminate);
      button.classList.toggle("is-ready", ready && !loading);
      button.style.setProperty("--model-progress", loading && !indeterminate ? `${progress.toFixed(1)}%` : "0%");
      progressElement.textContent = resourceLoading && measurable ? `${Math.round(progress)}%` : "";
      progressElement.classList.toggle("is-hidden", !progressElement.textContent);
      button.setAttribute("aria-busy", String(loading));
      button.setAttribute("aria-label", `${settingKey === "realtimeEngine" ? "实时显示" : "最后识别"}模型：${modelName}${loading ? `，正在加载${progressElement.textContent ? ` ${progressElement.textContent}` : ""}` : ""}`);
    };
    updateModelCard(elements.realtimeModelButton, elements.realtimeModelProgress, "realtimeEngine", currentRealtimeName);
    updateModelCard(elements.finalModelButton, elements.finalModelProgress, "finalEngine", currentFinalName);
  }

  function renderHistory() {
    const query = state.historyQuery.trim().toLocaleLowerCase("zh-CN");
    pruneHistorySelection();
    const filtered = state.history.filter((item) => String(item.text || "").toLocaleLowerCase("zh-CN").includes(query));
    const completedFiltered = filtered.filter((item) => !item.queueStatus);
    const ordered = [...filtered].sort((left, right) => historyTimestamp(left) - historyTimestamp(right));
    const visible = ordered.slice(Math.max(0, ordered.length - state.historyVisibleCount));
    elements.historyCount.textContent = `${state.history.length} 条记录 · 最多保存 500 条`;
    elements.historyEmptyTitle.textContent = "识别完成后会出现在这里";
    elements.historyEmptyText.textContent = "最多保存 500 条；本地识别不上传录音，系统识别取决于手机语音服务。";
    elements.clearHistoryButton.disabled = state.history.length === 0;
    elements.copyAllHistoryButton.disabled = completedFiltered.length === 0;
    const selectionCount = state.selectedHistoryIds.size;
    elements.historySelectionBar.classList.toggle("is-hidden", selectionCount === 0);
    elements.historyList.classList.toggle("is-selection-mode", selectionCount > 0);
    elements.historySelectionCount.textContent = `已选择 ${selectionCount} 条`;
    elements.historyEmpty.classList.toggle("is-hidden", filtered.length > 0);
    elements.historyList.replaceChildren(...visible.map(createHistoryCard));
    elements.loadMoreHistory.classList.toggle("is-hidden", visible.length >= ordered.length);
  }

  function historyTimestamp(item) {
    const raw = String(item?.createdAt || "").replace(" ", "T");
    const value = Date.parse(raw);
    return Number.isFinite(value) ? value : Number(item?.id) || 0;
  }

  function pruneHistorySelection() {
    const availableIds = new Set(state.history.map((item) => Number(item.id)));
    [...state.selectedHistoryIds].forEach((id) => {
      if (!availableIds.has(id)) state.selectedHistoryIds.delete(id);
    });
  }

  function scrollHistoryToLatest() {
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: reducedMotion.matches ? "auto" : "smooth" });
    });
  }

  function createHistoryCard(item) {
    const card = document.createElement("article");
    card.className = "history-card";
    if (item.queueStatus) {
      card.classList.add("is-pending");
      const status = document.createElement("p");
      status.className = "history-pending-status";
      status.textContent = item.queueStatus === "processing" ? "最后识别中···" : "排队等待";
      const text = document.createElement("p");
      text.className = "history-text";
      text.textContent = String(item.text || "等待生成最终文字");
      const meta = document.createElement("p");
      meta.className = "history-meta";
      meta.textContent = `${formatDate(item.createdAt)}　${engineName(item.finalEngine || item.engine)}`;
      card.append(status, text, meta);
      return card;
    }
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", "复制这条识别记录");
    const text = document.createElement("p");
    text.className = "history-text";
    text.textContent = String(item.text || "");
    const meta = document.createElement("p");
    meta.className = "history-meta";
    meta.textContent = `${formatDate(item.createdAt)}　${engineName(item.finalEngine || item.engine)}`;
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
    [copy, remove].forEach((button) => button.addEventListener("click", (event) => event.stopPropagation()));
    card.append(remove, text, footer);
    bindHistorySelection(card, item, copyCard);
    return card;
  }

  function bindHistorySelection(card, item, defaultAction) {
    const id = Number(item.id);
    let holdTimer = 0;
    let longPressed = false;
    let pointerStart = null;
    const clearHold = () => {
      window.clearTimeout(holdTimer);
      holdTimer = 0;
    };
    const toggle = () => {
      if (state.selectedHistoryIds.has(id)) state.selectedHistoryIds.delete(id);
      else state.selectedHistoryIds.add(id);
      renderHistory();
    };
    card.classList.toggle("is-selected", state.selectedHistoryIds.has(id));
    card.setAttribute("aria-selected", String(state.selectedHistoryIds.has(id)));
    card.addEventListener("pointerdown", (event) => {
      if ((event.button !== undefined && event.button !== 0) || event.target.closest("button")) return;
      longPressed = false;
      pointerStart = { x: event.clientX, y: event.clientY };
      holdTimer = window.setTimeout(() => {
        longPressed = true;
        toggle();
        navigator.vibrate?.(28);
      }, 520);
    });
    card.addEventListener("pointermove", (event) => {
      if (!pointerStart || !holdTimer) return;
      if (Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 9) clearHold();
    });
    ["pointerup", "pointercancel", "pointerleave"].forEach((name) => card.addEventListener(name, () => {
      clearHold();
      pointerStart = null;
    }));
    card.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      if (longPressed) {
        event.preventDefault();
        longPressed = false;
        return;
      }
      if (state.selectedHistoryIds.size > 0) {
        event.preventDefault();
        toggle();
        return;
      }
      defaultAction();
    });
    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      if (state.selectedHistoryIds.size > 0) toggle();
      else defaultAction();
    });
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
    elements.engineInputs.forEach((input) => {
      const settingKey = input.name === "realtimeEngine" ? "realtimeEngine" : "finalEngine";
      input.checked = input.value === state.settings[settingKey];
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
    window.requestAnimationFrame(() => ensureOverlayPreviewPosition());
    elements.overlayPreviewText.classList.toggle("is-hidden", state.settings.overlayTextEnabled === false);
    elements.overlayStatus.textContent = state.settings.overlayEnabled
      ? "悬浮小球已开启；点击开始或停止识别，长按可关闭。"
      : state.settings.overlayPermission
        ? "权限已允许，开启后可在其他应用上方识别。"
        : "首次开启时需要允许显示在其他应用上层。";
    elements.versionText.textContent = state.version ? `悬浮语音按钮 ${state.version}` : "";
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
    stats.append(amount, speed);

    const footer = document.createElement("div");
    footer.className = "resource-card-footer";
    const error = document.createElement("p");
    error.className = "resource-error is-hidden";
    card.append(header, progress, stats, error, footer);
    return { card, header, title, purpose, status, progress, amount, speed, error, footer, actionKey: "", statusValue: "" };
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
    if (page !== "settings" && elements.resourceManagerDialog.open) closeResourceManager();
    state.page = page;
    state.historyVisibleCount = 40;
    if (page !== "history") state.selectedHistoryIds.clear();
    elements.pages.forEach((section) => {
      const active = section.dataset.page === page;
      section.hidden = !active;
      section.classList.toggle("is-active", active);
      if (active) {
        section.setAttribute("tabindex", "-1");
        section.focus({ preventScroll: true });
        window.scrollTo(0, 0);
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
    if (page === "settings") window.requestAnimationFrame(ensureOverlayPreviewPosition);
    if (page === "history") scrollHistoryToLatest();
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

  function openResourceManager() {
    if (elements.resourceManagerDialog.open) return;
    resourceManagerReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    elements.resourceManagerDialog.showModal();
    elements.closeResourceManagerButton.focus();
  }

  function closeResourceManager() {
    if (elements.resourceManagerDialog.open) elements.resourceManagerDialog.close();
    const target = resourceManagerReturnFocus;
    resourceManagerReturnFocus = null;
    if (target?.isConnected) target.focus();
  }

  function handleBack() {
    if (elements.confirmDialog.open) {
      closeConfirm();
      return true;
    }
    if (elements.resourceManagerDialog.open) {
      closeResourceManager();
      return true;
    }
    if (state.page === "history" && state.selectedHistoryIds.size > 0) {
      state.selectedHistoryIds.clear();
      renderHistory();
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
    return ["realtimeEngine", "finalEngine"].some((settingKey) => {
      const expected = modelResourceAliases[settingKey][state.settings[settingKey]] || [];
      const normalizedExpected = new Set(expected.map(normalizeModelId));
      const matches = state.resources.filter((item) => normalizedExpected.has(normalizeModelId(item.id)));
      return matches.length > 0 && !matches.some((item) => item.status === "available");
    });
  }

  function selectedModelResource(settingKey) {
    const expected = modelResourceAliases[settingKey]?.[state.settings[settingKey]] || [];
    const normalizedExpected = new Set(expected.map(normalizeModelId));
    return state.resources.find((item) => normalizedExpected.has(normalizeModelId(item.id))) || null;
  }

  function normalizeModelId(value) {
    return String(value || "").trim().toLocaleLowerCase("en-US").replace(/_/g, "-");
  }

  function realtimeModelName(value) {
    return {
      streaming_paraformer: "Streaming Paraformer",
      zipformer: "Zipformer"
    }[value] || "正在读取模型";
  }

  function finalModelName(value) {
    return {
      faster_whisper_small: "Faster-Whisper Small",
      qwen3_asr_06b_int8: "Qwen3-ASR 0.6B INT8",
      qwen3_asr_17b_q5_k_m: "Qwen3-ASR 1.7B Q5_K_M"
    }[value] || "正在读取模型";
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
    const raw = String(engine || "");
    if (raw.includes("+")) {
      const [realtime, final] = raw.split("+", 2);
      return `${realtimeModelName(realtime)} ＋ ${finalModelName(final)}`;
    }
    return {
      local_dual: "实时＋校正",
      local_dual_qwen: "实时＋Qwen 校正",
      local_dual_whisper_acft: "实时＋Whisper 二次识别",
      local_zipformer: "仅实时",
      local_paraformer: "仅整段",
      local_qwen: "仅 Qwen",
      local_whisper_acft: "Whisper ACFT",
      streaming_paraformer: "Streaming Paraformer",
      zipformer: "Zipformer",
      faster_whisper_small: "Faster-Whisper Small",
      qwen3_asr_06b_int8: "Qwen3-ASR 0.6B INT8",
      qwen3_asr_17b_q5_k_m: "Qwen3-ASR 1.7B Q5_K_M"
    }[raw] || "未知方式";
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

  function overlayPreviewLimits() {
    const containerRect = elements.overlayPreview.getBoundingClientRect();
    const orbRect = elements.overlayPreviewOrb.getBoundingClientRect();
    const safeInset = 6;
    return {
      minX: safeInset,
      minY: safeInset,
      maxX: Math.max(safeInset, containerRect.width - orbRect.width - safeInset),
      maxY: Math.max(safeInset, containerRect.height - orbRect.height - safeInset),
      containerHeight: containerRect.height,
      orbWidth: orbRect.width,
      orbHeight: orbRect.height,
      visible: containerRect.width > 0 && containerRect.height > 0 && orbRect.width > 0 && orbRect.height > 0
    };
  }

  function updateOverlayPreviewTextPosition() {
    const limits = overlayPreviewLimits();
    if (!limits.visible) return;
    const textRect = elements.overlayPreviewText.getBoundingClientRect();
    const desiredCenterY = overlayPreviewPosition.y + limits.orbHeight / 2;
    const textSafeInset = 8;
    const textHalfHeight = textRect.height / 2;
    const minCenterY = textSafeInset + textHalfHeight;
    const maxCenterY = Math.max(minCenterY, limits.containerHeight - textSafeInset - textHalfHeight);
    const textCenterY = textRect.height
      ? Math.min(maxCenterY, Math.max(minCenterY, desiredCenterY))
      : desiredCenterY;
    elements.overlayPreview.style.setProperty("--overlay-demo-text-y", `${textCenterY}px`);
  }

  function setOverlayPreviewPosition(x, y, side = overlayPreviewPosition.side) {
    const limits = overlayPreviewLimits();
    if (!limits.visible) return;
    overlayPreviewPosition = {
      x: Math.min(limits.maxX, Math.max(limits.minX, Number(x) || 0)),
      y: Math.min(limits.maxY, Math.max(limits.minY, Number(y) || 0)),
      side: side === "left" ? "left" : "right"
    };
    elements.overlayPreview.style.setProperty("--overlay-demo-x", `${overlayPreviewPosition.x}px`);
    elements.overlayPreview.style.setProperty("--overlay-demo-y", `${overlayPreviewPosition.y}px`);
    elements.overlayPreview.dataset.side = overlayPreviewPosition.side;
    updateOverlayPreviewTextPosition();
  }

  function ensureOverlayPreviewPosition() {
    const limits = overlayPreviewLimits();
    if (!limits.visible) return;
    const y = overlayPreviewPosition.y == null
      ? limits.minY + (limits.maxY - limits.minY) / 2
      : overlayPreviewPosition.y;
    const x = overlayPreviewPosition.side === "left" ? limits.minX : limits.maxX;
    setOverlayPreviewPosition(x, y, overlayPreviewPosition.side);
  }

  function finishOverlayPreviewDrag(event) {
    if (!overlayPreviewDrag || event.pointerId !== overlayPreviewDrag.pointerId) return;
    const wasDragged = overlayPreviewDrag.moved;
    overlayPreviewDrag = null;
    elements.overlayPreviewOrb.classList.remove("is-dragging");
    if (elements.overlayPreviewOrb.hasPointerCapture?.(event.pointerId)) {
      elements.overlayPreviewOrb.releasePointerCapture(event.pointerId);
    }
    if (!wasDragged) return;

    const limits = overlayPreviewLimits();
    const previewCenter = (limits.minX + limits.maxX + limits.orbWidth) / 2;
    const orbCenter = overlayPreviewPosition.x + limits.orbWidth / 2;
    const side = orbCenter < previewCenter ? "left" : "right";
    const targetX = side === "left" ? limits.minX : limits.maxX;
    setOverlayPreviewPosition(targetX, overlayPreviewPosition.y, side);
    elements.overlayEdgeHint.textContent = `已贴到${side === "left" ? "左" : "右"}侧。继续拖动可切换贴边位置。`;
    suppressOverlayPreviewClick = true;
    window.setTimeout(() => { suppressOverlayPreviewClick = false; }, 350);
  }

  elements.navItems.forEach((item) => item.addEventListener("click", () => navigate(item.dataset.target)));
  elements.recordButton.addEventListener("click", () => callNative("toggleRecognition"));
  elements.cancelButton.addEventListener("click", () => callNative("cancelRecognition"));
  elements.copyTranscriptButton.addEventListener("click", () => callNative("copyText", state.recognition.text || ""));
  elements.resourceNotice.addEventListener("click", () => {
    navigate("settings");
    openResourceManager();
  });
  elements.realtimeModelButton.addEventListener("click", () => navigate("settings"));
  elements.finalModelButton.addEventListener("click", () => navigate("settings"));
  elements.openResourceManagerButton.addEventListener("click", openResourceManager);
  elements.closeResourceManagerButton.addEventListener("click", closeResourceManager);
  elements.resourceManagerDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeResourceManager();
  });
  elements.cancelHistorySelectionButton.addEventListener("click", () => {
    state.selectedHistoryIds.clear();
    renderHistory();
  });
  elements.copySelectedHistoryButton.addEventListener("click", () => {
    const records = state.history
      .filter((item) => state.selectedHistoryIds.has(Number(item.id)))
      .sort((left, right) => historyTimestamp(left) - historyTimestamp(right));
    if (!records.length) return;
    callNative("copyText", records.map((item) => String(item.text || "")).join("\n\n"));
  });
  elements.deleteSelectedHistoryButton.addEventListener("click", () => {
    const ids = [...state.selectedHistoryIds];
    if (!ids.length) return;
    openConfirm(`删除选中的 ${ids.length} 条记录？删除后无法恢复。`, "确认删除", () => {
      state.selectedHistoryIds.clear();
      renderHistory();
      ids.forEach((id) => callNative("deleteHistory", id));
    });
  });
  elements.copyAllHistoryButton.addEventListener("click", () => {
    const query = state.historyQuery.trim().toLocaleLowerCase("zh-CN");
    const records = state.history
      .filter((item) => String(item.text || "").toLocaleLowerCase("zh-CN").includes(query))
      .sort((left, right) => historyTimestamp(left) - historyTimestamp(right));
    if (!records.length) return;
    callNative("copyText", records.map((item) => String(item.text || "")).join("\n\n"));
  });
  elements.historySearch.addEventListener("input", (event) => {
    state.historyQuery = event.target.value || "";
    state.historyVisibleCount = 40;
    renderHistory();
  });
  elements.loadMoreHistory.addEventListener("click", () => {
    state.historyVisibleCount += 40;
    renderHistory();
  });
  elements.clearHistoryButton.addEventListener("click", () => {
    if (!state.history.length) return;
    openConfirm("清空全部识别记录？所有记录都会从这台手机中永久删除。", "确认清空", () => {
      state.selectedHistoryIds.clear();
      callNative("clearHistory");
    });
  });
  elements.engineInputs.forEach((input) => input.addEventListener("change", () => {
    if (state.recognition.active) {
      renderSettings();
      showToast("识别结束后才能切换模型");
      return;
    }
    if (!input.checked) return;
    const settingKey = input.name === "realtimeEngine" ? "realtimeEngine" : "finalEngine";
    setModelSelection(settingKey, input.value);
  }));
  elements.overlaySwitch.addEventListener("change", () => {
    const enabled = elements.overlaySwitch.checked;
    elements.overlaySwitch.disabled = true;
    callNative("setOverlayEnabled", enabled);
    window.setTimeout(() => { elements.overlaySwitch.disabled = false; }, 500);
  });
  elements.overlayTextSwitch.addEventListener("change", () => {
    elements.overlayPreviewText.classList.toggle("is-hidden", !elements.overlayTextSwitch.checked);
    window.requestAnimationFrame(updateOverlayPreviewTextPosition);
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
    window.requestAnimationFrame(() => ensureOverlayPreviewPosition());
  });
  elements.overlaySize.addEventListener("change", () => {
    callNative("setOverlaySize", Number(elements.overlaySize.value));
  });
  elements.overlayPreviewOrb.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || overlayPreviewDrag) return;
    overlayPreviewDrag = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: overlayPreviewPosition.x,
      startY: overlayPreviewPosition.y,
      moved: false
    };
    elements.overlayPreviewOrb.setPointerCapture(event.pointerId);
    elements.overlayPreviewOrb.classList.add("is-dragging");
  });
  elements.overlayPreviewOrb.addEventListener("pointermove", (event) => {
    if (!overlayPreviewDrag || event.pointerId !== overlayPreviewDrag.pointerId) return;
    const deltaX = event.clientX - overlayPreviewDrag.startClientX;
    const deltaY = event.clientY - overlayPreviewDrag.startClientY;
    if (!overlayPreviewDrag.moved && Math.hypot(deltaX, deltaY) < 5) return;
    overlayPreviewDrag.moved = true;
    event.preventDefault();
    setOverlayPreviewPosition(
      overlayPreviewDrag.startX + deltaX,
      overlayPreviewDrag.startY + deltaY,
      overlayPreviewPosition.side
    );
  });
  elements.overlayPreviewOrb.addEventListener("pointerup", finishOverlayPreviewDrag);
  elements.overlayPreviewOrb.addEventListener("pointercancel", finishOverlayPreviewDrag);
  elements.overlayPreviewOrb.addEventListener("lostpointercapture", finishOverlayPreviewDrag);
  window.addEventListener("pointerup", finishOverlayPreviewDrag);
  window.addEventListener("pointercancel", finishOverlayPreviewDrag);
  elements.overlayPreviewOrb.addEventListener("click", () => {
    if (suppressOverlayPreviewClick) return;
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
    window.requestAnimationFrame(updateOverlayPreviewTextPosition);
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
  window.addEventListener("resize", () => window.requestAnimationFrame(ensureOverlayPreviewPosition));

  window.VoiceApp = { receive, handleBack };
  applyFullState(loadInitialState());
  if (state.settings.testModeEnabled === true && native && typeof native.setTestModeEnabled === "function") {
    callNative("setTestModeEnabled", false);
  }
  callNative("ready");
})();
