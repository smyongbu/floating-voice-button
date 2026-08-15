"use strict";

const COLOR_PATTERN = /^#[0-9A-F]{6}$/;

const state = {
  saved: { color: "#2563EB", opacity: 100, hotkey: "Ctrl+Alt+Space", standby: false },
  draft: { color: "#2563EB", opacity: 100, hotkey: "Ctrl+Alt+Space", standby: false },
  defaults: { color: "#2563EB", opacity: 100, hotkey: "Ctrl+Alt+Space", standby: false },
  appearanceBusy: false,
  model: {
    engine_id: "local:sensevoice-small-int8",
    recognition_mode: "realtime",
    fallback_model: "sensevoice-small-int8",
    preference: "auto",
    local_models: [],
    providers: [],
  },
  modelBusy: false,
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
  toastTimer: null,
  bridgeAttempts: 0,
};

const elements = {};
let rootRule = null;
let bridgeStarted = false;

function collectElements() {
  const ids = [
    "appearanceView", "localModelView", "onlineModelView", "historyView", "saveState", "colorPicker", "colorText",
    "colorError", "opacityRange", "opacityOutput", "hotkeyInput", "hotkeyError",
    "hotkeyTestButton", "hotkeyStatus", "standbyToggle",
    "resetButton", "saveButton",
    "navHistoryCount", "clearButton", "historySearch", "historyCount",
    "refreshButton", "historyList", "historyEmpty", "historyDetail",
    "detailPlaceholder", "detailContent", "detailTime", "detailText",
    "deleteButton", "copyButton", "confirmModal", "modalTitle", "modalMessage",
    "modalCancel", "modalConfirm", "toast", "toastMessage", "bootScreen",
    "localModelState", "onlineModelState", "localEngineOptions", "onlineEngineOptions",
    "recognitionModeOptions", "recognitionModeHint", "sidebarPrivacyText",
    "localModelList", "deviceOptions", "fallbackModel",
    "providerList", "modelTestStatus", "localModelSaveButton", "onlineModelSaveButton",
    "localRecognitionSummary", "onlineRecognitionSummary",
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
  const api = window.pywebview?.api;
  if (!api || typeof api[method] !== "function") {
    throw new Error("本地功能尚未准备好，请稍后重试。");
  }
  const response = await api[method](...args);
  if (!response || response.ok !== true) {
    throw new Error(response?.message || "本地操作失败，请稍后重试。");
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
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value <= 0) return "未知";
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function syncModelControls(payload = state.model) {
  state.model = { ...state.model, ...(payload || {}) };
  if (state.model.engine_id?.startsWith("local:")) state.localEngineId = state.model.engine_id;
  if (state.model.engine_id?.startsWith("cloud:")) state.onlineEngineId = state.model.engine_id;
  const realtimeAvailable = state.model.realtime_model?.available === true;
  const realtimeInput = elements.recognitionModeOptions.querySelector('input[value="realtime"]');
  const batchInput = elements.recognitionModeOptions.querySelector('input[value="batch"]');
  realtimeInput.disabled = !realtimeAvailable;
  const selectedMode = state.model.recognition_mode === "realtime" && realtimeAvailable
    ? "realtime"
    : "batch";
  (selectedMode === "realtime" ? realtimeInput : batchInput).checked = true;
  elements.recognitionModeHint.textContent = realtimeAvailable
    ? "实时文字显示在悬浮按钮上方，录音结束后只向原软件粘贴一次。"
    : "实时中文模型暂时不可用，目前只能在停止录音后转换文字。";
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
  elements.fallbackModel.value = state.model.fallback_model || "sensevoice-small-int8";
  updateRecognitionSummary();
  elements.modelTestStatus.textContent = state.model.device_error || "";
  elements.modelTestStatus.classList.toggle("is-error", Boolean(state.model.device_error));
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
      description: model.summary || "本地离线识别",
      status: model.status || (model.available ? "已安装" : "不可用"),
      disabled: !model.available,
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
  for (const engine of engines) {
    const label = document.createElement("label");
    label.className = "engine-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = inputName;
    input.value = engine.id;
    input.checked = engine.id === state[stateKey];
    input.disabled = engine.disabled;
    input.addEventListener("change", () => {
      state[stateKey] = engine.id;
      updateRecognitionSummary();
    });
    label.append(input, createTextElement("b", "", engine.name),
      createTextElement("small", "", engine.description),
      createTextElement("em", "", engine.status));
    container.append(label);
  }
}

function renderLocalModels() {
  elements.localModelList.replaceChildren();
  for (const model of state.model.local_models || []) {
    const row = document.createElement("article");
    row.className = "local-model-row";
    if (`local:${model.model_id}` === state.model.engine_id) row.classList.add("is-selected");
    const name = document.createElement("div");
    name.className = "local-model-name";
    name.append(createTextElement("b", "", model.name),
      createTextElement("span", "", `${model.size_label || formatBytes(model.size_bytes)} · ${model.capabilities || "本地离线"}`));
    const hardware = document.createElement("div");
    hardware.className = "hardware-copy";
    const minimum = document.createElement("span");
    minimum.append(createTextElement("strong", "", "最低："), document.createTextNode(model.minimum || "未提供"));
    const recommended = document.createElement("span");
    recommended.append(createTextElement("strong", "", "建议："), document.createTextNode(model.recommended || "未提供"));
    const gpu = document.createElement("span");
    gpu.append(createTextElement("strong", "", "显卡："), document.createTextNode(model.gpu || "非必需"));
    hardware.append(minimum, recommended, gpu);
    const statusCell = document.createElement("div");
    statusCell.className = "model-status-cell";
    const status = createTextElement(
      "span",
      `status-pill${model.available ? "" : " is-missing"}`,
      model.status || (model.available ? "已安装" : "不可用"),
    );
    status.title = model.status_message || "";
    const test = createTextElement("button", "button button-secondary model-test-button", "测试模型");
    test.type = "button";
    test.disabled = !model.available;
    test.addEventListener("click", () => testLocalModel(model.model_id));
    statusCell.append(status, test);
    row.append(name, hardware, statusCell);
    elements.localModelList.append(row);
  }
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
  if (view === "localModel") return state.localEngineId || state.model.engine_id;
  return state.model.engine_id;
}

function selectedRecognitionMode() {
  return elements.recognitionModeOptions.querySelector('input[name="recognitionMode"]:checked')?.value || "batch";
}

function updateRecognitionSummary() {
  const realtime = selectedRecognitionMode() === "realtime";
  const modeCopy = realtime ? "边说边显示文字，停止后再校正并粘贴一次。" : "停止录音后转换并粘贴一次。";
  elements.localRecognitionSummary.textContent = `当前使用本地识别：${modeCopy}录音不会上传。`;
  elements.onlineRecognitionSummary.textContent = "当前使用在线识别：完整录音会上传给所选厂商，完成后只粘贴一次。";
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
      selectedRecognitionMode(),
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
  if (state.modelBusy) return;
  state.modelBusy = true;
  elements.modelTestStatus.textContent = "正在加载并测试模型…";
  try {
    const response = await callApi("test_local_model", modelId, selectedModelDevice());
    syncModelControls(response.data);
    elements.modelTestStatus.textContent = `${response.message} 加载耗时 ${response.data?.elapsed_ms || 0} 毫秒。`;
    showToast(response.message);
  } catch (error) {
    elements.modelTestStatus.textContent = error.message;
    elements.modelTestStatus.classList.add("is-error");
  } finally {
    state.modelBusy = false;
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
    || state.draft.standby !== state.saved.standby;
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
      submitted.standby
    );
    const data = response.data || {};
    state.saved = {
      color: normalizeColor(data.color || state.draft.color),
      opacity: clampOpacity(data.opacity ?? state.draft.opacity),
      hotkey: parseHotkey(data.hotkey || state.draft.hotkey).label,
      standby: data.standby_enabled === true,
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
  elements.resetButton.addEventListener("click", () => {
    state.draft = { ...state.defaults };
    syncAppearanceControls();
  });
  elements.saveButton.addEventListener("click", saveAppearance);
  elements.localModelSaveButton.addEventListener("click", () => saveModelSettings("localModel"));
  elements.onlineModelSaveButton.addEventListener("click", () => saveModelSettings("onlineModel"));
  elements.recognitionModeOptions.addEventListener("change", updateRecognitionSummary);

  elements.historySearch.maxLength = 200;
  elements.historySearch.addEventListener("input", () => {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => loadHistory({ silent: true }), 220);
  });
  elements.refreshButton.addEventListener("click", () => loadHistory());
  elements.copyButton.addEventListener("click", () => copyEntry());
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
  if (bridgeStarted || typeof window.pywebview?.api?.get_initial_state !== "function") {
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
    };
    state.draft = { ...state.saved };
    const defaultColor = normalizeColor(appearance.default_color || "#2563EB");
    state.defaults = {
      color: COLOR_PATTERN.test(defaultColor) ? defaultColor : "#2563EB",
      opacity: clampOpacity(appearance.default_opacity ?? 100),
      hotkey: parseHotkey(appearance.default_hotkey || "Ctrl+Alt+Space").label,
      standby: appearance.default_standby_enabled === true,
    };
    normalizeHistoryPayload(response.data?.history || {});
    syncModelControls(response.data?.model || {});
    syncAppearanceControls();
    renderHistory();
    state.pollTimer = window.setInterval(pollHistorySignature, 1200);
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

window.addEventListener("pywebviewready", initializeBridge);
if (typeof window.pywebview?.api?.get_initial_state === "function") {
  initializeBridge();
}
