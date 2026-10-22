"use strict";

const $ = (id) => document.getElementById(id);
const canvasSizes = {
  "9:16": [1080, 1920],
  "3:4": [1080, 1440],
  "4:5": [1080, 1350],
  "1:1": [1080, 1080],
  "4:3": [1440, 1080],
  "16:9": [1920, 1080],
};
const fileInputs = {background: "background", avatar: "avatar"};
const assetStatusInputs = {background: "backgroundStatus", avatar: "avatarStatus"};
const kinds = ["title", "subtitle"];

let ratio = "3:4";
let fonts = [];
let fontFamilies = [];
let selectedLocalFamilies = {title: "", subtitle: ""};
const localVariantHistory = {title: {}, subtitle: {}};
let openFontPickerKind = null;
let openFamilyPickerKind = null;
let fontCatalogRevision = 0;
const fontObservers = {};
let fontDefaults = {title: "", subtitle: "", local: ""};
let rememberedFonts = {
  title: {system: "", local: ""},
  subtitle: {system: "", local: ""},
};
let savedAssets = {};
let assetActions = {background: "retain", avatar: "retain"};
const textLayers = ["title", "subtitle", "account"];
const layerPositions = {
  title: {x: null, y: null},
  subtitle: {x: null, y: null},
  account: {x: 7.2, y: 68},
};
const layerDefaults = {
  title: {x: 0, y: 0},
  subtitle: {x: 0, y: 0},
  account: {x: 7.2, y: 68},
};
let layerDimensions = {
  title: {width: 0, height: 0},
  subtitle: {width: 0, height: 0},
  account: {width: 0, height: 0},
};
let previewTimer = null;
let renderController = null;
let previewUrl = null;

let renderSerial = 0;
let ready = false;
let previewReady = false;
let dragging = null;

function setMessage(message, error = false) {
  $("feedback").textContent = message;
  $("feedback").classList.toggle("error", error);
}

function setRenderingState(text, error = false) {
  $("renderState").textContent = text;
  $("renderState").classList.toggle("error", error);
}

function refreshAssetStatus(key) {
  const file = $(fileInputs[key]).files[0];
  const saved = savedAssets[key];
  const status = $(assetStatusInputs[key]);
  if (assetActions[key] === "clear") {
    status.textContent = "当前预览已移除；保存模板后同步更新";
  } else if (file) {
    status.textContent = "本次上传：" + file.name;
  } else if (saved) {
    status.textContent = "已存本机：" + saved;
  } else {
    status.textContent = key === "background" ?
      "未上传时使用内置黑色光晕背景" : "可选；自动裁切为圆形";
  }
  const clear = document.querySelector('[data-clear="' + key + '"]');
  if (clear) clear.textContent = assetActions[key] === "clear" ? "恢复已存" : "移除";
}

function updatePreviewDimensions() {
  const [width, height] = canvasSizes[ratio];
  const stage = document.querySelector(".preview-stage");
  const frame = $("previewFrame");
  const availableWidth = Math.max(185, stage.clientWidth - 52);
  const availableHeight = window.innerWidth <= 800 ? 535 : 620;
  const scale = Math.min(availableWidth / width, availableHeight / height);
  frame.style.width = Math.round(width * scale) + "px";
  frame.style.height = Math.round(height * scale) + "px";
  frame.style.aspectRatio = width + " / " + height;
  for (const name of textLayers) positionLayer(name);
}

function setRatio(value, doPreview = true) {
  if (!canvasSizes[value]) return;
  if (ratio !== value) {
    // 切换画幅时，旧图层尺寸不再适用；等待新的字体像素测量。
    layerDimensions = {
      title: {width: 0, height: 0},
      subtitle: {width: 0, height: 0},
      account: {width: 0, height: 0},
    };
    for (const name of textLayers) $(name + "DragHandle").hidden = true;
  }
  ratio = value;
  document.querySelectorAll(".ratio-choice").forEach((button) => {
    const selected = button.dataset.ratio === ratio;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  const [width, height] = canvasSizes[ratio];
  $("ratioSize").textContent = width + " × " + height + " 像素";
  $("outputSize").textContent = width + " × " + height;
  updatePreviewDimensions();
  if (doPreview) scheduleRender();
}

function currentFontMode(kind) {
  return $(kind + "FontMode").value;
}

function renderFamilyOptions(kind) {
  const mode = currentFontMode(kind);
  const row = $(kind + "FontFamilyRow");
  const selector = $(kind + "FontFamily");
  row.hidden = mode !== "local";
  $(kind + "FontVariantCaption").textContent = mode === "local" ? "字形与字重规格" : "系统字体";
  if (!fontFamilies.length) {
    selector.replaceChildren(new Option("暂无项目字体家族", ""));
    selector.disabled = true;
    selectedLocalFamilies[kind] = "";
    updateFamilyTrigger(kind);
    renderFamilyChoices(kind);
    return;
  }
  selector.disabled = false;
  let current = selectedLocalFamilies[kind];
  if (!fontFamilies.some((family) => family.id === current)) {
    const remembered = fonts.find((font) => font.id === rememberedFonts[kind].local && font.source === "local");
    current = remembered?.family || fontFamilies[0].id;
  }
  selectedLocalFamilies[kind] = current;
  selector.replaceChildren(...fontFamilies.map((family) =>
    new Option(family.name + "（" + family.count + " 种文件规格）", family.id)
  ));
  selector.value = current;
  updateFamilyTrigger(kind);
  renderFamilyChoices(kind);
}

function localDefaultScore(font) {
  const rank = {OTF: 0, TTF: 1, WOFF2: 2, WOFF: 3, TTC: 4, OTC: 5};
  return [
    font.monospace ? 1 : 0,
    Math.abs(Number(font.weight ?? 400) - 400),
    font.italic ? 1 : 0,
    rank[font.format] ?? 5,
  ];
}

function compareDefaultLocalVariant(a, b) {
  const ka = localDefaultScore(a);
  const kb = localDefaultScore(b);
  for (let i = 0; i < ka.length; i++) {
    if (ka[i] !== kb[i]) return ka[i] - kb[i];
  }
  return a.name.localeCompare(b.name);
}

function fontsForMode(kind, mode) {
  return fonts.filter((font) =>
    font.source === mode && (mode !== "local" || font.family === selectedLocalFamilies[kind])
  );
}

function fontForMode(kind, mode) {
  const available = fontsForMode(kind, mode);
  if (!available.length) return "";
  const remembered = mode === "local"
    ? localVariantHistory[kind][selectedLocalFamilies[kind]] || rememberedFonts[kind].local
    : rememberedFonts[kind].system;
  if (available.some((font) => font.id === remembered)) return remembered;
  if (mode === "local") {
    return available.slice().sort(compareDefaultLocalVariant)[0].id;
  }
  if (available.some((font) => font.id === fontDefaults[kind])) return fontDefaults[kind];
  return available[0].id;
}

function previewImageUrl(font) {
  return "/api/font-preview?id=" + encodeURIComponent(font.id) + "&compact=1&v=" + fontCatalogRevision;
}

function attachFontPreview(image, font, fallback = null) {
  image.alt = font.sample ? "字形示例：" + font.sample : "该字体的字形示例";
  image.decoding = "async";
  image.onerror = () => {
    image.hidden = true;
    if (fallback) {
      fallback.textContent = font.label || "字形样张暂不可用";
      fallback.hidden = false;
    }
  };
  image.onload = () => {
    image.hidden = false;
    if (fallback) fallback.hidden = true;
  };
  image.src = previewImageUrl(font);
}

function fontSampleBlock(font) {
  const preview = document.createElement("span");
  preview.className = "font-option-preview";
  if (font && font.sample !== "" && font.coverage !== "invalid") {
    const img = document.createElement("img");
    img.className = "font-sample-image pending";
    img.alt = font.sample ? "字形：" + font.sample : "字体真实字形";
    img.loading = "lazy";
    img.dataset.previewUrl = previewImageUrl(font);
    const note = document.createElement("span");
    note.className = "font-preview-note";
    note.textContent = "字形加载中…";
    preview.append(img, note);
  } else {
    const note = document.createElement("span");
    note.className = "font-preview-note";
    note.textContent = font?.label || "样张不可用";
    preview.append(note);
  }
  return preview;
}

function coverageBadge(font) {
  const badge = document.createElement("span");
  badge.className = "font-coverage-badge";
  if (font?.coverage === "latin") badge.classList.add("latin");
  if (font?.coverage === "invalid" || font?.coverage === "unsupported") badge.classList.add("invalid");
  badge.textContent = font?.label || (font?.source === "system" ? "系统字体" : "字体样张");
  return badge;
}

function fontOption(kind, font, selectedId) {
  const option = document.createElement("button");
  option.type = "button";
  option.className = "font-option";
  option.dataset.fontId = font.id;
  option.setAttribute("role", "option");
  option.setAttribute("aria-selected", String(font.id === selectedId));
  option.setAttribute("aria-label", font.source === "local" ?
    font.family + " " + font.variant + " · " + font.filename : font.name);
  option.tabIndex = -1;

  const details = document.createElement("span");
  details.className = "font-option-details";
  const name = document.createElement("span");
  name.className = "font-option-name";
  name.textContent = font.source === "local" ? font.variant : font.name;
  name.title = font.source === "local" ? font.relative_path : font.name;
  details.append(name);
  if (font.source === "local") {
    const filename = document.createElement("span");
    filename.className = "font-option-file";
    filename.textContent = font.filename;
    filename.title = font.relative_path;
    details.append(filename);
  }
  details.append(coverageBadge(font));
  option.append(fontSampleBlock(font), details);
  return option;
}

function familyRepresentative(kind, familyId) {
  const variants = fonts.filter((font) => font.source === "local" && font.family === familyId);
  if (!variants.length) return null;
  const remembered = localVariantHistory[kind][familyId];
  if (remembered) {
    const stored = variants.find((font) => font.id === remembered);
    if (stored && stored.coverage !== "invalid") return stored;
  }
  const usable = variants.filter((font) => font.coverage !== "invalid");
  return (usable.length ? usable : variants).slice().sort(compareDefaultLocalVariant)[0];
}

function familyOption(kind, family) {
  const representative = familyRepresentative(kind, family.id);
  const option = document.createElement("button");
  option.type = "button";
  option.className = "font-option font-family-option";
  option.dataset.familyId = family.id;
  option.setAttribute("role", "option");
  option.setAttribute("aria-selected", String(family.id === selectedLocalFamilies[kind]));
  option.setAttribute("aria-label", family.name + "，" + family.count + " 种文件规格");
  option.tabIndex = -1;

  const details = document.createElement("span");
  details.className = "font-option-details";
  const name = document.createElement("span");
  name.className = "font-option-name font-family-option-name";
  name.textContent = family.name;
  name.title = family.name;
  const count = document.createElement("span");
  count.className = "font-option-file";
  count.textContent = family.count + " 种可选规格";
  details.append(name, count);
  if (representative) details.append(coverageBadge(representative));
  option.append(fontSampleBlock(representative), details);
  return option;
}

function updateFamilyTrigger(kind) {
  const name = $(kind + "FontFamilyName");
  const info = $(kind + "FontFamilyBadge");
  const sample = $(kind + "FontFamilyPreview");
  const trigger = $(kind + "FontFamilyTrigger");
  const family = fontFamilies.find((item) => item.id === selectedLocalFamilies[kind]);
  if (!family) {
    name.textContent = "请添加字体家族";
    info.textContent = "fonts/ 下每个子目录是一种字体";
    sample.hidden = true;
    sample.removeAttribute("src");
    trigger.disabled = true;
    return;
  }
  trigger.disabled = false;
  name.textContent = family.name;
  name.title = family.name;
  info.textContent = family.count + " 种字形 / 字重规格";
  const chosen = familyRepresentative(kind, family.id);
  sample.hidden = true;
  if (chosen && chosen.coverage !== "invalid" && chosen.sample !== "") {
    attachFontPreview(sample, chosen);
  } else {
    sample.removeAttribute("src");
  }
}

function renderFamilyChoices(kind) {
  const filter = $(kind + "FontFamilySearch").value.trim().toLocaleLowerCase();
  const visible = fontFamilies.filter((family) => family.name.toLocaleLowerCase().includes(filter));
  const list = $(kind + "FontFamilyOptions");
  if (!visible.length) {
    const empty = document.createElement("div");
    empty.className = "font-option-empty";
    empty.textContent = fontFamilies.length ?
      "没有匹配的字体家族，请尝试其他名称。" : "fonts/ 中还没有字体家族。";
    list.replaceChildren(empty);
  } else {
    list.replaceChildren(...visible.map((family) => familyOption(kind, family)));
  }
  loadVisibleFontImages(kind, "family");
}

function loadVisibleFontImages(kind, type = "variant") {
  const family = type === "family";
  const list = $(kind + (family ? "FontFamilyOptions" : "FontOptions"));
  const observerKey = kind + ":" + type;
  if (fontObservers[observerKey]) fontObservers[observerKey].disconnect();
  const images = Array.from(list.querySelectorAll("img[data-preview-url]"));
  function activate(image) {
    const fallback = image.nextElementSibling;
    image.onerror = () => {
      image.hidden = true;
      if (fallback) fallback.textContent = "字形样张暂不可用";
    };
    image.onload = () => {
      image.classList.remove("pending");
      image.hidden = false;
      if (fallback) fallback.hidden = true;
    };
    image.src = image.dataset.previewUrl;
    delete image.dataset.previewUrl;
  }
  if (typeof IntersectionObserver !== "undefined") {
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          observer.unobserve(entry.target);
          activate(entry.target);
        }
      }
    }, {root: list, rootMargin: "140px"});
    fontObservers[observerKey] = observer;
    images.forEach((image) => observer.observe(image));
  } else {
    images.forEach(activate);
  }
}

function updateFontTrigger(kind, selected) {
  const nameElement = $(kind + "FontName");
  const preview = $(kind + "FontPreview");
  const badge = $(kind + "FontBadge");
  if (!selected) {
    nameElement.textContent = currentFontMode(kind) === "local" ? "项目目录还没有可选字体" : "未发现系统字体";
    badge.textContent = "";
    preview.hidden = true;
    preview.removeAttribute("src");
    $(kind + "FontTrigger").disabled = true;
    return;
  }
  $(kind + "FontTrigger").disabled = false;
  nameElement.textContent = selected.source === "local"
    ? selected.variant + " · " + selected.filename
    : selected.name;
  nameElement.title = selected.source === "local" ? selected.relative_path : selected.name;
  badge.textContent = selected.label || "系统字体";
  badge.className = "font-coverage-badge";
  if (selected.coverage === "latin") badge.classList.add("latin");
  if (selected.coverage === "invalid" || selected.coverage === "unsupported") badge.classList.add("invalid");
  preview.hidden = true;
  if (selected.sample === "" || selected.coverage === "invalid") {
    preview.removeAttribute("src");
  } else {
    attachFontPreview(preview, selected);
  }
}

function renderFontOptions(kind) {
  const mode = currentFontMode(kind);
  const select = $(kind + "Font");
  const all = fontsForMode(kind, mode);
  const selectedId = fontForMode(kind, mode);
  rememberedFonts[kind][mode] = selectedId;
  if (mode === "local" && selectedLocalFamilies[kind] && selectedId) {
    localVariantHistory[kind][selectedLocalFamilies[kind]] = selectedId;
  }
  select.replaceChildren(...all.map((font) => new Option(font.name, font.id)));
  select.value = selectedId;
  select.disabled = all.length === 0;
  updateFontTrigger(kind, all.find((font) => font.id === selectedId));

  const filter = $(kind + "FontSearch").value.trim().toLocaleLowerCase();
  const candidates = all.filter((font) =>
    !filter ||
    font.name.toLocaleLowerCase().includes(filter) ||
    (font.variant || "").toLocaleLowerCase().includes(filter) ||
    (font.filename || "").toLocaleLowerCase().includes(filter)
  );
  const list = $(kind + "FontOptions");
  if (candidates.length) {
    list.replaceChildren(...candidates.map((font) => fontOption(kind, font, selectedId)));
  } else {
    const empty = document.createElement("div");
    empty.className = "font-option-empty";
    empty.textContent = all.length ?
      "没有匹配的字体规格，请尝试其他关键词。" :
      (mode === "local" ? "所选家族暂无可用字体规格。" : "未找到可用系统字体。");
    list.replaceChildren(empty);
  }
  loadVisibleFontImages(kind);
}

function closeFontPicker(kind, focus = false) {
  $(kind + "FontMenu").hidden = true;
  $(kind + "FontTrigger").setAttribute("aria-expanded", "false");
  if (openFontPickerKind === kind) openFontPickerKind = null;
  if (focus) $(kind + "FontTrigger").focus();
}

function toggleFontPicker(kind) {
  for (const other of kinds) closeFamilyPicker(other);
  if (openFontPickerKind === kind) {
    closeFontPicker(kind);
    return;
  }
  for (const other of kinds) closeFontPicker(other);
  openFontPickerKind = kind;
  $(kind + "FontMenu").hidden = false;
  $(kind + "FontTrigger").setAttribute("aria-expanded", "true");
  $(kind + "FontSearch").value = "";
  renderFontOptions(kind);
  $(kind + "FontSearch").focus();
}

function pickFont(kind, id) {
  const mode = currentFontMode(kind);
  const selected = fonts.find((font) => font.id === id && font.source === mode);
  if (!selected) return;
  rememberedFonts[kind][mode] = selected.id;
  if (mode === "local") {
    localVariantHistory[kind][selectedLocalFamilies[kind]] = selected.id;
  }
  renderFontOptions(kind);
  if (mode === "local") updateFamilyTrigger(kind);
  closeFontPicker(kind, true);
  scheduleRender();
}

function closeFamilyPicker(kind, focus = false) {
  $(kind + "FontFamilyMenu").hidden = true;
  $(kind + "FontFamilyTrigger").setAttribute("aria-expanded", "false");
  if (openFamilyPickerKind === kind) openFamilyPickerKind = null;
  if (focus) $(kind + "FontFamilyTrigger").focus();
}

function toggleFamilyPicker(kind) {
  if (openFamilyPickerKind === kind) {
    closeFamilyPicker(kind);
    return;
  }
  for (const other of kinds) {
    closeFamilyPicker(other);
    closeFontPicker(other);
  }
  openFamilyPickerKind = kind;
  $(kind + "FontFamilyMenu").hidden = false;
  $(kind + "FontFamilyTrigger").setAttribute("aria-expanded", "true");
  $(kind + "FontFamilySearch").value = "";
  renderFamilyChoices(kind);
  $(kind + "FontFamilySearch").focus();
}

function pickFamily(kind, familyId) {
  if (!fontFamilies.some((family) => family.id === familyId)) return;
  closeFamilyPicker(kind, true);
  const select = $(kind + "FontFamily");
  select.value = familyId;
  select.dispatchEvent(new Event("change", {bubbles: true}));
}

function fontPickerKeydown(event, kind, type = "variant") {
  const family = type === "family";
  if (event.key === "Escape") {
    if (family) closeFamilyPicker(kind, true);
    else closeFontPicker(kind, true);
    event.preventDefault();
    return;
  }
  const list = $(kind + (family ? "FontFamilyOptions" : "FontOptions"));
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    const items = Array.from(list.querySelectorAll(".font-option"));
    if (!items.length) return;
    const focusIndex = items.indexOf(document.activeElement);
    const target = event.key === "ArrowDown" ?
      Math.min(items.length - 1, focusIndex + 1) :
      Math.max(0, focusIndex < 0 ? items.length - 1 : focusIndex - 1);
    items[target].focus();
    items[target].scrollIntoView({block: "nearest"});
    event.preventDefault();
  }
}

function loadFontCatalog(catalog, settings = null) {
  fontCatalogRevision += 1;
  fonts = catalog.fonts || [];
  fontFamilies = catalog.families || [];
  fontDefaults = catalog.defaults || {title: "", subtitle: "", local: ""};
  if (settings) {
    for (const kind of kinds) {
      const mode = settings[kind + "_font_mode"] === "local" ? "local" : "system";
      const id = settings[kind + "_font_id"] || "";
      const font = fonts.find((entry) => entry.id === id && entry.source === mode);
      if (font) {
        rememberedFonts[kind][mode] = font.id;
        if (mode === "local") {
          selectedLocalFamilies[kind] = font.family;
          localVariantHistory[kind][font.family] = font.id;
        }
      }
      $(kind + "FontMode").value = mode;
    }
  }
  for (const kind of kinds) {
    renderFamilyOptions(kind);
    renderFontOptions(kind);
  }
  const localCount = catalog.local_count ?? fonts.filter((font) => font.source === "local").length;
  $("localFontCount").textContent = localCount
    ? "已识别 " + fontFamilies.length + " 个字体家族、" + localCount + " 个字体文件（规格可单独选择）"
    : "fonts/ 目录已就绪：放入字体后点击「刷新字体列表」";
}

async function refreshFontCatalog() {
  const button = $("refreshFonts");
  button.disabled = true;
  try {
    const response = await fetch("/api/fonts", {cache: "no-store"});
    if (!response.ok) throw new Error("读取项目字体目录失败。");
    const catalog = await response.json();
    loadFontCatalog(catalog);
    setMessage("字体列表已刷新，共识别 " + catalog.local_count + " 个项目字体。");
    scheduleRender();
  } catch (error) {
    setMessage(error.message || "刷新字体失败。", true);
  } finally {
    button.disabled = false;
  }
}

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

function layerLimitPercent(name) {
  const [width, height] = canvasSizes[ratio];
  const dimension = layerDimensions[name];
  return {
    x: 100 * Math.max(0, width - dimension.width) / width,
    y: 100 * Math.max(0, height - dimension.height) / height,
  };
}

function layerDisplayPosition(name) {
  const manual = layerPositions[name];
  const defaultPosition = layerDefaults[name];
  const max = layerLimitPercent(name);
  return {
    x: clamp(manual.x == null ? defaultPosition.x : manual.x, 0, max.x),
    y: clamp(manual.y == null ? defaultPosition.y : manual.y, 0, max.y),
  };
}

function positionLayer(name) {
  const position = layerDisplayPosition(name);
  const dimension = layerDimensions[name];
  const [width, height] = canvasSizes[ratio];
  const handle = $(name + "DragHandle");
  handle.style.width = dimension.width / width * 100 + "%";
  handle.style.height = dimension.height / height * 100 + "%";
  handle.style.left = position.x + "%";
  handle.style.top = position.y + "%";
  const entry = layerPositions[name];
  // 标题的空值代表持续自动布局；编辑框显示自动状态。
  for (const axis of ["x", "y"]) {
    const key = name + axis.toUpperCase();
    $(key).value = entry[axis] == null ? "" : position[axis].toFixed(2);
  }
}

function setLayerPosition(name, x, y) {
  if (!Number.isFinite(x) || !Number.isFinite(y)) return;
  const limit = layerLimitPercent(name);
  layerPositions[name] = {
    x: Math.round(clamp(x, 0, limit.x) * 10000) / 10000,
    y: Math.round(clamp(y, 0, limit.y) * 10000) / 10000,
  };
  positionLayer(name);
}

function updateLayerCoordinate(name) {
  const state = layerPositions[name];
  const next = {...state};
  for (const axis of ["x", "y"]) {
    const raw = $(name + axis.toUpperCase()).value.trim();
    // 允许仅让某一轴进入自动布局，另一轴仍采用手动坐标。
    if (!raw && name !== "account") next[axis] = null;
    else if (raw && Number.isFinite(Number(raw))) next[axis] = clamp(Number(raw), 0, 100);
    else next[axis] = state[axis];
  }
  layerPositions[name] = next;
  const shown = layerDisplayPosition(name);
  // 显示值会裁剪到允许位置；保存时对手动值作同样裁剪。
  for (const axis of ["x", "y"]) {
    if (layerPositions[name][axis] !== null) layerPositions[name][axis] = shown[axis];
  }
  positionLayer(name);
}

function resetTextLayer(name) {
  if (name === "account") {
    layerPositions.account = {x: 7.2, y: 68};
  } else {
    layerPositions[name] = {x: null, y: null};
  }
  positionLayer(name);
}

function buildFormData() {
  const fd = new FormData();
  fd.set("title", $("title").value);
  fd.set("subtitle", $("subtitle").value);
  fd.set("account", $("account").value);
  for (const name of textLayers) {
    for (const axis of ["x", "y"]) {
      const coord = layerPositions[name][axis];
      fd.set(name + "_" + axis, coord == null ? "" : String(coord));
    }
  }
  fd.set("ratio", ratio);
  fd.set("darkness", $("darkness").value);
  fd.set("focus_y", $("focusY").value);
  fd.set("glow", $("glow").checked ? "true" : "false");
  for (const kind of kinds) {
    const mode = currentFontMode(kind);
    fd.set(kind + "_font_mode", mode);
    fd.set(kind + "_font_id", fontForMode(kind, mode));
  }
  for (const [key, id] of Object.entries(fileInputs)) {
    fd.set(key + "_action", assetActions[key]);
    if (assetActions[key] !== "clear" && $(id).files.length) {
      fd.set(key, $(id).files[0]);
    }
  }
  return fd;
}

function scheduleRender() {
  if (!ready) return;
  clearTimeout(previewTimer);
  renderSerial += 1;
  if (renderController) renderController.abort();
  $("loadingCover").classList.add("hidden");
  for (const name of textLayers) $(name + "DragHandle").hidden = true;
  $("downloadCover").disabled = true;
  previewReady = false;
  setRenderingState("待更新");
  previewTimer = setTimeout(renderPreview, 400);
}

async function parseError(response) {
  try {
    const payload = await response.json();
    return payload.error || "生成失败，请检查输入内容。";
  } catch {
    return "请求失败（" + response.status + "），请检查服务日志。";
  }
}

async function renderPreview() {
  if (!ready) return;
  clearTimeout(previewTimer);
  const serial = ++renderSerial;
  if (renderController) renderController.abort();
  renderController = new AbortController();
  const controller = renderController;
  $("loadingCover").classList.remove("hidden");
  for (const name of textLayers) $(name + "DragHandle").hidden = true;
  $("downloadCover").disabled = true;
  previewReady = false;
  setRenderingState("正在渲染");
  setMessage("");

  try {
    const [baseResponse, layersResponse] = await Promise.all([
      fetch("/api/render?preview=all-text", {
        method: "POST", body: buildFormData(), signal: controller.signal, cache: "no-store",
      }),
      fetch("/api/text-layers", {
        method: "POST", body: buildFormData(), signal: controller.signal, cache: "no-store",
      }),
    ]);
    if (!baseResponse.ok) throw new Error(await parseError(baseResponse));
    if (!layersResponse.ok) throw new Error(await parseError(layersResponse));
    const [baseBlob, layersPayload] = await Promise.all([baseResponse.blob(), layersResponse.json()]);
    if (serial !== renderSerial) return;

    const nextPreviewUrl = URL.createObjectURL(baseBlob);
    const oldPreview = previewUrl;
    previewUrl = nextPreviewUrl;
    $("previewImage").src = previewUrl;
    $("previewImage").hidden = false;
    $("previewPlaceholder").classList.add("hidden");

    for (const name of textLayers) {
      const layer = layersPayload.layers[name];
      const dimensions = {width: Number(layer.width) || 0, height: Number(layer.height) || 0};
      const [width, height] = canvasSizes[ratio];
      layerDimensions[name] = dimensions;
      layerDefaults[name] = {
        x: Number(layer.default_position[0]) / width * 100,
        y: Number(layer.default_position[1]) / height * 100,
      };
      $(name + "LayerImage").src = "data:image/png;base64," + layer.png;
      positionLayer(name);
      $(name + "DragHandle").hidden = !(dimensions.width && dimensions.height);
    }
    const lines = baseResponse.headers.get("X-Title-Lines") || "1";
    const titleSize = baseResponse.headers.get("X-Title-Font-Px") || "—";
    const subLines = baseResponse.headers.get("X-Subtitle-Lines") || "1";
    $("layoutInfo").textContent = "大标题 " + lines + " 行 · " + titleSize +
      "px / 小标题 " + subLines + " 行";
    previewReady = true;
    $("downloadCover").disabled = false;
    setRenderingState("三块文字可拖动");
    if (oldPreview) URL.revokeObjectURL(oldPreview);
  } catch (error) {
    if (error.name === "AbortError" || serial !== renderSerial) return;
    setRenderingState("排版失败", true);
    setMessage(error.message || "预览失败，请重试。", true);
    for (const name of textLayers) $(name + "DragHandle").hidden = true;
  } finally {
    if (serial === renderSerial) $("loadingCover").classList.add("hidden");
  }
}

async function savePreset() {
  if (!ready) return;
  const button = $("savePreset");
  button.disabled = true;
  setMessage("正在保存默认模板…");
  try {
    const response = await fetch("/api/preset", {method: "POST", body: buildFormData()});
    if (!response.ok) throw new Error(await parseError(response));
    const result = await response.json();
    savedAssets = result.assets || {};
    for (const key of Object.keys(fileInputs)) {
      $(fileInputs[key]).value = "";
      assetActions[key] = "retain";
      refreshAssetStatus(key);
    }
    setMessage(result.message || "模板已保存。");
    scheduleRender();
  } catch (error) {
    setMessage(error.message || "保存失败。", true);
  } finally {
    button.disabled = false;
  }
}

async function downloadCover() {
  if (!previewReady) return;
  const button = $("downloadCover");
  button.disabled = true;
  const originalLabel = button.innerHTML;
  button.textContent = "正在导出高清 PNG…";
  try {
    const response = await fetch("/api/render", {method: "POST", body: buildFormData()});
    if (!response.ok) throw new Error(await parseError(response));
    const blob = await response.blob();
    const filename = ($("title").value.trim() || "封面")
      .replace(/[\\/:*?"<>|]/g, "_").replace(/\s+/g, "_").slice(0, 40);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename + "_" + ratio.replace(":", "x") + ".png";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 10000);
    setMessage("高清封面已准备完成。");
  } catch (error) {
    setMessage(error.message || "下载失败。", true);
  } finally {
    button.innerHTML = originalLabel;
    button.disabled = !previewReady;
  }
}

function beginDrag(event, name) {
  if (!ready || !previewReady || !layerDimensions[name].width || dragging) return;
  if (event.pointerType === "mouse" && event.button !== 0) return;
  const handle = $(name + "DragHandle");
  const bounds = handle.getBoundingClientRect();
  dragging = {
    name,
    id: event.pointerId,
    offsetX: event.clientX - bounds.left,
    offsetY: event.clientY - bounds.top,
  };
  handle.setPointerCapture(event.pointerId);
  handle.classList.add("dragging");
  event.preventDefault();
}

function continueDrag(event, name) {
  if (!dragging || dragging.name !== name || event.pointerId !== dragging.id) return;
  const frame = $("previewFrame").getBoundingClientRect();
  setLayerPosition(
    name,
    100 * (event.clientX - frame.left - dragging.offsetX) / frame.width,
    100 * (event.clientY - frame.top - dragging.offsetY) / frame.height,
  );
  event.preventDefault();
}

function finishDrag(event, name) {
  if (!dragging || dragging.name !== name || event.pointerId !== dragging.id) return;
  const handle = $(name + "DragHandle");
  if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
  handle.classList.remove("dragging");
  dragging = null;
}

function nudgeLayer(event, name) {
  if (!previewReady || !layerDimensions[name].width) return;
  const [width, height] = canvasSizes[ratio];
  const step = event.shiftKey ? 10 : 1;
  const movements = {
    ArrowLeft: [-step / width * 100, 0],
    ArrowRight: [step / width * 100, 0],
    ArrowUp: [0, -step / height * 100],
    ArrowDown: [0, step / height * 100],
  };
  const change = movements[event.key];
  if (!change) return;
  const current = layerDisplayPosition(name);
  setLayerPosition(name, current.x + change[0], current.y + change[1]);
  event.preventDefault();
}

function bindEvents() {
  ["title", "subtitle", "account"].forEach((id) => $(id).addEventListener("input", scheduleRender));
  document.querySelectorAll(".ratio-choice").forEach((button) => {
    button.addEventListener("click", () => setRatio(button.dataset.ratio));
  });
  for (const kind of kinds) {
    $(kind + "FontTrigger").addEventListener("click", () => toggleFontPicker(kind));
    $(kind + "FontSearch").addEventListener("input", () => renderFontOptions(kind));
    $(kind + "FontMenu").addEventListener("keydown", (event) => fontPickerKeydown(event, kind));
    $(kind + "FontOptions").addEventListener("click", (event) => {
      const option = event.target.closest("button[data-font-id]");
      if (option) pickFont(kind, option.dataset.fontId);
    });
    $(kind + "FontFamilyTrigger").addEventListener("click", () => toggleFamilyPicker(kind));
    $(kind + "FontFamilySearch").addEventListener("input", () => renderFamilyChoices(kind));
    $(kind + "FontFamilyMenu").addEventListener("keydown", (event) =>
      fontPickerKeydown(event, kind, "family"));
    $(kind + "FontFamilyOptions").addEventListener("click", (event) => {
      const option = event.target.closest("button[data-family-id]");
      if (option) pickFamily(kind, option.dataset.familyId);
    });
    $(kind + "FontMode").addEventListener("change", () => {
      closeFontPicker(kind);
      closeFamilyPicker(kind);
      $(kind + "FontSearch").value = "";
      $(kind + "FontFamilySearch").value = "";
      renderFamilyOptions(kind);
      renderFontOptions(kind);
      scheduleRender();
    });
    $(kind + "FontFamily").addEventListener("change", (event) => {
      selectedLocalFamilies[kind] = event.target.value;
      closeFontPicker(kind);
      closeFamilyPicker(kind);
      $(kind + "FontSearch").value = "";
      renderFamilyOptions(kind);
      renderFontOptions(kind);
      scheduleRender();
    });
  }
  document.addEventListener("pointerdown", (event) => {
    if (openFontPickerKind && !$(openFontPickerKind + "FontPicker").contains(event.target)) {
      closeFontPicker(openFontPickerKind);
    }
    if (openFamilyPickerKind && !$(openFamilyPickerKind + "FontFamilyPicker").contains(event.target)) {
      closeFamilyPicker(openFamilyPickerKind);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (openFontPickerKind) closeFontPicker(openFontPickerKind, true);
      if (openFamilyPickerKind) closeFamilyPicker(openFamilyPickerKind, true);
    }
  });
  for (const [key, id] of Object.entries(fileInputs)) {
    $(id).addEventListener("change", () => {
      assetActions[key] = "retain";
      refreshAssetStatus(key);
      scheduleRender();
    });
  }
  document.querySelectorAll("[data-clear]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.clear;
      assetActions[key] = assetActions[key] === "clear" ? "retain" : "clear";
      $(fileInputs[key]).value = "";
      refreshAssetStatus(key);
      scheduleRender();
    });
  });
  for (const key of ["darkness", "focusY"]) {
    $(key).addEventListener("input", () => {
      $(key + "Value").textContent = $(key).value + "%";
      scheduleRender();
    });
  }
  for (const name of textLayers) {
    for (const axis of ["X", "Y"]) {
      $(name + axis).addEventListener("change", () => updateLayerCoordinate(name));
    }
    $("reset" + name[0].toUpperCase() + name.slice(1)).addEventListener(
      "click", () => resetTextLayer(name));
    const handle = $(name + "DragHandle");
    handle.addEventListener("pointerdown", (event) => beginDrag(event, name));
    handle.addEventListener("pointermove", (event) => continueDrag(event, name));
    handle.addEventListener("pointerup", (event) => finishDrag(event, name));
    handle.addEventListener("pointercancel", (event) => finishDrag(event, name));
    handle.addEventListener("keydown", (event) => nudgeLayer(event, name));
    $(name + "LayerImage").addEventListener("dragstart", (event) => event.preventDefault());
  }
  $("glow").addEventListener("change", scheduleRender);
  $("refreshFonts").addEventListener("click", refreshFontCatalog);
  $("refreshPreview").addEventListener("click", renderPreview);
  $("savePreset").addEventListener("click", savePreset);
  $("downloadCover").addEventListener("click", downloadCover);
  window.addEventListener("resize", updatePreviewDimensions);
  $("coverForm").addEventListener("submit", (event) => event.preventDefault());
}

async function initialize() {
  bindEvents();
  try {
    const [fontResponse, presetResponse] = await Promise.all([
      fetch("/api/fonts", {cache: "no-store"}),
      fetch("/api/preset", {cache: "no-store"}),
    ]);
    if (!fontResponse.ok || !presetResponse.ok) throw new Error("加载本机字体或模板配置失败。");
    const catalog = await fontResponse.json();
    const preset = await presetResponse.json();
    const settings = preset.settings || {};
    savedAssets = preset.assets || {};
    for (const key of ["title", "subtitle", "account", "darkness"]) {
      if (settings[key] !== undefined) $(key).value = settings[key];
    }
    if (settings.focus_y !== undefined) $("focusY").value = settings.focus_y;
    $("glow").checked = settings.glow !== false;
    $("darknessValue").textContent = $("darkness").value + "%";
    $("focusYValue").textContent = $("focusY").value + "%";
    loadFontCatalog(catalog, settings);
    setRatio(settings.ratio || "3:4", false);
    for (const name of textLayers) {
      const fallback = name === "account" ? {x: 7.2, y: 68} : {x: null, y: null};
      const parseValue = (value, def) => value === null || value === undefined || value === "" ? def : Number(value);
      layerPositions[name] = {
        x: parseValue(settings[name + "_x"], fallback.x),
        y: parseValue(settings[name + "_y"], fallback.y),
      };
      positionLayer(name);
    }
    for (const key of Object.keys(fileInputs)) refreshAssetStatus(key);
    ready = true;
    renderPreview();
  } catch (error) {
    setRenderingState("初始化失败", true);
    setMessage(error.message || "初始化失败，请检查本地服务。", true);
  }
}

window.addEventListener("beforeunload", () => {
  if (previewUrl) URL.revokeObjectURL(previewUrl);

});

initialize();
