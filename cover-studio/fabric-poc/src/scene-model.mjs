/** Cover Studio 场景模型 v2：浏览器端状态投影与每个画幅的独立位置。 */

export const RATIO_DIMENSIONS = {
  "3:4": [1080, 1440], "9:16": [1080, 1920],
  "16:9": [1920, 1080], "4:3": [1440, 1080],
  "4:5": [1080, 1350], "1:1": [1080, 1080],
};

export const TEXT_LAYER_IDS = ["title", "subtitle", "account"];

export function autoPosition() {
  return {mode: "auto", x: null, y: null};
}
export function manualPosition(x, y) {
  if (x == null && y == null) return autoPosition();
  return {mode: "manual", x: x ?? null, y: y ?? null};
}
export function defaultVariant() {
  return Object.fromEntries(TEXT_LAYER_IDS.map((id) => [id, autoPosition()]));
}
export function getPosition(scene, ratio, kind) {
  const data = scene?.variants?.[ratio]?.[kind] || autoPosition();
  return data.mode === "manual"
    ? {x: data.x ?? null, y: data.y ?? null}
    : {x: null, y: null};
}
export function getPositions(scene, ratio) {
  return Object.fromEntries(TEXT_LAYER_IDS.map(
    (kind) => [kind, getPosition(scene, ratio, kind)]
  ));
}
export function setPosition(scene, ratio, kind, x, y) {
  if (!RATIO_DIMENSIONS[ratio] || !TEXT_LAYER_IDS.includes(kind)) {
    throw Error("画幅或文字层不存在。");
  }
  for (const n of [x,y]) {
    if (n !== null && (!Number.isFinite(n) || n < 0 || n > 100)) {
      throw Error("坐标须为 0～100% 或自动定位。");
    }
  }
  scene.variants ||= {};
  scene.variants[ratio] ||= defaultVariant();
  scene.variants[ratio][kind] = manualPosition(x, y);
}
export function setContent(scene, values) {
  if (!scene || scene.schemaVersion !== 2) throw Error("场景版本不正确。");
  Object.assign(scene.content, values);
}
export function cloneAsNewDesign(scene) {
  const copy = structuredClone(scene);
  copy.id = null;
  copy.revision = 0;
  copy.updatedAt = null;
  return copy;
}
export function sceneSummary(scene) {
  return {
    id: scene.id, name: scene.name,
    ratio: scene.activeRatio,
    variants: Object.keys(scene.variants),
    revision: scene.revision,
  };
}
