/** 场景 v2 的布局质量偏好：按画幅安全区与人工重叠确认。 */
import {
  SAFETY_PROFILES,availableSafetyProfiles,canonicalPair
} from "./layout-diagnostics.mjs";

export function ensureQuality(scene){
  if(!scene || typeof scene!=="object")throw Error("设计尚未加载");
  scene.quality ||= {
    profilesByRatio:{},allowedOverlaps:[],allowedByRatio:{}
  };
  scene.quality.profilesByRatio ||= {};
  scene.quality.allowedOverlaps ||= []; // 兼容旧版全画幅确认关系
  scene.quality.allowedByRatio ||= {};
  return scene.quality;
}
export function getQualityProfile(scene,ratio){
  const preferences=ensureQuality(scene);
  const value=preferences.profilesByRatio[ratio]||"general";
  return availableSafetyProfiles(ratio).includes(value)?value:"general";
}
export function setQualityProfile(scene,ratio,id){
  if(!SAFETY_PROFILES[id] || !availableSafetyProfiles(ratio).includes(id))
    throw Error("当前画幅无法使用指定安全区方案");
  const quality=ensureQuality(scene);
  const before=getQualityProfile(scene,ratio);
  if(before===id)return false;
  if(id==="general")delete quality.profilesByRatio[ratio];
  else quality.profilesByRatio[ratio]=id;
  return true;
}
function lookupPairs(scene,ratio){
  const quality=ensureQuality(scene);
  if(ratio==="*")return quality.allowedOverlaps;
  if(!availableSafetyProfiles(ratio).includes("general"))throw Error("画幅比例无效");
  quality.allowedByRatio[ratio] ||= [];
  return quality.allowedByRatio[ratio];
}
export function approvedPairs(scene,ratio){
  const quality=ensureQuality(scene);
  const shared=quality.allowedOverlaps.map(pair=>({pair,scope:"*"}));
  const current=(quality.allowedByRatio[ratio]||[]).map(pair=>({pair,scope:ratio}));
  return [...shared,...current];
}
export function effectiveAllowedOverlaps(scene,ratio){
  const list=approvedPairs(scene,ratio);
  return [...new Map(list.map(x=>[x.pair.join("|"),x.pair])).values()];
}
export function isAllowedOverlap(scene,a,b,ratio=scene.activeRatio){
  const ids=canonicalPair(a,b);
  return effectiveAllowedOverlaps(scene,ratio).some(pair=>
    pair[0]===ids[0]&&pair[1]===ids[1]
  );
}
/** 默认仅作用于当前画幅；scope="*" 可撤销历史全画幅规则。 */
export function setAllowedOverlap(scene,a,b,allowed,ratio=scene.activeRatio){
  if(typeof allowed!=="boolean")throw Error("允许重叠开关必须是布尔值");
  const pair=canonicalPair(a,b);
  if(pair.includes("background"))throw Error("背景不参与重叠确认");
  const all=new Set([
    ...(scene.layers||[]).map(item=>item.id),
    ...(scene.extras?.layers||[]).map(item=>item.id),
    ...(scene.extras?.groups||[]).map(item=>item.id),
  ]);
  if(pair.some(id=>!all.has(id)))throw Error("存在已删除或不存在的图层");
  const quality=ensureQuality(scene);
  const pairs=lookupPairs(scene,ratio);
  const index=pairs.findIndex(item=>item[0]===pair[0]&&item[1]===pair[1]);
  if(allowed && index===-1){
    const total=quality.allowedOverlaps.length+
      Object.values(quality.allowedByRatio).reduce((n,list)=>n+list.length,0);
    if(total>=100)throw Error("允许重叠关系最多记录 100 组");
    pairs.push(pair);
    pairs.sort((x,y)=>x.join("|").localeCompare(y.join("|")));
    return true;
  }
  if(!allowed && index!==-1){
    pairs.splice(index,1);
    if(ratio!=="*" && !pairs.length)delete quality.allowedByRatio[ratio];
    return true;
  }
  return false;
}
export function forgetQualityLayer(scene,id){
  const quality=ensureQuality(scene);
  quality.allowedOverlaps=quality.allowedOverlaps.filter(pair=>!pair.includes(id));
  for(const [ratio,pairs] of Object.entries(quality.allowedByRatio)){
    const kept=pairs.filter(pair=>!pair.includes(id));
    if(kept.length)quality.allowedByRatio[ratio]=kept;
    else delete quality.allowedByRatio[ratio];
  }
}
