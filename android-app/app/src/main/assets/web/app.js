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
      microphonePermission: false,
      testModeEnabled: false
    },
    resources: [],
    history: [],
    version: "",
    page: "recording",
    engineMode: null,
    historyQuery: "",
    historyTestOnly: false,
    historyVisibleCount: 40,
    latestTestRecordId: null,
    openTestRecordId: null,
    testAudioPositionMs: 0,
    testAudioPlaying: false
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
    recognitionAnnouncement: document.getElementById("recognitionAnnouncement"),
    copyTranscriptButton: document.getElementById("copyTranscriptButton"),
    resourceNotice: document.getElementById("resourceNotice"),
    activeModelsButton: document.getElementById("activeModelsButton"),
    activeModelsTitle: document.getElementById("activeModelsTitle"),
    activeModelsDetail: document.getElementById("activeModelsDetail"),
    testModeBanner: document.getElementById("testModeBanner"),
    testModeBannerText: document.getElementById("testModeBannerText"),
    openLatestTestButton: document.getElementById("openLatestTestButton"),
    historyCount: document.getElementById("historyCount"),
    historySearch: document.getElementById("historySearch"),
    historyFilterButtons: [...document.querySelectorAll("[data-history-filter]")],
    historyTestFilterCount: document.getElementById("historyTestFilterCount"),
    historyEmpty: document.getElementById("historyEmpty"),
    historyEmptyTitle: document.getElementById("historyEmptyTitle"),
    historyEmptyText: document.getElementById("historyEmptyText"),
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
    overlayEdgeHint: document.getElementById("overlayEdgeHint"),
    overlayPreviewText: document.getElementById("overlayPreviewText"),
    overlayPreviewOrb: document.getElementById("overlayPreviewOrb"),
    overlayWaveform: document.getElementById("overlayWaveform"),
    overlayWaveFront: document.getElementById("overlayWaveFront"),
    overlayWaveMiddle: document.getElementById("overlayWaveMiddle"),
    overlayWaveBack: document.getElementById("overlayWaveBack"),
    testModeSwitch: document.getElementById("testModeSwitch"),
    testModeDetails: document.getElementById("testModeDetails"),
    testStorageSummary: document.getElementById("testStorageSummary"),
    testModeEngineNote: document.getElementById("testModeEngineNote"),
    openTestRecordsButton: document.getElementById("openTestRecordsButton"),
    clearTestDataButton: document.getElementById("clearTestDataButton"),
    copyDiagnosticsButton: document.getElementById("copyDiagnosticsButton"),
    versionText: document.getElementById("versionText"),
    testDetailDialog: document.getElementById("testDetailDialog"),
    testDetailTitle: document.getElementById("testDetailTitle"),
    closeTestDetailButton: document.getElementById("closeTestDetailButton"),
    deleteTestRecordButton: document.getElementById("deleteTestRecordButton"),
    testAudioPlayButton: document.getElementById("testAudioPlayButton"),
    testAudioProgress: document.getElementById("testAudioProgress"),
    testAudioCurrentTime: document.getElementById("testAudioCurrentTime"),
    testAudioTotalTime: document.getElementById("testAudioTotalTime"),
    testAudioDurationBadge: document.getElementById("testAudioDurationBadge"),
    testDecisionText: document.getElementById("testDecisionText"),
    testDifferenceSummary: document.getElementById("testDifferenceSummary"),
    beforeCalibrationKicker: document.getElementById("beforeCalibrationKicker"),
    beforeCalibrationTitle: document.getElementById("beforeCalibrationTitle"),
    beforeCalibrationText: document.getElementById("beforeCalibrationText"),
    afterCalibrationBlock: document.getElementById("afterCalibrationBlock"),
    afterCalibrationKicker: document.getElementById("afterCalibrationKicker"),
    afterCalibrationTitle: document.getElementById("afterCalibrationTitle"),
    afterCalibrationText: document.getElementById("afterCalibrationText"),
    copyBeforeCalibrationButton: document.getElementById("copyBeforeCalibrationButton"),
    copyAfterCalibrationButton: document.getElementById("copyAfterCalibrationButton"),
    testRecordMeta: document.getElementById("testRecordMeta"),
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
  let previewAudioTimer = 0;
  let testDetailReturnFocus = null;
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
      state.engineMode = isCorrectionEngine(state.settings.engine) ? "correction" : "recognition";
      renderSettings();
      renderRecognition();
      showToast("预览：识别方案已切换");
      return undefined;
    }
    if (method === "setTestModeEnabled") {
      state.settings.testModeEnabled = Boolean(args[0]);
      renderSettings();
      renderRecognition();
      showToast(state.settings.testModeEnabled ? "测试模式已开启" : "测试模式已关闭，已有资料仍会保留");
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
        const hasCorrection = isCorrectionEngine(state.settings.engine);
        state.recognition = {
          active: true,
          capturing: false,
          phase: "processing",
          status: hasCorrection ? "正在使用校准模型整理文字…" : "正在生成最终文字…",
          text: state.recognition.text
        };
        renderRecognition();
        previewRecordingTimer = window.setTimeout(() => {
          const rawText = "我今天要 review this project，然后 update the README and fix the login bug。";
          const secondPassText = "我今天要 review this project，今天下午三点开会，然后 update the README and fix the login bug。";
          const id = Date.now();
          state.recognition = { active: false, capturing: false, phase: "idle", status: "识别完成", text: rawText };
          const item = { id, text: rawText, createdAt: new Date().toISOString().replace("T", " ").slice(0, 19), engine: state.settings.engine };
          if (state.settings.testModeEnabled) {
            item.test = {
              rawText,
              secondPassText: hasCorrection ? secondPassText : null,
              selected: hasCorrection ? (state.settings.engine === "local_dual_whisper_acft" ? "second_pass" : "realtime_draft") : "single_result",
              audioAvailable: true,
              durationMs: 12400,
              audioBytes: 1232896
            };
            state.latestTestRecordId = id;
          }
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
      if (Number(state.openTestRecordId) === Number(args[0])) closeTestDetail();
      renderHistory();
      renderSettings();
      return undefined;
    }
    if (method === "clearHistory") { state.history = []; closeTestDetail(); renderHistory(); renderSettings(); return undefined; }
    if (method === "clearTestData") {
      state.history = state.history.map((item) => item.test ? { id: item.id, text: item.text, createdAt: item.createdAt, engine: item.engine } : item);
      state.latestTestRecordId = null;
      closeTestDetail();
      renderAll();
      showToast("测试录音和识别对照已清空，最终文字仍保留");
      return undefined;
    }
    if (method === "copyText" || method === "copyHistory" || method === "copyDiagnostics" || method === "copyTestText") { showToast("预览：已模拟复制"); return undefined; }
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
      settings: { ...state.settings, testModeEnabled: true },
      resources: [
        { id: "zipformer-bilingual", name: "Zipformer｜中英双语实时模型", purpose: "边说边显示中文、英文和中英混说结果", version: "2024-03-20-exp32-int8", totalBytes: 60142871, presentBytes: 60142871, installedBytes: 60142871, status: "available", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 11717148672, errorMessage: "" },
        { id: "paraformer", name: "Paraformer｜中英双语整段校正模型", purpose: "停止后重新校正完整句子，改善长句连贯度", version: "2024-03-09-small-int8", totalBytes: 81904027, presentBytes: 81904027, installedBytes: 81904027, status: "available", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 11717148672, errorMessage: "" },
        { id: "qwen3-asr-0.6b-int8", name: "Qwen3-ASR 0.6B INT8 高质量校正模型", purpose: "停止后高质量校正中英文和中英混说；下载较大、处理较慢", version: "2026-03-25-int8", totalBytes: 987015347, presentBytes: 0, installedBytes: 0, status: "missing", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 0, errorMessage: "" },
        { id: "whisper-acft-multilingual-74", name: "Whisper ACFT｜多语言整段模型", purpose: "停止后对原始录音进行完整识别；组合方案中作为第二次完整识别", version: "base-74m-q8_0-acft", totalBytes: 81768602, presentBytes: 0, installedBytes: 0, status: "missing", speedBytesPerSecond: 0, etaSeconds: 0, freeBytes: 0, errorMessage: "" }
      ],
      history: [
        {
          id: 3,
          text: "我今天要 review this project，然后 update the README and fix the login bug。",
          createdAt: "2026-08-20 14:32:00",
          engine: "local_dual",
          test: {
            rawText: "我今天要 review this project，然后 update the README and fix the login bug。",
            secondPassText: "我今天要 review this project，今天下午三点开会，然后 update the README and fix the login bug。",
            selected: "realtime_draft",
            audioAvailable: true,
            durationMs: 12840,
            audioBytes: 1268777
          }
        },
        { id: 2, text: "Please create a new note and copy this sentence.", createdAt: "2026-08-18 17:16:00", engine: "local_dual_qwen" },
        { id: 1, text: "这是一条较长的模拟历史记录，用于检查卡片换行、复制按钮和删除按钮在窄屏幕上的排版。", createdAt: "2026-08-18 16:03:00", engine: "local_zipformer" }
      ],
      version: "独立 UI 预览"
    };
  }

  function applyFullState(next) {
    if (!next) return;
    if (next.recognition) state.recognition = next.recognition;
    if (next.settings) {
      const previousEngine = state.settings.engine;
      state.settings = next.settings;
      if (state.settings.engine !== previousEngine) {
        state.engineMode = isCorrectionEngine(state.settings.engine) ? "correction" : "recognition";
      }
    }
    if (Array.isArray(next.resources)) state.resources = next.resources;
    if (Array.isArray(next.history)) {
      state.history = next.history;
      updateLatestTestRecordId();
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
        updateLatestTestRecordId();
        if (state.openTestRecordId != null && !currentTestRecord()) closeTestDetail();
        renderHistory();
        renderSettings();
        renderRecognition();
        break;
      case "testAudio":
        receiveTestAudioState(event);
        break;
      case "settings":
        if (event.settings) {
          const previousEngine = state.settings.engine;
          state.settings = event.settings;
          if (state.settings.engine !== previousEngine) {
            state.engineMode = isCorrectionEngine(state.settings.engine) ? "correction" : "recognition";
          }
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
    const text = typeof recognition.text === "string" ? recognition.text : "";
    const missingRequiredResources = hasMissingRequiredResources();
    elements.statusText.textContent = missingRequiredResources && !active
      ? "需要先下载所需离线模型"
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
      ? phase === "processing" ? "正在整理文字" : "停止识别"
      : missingRequiredResources ? "请先下载模型" : "开始识别";
    elements.cancelButton.classList.toggle("is-hidden", !active);
    elements.transcriptText.textContent = text || "识别文字会显示在这里";
    elements.transcriptText.classList.toggle("is-placeholder", !text);
    if (previousRecognitionActive && !active) {
      elements.recognitionAnnouncement.textContent = text ? "识别完成，文字已保存。" : "本次识别已结束。";
    }
    previousRecognitionActive = active;
    waveform.setActive(capturing);
    elements.resourceNotice.classList.toggle("is-hidden", !missingRequiredResources);
    elements.engineInputs.forEach((input) => { input.disabled = active; });
    elements.engineModeButtons.forEach((button) => { button.disabled = active; });
    elements.testModeSwitch.disabled = active;
    const modelCopy = {
      local_dual: ["Zipformer ＋ Paraformer", "2 套模型 · 实时出字，停止后分段校正"],
      local_dual_qwen: ["Zipformer ＋ Qwen3-ASR", "2 套模型 · 实时出字，停止后高质量校正"],
      local_dual_whisper_acft: ["Zipformer ＋ Whisper ACFT", "2 套模型 · 实时出字，停止后进行第二次完整识别"],
      local_zipformer: ["仅 Zipformer", "1 套模型 · 只做实时识别"],
      local_paraformer: ["仅 Paraformer", "1 套模型 · 停止后生成全文"],
      local_qwen: ["仅 Qwen3-ASR", "1 套模型 · 停止后高质量生成全文"],
      local_whisper_acft: ["Whisper ACFT 多语言", "1 套模型 · 停止后识别中英文混说"]
    }[state.settings.engine] || ["正在读取模型", "请稍候"];
    elements.activeModelsTitle.textContent = modelCopy[0];
    elements.activeModelsDetail.textContent = modelCopy[1];
    const testModeEnabled = Boolean(state.settings.testModeEnabled);
    const hasCorrection = isCorrectionEngine(state.settings.engine);
    const latestTestRecord = state.history.find((item) => Number(item.id) === Number(state.latestTestRecordId) && item.test);
    const latestHasSecondPass = Boolean(testSecondPassText(latestTestRecord?.test));
    const latestUsesWhisperSecondPass = Boolean(latestTestRecord && isWhisperSecondPassEngine(latestTestRecord.engine));
    const currentUsesWhisperSecondPass = isWhisperSecondPassEngine(state.settings.engine);
    const usesSystemRecognition = state.settings.engine === "system";
    elements.testModeBanner.classList.toggle("is-hidden", !testModeEnabled);
    elements.openLatestTestButton.classList.toggle("is-hidden", !latestTestRecord || active);
    elements.testModeBannerText.textContent = usesSystemRecognition
      ? "手机系统识别不保存测试录音，请切换本地方案"
      : latestTestRecord && !active
      ? latestHasSecondPass
        ? latestUsesWhisperSecondPass
          ? "测试资料已保存，可回听录音并比较实时初稿与第二次完整识别结果"
          : "测试资料已保存，可回听录音并查看校准前后文字"
        : "测试资料已保存，可回听录音并查看识别文字"
      : phase === "processing"
        ? hasCorrection
          ? currentUsesWhisperSecondPass
            ? "正在保留录音，并进行第二次完整识别"
            : "正在保留录音，并生成校准前后对照"
          : "正在保留录音和本次识别文字"
        : hasCorrection
          ? currentUsesWhisperSecondPass
            ? "本次将保留实时初稿、第二次完整识别结果和录音"
            : "本次将保留校准前文字、校准后文字和录音"
          : "本次将保留识别文字和录音，不生成前后对照";
  }

  function renderHistory() {
    const query = state.historyQuery.trim().toLocaleLowerCase("zh-CN");
    const testCount = state.history.filter((item) => item.test).length;
    const scoped = state.historyTestOnly ? state.history.filter((item) => item.test) : state.history;
    const filtered = scoped.filter((item) => [item.text, item.test?.rawText, item.test?.secondPassText]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase("zh-CN")
      .includes(query));
    const visible = filtered.slice(0, state.historyVisibleCount).reverse();
    elements.historyCount.textContent = state.historyTestOnly
      ? `${testCount} 条测试记录`
      : testCount
        ? `${state.history.length} 条记录 · ${testCount} 条含测试资料`
        : `${state.history.length} 条记录`;
    elements.historyTestFilterCount.textContent = String(testCount);
    elements.historyFilterButtons.forEach((button) => {
      const active = button.dataset.historyFilter === (state.historyTestOnly ? "test" : "all");
      button.setAttribute("aria-selected", String(active));
    });
    elements.historyEmptyTitle.textContent = state.historyTestOnly ? "还没有测试记录" : "识别完成后会出现在这里";
    elements.historyEmptyText.textContent = state.historyTestOnly
      ? "请先在设置中开启识别测试模式；之后录音和用于对照的两份识别文字会保存在这里。"
      : "最多保存 500 条；本地识别不上传录音，系统识别取决于手机语音服务。";
    elements.clearHistoryButton.disabled = state.history.length === 0;
    elements.historyEmpty.classList.toggle("is-hidden", filtered.length > 0);
    elements.historyList.replaceChildren(...visible.map(createHistoryCard));
    elements.loadMoreHistory.classList.toggle("is-hidden", visible.length >= filtered.length);
  }

  function createHistoryCard(item) {
    if (item.test) return createTestHistoryCard(item);
    const card = document.createElement("article");
    card.className = "history-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", "复制这条识别记录");
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
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        copyCard();
      }
    });
    [copy, remove].forEach((button) => button.addEventListener("click", (event) => event.stopPropagation()));
    card.append(remove, text, footer);
    return card;
  }

  function createTestHistoryCard(item) {
    const card = document.createElement("article");
    card.className = "history-card has-test-record";
    const test = item.test;
    const hasCorrection = testSecondPassText(test).length > 0;
    const usesWhisperSecondPass = isWhisperSecondPassEngine(item.engine);
    const diff = hasCorrection ? getDiffStats(test.rawText, testSecondPassText(test)) : { addedCount: 0, removedCount: 0 };

    const head = document.createElement("div");
    head.className = "history-test-head";
    const badge = document.createElement("span");
    badge.className = "history-test-badge";
    badge.textContent = hasCorrection ? "测试记录" : "仅识别测试";
    const difference = document.createElement("span");
    difference.className = "history-test-difference";
    difference.textContent = hasCorrection
      ? diff.addedCount > 0
        ? `${usesWhisperSecondPass ? "二次识别" : "校准"}新增 ${diff.addedCount} 字`
        : usesWhisperSecondPass ? "二次识别无新增" : "校准无新增"
      : "没有第二份识别结果";
    head.append(badge, difference);

    const text = document.createElement("p");
    text.className = "history-text";
    text.textContent = String(item.text || "");

    const audio = document.createElement("span");
    audio.className = "history-test-audio";
    audio.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18V6l10-2v12"></path><circle cx="6" cy="18" r="3"></circle><circle cx="16" cy="16" r="3"></circle></svg>';
    const audioCopy = document.createElement("span");
    audioCopy.textContent = test.audioAvailable ? `原始录音 ${formatDuration(test.durationMs)}` : "没有可用录音";
    audio.append(audioCopy);

    const meta = document.createElement("p");
    meta.className = "history-meta";
    meta.textContent = `${formatDate(item.createdAt)}　${engineName(item.engine)}`;
    const copy = iconActionButton("复制最终文字", "copy", () => callNative("copyHistory", Number(item.id)));
    copy.classList.add("history-test-copy");
    const open = document.createElement("button");
    open.type = "button";
    open.className = "history-test-open";
    open.textContent = hasCorrection ? (usesWhisperSecondPass ? "查看二次识别对照" : "查看校准对照") : "查看测试详情";
    open.addEventListener("click", () => openTestDetail(item.id));
    const actions = document.createElement("div");
    actions.className = "history-test-actions";
    actions.append(copy, open);
    const footer = document.createElement("div");
    footer.className = "history-test-footer";
    footer.append(meta, actions);

    const remove = iconActionButton("删除这条测试记录", "close", () => {
      openConfirm("删除这条测试记录？最终文字、测试文字和录音都会删除，且无法恢复。", "确认删除", () => callNative("deleteHistory", Number(item.id)));
    });
    remove.classList.add("history-remove");
    card.append(remove, head, text, audio, footer);
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
      state.engineMode = isCorrectionEngine(state.settings.engine) ? "correction" : "recognition";
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
    window.requestAnimationFrame(() => ensureOverlayPreviewPosition());
    elements.overlayPreviewText.classList.toggle("is-hidden", state.settings.overlayTextEnabled === false);
    elements.overlayStatus.textContent = state.settings.overlayEnabled
      ? "悬浮小球已开启；点击开始或停止识别，长按可关闭。"
      : state.settings.overlayPermission
        ? "权限已允许，开启后可在其他应用上方识别。"
        : "首次开启时需要允许显示在其他应用上层。";
    const testModeEnabled = Boolean(state.settings.testModeEnabled);
    const testRecords = state.history.filter((item) => item.test);
    const testBytes = testRecords.reduce((total, item) => total + Math.max(0, Number(item.test?.audioBytes) || 0), 0);
    elements.testModeSwitch.checked = testModeEnabled;
    elements.testModeDetails.classList.toggle("is-hidden", !testModeEnabled && testRecords.length === 0);
    elements.testStorageSummary.textContent = testRecords.length
      ? `${testRecords.length} 条测试记录 · ${formatBytes(testBytes)}`
      : "还没有测试记录";
    elements.clearTestDataButton.disabled = testRecords.length === 0;
    elements.openTestRecordsButton.disabled = testRecords.length === 0;
    elements.testModeEngineNote.textContent = !testModeEnabled
      ? "测试模式已关闭，不会新增录音或识别对照；已有测试资料仍保留在本机。"
      : state.settings.engine === "system"
        ? "手机系统识别不保存测试录音，请切换本地方案。"
        : isWhisperSecondPassEngine(state.settings.engine)
        ? "当前方案会同时保存实时初稿、第二次完整识别结果和录音。"
        : isCorrectionEngine(state.settings.engine)
          ? "当前方案会同时保存校准前文字、校准后文字和录音。"
          : "当前是“仅识别”方案，只会保存识别文字和录音，不会生成前后对照。";
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

  function segmentMixedText(value) {
    const text = String(value || "");
    if (!text) return [];
    if (typeof Intl.Segmenter === "function") {
      const segmenter = new Intl.Segmenter("zh-CN", { granularity: "word" });
      return [...segmenter.segment(text)].map((entry) => entry.segment);
    }
    return text.match(/[\p{Script=Han}]|[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*|\s+|[^\s]/gu) || [text];
  }

  function diffText(before, after) {
    const left = segmentMixedText(before);
    const right = segmentMixedText(after);
    const matrix = Array.from({ length: left.length + 1 }, () => new Uint16Array(right.length + 1));
    for (let i = left.length - 1; i >= 0; i -= 1) {
      for (let j = right.length - 1; j >= 0; j -= 1) {
        matrix[i][j] = left[i] === right[j]
          ? matrix[i + 1][j + 1] + 1
          : Math.max(matrix[i + 1][j], matrix[i][j + 1]);
      }
    }
    const result = [];
    let i = 0;
    let j = 0;
    while (i < left.length && j < right.length) {
      if (left[i] === right[j]) {
        result.push({ type: "same", value: left[i] });
        i += 1;
        j += 1;
      } else if (matrix[i + 1][j] >= matrix[i][j + 1]) {
        result.push({ type: "removed", value: left[i] });
        i += 1;
      } else {
        result.push({ type: "added", value: right[j] });
        j += 1;
      }
    }
    while (i < left.length) result.push({ type: "removed", value: left[i++] });
    while (j < right.length) result.push({ type: "added", value: right[j++] });
    return result;
  }

  function countVisibleCharacters(value) {
    return [...String(value || "").replace(/\s/gu, "")].length;
  }

  function getDiffStats(before, after) {
    const parts = diffText(before, after);
    return {
      parts,
      addedCount: parts.filter((part) => part.type === "added").reduce((total, part) => total + countVisibleCharacters(part.value), 0),
      removedCount: parts.filter((part) => part.type === "removed").reduce((total, part) => total + countVisibleCharacters(part.value), 0)
    };
  }

  function renderTextDifference(target, parts, view) {
    const fragment = document.createDocumentFragment();
    parts.forEach((part) => {
      if (view === "before" && part.type === "added") return;
      if (view === "after" && part.type === "removed") return;
      if (part.type === "same") {
        fragment.append(document.createTextNode(part.value));
        return;
      }
      const node = document.createElement(part.type === "added" ? "mark" : "del");
      node.className = part.type === "added" ? "diff-added" : "diff-removed";
      node.textContent = part.value;
      fragment.append(node);
    });
    target.replaceChildren(fragment);
  }

  function formatDuration(milliseconds) {
    const totalSeconds = Math.max(0, Math.round((Number(milliseconds) || 0) / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function currentTestRecord() {
    return state.history.find((item) => Number(item.id) === Number(state.openTestRecordId) && item.test) || null;
  }

  function openTestDetail(id) {
    const item = state.history.find((entry) => Number(entry.id) === Number(id) && entry.test);
    if (!item) {
      showToast("这条记录没有测试资料");
      return;
    }
    testDetailReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    state.openTestRecordId = item.id;
    state.testAudioPositionMs = 0;
    state.testAudioPlaying = false;
    const test = item.test;
    const secondPassText = testSecondPassText(test);
    const hasCorrection = secondPassText.length > 0;
    const usesWhisperSecondPass = isWhisperSecondPassEngine(item.engine);
    elements.testDetailTitle.textContent = hasCorrection
      ? usesWhisperSecondPass ? "二次识别对照" : "校准对照"
      : "识别测试详情";
    elements.testDifferenceSummary.classList.toggle("is-neutral", !hasCorrection);
    elements.afterCalibrationBlock.classList.toggle("is-hidden", !hasCorrection);
    elements.beforeCalibrationKicker.textContent = hasCorrection
      ? usesWhisperSecondPass ? "Zipformer 实时识别" : "实时识别"
      : "单模型识别";
    elements.beforeCalibrationTitle.textContent = hasCorrection
      ? usesWhisperSecondPass ? "实时初稿" : "校准前"
      : "识别文字";
    elements.afterCalibrationKicker.textContent = usesWhisperSecondPass ? "第二次完整识别" : "校准模型";
    elements.afterCalibrationTitle.textContent = usesWhisperSecondPass ? "二次整段识别结果" : "校准后";
    if (hasCorrection) {
      const diff = getDiffStats(test.rawText, secondPassText);
      renderTextDifference(elements.beforeCalibrationText, diff.parts, "before");
      renderTextDifference(elements.afterCalibrationText, diff.parts, "after");
      elements.testDecisionText.textContent = test.selected === "second_pass"
        ? usesWhisperSecondPass ? "二次识别结果" : "校准后文字"
        : usesWhisperSecondPass ? "实时初稿" : "校准前文字";
      elements.testDifferenceSummary.textContent = diff.addedCount || diff.removedCount
        ? [`新增 ${diff.addedCount} 字`, `删除 ${diff.removedCount} 字`].filter((value) => !value.includes(" 0 ")).join(" · ")
        : "前后相同";
    } else {
      elements.beforeCalibrationText.replaceChildren(document.createTextNode(String(test.rawText || item.text || "")));
      elements.afterCalibrationText.replaceChildren();
      elements.testDecisionText.textContent = "识别文字";
      elements.testDifferenceSummary.textContent = "没有第二份识别结果";
    }
    elements.testAudioProgress.max = String(Math.max(1, Number(test.durationMs) || 1));
    elements.testAudioProgress.value = "0";
    elements.testAudioTotalTime.textContent = formatDuration(test.durationMs);
    elements.testAudioDurationBadge.textContent = formatDuration(test.durationMs);
    elements.testRecordMeta.textContent = `${formatDate(item.createdAt)}　${engineName(item.engine)}　录音 ${formatBytes(test.audioBytes)}`;
    setTestAudioPlaying(false);
    updateTestAudioUi();
    if (!elements.testDetailDialog.open) elements.testDetailDialog.showModal();
    elements.closeTestDetailButton.focus();
  }
  function updateTestAudioUi() {
    const item = currentTestRecord();
    const duration = Math.max(1, Number(item?.test?.durationMs) || 1);
    state.testAudioPositionMs = Math.min(duration, Math.max(0, Number(state.testAudioPositionMs) || 0));
    elements.testAudioProgress.value = String(state.testAudioPositionMs);
    elements.testAudioCurrentTime.textContent = formatDuration(state.testAudioPositionMs);
  }

  function setTestAudioPlaying(playing) {
    state.testAudioPlaying = Boolean(playing);
    elements.testAudioPlayButton.setAttribute("aria-pressed", String(state.testAudioPlaying));
    elements.testAudioPlayButton.setAttribute("aria-label", state.testAudioPlaying ? "暂停测试录音" : "播放测试录音");
  }

  function receiveTestAudioState(event) {
    if (Number(event.recordId) !== Number(state.openTestRecordId)) return;
    if (Number.isFinite(Number(event.durationMs)) && Number(event.durationMs) > 0) {
      elements.testAudioProgress.max = String(Number(event.durationMs));
      elements.testAudioTotalTime.textContent = formatDuration(event.durationMs);
      elements.testAudioDurationBadge.textContent = formatDuration(event.durationMs);
    }
    state.testAudioPositionMs = Number(event.positionMs) || 0;
    setTestAudioPlaying(Boolean(event.playing));
    updateTestAudioUi();
  }

  function stopTestAudioPlayback(reset = false) {
    window.clearInterval(previewAudioTimer);
    previewAudioTimer = 0;
    if (native && typeof native.stopTestAudio === "function") callNative("stopTestAudio");
    setTestAudioPlaying(false);
    if (reset) state.testAudioPositionMs = 0;
    if (elements.testDetailDialog.open) updateTestAudioUi();
  }

  function toggleTestAudioPlayback() {
    const item = currentTestRecord();
    if (!item?.test?.audioAvailable) {
      showToast("这条记录没有可播放的录音");
      return;
    }
    if (native && typeof native.toggleTestAudio === "function") {
      callNative("toggleTestAudio", Number(item.id), Math.round(state.testAudioPositionMs));
      return;
    }
    if (state.testAudioPlaying) {
      window.clearInterval(previewAudioTimer);
      previewAudioTimer = 0;
      setTestAudioPlaying(false);
      return;
    }
    const duration = Math.max(1, Number(item.test.durationMs) || 1);
    if (state.testAudioPositionMs >= duration) state.testAudioPositionMs = 0;
    setTestAudioPlaying(true);
    previewAudioTimer = window.setInterval(() => {
      state.testAudioPositionMs += 120;
      if (state.testAudioPositionMs >= duration) {
        state.testAudioPositionMs = duration;
        updateTestAudioUi();
        window.clearInterval(previewAudioTimer);
        previewAudioTimer = 0;
        setTestAudioPlaying(false);
        return;
      }
      updateTestAudioUi();
    }, 120);
  }
  function closeTestDetail() {
    stopTestAudioPlayback(true);
    if (elements.testDetailDialog.open) elements.testDetailDialog.close();
    state.openTestRecordId = null;
    const target = testDetailReturnFocus;
    testDetailReturnFocus = null;
    if (target?.isConnected) target.focus();
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
    if (elements.testDetailDialog.open) {
      closeTestDetail();
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
      local_dual_whisper_acft: ["zipformer-bilingual", "whisper-acft-multilingual-74"],
      local_zipformer: ["zipformer-bilingual"],
      local_paraformer: ["paraformer"],
      local_qwen: ["qwen3-asr-0.6b-int8"],
      local_whisper_acft: ["whisper-acft-multilingual-74"]
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
      local_dual_whisper_acft: "实时＋Whisper 二次识别",
      local_zipformer: "仅实时",
      local_paraformer: "仅整段",
      local_qwen: "仅 Qwen",
      local_whisper_acft: "Whisper ACFT"
    }[engine] || "未知方式";
  }

  function isCorrectionEngine(engine) {
    return ["local_dual", "local_dual_qwen", "local_dual_whisper_acft"].includes(String(engine || ""));
  }

  function isWhisperSecondPassEngine(engine) {
    return String(engine || "") === "local_dual_whisper_acft";
  }

  function testSecondPassText(test) {
    if (!test) return "";
    return typeof test.secondPassText === "string" ? test.secondPassText : "";
  }

  function updateLatestTestRecordId() {
    const latest = state.history.find((item) => item && item.test);
    state.latestTestRecordId = latest ? latest.id : null;
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
  elements.resourceNotice.addEventListener("click", () => navigate("settings"));
  elements.activeModelsButton.addEventListener("click", () => navigate("settings"));
  elements.openLatestTestButton.addEventListener("click", () => openTestDetail(state.latestTestRecordId));
  elements.historySearch.addEventListener("input", (event) => {
    state.historyQuery = event.target.value || "";
    state.historyVisibleCount = 40;
    renderHistory();
  });
  elements.historyFilterButtons.forEach((button) => button.addEventListener("click", () => {
    state.historyTestOnly = button.dataset.historyFilter === "test";
    state.historyVisibleCount = 40;
    renderHistory();
    if (state.historyTestOnly) {
      requestAnimationFrame(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: reducedMotion.matches ? "auto" : "smooth" }));
    }
  }));
  elements.loadMoreHistory.addEventListener("click", () => {
    state.historyVisibleCount += 40;
    renderHistory();
  });
  elements.clearHistoryButton.addEventListener("click", () => {
    if (!state.history.length) return;
    openConfirm("清空全部识别记录？所有记录都会从这台手机中永久删除。", "确认清空", () => callNative("clearHistory"));
  });
  elements.engineInputs.forEach((input) => input.addEventListener("change", () => {
    if (state.recognition.active) {
      renderSettings();
      showToast("识别结束后才能切换方案");
      return;
    }
    if (input.checked) callNative("setEngine", input.value);
  }));
  elements.engineModeButtons.forEach((button) => button.addEventListener("click", () => {
    if (state.recognition.active) {
      showToast("识别结束后才能切换方案");
      return;
    }
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
  elements.testModeSwitch.addEventListener("change", () => {
    if (state.recognition.active) {
      elements.testModeSwitch.checked = Boolean(state.settings.testModeEnabled);
      showToast("识别结束后再更改测试模式");
      return;
    }
    callNative("setTestModeEnabled", elements.testModeSwitch.checked);
  });
  elements.openTestRecordsButton.addEventListener("click", () => {
    state.historyQuery = "";
    state.historyTestOnly = true;
    elements.historySearch.value = "";
    navigate("history");
    renderHistory();
    requestAnimationFrame(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: reducedMotion.matches ? "auto" : "smooth" }));
  });
  elements.clearTestDataButton.addEventListener("click", () => {
    if (!state.history.some((item) => item.test)) return;
    openConfirm(
      "清空全部测试资料？录音和测试文字将删除，最终识别文字会继续保留在普通记录中。",
      "清空测试资料",
      () => callNative("clearTestData")
    );
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
  elements.closeTestDetailButton.addEventListener("click", closeTestDetail);
  elements.testAudioPlayButton.addEventListener("click", toggleTestAudioPlayback);
  elements.testAudioProgress.addEventListener("input", () => {
    state.testAudioPositionMs = Number(elements.testAudioProgress.value) || 0;
    updateTestAudioUi();
  });
  elements.testAudioProgress.addEventListener("change", () => {
    const item = currentTestRecord();
    if (item && native && typeof native.seekTestAudio === "function") {
      callNative("seekTestAudio", Number(item.id), Math.round(state.testAudioPositionMs));
    }
  });
  elements.copyBeforeCalibrationButton.addEventListener("click", () => {
    const item = currentTestRecord();
    if (item) callNative("copyTestText", item.test.rawText);
  });
  elements.copyAfterCalibrationButton.addEventListener("click", () => {
    const item = currentTestRecord();
    if (item) callNative("copyTestText", testSecondPassText(item.test));
  });
    elements.deleteTestRecordButton.addEventListener("click", () => {
      const item = currentTestRecord();
      if (!item) return;
      const hasCorrection = testSecondPassText(item.test).length > 0;
      openConfirm(
        hasCorrection
          ? "删除这条测试记录？最终文字、测试文字和录音都会删除，且无法恢复。"
          : "删除这条测试记录？识别文字和录音都会删除，且无法恢复。",
        "确认删除",
        () => callNative("deleteHistory", Number(item.id))
      );
    });
  elements.testDetailDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeTestDetail();
  });
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
    if (document.hidden) stopTestAudioPlayback();
  });
  window.addEventListener("resize", () => window.requestAnimationFrame(ensureOverlayPreviewPosition));

  window.VoiceApp = { receive, handleBack };
  applyFullState(loadInitialState());
  callNative("ready");
})();
