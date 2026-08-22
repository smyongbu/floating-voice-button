"use strict";

const PREVIEW_MODE = new URLSearchParams(window.location.search).get("preview") === "1";
let previewDownloadState = "not_started";
let previewDownloadPercent = 0;
let previewRealtimeModel = "streaming-paraformer-bilingual-zh-en";
const previewApi = {
  async get_initial_state() {
    const modelDetails = [
      [486000000, "4 核 64 位 CPU、4 GB 内存", "6 至 8 核 CPU、8 GB 内存", "CPU 可用；GPU 需要 NVIDIA CUDA 12 和 cuDNN 9"],
      [982000000, "4 核 64 位 CPU、8 GB 内存", "6 核以上 CPU、16 GB 内存", "不需要显卡；NVIDIA CUDA 可选"],
      [1517290464, "4 核 64 位 CPU、12 GB 内存", "8 核 CPU、16 GB 内存，或支持 Vulkan 的显卡", "支持 Intel、AMD、NVIDIA Vulkan；不可用时回退 CPU"],
    ];
    const localModels = [
      ["faster-whisper-small", "Faster-Whisper Small", "多语言自动检测，并支持时间戳"],
      ["qwen3-asr-0.6b-int8", "Qwen3-ASR 0.6B INT8", "兼顾多种语言、中文方言、歌词和说唱"],
      ["qwen3-asr-1.7b-q5km", "Qwen3-ASR 1.7B Q5_K_M", "识别能力更强，可自动检测 30 种语言"],
    ].map(([model_id, name, summary], index) => {
      const [size_bytes, minimum, recommended, gpu] = modelDetails[index];
      const downloadable = model_id.startsWith("qwen3-asr-1.7b-q5km");
      const downloadComplete = downloadable && previewDownloadState === "completed";
      return {
        model_id, name, summary, size_bytes, minimum, recommended, gpu,
        language_support: "中文、英文及中英混说",
        size_on_disk_bytes: downloadable && !downloadComplete ? 0 : size_bytes,
        available: !downloadable || downloadComplete,
        downloadable,
        status: downloadable && !downloadComplete ? "可下载" : "已安装",
        status_message: downloadable ? "模型约 1.52 GB，下载并校验后可使用。" : "已安装，可直接使用。",
        install_size: downloadable ? "约 1.52 GB" : "",
        resource_status: downloadable ? {
          state: previewDownloadState, installed: downloadComplete, target_exists: downloadComplete,
          verified: downloadComplete,
          downloaded_bytes: Math.round(1517290464 * previewDownloadPercent / 100),
          installed_bytes: downloadComplete ? 1517290464 : 0,
          total_bytes: 1517290464, percent: previewDownloadPercent,
          version: "handy-computer/Qwen3-ASR-1.7B-gguf@92282af1",
        } : null,
      };
    });
    return {
      ok: true,
      data: {
        appearance: {
          color: "#2563EB", opacity: 100, hotkey: "Ctrl+Alt+Space",
          standby_enabled: false, standby_confidence: 80,
          live_transcript_visible: true, auto_paste_enabled: true,
          default_color: "#2563EB", default_opacity: 100,
          default_hotkey: "Ctrl+Alt+Space", default_standby_enabled: false,
          default_standby_confidence: 80,
          default_live_transcript_visible: true, default_auto_paste_enabled: true,
        },
        history: { available: true, entries: [], signature: [0, 0] },
        model: {
          engine_id: "local:qwen3-asr-1.7b-q5km", fallback_model: "faster-whisper-small",
          preference: "auto", realtime_model: previewRealtimeModel,
          realtime_models: [
            {
              model_id: "streaming-paraformer-bilingual-zh-en",
              name: "Streaming Paraformer",
              available: true,
            },
            {
              model_id: "zipformer-bilingual-zh-en-exp32-int8",
              name: "Zipformer",
              available: true,
            },
          ],
          local_models: localModels, providers: [],
        },
      },
    };
  },
  async manage_local_model_resource(_modelId, action) {
    if (action === "start") previewDownloadState = "downloading";
    if (action === "pause") previewDownloadState = "paused";
    if (action === "delete") {
      previewDownloadState = "not_started";
      previewDownloadPercent = 0;
    }
    if (action === "status" && previewDownloadState === "downloading") {
      previewDownloadPercent = Math.min(100, previewDownloadPercent + 18);
      if (previewDownloadPercent >= 100) previewDownloadState = "completed";
    }
    const response = await this.get_initial_state();
    return { ok: true, data: response.data.model, message: "模型状态已更新。" };
  },
  async save_recognition_settings(engineId, fallbackModel, preference, realtimeModel) {
    previewRealtimeModel = realtimeModel;
    const response = await this.get_initial_state();
    Object.assign(response.data.model, {
      engine_id: engineId,
      fallback_model: fallbackModel,
      preference,
      realtime_model: realtimeModel,
    });
    return { ok: true, data: response.data.model, message: "识别设置已保存并应用。" };
  },
};

function getLocalApi() {
  return PREVIEW_MODE ? previewApi : window.pywebview?.api;
}

const COLOR_PATTERN = /^#[0-9A-F]{6}$/;
const DEFAULT_REALTIME_MODEL = "streaming-paraformer-bilingual-zh-en";

const state = {
  saved: { color: "#2563EB", opacity: 100, hotkey: "Ctrl+Alt+Space", standby: false, transcript: true, autoPaste: true, confidence: 80 },
  draft: { color: "#2563EB", opacity: 100, hotkey: "Ctrl+Alt+Space", standby: false, transcript: true, autoPaste: true, confidence: 80 },
  defaults: { color: "#2563EB", opacity: 100, hotkey: "Ctrl+Alt+Space", standby: false, transcript: true, autoPaste: true, confidence: 80 },
  appearanceBusy: false,
  model: {
    engine_id: "local:faster-whisper-small",
    realtime_model: DEFAULT_REALTIME_MODEL,
    realtime_models: [],
    fallback_model: "faster-whisper-small",
    preference: "auto",
    local_models: [],
    providers: [],
  },
  modelBusy: false,
  testBusy: false,
  controlTestActive: false,
  localEngineId: null,
  onlineEngineId: null,
  entries: [],
  selectedId: null,
  signature: [0, 0],
  historyAvailable: true,
  historyRequest: 0,
  historyBusy: false,
  confirmAction: null,
  confirmFocus: null,
  searchTimer: null,
  pollTimer: null,
  modelResourceTimer: null,
  toastTimer: null,
  bridgeAttempts: 0,
};

const elements = {};
let rootRule = null;
let bridgeStarted = false;
let recordingPreviewFrame = null;
let recordingPreviewLastTime = 0;
let recordingPreviewPhase = 0;
let recordingMotionQuery = null;

function collectElements() {
  const ids = [
    "appearanceView", "localModelView", "onlineModelView", "historyView", "saveState", "colorPicker", "colorText",
    "colorError", "opacityRange", "opacityOutput", "hotkeyInput", "hotkeyError",
    "hotkeyTestButton", "hotkeyStatus", "standbyToggle", "transcriptToggle", "autoPasteToggle",
    "standbyConfidence", "standbyConfidenceValue", "controlWordTestButton", "controlWordTestStatus",
    "resetButton", "saveButton",
    "navHistoryCount", "clearButton", "copyAllButton", "historySearch", "historyCount",
    "refreshButton", "historyList", "historyEmpty", "historyDetail",
    "detailPlaceholder", "detailContent", "detailTime", "detailText",
    "deleteButton", "copyButton", "confirmModal", "modalTitle", "modalMessage",
    "modalCancel", "modalConfirm", "toast", "toastMessage", "bootScreen",
    "localModelState", "onlineModelState", "localEngineOptions", "onlineEngineOptions",
    "realtimeModelOptions", "sidebarPrivacyText",
    "localModelList", "deviceOptions", "fallbackModel",
    "providerList", "modelTestStatus", "localModelSaveButton", "onlineModelSaveButton",
    "localRecognitionSummary", "onlineRecognitionSummary", "recordingLayeredWave",
  ];
  for (const id of ids) {
    elements[id] = document.getElementById(id);
  }
  elements.navItems = Array.from(document.querySelectorAll(".nav-item"));
  elements.swatches = Array.from(document.querySelectorAll(".swatches button"));
  elements.appShell = document.querySelector(".app-shell");
  elements.emptyTitle = elements.historyEmpty.querySelector("strong");
  elements.emptyMessage = elements.historyEmpty.querySelector("p");
}

function findRootRule() {
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      for (const rule of Array.from(sheet.cssRules || [])) {
        if (rule.selectorText === ":root") {
          return rule;
        }
      }
    } catch (_error) {
      // 本地样式表正常情况下可访问；不可访问时保留静态默认值。
    }
  }
  return null;
}

function setDesignToken(name, value) {
  if (rootRule) {
    rootRule.style.setProperty(name, value);
  }
}

function normalizeColor(value) {
  let normalized = String(value ?? "").trim().toUpperCase();
  if (normalized && !normalized.startsWith("#")) {
    normalized = `#${normalized}`;
  }
  return normalized;
}

function clampOpacity(value) {
  const numeric = Number.parseInt(value, 10);
  if (!Number.isFinite(numeric)) {
    return 100;
  }
  return Math.max(30, Math.min(100, numeric));
}

function parseHotkey(value) {
  const modifierAliases = new Map([
    ["ctrl", "Ctrl"], ["control", "Ctrl"], ["alt", "Alt"],
    ["shift", "Shift"], ["win", "Win"], ["windows", "Win"], ["meta", "Win"],
  ]);
  const namedKeys = new Map([
    ["space", "Space"], ["enter", "Enter"], ["home", "Home"], ["end", "End"],
    ["pageup", "PageUp"], ["pagedown", "PageDown"], ["insert", "Insert"],
  ]);
  const parts = String(value || "").split("+").map((part) => part.trim()).filter(Boolean);
  const modifiers = new Set();
  let mainKey = "";
  for (const part of parts) {
    const lowered = part.toLowerCase().replaceAll(" ", "");
    if (modifierAliases.has(lowered)) {
      modifiers.add(modifierAliases.get(lowered));
      continue;
    }
    if (mainKey) {
      return { valid: false, label: String(value || "").trim(), error: "快捷键只能包含一个主按键。" };
    }
    if (/^[a-z0-9]$/i.test(part)) {
      mainKey = part.toUpperCase();
    } else if (/^f(?:[1-9]|1[0-9]|2[0-4])$/i.test(part)) {
      mainKey = part.toUpperCase();
    } else if (namedKeys.has(lowered)) {
      mainKey = namedKeys.get(lowered);
    } else {
      return { valid: false, label: String(value || "").trim(), error: "请输入例如 Ctrl+Alt+Space 的组合键。" };
    }
  }
  if (!mainKey) {
    return { valid: false, label: String(value || "").trim(), error: "快捷键还需要一个主按键。" };
  }
  const isFunctionKey = /^F(?:[1-9]|1[0-9]|2[0-4])$/.test(mainKey);
  if (!isFunctionKey && !["Ctrl", "Alt", "Win"].some((name) => modifiers.has(name))) {
    return { valid: false, label: String(value || "").trim(), error: "普通按键必须包含 Ctrl、Alt 或 Win；功能键可以单独使用。" };
  }
  const ordered = ["Ctrl", "Alt", "Shift", "Win"].filter((name) => modifiers.has(name));
  return { valid: true, label: [...ordered, mainKey].join("+"), error: "" };
}

async function callApi(method, ...args) {
  const api = getLocalApi();
  if (!api || typeof api[method] !== "function") {
    throw new Error("本地功能尚未准备好，请稍后重试。");
  }
  const response = await api[method](...args);
  if (!response || response.ok !== true) {
    const error = new Error(response?.message || "本地操作失败，请稍后重试。");
    error.data = response?.data || null;
    throw error;
  }
  return response;
}

function showToast(message, isError = false) {
  window.clearTimeout(state.toastTimer);
  elements.toastMessage.textContent = String(message || (isError ? "操作失败。" : "操作完成。"));
  elements.toast.classList.toggle("is-error", isError);
  elements.toast.classList.add("is-visible");
  state.toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("is-visible");
  }, isError ? 4200 : 2800);
}

function hideBootScreen() {
  elements.bootScreen.classList.add("is-leaving");
  window.setTimeout(() => {
    elements.bootScreen.hidden = true;
  }, 190);
}

function currentView() {
  if (!elements.historyView.hidden) return "history";
  if (!elements.onlineModelView.hidden) return "onlineModel";
  if (!elements.localModelView.hidden) return "localModel";
  return "appearance";
}

function buildRecordingPreviewPoints(width, centerY, amplitude, cycles, phase, count = 36) {
  const points = [];
  for (let index = 0; index <= count; index += 1) {
    const ratio = index / count;
    const envelope = Math.pow(Math.sin(Math.PI * ratio), 1.65);
    const harmonic = Math.sin(ratio * Math.PI * 2 * cycles + phase);
    const detail = Math.sin(ratio * Math.PI * 2 * (cycles * 1.9) - phase * 0.6) * 0.17;
    points.push({
      x: ratio * width,
      y: centerY + (harmonic + detail) * amplitude * envelope,
    });
  }
  return points;
}

function buildRecordingPreviewPath(points) {
  let path = `M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let index = 1; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    path += ` Q${current.x.toFixed(1)} ${current.y.toFixed(1)} ${((current.x + next.x) / 2).toFixed(1)} ${((current.y + next.y) / 2).toFixed(1)}`;
  }
  const last = points[points.length - 1];
  return `${path} L${last.x.toFixed(1)} ${last.y.toFixed(1)}`;
}

function renderRecordingPreviewWave() {
  const container = elements.recordingLayeredWave;
  if (!container) return;
  const amplitude = 2 + 0.42 * 18.5;
  const layers = [
    [".preview-layered-wave-path-back", amplitude * 0.43, 2.9, -recordingPreviewPhase * 0.82],
    [".preview-layered-wave-path-middle", amplitude * 0.68, 1.82, recordingPreviewPhase * 0.64 + 0.7],
    [".preview-layered-wave-path-front", amplitude, 2.25, recordingPreviewPhase],
  ];
  for (const [selector, layerAmplitude, cycles, phase] of layers) {
    const path = container.querySelector(selector);
    path?.setAttribute("d", buildRecordingPreviewPath(
      buildRecordingPreviewPoints(120, 36, layerAmplitude, cycles, phase),
    ));
  }
}

function tickRecordingPreview(time) {
  recordingPreviewFrame = null;
  const elapsed = recordingPreviewLastTime
    ? Math.min(40, Math.max(0, time - recordingPreviewLastTime))
    : 0;
  recordingPreviewLastTime = time;
  recordingPreviewPhase += elapsed * (0.0022 + 0.065 * 0.0255);
  renderRecordingPreviewWave();
  syncRecordingPreviewMotion();
}

function syncRecordingPreviewMotion() {
  if (!elements.recordingLayeredWave) return;
  const shouldRun = recordingMotionQuery?.matches !== true
    && !document.hidden
    && currentView() === "appearance";
  if (shouldRun && recordingPreviewFrame === null) {
    recordingPreviewFrame = window.requestAnimationFrame(tickRecordingPreview);
  } else if (!shouldRun && recordingPreviewFrame !== null) {
    window.cancelAnimationFrame(recordingPreviewFrame);
    recordingPreviewFrame = null;
    recordingPreviewLastTime = 0;
  }
  renderRecordingPreviewWave();
}

function initializeRecordingPreviewMotion() {
  recordingMotionQuery = typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;

  const handleMotionPreference = () => syncRecordingPreviewMotion();
  if (typeof recordingMotionQuery?.addEventListener === "function") {
    recordingMotionQuery.addEventListener("change", handleMotionPreference);
  } else if (typeof recordingMotionQuery?.addListener === "function") {
    recordingMotionQuery.addListener(handleMotionPreference);
  }
  document.addEventListener("visibilitychange", syncRecordingPreviewMotion);
  document.addEventListener("visibilitychange", scheduleModelResourcePoll);
  window.addEventListener("pagehide", () => {
    window.clearTimeout(state.modelResourceTimer);
    if (recordingPreviewFrame !== null) window.cancelAnimationFrame(recordingPreviewFrame);
    recordingPreviewFrame = null;
    recordingPreviewLastTime = 0;
  });
  syncRecordingPreviewMotion();
}

function switchView(view, focusSearch = false) {
  const next = ["appearance", "localModel", "onlineModel", "history"].includes(view) ? view : "appearance";
  for (const name of ["appearance", "localModel", "onlineModel", "history"]) {
    const target = elements[`${name}View`];
    const active = name === next;
    target.hidden = !active;
    target.classList.toggle("is-active", active);
  }
  for (const button of elements.navItems) {
    const selected = button.dataset.view === next;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-selected", String(selected));
  }
  const privacyCopy = {
    localModel: "本地模式不会上传录音",
    onlineModel: "在线识别会将录音上传至所选服务",
  };
  elements.sidebarPrivacyText.textContent = privacyCopy[next] || "设置与历史记录仅保存在本机";
  if (next === "history" && focusSearch) {
    window.setTimeout(() => {
      elements.historySearch.focus();
      elements.historySearch.select();
    }, 0);
  }
  syncRecordingPreviewMotion();
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value <= 0) return "未知";
  if (value >= 1024 * 1024 * 1024) {
    return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "正在估算";
  if (value < 60) return `约 ${Math.max(1, Math.round(value))} 秒`;
  const minutes = Math.ceil(value / 60);
  if (minutes < 60) return `约 ${minutes} 分钟`;
  return `约 ${Math.ceil(minutes / 60)} 小时`;
}

function formatSpeed(bytesPerSecond) {
  const value = Number(bytesPerSecond || 0);
  if (value <= 0) return "正在测速";
  return `${formatBytes(value)}/秒`;
}

function syncModelControls(payload = state.model) {
  const localDraft = state.localEngineId;
  const onlineDraft = state.onlineEngineId;
  state.model = { ...state.model, ...(payload || {}) };
  if (localDraft) {
    state.localEngineId = localDraft;
  } else if (state.model.engine_id?.startsWith("local:")) {
    state.localEngineId = state.model.engine_id;
  }
  if (onlineDraft) {
    state.onlineEngineId = onlineDraft;
  } else if (state.model.engine_id?.startsWith("cloud:")) {
    state.onlineEngineId = state.model.engine_id;
  }
  const realtimeModel = String(state.model.realtime_model || DEFAULT_REALTIME_MODEL);
  const realtimeStatuses = new Map(
    (state.model.realtime_models || []).map((item) => [String(item.model_id || ""), item]),
  );
  for (const input of elements.realtimeModelOptions.querySelectorAll('input[name="realtimeModel"]')) {
    const status = realtimeStatuses.get(input.value);
    input.disabled = status ? status.available !== true : false;
    input.closest("label")?.classList.toggle("is-unavailable", input.disabled);
  }
  const realtimeInput = elements.realtimeModelOptions.querySelector(`input[value="${realtimeModel}"]`);
  if (realtimeInput && !realtimeInput.disabled) realtimeInput.checked = true;
  renderEngineOptions();
  renderLocalModels();
  renderProviders();
  const selected = state.model.preference || "auto";
  const radio = elements.deviceOptions.querySelector(`input[value="${selected}"]`);
  if (radio) radio.checked = true;
  elements.fallbackModel.replaceChildren();
  for (const model of state.model.local_models || []) {
    if (!model.available) continue;
    const option = document.createElement("option");
    option.value = model.model_id;
    option.textContent = model.name;
    elements.fallbackModel.append(option);
  }
  elements.fallbackModel.value = state.model.fallback_model || "faster-whisper-small";
  updateRecognitionSummary();
  elements.modelTestStatus.textContent = state.model.device_error || "";
  elements.modelTestStatus.classList.toggle("is-error", Boolean(state.model.device_error));
  scheduleModelResourcePoll();
}

function createTextElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = String(text || "");
  return element;
}

function renderEngineOptions() {
  elements.localEngineOptions.replaceChildren();
  elements.onlineEngineOptions.replaceChildren();
  const localEngines = [];
  const onlineEngines = [];
  for (const model of state.model.local_models || []) {
    localEngines.push({
      id: `local:${model.model_id}`,
      name: model.name,
      description: model.summary || model.language_support || "本地离线识别",
      status: model.status || (model.available ? "已安装" : "不可用"),
      modelId: model.model_id,
      available: model.available === true,
      downloadable: model.downloadable === true,
      resourceStatus: model.resource_status || null,
      disabled: !model.available || (
        state.model.voice_test_active === true
        && state.model.voice_test_model_id !== model.model_id
      ),
    });
  }
  for (const provider of state.model.providers || []) {
    onlineEngines.push({
      id: `cloud:${provider.provider_id}`,
      name: provider.name,
      description: provider.short_description || "在线语音识别",
      status: provider.configured ? "凭据已保存" : "需要填写凭据",
      disabled: !provider.configured,
    });
  }
  const firstLocal = localEngines.find((engine) => !engine.disabled)?.id || null;
  const firstOnline = onlineEngines.find((engine) => !engine.disabled)?.id || null;
  if (!localEngines.some((engine) => engine.id === state.localEngineId && !engine.disabled)) {
    state.localEngineId = firstLocal;
  }
  if (!onlineEngines.some((engine) => engine.id === state.onlineEngineId && !engine.disabled)) {
    state.onlineEngineId = firstOnline;
  }
  renderEngineGroup(elements.localEngineOptions, localEngines, "localRecognitionEngine", "localEngineId");
  renderEngineGroup(elements.onlineEngineOptions, onlineEngines, "onlineRecognitionEngine", "onlineEngineId");
}

function renderEngineGroup(container, engines, inputName, stateKey) {
  const isLocalGroup = inputName === "localRecognitionEngine";
  for (const engine of engines) {
    const label = document.createElement("label");
    label.className = "engine-option";
    const resourceState = String(engine.resourceStatus?.state || "");
    const downloading = ["queued", "downloading", "verifying", "pausing"].includes(resourceState);
    if (isLocalGroup && engine.downloadable && !engine.available) {
      const percent = resourceState === "verifying" ? 100 : Number(engine.resourceStatus?.percent || 0);
      label.classList.add("is-unavailable", "is-downloadable");
      if (downloading) label.classList.add("is-downloading");
      label.style.setProperty("--download-progress", `${Math.max(0, Math.min(100, percent))}%`);
    }
    const input = document.createElement("input");
    input.type = "radio";
    input.name = inputName;
    input.value = engine.id;
    input.checked = engine.id === state[stateKey];
    input.disabled = engine.disabled;
    input.addEventListener("change", () => {
      state[stateKey] = engine.id;
      updateRecognitionSummary();
      if (isLocalGroup) renderLocalModels();
    });
    const content = [input, createTextElement("b", "", engine.name),
      createTextElement("small", "", engine.description)];
    if (isLocalGroup && engine.downloadable && !engine.available) {
      const percent = Math.round(Number(engine.resourceStatus?.percent || 0));
      const labelByState = {
        queued: "准备中",
        downloading: `${percent}%`,
        verifying: "校验中",
        pausing: "暂停中",
        paused: "继续下载",
        failed: "重试下载",
        deleting: "删除中",
      };
      const downloadButton = createTextElement(
        "button", "model-card-download", labelByState[resourceState] || "下载",
      );
      downloadButton.type = "button";
      downloadButton.disabled = state.modelBusy || ["verifying", "pausing", "deleting"].includes(resourceState);
      downloadButton.title = ["queued", "downloading"].includes(resourceState) ? "点击暂停下载" : "";
      downloadButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const action = ["queued", "downloading"].includes(resourceState) ? "pause" : "start";
        manageLocalModelResource(engine.modelId, action);
      });
      content.push(downloadButton);
    }
    if (!isLocalGroup) content.push(createTextElement("em", "", engine.status));
    label.append(...content);
    container.append(label);
  }
}

function renderLocalModels() {
  elements.localModelList.replaceChildren();
  const selectedId = String(state.localEngineId || state.model.engine_id || "").replace(/^local:/, "");
  const models = state.model.local_models || [];
  const model = models.find((item) => item.model_id === selectedId)
    || models.find((item) => item.available)
    || models[0];
  if (!model) {
    elements.localModelList.append(createTextElement("p", "local-model-empty", "没有可用的本地模型。"));
    return;
  }

  const row = document.createElement("article");
  row.className = "local-model-row local-model-detail";
  if (`local:${model.model_id}` === state.model.engine_id) row.classList.add("is-selected");

  const heading = document.createElement("div");
  heading.className = "local-model-detail-heading";
  const headingCopy = document.createElement("div");
  headingCopy.className = "local-model-heading-copy";
  const name = document.createElement("div");
  name.className = "local-model-name";
  name.append(createTextElement("b", "", model.name));

  const statusCell = document.createElement("div");
  statusCell.className = "model-status-cell";
  const resourceStatus = model.resource_status || null;
  const resourceState = String(resourceStatus?.state || "");
  const resourceStateText = {
    queued: "准备下载",
    downloading: `下载 ${Number(resourceStatus?.percent || 0).toFixed(1)}%`,
    verifying: "正在校验",
    pausing: "正在暂停",
    paused: "已暂停",
    completed: "已安装",
    failed: "下载失败",
    deleting: "正在删除",
  }[resourceState];
  const status = createTextElement(
    "span",
    `status-pill${model.available ? "" : " is-missing"}`,
    resourceStateText || model.status || (model.available ? "已安装" : "不可用"),
  );
  status.title = model.status_message || "";
  statusCell.append(status);
  headingCopy.append(statusCell, name);
  heading.append(headingCopy);

  const details = document.createElement("dl");
  details.className = "local-model-specs";
  const specs = [
    ["模型大小", model.size_label || formatBytes(model.size_bytes)],
    ["已占空间", formatBytes(resourceStatus?.installed_bytes || model.size_on_disk_bytes)],
    ["语言支持", model.language_support || "语言支持情况未说明"],
    ["最低配置", model.minimum || "未提供"],
    ["建议配置", model.recommended || "未提供"],
    ["显卡支持", model.gpu || "非必需"],
  ];
  for (const [term, value] of specs) {
    const item = document.createElement("div");
    item.className = "local-model-spec";
    item.append(createTextElement("dt", "", term), createTextElement("dd", "", value));
    details.append(item);
  }
  row.append(heading, details);
  elements.localModelList.append(row);
}

function scheduleModelResourcePoll() {
  window.clearTimeout(state.modelResourceTimer);
  const models = state.model.local_models || [];
  const active = models.some((model) => {
    const resourceState = String(model.resource_status?.state || "");
    return ["queued", "downloading", "verifying", "pausing", "deleting"].includes(resourceState);
  });
  if (!active || document.hidden) return;
  state.modelResourceTimer = window.setTimeout(async () => {
    const activeModel = models.find((model) => {
      const resourceState = String(model.resource_status?.state || "");
      return ["queued", "downloading", "verifying", "pausing", "deleting"].includes(resourceState);
    });
    const modelId = activeModel?.model_id;
    if (!modelId) return;
    try {
      const response = await callApi("manage_local_model_resource", modelId, "status");
      syncModelControls(response.data);
    } catch (error) {
      if (error.data) {
        syncModelControls(error.data);
      }
      showToast(error.message, true);
      elements.modelTestStatus.textContent = error.message;
      elements.modelTestStatus.classList.add("is-error");
      if (!error.data) scheduleModelResourcePoll();
    }
  }, 500);
}

async function manageLocalModelResource(modelId, action) {
  if (state.modelBusy) return;
  state.modelBusy = true;
  try {
    const response = await callApi("manage_local_model_resource", modelId, action);
    syncModelControls(response.data);
    if (response.message) showToast(response.message);
  } catch (error) {
    if (error.data) syncModelControls(error.data);
    showToast(error.message, true);
    elements.modelTestStatus.textContent = error.message;
    elements.modelTestStatus.classList.add("is-error");
  } finally {
    state.modelBusy = false;
    renderLocalModels();
    scheduleModelResourcePoll();
  }
}

function confirmModelResourceDelete(model) {
  openConfirm({
    title: `删除 ${model.name}？`,
    message: "会删除本机保存的 1.7B 模型和未完成下载。",
    confirmLabel: "删除模型",
    action: () => manageLocalModelResource(model.model_id, "delete"),
  });
}

function renderProviders() {
  elements.providerList.replaceChildren();
  for (const provider of state.model.providers || []) {
    const card = document.createElement("article");
    card.className = "provider-card";
    card.dataset.providerId = provider.provider_id;
    const header = document.createElement("div");
    header.className = "provider-header";
    const title = document.createElement("div");
    title.className = "provider-title";
    title.append(createTextElement("b", "", provider.name),
      createTextElement("span", "", provider.configured ? "凭据已保存在本机" : "尚未配置"));
    const description = createTextElement("div", "provider-description", provider.description || provider.short_description);
    const actions = document.createElement("div");
    actions.className = "provider-actions";
    const configure = createTextElement("button", "button button-secondary", provider.configured ? "更新凭据" : "填写凭据");
    configure.type = "button";
    actions.append(configure);
    if (provider.configured) {
      const remove = createTextElement("button", "button button-danger-ghost", "删除凭据");
      remove.type = "button";
      remove.addEventListener("click", () => deleteProviderCredentials(provider.provider_id));
      actions.append(remove);
    }
    const form = document.createElement("form");
    form.className = "provider-form";
    form.hidden = true;
    for (const field of provider.fields || []) {
      const wrapper = document.createElement("div");
      wrapper.className = "credential-field";
      const label = createTextElement("label", "", field.label);
      const input = document.createElement("input");
      input.name = field.name;
      input.type = field.secret ? "password" : "text";
      input.maxLength = Number(field.max_length || 256);
      input.autocomplete = "off";
      input.placeholder = provider.configured ? "留空则保持原值" : `请输入${field.label}`;
      label.htmlFor = `credential-${provider.provider_id}-${field.name}`;
      input.id = label.htmlFor;
      wrapper.append(label, input);
      form.append(wrapper);
    }
    const formActions = document.createElement("div");
    formActions.className = "provider-form-actions";
    const cancel = createTextElement("button", "button button-secondary", "取消");
    cancel.type = "button";
    const save = createTextElement("button", "button button-primary", "保存到本机");
    save.type = "submit";
    formActions.append(cancel, save);
    form.append(formActions);
    configure.addEventListener("click", () => { form.hidden = !form.hidden; });
    cancel.addEventListener("click", () => { form.hidden = true; form.reset(); });
    form.addEventListener("submit", (event) => saveProviderCredentials(event, provider));
    header.append(title, description, actions);
    card.append(header, form);
    elements.providerList.append(card);
  }
}

function selectedEngineId(view = currentView()) {
  if (view === "onlineModel") return state.onlineEngineId || state.model.engine_id;
  if (view === "localModel") {
    return state.localEngineId || state.model.engine_id;
  }
  return state.model.engine_id;
}

function selectedRealtimeModel() {
  return elements.realtimeModelOptions.querySelector('input[name="realtimeModel"]:checked')?.value
    || state.model.realtime_model
    || DEFAULT_REALTIME_MODEL;
}

function selectedRealtimeModelName() {
  const modelId = selectedRealtimeModel();
  return (state.model.realtime_models || []).find((item) => item.model_id === modelId)?.name
    || ({
      "streaming-paraformer-bilingual-zh-en": "Streaming Paraformer",
      "zipformer-bilingual-zh-en-exp32-int8": "Zipformer",
    })[modelId]
    || modelId;
}

function selectedLocalModelName() {
  const engineId = selectedEngineId("localModel");
  const modelId = String(engineId || "").replace(/^local:/, "");
  return (state.model.local_models || []).find((item) => item.model_id === modelId)?.name
    || modelId;
}

function selectedOnlineProviderName() {
  const engineId = selectedEngineId("onlineModel");
  const providerId = String(engineId || "").replace(/^cloud:/, "");
  return (state.model.providers || []).find((item) => item.provider_id === providerId)?.name
    || "所选在线服务";
}

function updateRecognitionSummary() {
  const realtimeName = selectedRealtimeModelName();
  const deviceName = {
    auto: "自动选择",
    cpu: "使用处理器",
    gpu: "使用显卡",
  }[selectedModelDevice()] || "自动选择";
  elements.localRecognitionSummary.textContent = `当前选择：${realtimeName}；${selectedLocalModelName()}；${deviceName}`;
  elements.onlineRecognitionSummary.textContent = `实时：${realtimeName}；最终：${selectedOnlineProviderName()}；不做文字校正，完整录音会上传。`;
  elements.localModelState.classList.toggle("is-dirty", false);
  elements.onlineModelState.classList.toggle("is-dirty", false);
  elements.localModelState.lastChild.textContent = state.model.engine_id?.startsWith("local:") ? "正在使用" : "可以切换";
  elements.onlineModelState.lastChild.textContent = state.model.engine_id?.startsWith("cloud:") ? "正在使用" : "可以切换";
}

function selectedModelDevice() {
  return elements.deviceOptions.querySelector('input[name="modelDevicePreference"]:checked')?.value || "auto";
}

async function saveModelSettings(targetView) {
  if (state.modelBusy) return;
  state.modelBusy = true;
  elements.localModelSaveButton.disabled = true;
  elements.onlineModelSaveButton.disabled = true;
  try {
    const response = await callApi(
      "save_recognition_settings",
      selectedEngineId(targetView),
      elements.fallbackModel.value,
      selectedModelDevice(),
      selectedRealtimeModel(),
    );
    syncModelControls(response.data);
    showToast(response.message || "识别设备已保存并应用。");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.modelBusy = false;
    elements.localModelSaveButton.disabled = false;
    elements.onlineModelSaveButton.disabled = false;
  }
}

async function testLocalModel(modelId) {
  if (state.modelBusy || state.testBusy || state.controlTestActive) return;
  state.modelBusy = true;
  state.testBusy = true;
  elements.controlWordTestButton.disabled = true;
  const stopping = state.model.voice_test_active === true && state.model.voice_test_model_id === modelId;
  elements.modelTestStatus.textContent = stopping ? "正在停止录音并识别…" : "正在打开麦克风…";
  try {
    const response = await callApi("test_local_model", modelId, selectedModelDevice(), stopping ? "stop" : "start");
    syncModelControls(response.data);
    const recognized = String(response.data?.voice_test_text || "");
    elements.modelTestStatus.textContent = recognized
      ? `${response.message} 识别结果：${recognized}`
      : response.message;
    showToast(response.message);
  } catch (error) {
    if (stopping) {
      state.model.voice_test_active = false;
      state.model.voice_test_model_id = "";
      renderLocalModels();
    }
    elements.modelTestStatus.textContent = error.message;
    elements.modelTestStatus.classList.add("is-error");
  } finally {
    state.modelBusy = false;
    state.testBusy = false;
    elements.controlWordTestButton.disabled = state.model.voice_test_active === true;
    renderLocalModels();
  }
}

async function saveProviderCredentials(event, provider) {
  event.preventDefault();
  if (state.modelBusy) return;
  const values = {};
  for (const field of provider.fields || []) {
    values[field.name] = String(event.currentTarget.elements[field.name]?.value || "").trim();
  }
  state.modelBusy = true;
  try {
    const response = await callApi("save_provider_credentials", provider.provider_id, values);
    syncModelControls(response.data);
    showToast(response.message || "在线服务凭据已保存到本机。");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.modelBusy = false;
  }
}

async function deleteProviderCredentials(providerId) {
  if (state.modelBusy) return;
  state.modelBusy = true;
  try {
    const response = await callApi("delete_provider_credentials", providerId);
    syncModelControls(response.data);
    showToast(response.message || "在线服务凭据已删除。");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.modelBusy = false;
  }
}

function isAppearanceValid() {
  return COLOR_PATTERN.test(state.draft.color) && parseHotkey(state.draft.hotkey).valid;
}

function isAppearanceDirty() {
  return state.draft.color !== state.saved.color
    || state.draft.opacity !== state.saved.opacity
    || state.draft.hotkey !== state.saved.hotkey
    || state.draft.standby !== state.saved.standby
    || state.draft.transcript !== state.saved.transcript
    || state.draft.autoPaste !== state.saved.autoPaste
    || state.draft.confidence !== state.saved.confidence;
}

function updateSaveState() {
  const dirty = isAppearanceDirty();
  elements.saveState.classList.toggle("is-dirty", dirty);
  elements.saveState.lastChild.textContent = dirty ? "有未保存的更改" : "设置已同步";
  elements.saveButton.disabled = state.appearanceBusy || !dirty || !isAppearanceValid();
  elements.resetButton.disabled = state.appearanceBusy;
}

function setAppearanceInputsDisabled(disabled) {
  elements.colorPicker.disabled = disabled;
  elements.colorText.disabled = disabled;
  elements.opacityRange.disabled = disabled;
  elements.hotkeyInput.disabled = disabled;
  elements.hotkeyTestButton.disabled = disabled;
  elements.standbyToggle.disabled = disabled;
  elements.transcriptToggle.disabled = disabled;
  elements.autoPasteToggle.disabled = disabled;
  elements.standbyConfidence.disabled = disabled;
  for (const swatch of elements.swatches) {
    swatch.disabled = disabled;
  }
}

function applyAppearancePreview() {
  if (COLOR_PATTERN.test(state.draft.color)) {
    setDesignToken("--button-color", state.draft.color);
  }
  const alpha = Math.max(0.3, Math.min(1, state.draft.opacity / 100));
  const progress = ((state.draft.opacity - 30) / 70) * 100;
  setDesignToken("--preview-opacity", String(alpha));
  setDesignToken("--range-progress", `${progress}%`);
  elements.opacityOutput.textContent = `${state.draft.opacity}%`;
  for (const swatch of elements.swatches) {
    swatch.classList.toggle("is-active", swatch.dataset.color === state.draft.color);
  }
  updateSaveState();
}

function syncAppearanceControls() {
  elements.colorPicker.value = COLOR_PATTERN.test(state.draft.color)
    ? state.draft.color
    : state.saved.color;
  elements.colorText.value = state.draft.color;
  elements.opacityRange.value = String(state.draft.opacity);
  elements.hotkeyInput.value = state.draft.hotkey;
  elements.standbyToggle.checked = state.draft.standby;
  elements.standbyToggle.parentElement.querySelector("b").textContent = state.draft.standby ? "开启" : "关闭";
  elements.transcriptToggle.checked = state.draft.transcript;
  elements.transcriptToggle.parentElement.querySelector("b").textContent = state.draft.transcript ? "显示" : "隐藏";
  elements.autoPasteToggle.checked = state.draft.autoPaste;
  elements.autoPasteToggle.parentElement.querySelector("b").textContent = state.draft.autoPaste ? "开启" : "关闭";
  elements.standbyConfidence.value = String(state.draft.confidence);
  elements.standbyConfidenceValue.textContent = `${state.draft.confidence}%`;
  elements.colorError.textContent = COLOR_PATTERN.test(state.draft.color)
    ? ""
    : "请输入 6 位十六进制颜色，例如 #2563EB。";
  const hotkey = parseHotkey(state.draft.hotkey);
  elements.hotkeyError.textContent = hotkey.error;
  applyAppearancePreview();
}

function setDraftColor(value) {
  const normalized = normalizeColor(value);
  state.draft.color = normalized;
  elements.colorText.value = normalized;
  const valid = COLOR_PATTERN.test(normalized);
  elements.colorError.textContent = valid ? "" : "请输入 6 位十六进制颜色，例如 #2563EB。";
  if (valid) {
    elements.colorPicker.value = normalized;
  }
  applyAppearancePreview();
}

function setDraftHotkey(value, normalize = false) {
  const hotkey = parseHotkey(value);
  state.draft.hotkey = normalize && hotkey.valid ? hotkey.label : String(value || "").trim();
  elements.hotkeyInput.value = state.draft.hotkey;
  elements.hotkeyError.textContent = hotkey.error;
  elements.hotkeyStatus.textContent = "";
  elements.hotkeyStatus.classList.remove("is-error");
  updateSaveState();
}

async function testHotkey() {
  const hotkey = parseHotkey(state.draft.hotkey);
  if (!hotkey.valid || state.appearanceBusy) {
    elements.hotkeyError.textContent = hotkey.error;
    return;
  }
  const oldLabel = elements.hotkeyTestButton.textContent;
  elements.hotkeyTestButton.disabled = true;
  elements.hotkeyTestButton.textContent = "测试中…";
  elements.hotkeyStatus.textContent = "";
  try {
    const response = await callApi("test_hotkey", hotkey.label);
    const available = response.data?.available === true;
    elements.hotkeyStatus.textContent = response.message;
    elements.hotkeyStatus.classList.toggle("is-error", !available);
    if (available) {
      setDraftHotkey(response.data?.hotkey || hotkey.label, true);
      elements.hotkeyStatus.textContent = response.message;
    }
  } catch (error) {
    elements.hotkeyStatus.textContent = error.message;
    elements.hotkeyStatus.classList.add("is-error");
  } finally {
    elements.hotkeyTestButton.disabled = false;
    elements.hotkeyTestButton.textContent = oldLabel;
  }
}

async function saveAppearance() {
  if (state.appearanceBusy || !isAppearanceValid() || !isAppearanceDirty()) {
    return;
  }
  state.appearanceBusy = true;
  const submitted = { ...state.draft };
  setAppearanceInputsDisabled(true);
  const label = elements.saveButton.querySelector("span");
  const oldLabel = label.textContent;
  label.textContent = "正在保存…";
  updateSaveState();
  try {
    const response = await callApi(
      "save_appearance", submitted.color, submitted.opacity, submitted.hotkey,
      submitted.standby, submitted.transcript, submitted.confidence, submitted.autoPaste
    );
    const data = response.data || {};
    state.saved = {
      color: normalizeColor(data.color || state.draft.color),
      opacity: clampOpacity(data.opacity ?? state.draft.opacity),
      hotkey: parseHotkey(data.hotkey || state.draft.hotkey).label,
      standby: data.standby_enabled === true,
      transcript: data.live_transcript_visible !== false,
      autoPaste: data.auto_paste_enabled !== false,
      confidence: Number(data.standby_confidence || 80),
    };
    state.draft = { ...state.saved };
    syncAppearanceControls();
    showToast(response.message || "设置已保存并应用。");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.appearanceBusy = false;
    setAppearanceInputsDisabled(false);
    label.textContent = oldLabel;
    updateSaveState();
  }
}

function formatDate(value, includeYear = true) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value || "时间未知");
  }
  const options = includeYear
    ? { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }
    : { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" };
  return new Intl.DateTimeFormat("zh-CN", options).format(date);
}

function previewText(value) {
  const compact = String(value || "").replace(/\s+/g, " ").trim();
  return compact || "（空白记录）";
}

function selectedEntry() {
  return state.entries.find((entry) => entry.id === state.selectedId) || null;
}

function renderDetail() {
  const entry = selectedEntry();
  const hasEntry = Boolean(entry);
  elements.detailPlaceholder.hidden = hasEntry;
  elements.detailContent.hidden = !hasEntry;
  elements.detailTime.textContent = hasEntry
    ? formatDate(entry.created_at, true)
    : "选择一条记录查看全文";
  if (!entry) {
    return;
  }
  elements.detailText.textContent = entry.text;
}

function selectEntry(operationId) {
  const exists = state.entries.some((entry) => entry.id === operationId);
  state.selectedId = exists ? operationId : null;
  for (const button of elements.historyList.querySelectorAll(".history-item")) {
    const selected = button.dataset.id === state.selectedId;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-selected", String(selected));
  }
  renderDetail();
}

function renderHistory() {
  const previousId = state.selectedId;
  const fragment = document.createDocumentFragment();
  for (const entry of state.entries) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.dataset.id = entry.id;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", "false");

    const text = document.createElement("p");
    text.textContent = previewText(entry.text);
    const time = document.createElement("time");
    time.dateTime = entry.created_at;
    time.textContent = formatDate(entry.created_at, false);
    button.append(text, time);
    button.addEventListener("click", () => selectEntry(entry.id));
    button.addEventListener("dblclick", () => copyEntry(entry.id));
    fragment.append(button);
  }
  elements.historyList.replaceChildren(fragment);

  const query = elements.historySearch.value.trim();
  const empty = state.entries.length === 0;
  elements.historyEmpty.hidden = !empty;
  elements.historyList.hidden = empty;
  if (!state.historyAvailable) {
    elements.emptyTitle.textContent = "历史记录暂时不可用";
    elements.emptyMessage.textContent = "语音输入仍可使用，请稍后重新打开此窗口。";
  } else if (query) {
    elements.emptyTitle.textContent = "没有找到匹配内容";
    elements.emptyMessage.textContent = "换一个关键词再试试。";
  } else {
    elements.emptyTitle.textContent = "还没有识别记录";
    elements.emptyMessage.textContent = "完成一次语音输入后会显示在这里。";
  }

  const total = Number(state.signature[0] || 0);
  elements.navHistoryCount.textContent = total > 999 ? "999+" : String(total);
  elements.historyCount.textContent = query ? `${state.entries.length} 条匹配` : `${total} 条记录`;
  elements.clearButton.disabled = !state.historyAvailable || total === 0 || state.historyBusy;
  elements.copyAllButton.disabled = !state.historyAvailable || total === 0 || state.historyBusy;

  const nextId = state.entries.some((entry) => entry.id === previousId)
    ? previousId
    : (state.entries[0]?.id || null);
  selectEntry(nextId);
}

function normalizeHistoryPayload(payload) {
  const rawEntries = Array.isArray(payload?.entries) ? payload.entries : [];
  state.entries = rawEntries
    .filter((entry) => entry && typeof entry.id === "string" && typeof entry.text === "string")
    .map((entry) => ({
      id: entry.id,
      created_at: String(entry.created_at || ""),
      text: entry.text,
    }));
  const signature = Array.isArray(payload?.signature) ? payload.signature : [state.entries.length, 0];
  state.signature = [Number(signature[0] || 0), Number(signature[1] || 0)];
  state.historyAvailable = payload?.available !== false;
}

async function loadHistory({ silent = false } = {}) {
  const requestId = ++state.historyRequest;
  elements.refreshButton.disabled = true;
  if (!silent) {
    elements.refreshButton.classList.add("is-spinning");
  }
  try {
    const response = await callApi("get_history", elements.historySearch.value.slice(0, 200));
    if (requestId !== state.historyRequest) {
      return;
    }
    normalizeHistoryPayload(response.data);
    renderHistory();
  } catch (error) {
    if (requestId === state.historyRequest && !silent) {
      showToast(error.message, true);
    }
  } finally {
    if (requestId === state.historyRequest) {
      elements.refreshButton.disabled = false;
      elements.refreshButton.classList.remove("is-spinning");
    }
  }
}

async function copyEntry(operationId = state.selectedId) {
  const fixedId = String(operationId || "");
  if (!fixedId || state.historyBusy) {
    return;
  }
  state.historyBusy = true;
  elements.copyButton.disabled = true;
  try {
    const response = await callApi("copy_history", fixedId);
    showToast(response.message || "已复制到系统剪贴板。");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.historyBusy = false;
    elements.copyButton.disabled = false;
  }
}

async function copyAllHistory() {
  if (!state.historyAvailable || Number(state.signature[0] || 0) === 0 || state.historyBusy) {
    return;
  }
  state.historyBusy = true;
  elements.copyAllButton.disabled = true;
  elements.clearButton.disabled = true;
  try {
    const response = await callApi("copy_all_history");
    showToast(response.message || "全部历史文字已复制到系统剪贴板。");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.historyBusy = false;
    renderHistory();
  }
}

function openConfirm({ title, message, confirmLabel, action }) {
  if (state.historyBusy || !elements.confirmModal.hidden) {
    return;
  }
  state.confirmAction = action;
  state.confirmFocus = document.activeElement;
  elements.modalTitle.textContent = title;
  elements.modalMessage.textContent = message;
  elements.modalConfirm.textContent = confirmLabel;
  elements.modalConfirm.disabled = false;
  elements.modalCancel.disabled = false;
  elements.appShell.inert = true;
  elements.confirmModal.hidden = false;
  window.setTimeout(() => elements.modalCancel.focus(), 0);
}

function closeConfirm(force = false) {
  if (state.historyBusy && !force) {
    return;
  }
  elements.confirmModal.hidden = true;
  elements.appShell.inert = false;
  state.confirmAction = null;
  const target = state.confirmFocus;
  state.confirmFocus = null;
  if (target && typeof target.focus === "function") {
    target.focus();
  }
}

async function confirmCurrentAction() {
  const action = state.confirmAction;
  if (!action || state.historyBusy) {
    return;
  }
  state.historyBusy = true;
  elements.modalConfirm.disabled = true;
  elements.modalCancel.disabled = true;
  try {
    await action();
    closeConfirm(true);
  } catch (error) {
    closeConfirm(true);
    showToast(error.message, true);
    await loadHistory({ silent: true });
  } finally {
    state.historyBusy = false;
    elements.modalConfirm.disabled = false;
    elements.modalCancel.disabled = false;
    renderHistory();
  }
}

function requestDeleteSelected() {
  if (state.historyBusy) {
    return;
  }
  const entry = selectedEntry();
  if (!entry) {
    return;
  }
  const fixedId = entry.id;
  openConfirm({
    title: "删除这条记录？",
    message: "删除后无法恢复，但不会影响已经粘贴到其他软件中的文字。",
    confirmLabel: "确认删除",
    action: async () => {
      const response = await callApi("delete_history", fixedId);
      showToast(response.message || "记录已删除。");
      await loadHistory({ silent: true });
    },
  });
}

function requestClearHistory() {
  if (state.historyBusy || !state.historyAvailable || Number(state.signature[0]) === 0) {
    return;
  }
  const expectedRevision = Number(state.signature[1] || 0);
  openConfirm({
    title: "清空全部历史？",
    message: `将删除本机保存的 ${state.signature[0]} 条识别文字，此操作无法恢复。`,
    confirmLabel: "清空全部",
    action: async () => {
      const response = await callApi("clear_history", expectedRevision);
      showToast(response.message || "历史记录已清空。");
      elements.historySearch.value = "";
      await loadHistory({ silent: true });
    },
  });
}

async function pollHistorySignature() {
  if (document.hidden || state.historyBusy) {
    return;
  }
  try {
    const response = await callApi("get_history_signature");
    const signature = response.data?.signature;
    if (!Array.isArray(signature)) {
      return;
    }
    const next = `${Number(signature[0] || 0)}:${Number(signature[1] || 0)}`;
    const current = `${state.signature[0]}:${state.signature[1]}`;
    if (next !== current) {
      await loadHistory({ silent: true });
    }
  } catch (_error) {
    // 低频检查失败不打断用户；手动刷新会显示具体错误。
  }
}

function bindEvents() {
  for (const button of elements.navItems) {
    button.addEventListener("click", () => switchView(button.dataset.view));
  }

  elements.colorPicker.addEventListener("input", (event) => setDraftColor(event.target.value));
  elements.colorText.addEventListener("input", (event) => setDraftColor(event.target.value));
  elements.colorText.addEventListener("blur", () => {
    if (isAppearanceValid()) {
      syncAppearanceControls();
    }
  });
  for (const swatch of elements.swatches) {
    swatch.addEventListener("click", () => setDraftColor(swatch.dataset.color));
  }
  elements.opacityRange.addEventListener("input", (event) => {
    state.draft.opacity = clampOpacity(event.target.value);
    applyAppearancePreview();
  });
  elements.hotkeyInput.addEventListener("input", (event) => setDraftHotkey(event.target.value));
  elements.hotkeyInput.addEventListener("blur", () => setDraftHotkey(state.draft.hotkey, true));
  elements.hotkeyTestButton.addEventListener("click", testHotkey);
  elements.standbyToggle.addEventListener("change", (event) => {
    state.draft.standby = event.target.checked;
    event.target.parentElement.querySelector("b").textContent = event.target.checked ? "开启" : "关闭";
    updateSaveState();
  });
  elements.transcriptToggle.addEventListener("change", (event) => {
    state.draft.transcript = event.target.checked;
    syncAppearanceControls();
  });
  elements.autoPasteToggle.addEventListener("change", (event) => {
    state.draft.autoPaste = event.target.checked;
    syncAppearanceControls();
  });
  elements.standbyConfidence.addEventListener("input", (event) => {
    state.draft.confidence = Math.max(70, Math.min(100, Number(event.target.value) || 80));
    syncAppearanceControls();
  });
  elements.controlWordTestButton.addEventListener("click", async () => {
    if (state.testBusy || state.model.voice_test_active === true) return;
    const stopping = elements.controlWordTestButton.dataset.active === "true";
    state.testBusy = true;
    elements.controlWordTestButton.disabled = true;
    elements.controlWordTestButton.setAttribute("aria-busy", "true");
    elements.controlWordTestStatus.classList.remove("is-error");
    renderLocalModels();
    try {
      const response = await callApi("test_standby_control", stopping ? "stop" : "start");
      state.controlTestActive = !stopping;
      elements.controlWordTestButton.dataset.active = stopping ? "false" : "true";
      elements.controlWordTestButton.setAttribute("aria-pressed", stopping ? "false" : "true");
      elements.controlWordTestButton.textContent = stopping ? "测试控制词" : "停止测试";
      elements.controlWordTestStatus.textContent = response.message;
      if (!stopping) {
        const poll = async () => {
          if (elements.controlWordTestButton.dataset.active !== "true") return;
          try {
            const status = await callApi("test_standby_control", "status");
            const data = status.data || {};
            if (data.word) elements.controlWordTestStatus.textContent = `识别为“${data.word}”，匹配置信度 ${data.confidence}%`;
          } catch (_error) {}
          window.setTimeout(poll, 400);
        };
        window.setTimeout(poll, 400);
      }
    } catch (error) {
      state.controlTestActive = false;
      elements.controlWordTestButton.dataset.active = "false";
      elements.controlWordTestButton.setAttribute("aria-pressed", "false");
      elements.controlWordTestStatus.textContent = error.message;
      elements.controlWordTestStatus.classList.add("is-error");
    } finally {
      state.testBusy = false;
      elements.controlWordTestButton.removeAttribute("aria-busy");
      elements.controlWordTestButton.disabled = state.model.voice_test_active === true;
      renderLocalModels();
    }
  });
  elements.resetButton.addEventListener("click", () => {
    state.draft = { ...state.defaults };
    syncAppearanceControls();
  });
  elements.saveButton.addEventListener("click", saveAppearance);
  elements.localModelSaveButton.addEventListener("click", () => saveModelSettings("localModel"));
  elements.onlineModelSaveButton.addEventListener("click", () => saveModelSettings("onlineModel"));
  elements.realtimeModelOptions.addEventListener("change", updateRecognitionSummary);
  elements.deviceOptions.addEventListener("change", updateRecognitionSummary);

  elements.historySearch.maxLength = 200;
  elements.historySearch.addEventListener("input", () => {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => loadHistory({ silent: true }), 220);
  });
  elements.refreshButton.addEventListener("click", () => loadHistory());
  elements.copyButton.addEventListener("click", () => copyEntry());
  elements.copyAllButton.addEventListener("click", copyAllHistory);
  elements.deleteButton.addEventListener("click", requestDeleteSelected);
  elements.clearButton.addEventListener("click", requestClearHistory);

  elements.modalCancel.addEventListener("click", closeConfirm);
  elements.modalConfirm.addEventListener("click", confirmCurrentAction);
  elements.confirmModal.addEventListener("mousedown", (event) => {
    if (event.target === elements.confirmModal) {
      closeConfirm();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.confirmModal.hidden) {
      event.preventDefault();
      closeConfirm();
      return;
    }
    if (event.ctrlKey && event.key.toLowerCase() === "f") {
      event.preventDefault();
      switchView("history", true);
      return;
    }
    if (event.ctrlKey && event.key.toLowerCase() === "s" && currentView() === "appearance") {
      event.preventDefault();
      saveAppearance();
    }
  });
}

async function initializeBridge() {
  if (bridgeStarted || typeof getLocalApi()?.get_initial_state !== "function") {
    return;
  }
  bridgeStarted = true;
  state.bridgeAttempts += 1;
  try {
    const response = await callApi("get_initial_state");
    const appearance = response.data?.appearance || {};
    const color = normalizeColor(appearance.color || "#2563EB");
    const opacity = clampOpacity(appearance.opacity ?? 100);
    const hotkey = parseHotkey(appearance.hotkey || "Ctrl+Alt+Space");
    state.saved = {
      color: COLOR_PATTERN.test(color) ? color : "#2563EB",
      opacity,
      hotkey: hotkey.valid ? hotkey.label : "Ctrl+Alt+Space",
      standby: appearance.standby_enabled === true,
      transcript: appearance.live_transcript_visible !== false,
      autoPaste: appearance.auto_paste_enabled !== false,
      confidence: Number(appearance.standby_confidence || 80),
    };
    state.draft = { ...state.saved };
    const defaultColor = normalizeColor(appearance.default_color || "#2563EB");
    state.defaults = {
      color: COLOR_PATTERN.test(defaultColor) ? defaultColor : "#2563EB",
      opacity: clampOpacity(appearance.default_opacity ?? 100),
      hotkey: parseHotkey(appearance.default_hotkey || "Ctrl+Alt+Space").label,
      standby: appearance.default_standby_enabled === true,
      transcript: appearance.default_live_transcript_visible !== false,
      autoPaste: appearance.default_auto_paste_enabled !== false,
      confidence: Number(appearance.default_standby_confidence || 80),
    };
    normalizeHistoryPayload(response.data?.history || {});
    syncModelControls(response.data?.model || {});
    syncAppearanceControls();
    renderHistory();
    state.pollTimer = window.setInterval(pollHistorySignature, 3000);
  } catch (error) {
    bridgeStarted = false;
    if (state.bridgeAttempts < 2) {
      window.setTimeout(initializeBridge, 450);
      return;
    }
    showToast(error.message, true);
  } finally {
    if (bridgeStarted || state.bridgeAttempts >= 2) {
      hideBootScreen();
    }
  }
}

collectElements();
rootRule = findRootRule();
bindEvents();
syncAppearanceControls();
renderHistory();
initializeRecordingPreviewMotion();

window.addEventListener("pywebviewready", initializeBridge);
if (typeof getLocalApi()?.get_initial_state === "function") {
  initializeBridge();
}
