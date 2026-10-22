import {Canvas, FabricText, FabricImage, Group, Line, Rect, Pattern, Shadow} from "fabric";
import {
  RATIO_DIMENSIONS, TEXT_LAYER_IDS, getPositions, setPosition as setScenePosition,
  setContent as setSceneContent, cloneAsNewDesign, sceneSummary
} from "./scene-model.mjs";
import {getProfile} from "./ratio-layout.mjs";
import {HistoryManager} from "./history-manager.mjs";
import {candidateAxes,snapBounds,clampBounds} from "./snapping-engine.mjs";
import {LAYER_NAMES,orderedLayers,getLayer,setLayerVisibility,setLayerLock,reorderLayer} from "./layer-state.mjs";
import {defaultStyle,getLayerStyle,setStyleProperty} from "./style-state.mjs";
import {
  ensureExtras,createLayer,layerById,groupById,groupLayers,ungroupLayers,
  removeFreeLayer,moveFreeFrame,getFreeFrame,hasFreeFrameOverride,
  resetFreeFrame,applyFreeFrameToAll,moveGroupInRatio,
  setFreeVisibility,setFreeLock,reorderFreeLayer,extraEntries,FREE_LABELS
} from "./free-layer-state.mjs";
import {constructFreeObjects} from "./free-layer-renderer.mjs";
import {
  diagnoseLayout,resolveSafetyArea,availableSafetyProfiles,SAFETY_PROFILES
} from "./layout-diagnostics.mjs";
import {
  ensureQuality,getQualityProfile,setQualityProfile,setAllowedOverlap,
  effectiveAllowedOverlaps,approvedPairs
} from "./quality-state.mjs";

/** 仅用于技术验证。网页排版和高清 PNG 使用同一 Fabric.js 画布。 */
const $ = (id) => document.getElementById(id);
const RATIOS = RATIO_DIMENSIONS;
const OPENING = new Set(Array.from("（【《〈「『([{“‘"));
const CLOSING = new Set(Array.from("，。！？：；、）】》〉」』)]}”’"));
const state = {
  scene:null,
  designs:[],
  ratio:"3:4",
  text:{title:"复利思维",subtitle:"存款百万不是结束而是开始",account:"@尚书观世"},
  fontIds:{title:"",subtitle:""},
  settings:{darkness:78,focus_y:50,glow:true},
  positions:{
    title:{x:null,y:null}, subtitle:{x:null,y:null},
    account:{x:7.2,y:68}
  },
  background:null, avatar:null,
  objects:{}, fontCatalog:[], fontNames:new Map(), fontPromises:new Map(),
  buildVersion:0, ready:false, layout:null,
  snapEnabled:true,viewportScale:1,guides:{x:null,y:null},
  showSafetyOverlay:false,qualityReport:null,fontDiagnostics:null,fontChecking:false,
  inspectedLayer:"title",
  inspectedFree:null,
  selectedFree:new Set(),
  freeImageCache:new Map(),
  freeGroupOrigins:{},
  metrics:{sceneBuilds:0,fontRequests:0,materialRequests:0,legacyReferenceRequests:0,exportCount:0,designSaves:0}
};

const history = new HistoryManager(80);
let historyRestoring = false;
let textCommitTimer = null;
function updateHistoryUI() {
  const h=history.getStatus();
  $("undoEdit").disabled=!h.canUndo;
  $("redoEdit").disabled=!h.canRedo;
  $("historyState").textContent="历史记录 "+(h.cursor+1)+"/"+h.length;
}
function commitHistory() {
  if(historyRestoring || !state.scene)return;
  syncSceneData();
  history.commit(state.scene);
  updateHistoryUI();
}
function scheduleTextHistory() {
  clearTimeout(textCommitTimer);
  textCommitTimer=setTimeout(commitHistory,500);
}
async function restoreFromHistory(scene) {
  if(!scene)return;
  historyRestoring=true;
  try{ await applyScene(scene,{resetHistory:false}); }
  finally{historyRestoring=false;updateHistoryUI();}
}
async function undoEdit(){
  clearTimeout(textCommitTimer);
  commitHistory();
  await restoreFromHistory(history.undo());
}
async function redoEdit(){
  clearTimeout(textCommitTimer);
  await restoreFromHistory(history.redo());
}
const artboard = new Canvas("artboard",{
  width:1080,height:1440,backgroundColor:"#000",selection:true,
  preserveObjectStacking:true,renderOnAddRemove:false
});
const guideCanvas=$("guide-overlay");
const guideContext=guideCanvas.getContext("2d");
const measuringCanvas=document.createElement("canvas");
const measuringCtx=measuringCanvas.getContext("2d");

const unboundedClamp = (v,lo,hi) => Math.max(lo,Math.min(hi,v));
const clamp = (v,lo,hi) => Math.max(lo,Math.min(hi,v));
const simplifyText = (value) => value.replace(/\r\n?/g,"\n").trim();
const roundNumber = (x) => Math.round(x*10000)/10000;
function viewportSize(){return RATIOS[state.ratio];}
function setStatus(value,isError=false){
  $("status").textContent=value;
  $("message").classList.toggle("error",isError);
  $("message").textContent=isError?value:"";
}
function fontKey(id){return "CoverFont_"+id.replace(/[^a-zA-Z0-9]/g,"_");}

async function loadFont(id) {
  if(!id) throw new Error("请选择可用字体");
  if(state.fontPromises.has(id))return state.fontPromises.get(id);
  const promise=(async()=>{
    state.metrics.fontRequests += 1;
    const response=await fetch("/api/fabric-poc/font?id="+encodeURIComponent(id),{cache:"force-cache"});
    if(!response.ok)throw new Error("字体加载失败："+id+"（状态 "+response.status+"）");
    const bytes=await response.arrayBuffer();
    const family=fontKey(id);
    const fontFace = new FontFace(family,bytes,{style:"normal",weight:"400"});
    await fontFace.load();
    document.fonts.add(fontFace);
    await document.fonts.load('24px "'+family+'"',"复利思维");
    return family;
  })();
  state.fontPromises.set(id,promise);
  try{return await promise;}catch(e){state.fontPromises.delete(id);throw e;}
}
async function loadSceneAsset(kind, reference) {
  if(!reference || reference.source === "none") return null;
  const route = reference.source === "managed"
    ? "/api/designs/assets/" + encodeURIComponent(reference.id)
    : "/api/fabric-poc/asset/" + kind;
  state.metrics.materialRequests += 1;
  const response=await fetch(route,{cache:"no-store"});
  if(response.status===404) throw Error(kind+" 图片素材已不存在，请重新上传。");
  if(!response.ok) throw Error(kind+" 素材加载失败（状态 "+response.status+"）");
  return decodeImageBlob(await response.blob());
}
async function decodeImageBlob(blob){
  if(!blob.type.startsWith("image/")) throw new Error("请选择 PNG、JPEG 或 WebP 图片。");
  const url=URL.createObjectURL(blob);
  try {
    const picture=new Image();
    picture.decoding="async";
    picture.src=url;
    await picture.decode();
    return picture;
  }finally{
    URL.revokeObjectURL(url);
  }
}
function fillFontSelect(id, selected){
  const select=$(id),fragment=document.createDocumentFragment();
  const familyGroups=new Map();
  for(const f of state.fontCatalog.filter(f=>f.source==="local")){
    const family=f.family||"其他本机字体";
    if(!familyGroups.has(family))familyGroups.set(family,[]);
    familyGroups.get(family).push(f);
  }
  for(const [family,variants] of familyGroups){
    const group=document.createElement("optgroup");
    group.label="项目 · "+family;
    for(const f of variants){
      const option=new Option((f.variant||f.name)+" · "+f.filename,f.id);
      group.appendChild(option);
    }
    fragment.appendChild(group);
  }
  const systems=document.createElement("optgroup");
  systems.label="Windows 已安装字体";
  for(const f of state.fontCatalog.filter(f=>f.source==="system")){
    systems.appendChild(new Option(f.name,f.id));
  }
  fragment.appendChild(systems);
  select.replaceChildren(fragment);
  const ids=new Set(state.fontCatalog.map(f=>f.id));
  select.value=ids.has(selected)?selected:state.fontCatalog[0]?.id||"";
  return select.value;
}
function syncSceneData(){
  if(!state.scene)return;
  state.scene.content={...state.text};
  state.scene.fontRefs={...state.fontIds};
  state.scene.backgroundStyle={
    darkness:state.settings.darkness,
    focusY:state.settings.focus_y,
    glow:state.settings.glow
  };
  state.scene.activeRatio=state.ratio;
  for(const kind of TEXT_LAYER_IDS) {
    const pos=state.positions[kind];
    setScenePosition(state.scene,state.ratio,kind,pos.x,pos.y);
  }
}

function refreshRevision(){
  const scene=state.scene;
  $("designRevision").textContent=scene?.id
    ? "已保存设计 · 版本 "+scene.revision+" · "+scene.activeRatio
    : "当前设计草稿 · 尚未保存 · 场景模型 v2";
}
function renderDesignList(){
  const options=[new Option("经典封面 · 导入草稿","legacy")];
  for(const item of state.designs){
    options.push(new Option(item.name+" · v"+item.revision,item.id));
  }
  $("designSelect").replaceChildren(...options);
  const selected=state.scene?.id||"legacy";
  $("designSelect").value=state.designs.some(x=>x.id===selected)?selected:"legacy";
}
async function refreshDesignList(){
  const response=await fetch("/api/designs",{cache:"no-store"});
  if(!response.ok)throw Error("无法读取本机设计库。");
  state.designs=(await response.json()).designs||[];
  renderDesignList();
}
async function applyScene(scene,{resetHistory=true}={}){
  if(!scene || scene.schemaVersion!==2)throw Error("场景模型版本错误。");
  ++state.buildVersion;
  state.scene=structuredClone(scene);
  ensureExtras(state.scene);
  ensureQuality(state.scene);
  state.fontDiagnostics=null;
  state.qualityReport=null;
  state.selectedFree.clear();
  state.inspectedFree=null;
  $("designName").value=scene.name;
  state.text={...scene.content};
  for(const key of TEXT_LAYER_IDS)$(key).value=state.text[key]||"";
  state.ratio=RATIOS[scene.activeRatio]?scene.activeRatio:"3:4";
  $("ratio").value=state.ratio;
  state.positions=getPositions(scene,state.ratio);
  for(const kind of ["title","subtitle"]){
    state.fontIds[kind]=fillFontSelect(kind+"Font",scene.fontRefs[kind]);
  }
  const bg=scene.backgroundStyle;
  state.settings={
    darkness:bg.darkness,focus_y:bg.focusY,glow:bg.glow,
  };
  const [background,avatar]=await Promise.all([
    loadSceneAsset("background",scene.assets.background),
    loadSceneAsset("avatar",scene.assets.avatar)
  ]);
  state.background=background;
  state.avatar=avatar;
  syncSceneData();
  refreshRevision();
  renderDesignList();
  await safeRebuild();
  if(resetHistory){ history.reset(state.scene); updateHistoryUI(); }
}
async function openDesignById(id) {
  const route=id==="legacy"?"/api/designs/legacy":"/api/designs/"+encodeURIComponent(id);
  const result=await fetch(route,{cache:"no-store"});
  if(!result.ok)throw Error((await result.json()).error||"无法打开设计。");
  const payload=await result.json();
  await applyScene(id==="legacy"?payload:payload.design);
  $("message").textContent="已打开："+state.scene.name;
}
async function saveDesign(asCopy=false){
  if(!state.ready || !state.scene)throw Error("封面还未准备完成。");
  syncSceneData();
  const scene=asCopy?cloneAsNewDesign(state.scene):structuredClone(state.scene);
  scene.name=$("designName").value.trim()||"封面设计";
  if(!scene.id)scene.revision=0;
  const update=Boolean(scene.id);
  const response=await fetch(update?"/api/designs/"+encodeURIComponent(scene.id):"/api/designs",{
    method:update?"PUT":"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(scene),
  });
  if(!response.ok){
    const body=await response.json().catch(()=>({}));
    throw Error(body.error||("保存设计失败（"+response.status+"）"));
  }
  const body=await response.json();
  state.scene=body.design;
  history.reset(state.scene);updateHistoryUI();
  state.metrics.designSaves+=1;
  await refreshDesignList();
  refreshRevision();
  $("message").textContent="设计已保存 · "+state.scene.name+" · 版本 "+state.scene.revision;
  return state.scene;
}
async function uploadAsset(file,kind){
  const fd=new FormData();
  fd.set("kind",kind);fd.set("file",file);
  const response=await fetch("/api/designs/assets",{method:"POST",body:fd});
  if(!response.ok){
    const body=await response.json().catch(()=>({}));
    throw Error(body.error||"图片保存失败。");
  }
  const stored=await response.json();
  state.scene.assets[kind]={source:"managed",id:stored.asset.id};
}

function measure(text,family,size,charSpacing=0) {
  measuringCtx.font=size+'px "'+family+'"';
  const letters=Array.from(text);
  return measuringCtx.measureText(text).width+
    Math.max(0,letters.length-1)*size*charSpacing/1000;
}
function breakBalanced(text,family,size,maximumWidth,preferLargeTitle=false,charSpacing=0){
  const explicit=text.split("\n");
  if(explicit.length>2 || explicit.some(line=>line.trim().length===0)){
    throw new Error("手动换行最多两行，且每行都需包含文字。");
  }
  const widths=explicit.map(x=>measure(x,family,size,charSpacing));
  if(explicit.length===2) return Math.max(...widths)<=maximumWidth?explicit:null;
  const letters=Array.from(text);
  // 知识封面的大标题优先采用大字：长于 8 字时主动尝试视觉均衡的两行，
  // 即使宽屏能够勉强装下一行，也不牺牲书法大字的视觉权重。
  if(widths[0]<=maximumWidth && (!preferLargeTitle || letters.length<=8))return explicit;
  let best=null;
  for(let i=1;i<letters.length;i++){
    const left=letters.slice(0,i).join("").trim(),right=letters.slice(i).join("").trim();
    if(!left||!right)continue;
    if(OPENING.has(Array.from(left).at(-1))||CLOSING.has(Array.from(right)[0]))continue;
    const a=measure(left,family,size,charSpacing),b=measure(right,family,size,charSpacing);
    if(a>maximumWidth||b>maximumWidth)continue;
    const score=Math.abs(a-b)+.15*Math.max(a,b);
    if(!best||score<best.score)best={lines:[left,right],score};
  }
  return best?.lines||(widths[0]<=maximumWidth?explicit:null);
}
function fitText(text,family,{maxWidth,maxHeight,start,min,lineGap,role,
  fontSize=null,charSpacing=0,lineHeight=1.15}){
  const sizes=fontSize===null
    ? Array.from({length:Math.floor((Math.floor(start)-min)/2)+1},(_,i)=>Math.floor(start)-i*2)
    : [fontSize];
  for(const size of sizes){
    const lines=breakBalanced(text,family,size,maxWidth,role==="大标题",charSpacing);
    if(!lines)continue;
    const approxHeight=lines.length*size*(lineHeight-.02)+(lines.length-1)*size*lineGap;
    if(approxHeight>maxHeight)continue;
    return {lines,size,approxHeight};
  }
  throw new Error(role+(fontSize!==null?"固定字号无法完整放入，请减小字号或换画幅。":"无法完整排入两行，请缩短文字或更换比例。"));
}
function shadowFromStyle(spec){
  if(!spec?.enabled)return null;
  const rgb=spec.color.match(/[a-f0-9]{2}/gi).map(value=>parseInt(value,16));
  return new Shadow({
    color:"rgba("+rgb.join(",")+","+spec.opacity+")",
    blur:spec.blur,offsetX:spec.offsetX,offsetY:spec.offsetY
  });
}
function textStyle(family,size,fill,style){
  return {
    fontFamily:family,fontSize:size,fontWeight:"normal",fontStyle:"normal",
    fill:style?.fill??fill,originX:"left",originY:"top",
    lineHeight:style?.lineHeight??1.15,
    charSpacing:style?.charSpacing??0,
    opacity:style?.opacity??1,angle:style?.angle??0,
    stroke:style?.stroke??"#000000",strokeWidth:style?.strokeWidth??0,
    strokeUniform:true,shadow:shadowFromStyle(style?.shadow),
    paintFirst:"stroke",
    objectCaching:false,cornerColor:"#e4c9a3",borderColor:"#d7bb98",
    transparentCorners:false,cornerSize:15,
  };
}
function clampLayerPosition(obj,key,w,h){
  const stored=state.positions[key];
  const defaultLeft=obj.left,defaultTop=obj.top;
  obj.set({
    left:stored.x==null?defaultLeft:w*stored.x/100,
    top:stored.y==null?defaultTop:h*stored.y/100,
  });
  obj.setCoords();
  // 用旋转后的实际轴对齐包围盒约束，避免文本绕旋转中心超出画布。
  const rect=obj.getBoundingRect();
  const bounded=clampBounds(rect.left,rect.top,rect.width,rect.height,w,h);
  obj.set({
    left:obj.left+bounded.x-rect.left,
    top:obj.top+bounded.y-rect.top,
  });
  obj.setCoords();
}
function offscreenBackground(w,h) {
  const c=document.createElement("canvas");c.width=w;c.height=h;
  const ctx=c.getContext("2d",{alpha:false});
  ctx.fillStyle="#07080a";ctx.fillRect(0,0,w,h);
  if(state.background){
    const img=state.background;
    const scale=Math.max(w/img.naturalWidth,h/img.naturalHeight);
    const renderW=img.naturalWidth*scale,renderH=img.naturalHeight*scale;
    const x=(w-renderW)/2,y=(h-renderH)*state.settings.focus_y/100;
    ctx.drawImage(img,x,y,renderW,renderH);
    ctx.fillStyle="rgba(0,0,0,"+(state.settings.darkness/100)+")";
    ctx.fillRect(0,0,w,h);
  }
  if(state.settings.glow){
    // 使用不依赖 CSS filter 的 Canvas 2D 径向渐变，确保无头浏览器与普通浏览器表现一致。
    for(const [pct,spread,strength] of [[.12,.29,.29],[.45,.27,.19],[.87,.31,.26]]){
      const cx=w*pct;
      const gradient=ctx.createRadialGradient(cx,0,0,cx,0,w*spread);
      gradient.addColorStop(0,"rgba(239,240,237,"+strength+")");
      gradient.addColorStop(1,"rgba(239,240,237,0)");
      ctx.fillStyle=gradient;
      ctx.fillRect(0,0,w,h*.29);
    }
  }
  return c;
}
async function circleAvatarImage(w,h,y){
  if(!state.avatar)return null;
  const avatarStyle=getLayerStyle(state.scene,"avatar");
  const size=Math.round(Math.min(w*.245,h*.23));
  const c=document.createElement("canvas");c.width=size+4;c.height=size+4;
  const ctx=c.getContext("2d");
  const img=state.avatar, iw=img.naturalWidth,ih=img.naturalHeight;
  const crop=Math.min(iw,ih),sx=(iw-crop)/2,sy=(ih-crop)/2;
  ctx.save();
  ctx.beginPath();ctx.arc(size/2+2,size/2+2,size/2,0,Math.PI*2);ctx.clip();
  ctx.drawImage(img,sx,sy,crop,crop,2,2,size,size);
  ctx.restore();
  ctx.strokeStyle="rgba(225,224,216,.9)";
  ctx.lineWidth=2;
  ctx.beginPath();ctx.arc(size/2+2,size/2+2,size/2,0,Math.PI*2);ctx.stroke();
  const drawnSize=(size+4)*avatarStyle.scale;
  const x=w-Math.round(w*.075)-drawnSize;
  const profile=getProfile(state.ratio);
  const ypos=Math.min(h-drawnSize-2,Math.max(
    Math.round(h*profile.avatarMinTop),y+Math.round(h*profile.flowGap)
  ));
  return new Rect({
    left:Math.max(0,x),top:Math.max(0,ypos),width:size+4,height:size+4,
    scaleX:avatarStyle.scale,scaleY:avatarStyle.scale,
    angle:avatarStyle.angle,opacity:avatarStyle.opacity,
    originX:"left",originY:"top",
    fill:new Pattern({source:c,repeat:"no-repeat"}),
    selectable:false,evented:false,excludeFromExport:false,
    data:{layerId:"avatar"},objectCaching:false
  });
}
function overlapRect(a,b){
  if(!a||!b)return false;
  const r1=a.getBoundingRect(),r2=b.getBoundingRect();
  // 轻微笔画触碰不应被判定为明显碰撞。
  const ix=Math.max(0,Math.min(r1.left+r1.width,r2.left+r2.width)-Math.max(r1.left,r2.left));
  const iy=Math.max(0,Math.min(r1.top+r1.height,r2.top+r2.height)-Math.max(r1.top,r2.top));
  return ix>Math.min(r1.width,r2.width)*.065 && iy>Math.min(r1.height,r2.height)*.17;
}

function attachObject(o,key) {
  o.set({name:key,data:{layerId:key},lockSkewingX:true,lockSkewingY:true});
  o.setControlsVisibility({mtr:true,mt:false,mb:false,ml:false,mr:false});
  state.objects[key]=o;
  artboard.add(o);
}
function stageScale(){
  const stage=$("preview-stage");
  const holder=$("preview-holder");
  const [w,h]=viewportSize();
  const maxW=Math.max(210,stage.clientWidth-48),maxH=Math.max(320,Math.min(760,window.innerHeight*.73));
  const scale=Math.min(maxW/w,maxH/h,1);
  holder.style.width=Math.round(w*scale)+"px";
  holder.style.height=Math.round(h*scale)+"px";
  state.viewportScale=scale;
  guideCanvas.width=w;guideCanvas.height=h;
  guideCanvas.style.width=w+"px";guideCanvas.style.height=h+"px";
  guideCanvas.style.transform="scale("+scale+")";
  paintGuides();
  const wrapper=artboard.wrapperEl;
  if(wrapper){
    wrapper.style.transformOrigin="top left";
    wrapper.style.transform="scale("+scale+")";
  }
}
function paintSafetyOverlay(){
  if(!state.showSafetyOverlay || !state.scene || !state.layout)return;
  const [w,h]=viewportSize();
  const area=resolveSafetyArea(
    state.ratio,w,h,getQualityProfile(state.scene,state.ratio),
    getProfile(state.ratio).safeMargin
  );
  const scale=Math.max(state.viewportScale,.1);
  const ctx=guideContext;
  const inner=area.inner;
  ctx.save();
  ctx.strokeStyle="rgba(123,220,201,.92)";
  ctx.lineWidth=1.4/scale;
  ctx.setLineDash([9/scale,5/scale]);
  ctx.strokeRect(inner.left,inner.top,
    inner.right-inner.left,inner.bottom-inner.top);
  ctx.setLineDash([]);
  ctx.font=Math.min(34,11/scale)+"px sans-serif";
  ctx.fillStyle="rgba(156,237,213,.96)";
  ctx.fillText("安全内容范围 · "+area.label,inner.left+5/scale,
    Math.max(22/scale,inner.top+17/scale));
  for(const zone of area.blocked){
    ctx.fillStyle="rgba(236,151,112,.17)";
    ctx.fillRect(zone.rect.left,zone.rect.top,zone.rect.width,zone.rect.height);
    ctx.strokeStyle="rgba(245,162,119,.85)";
    ctx.setLineDash([6/scale,5/scale]);
    ctx.strokeRect(zone.rect.left,zone.rect.top,zone.rect.width,zone.rect.height);
    ctx.setLineDash([]);
    ctx.fillStyle="#f0c3a5";
    ctx.fillText(zone.label,zone.rect.left+4/scale,
      Math.max(24/scale,zone.rect.top+16/scale));
  }
  ctx.restore();
}
function paintGuides(){
  const [w,h]=viewportSize();
  guideContext.clearRect(0,0,guideCanvas.width,guideCanvas.height);
  paintSafetyOverlay();
  if(!state.snapEnabled)return;
  const {x,y}=state.guides;
  if(x===null&&y===null)return;
  const strokeWidth=1.6/Math.max(state.viewportScale,.1);
  guideContext.save();
  guideContext.lineWidth=strokeWidth;
  guideContext.strokeStyle="#efc27f";
  guideContext.setLineDash([11/Math.max(state.viewportScale,.1),7/Math.max(state.viewportScale,.1)]);
  if(x!==null){
    guideContext.beginPath();guideContext.moveTo(x,0);guideContext.lineTo(x,h);guideContext.stroke();
  }
  if(y!==null){
    guideContext.beginPath();guideContext.moveTo(0,y);guideContext.lineTo(w,y);guideContext.stroke();
  }
  guideContext.restore();
}
function clearGuides(){
  state.guides={x:null,y:null};
  paintGuides();
}

function snappedMove(target){
  const key=target?.data?.layerId;
  if(!TEXT_LAYER_IDS.includes(key) && !isFreeId(key))return;
  const record=isFreeId(key)?freeEntry(key):getLayer(state.scene,key);
  if(record.locked || record.visible===false)return;
  const [width,height]=viewportSize();
  // Fabric.js 拖动事件发生时 aCoords 可能仍是上一帧的缓存，
  // 必须先重算，才能根据当前指针位置正确吸附。
  target.setCoords();
  const rect=target.getBoundingRect();
  let delta={dx:0,dy:0,guides:{x:null,y:null}};
  if(state.snapEnabled){
    const peers=Object.values(state.objects)
      .filter(item=>item!==target && item.visible && item.data?.layerId!=="background")
      .map(item=>item.getBoundingRect());
    const axes=candidateAxes(width,height,getProfile(state.ratio).safeMargin,peers);
    delta=snapBounds(rect,axes,{scale:state.viewportScale,thresholdScreenPx:9});
  }
  const next=clampBounds(
    rect.left+delta.dx,rect.top+delta.dy,
    rect.width,rect.height,width,height
  );
  target.set({
    left:target.left+next.x-rect.left,
    top:target.top+next.y-rect.top,
  });
  target.setCoords();
  state.guides=delta.guides;
  paintGuides();
  if(!isFreeId(key))markManual(target);
}

/** 编辑面板图层顺序与画布绘制栈从同一场景数据解析。 */
function applyLayerObjects(){
  if(!state.scene)return;
  const byId=state.objects;
  for(const layer of state.scene.layers){
    const obj=byId[layer.id];
    if(!obj)continue;
    const visible=layer.visible!==false;
    const editable=visible && !layer.locked && TEXT_LAYER_IDS.includes(layer.id);
    obj.set({
      visible,selectable:editable,evented:editable,
      hasControls:editable,lockMovementX:!editable,lockMovementY:!editable,
    });
    if(!editable && artboard.getActiveObject()===obj)artboard.discardActiveObject();
  }
  const order=[...state.scene.layers].sort((a,b)=>a.zIndex-b.zIndex);
  order.forEach((layer,index)=>{
    const obj=byId[layer.id];
    if(obj)artboard.moveObjectTo(obj,index);
  });
  artboard.requestRenderAll();
}

function buttonFor(action,id,label,{disabled=false,pressed=null,title=""}={}){
  const button=document.createElement("button");
  button.type="button";button.textContent=label;
  button.dataset.layerAction=action;button.dataset.layerId=id;
  button.disabled=disabled;
  if(pressed!==null)button.setAttribute("aria-pressed",String(pressed));
  button.title=title||label;
  return button;
}
function renderLayerPanel(){
  const list=$("layerList");
  if(!state.scene){list.replaceChildren();return;}
  const ordered=orderedLayers(state.scene);
  list.replaceChildren(...ordered.map((layer,index)=>{
    const row=document.createElement("div");
    row.className="layer-control-row";
    row.dataset.layer=layer.id;
    row.dataset.hidden=String(layer.visible===false);
    const heading=document.createElement("div");
    heading.className="layer-name";
    heading.textContent=LAYER_NAMES[layer.id]||layer.id;
    const desc=document.createElement("span");
    desc.className="layer-desc";
    desc.textContent=layer.id==="background"?"固定底层":
      layer.id==="avatar"?"头像位置由画幅模板管理":
      layer.locked?"已锁定":"可以选中和拖动";
    heading.append(desc);
    const actions=document.createElement("div");
    actions.className="layer-actions";
    const isText=TEXT_LAYER_IDS.includes(layer.id);
    const active=state.objects[layer.id];
    if(isText) actions.append(buttonFor("select",layer.id,"选中",{
      disabled:!active||layer.locked||layer.visible===false,
    }));
    actions.append(buttonFor("visibility",layer.id,layer.visible===false?"显示":"隐藏",{
      pressed:layer.visible===false,
      title:layer.visible===false?"显示图层":"隐藏图层",
    }));
    actions.append(buttonFor("lock",layer.id,layer.locked?"解锁":"锁定",{
      disabled:!isText,pressed:layer.locked,title:"锁定或解锁图层",
    }));
    if(isText) actions.append(buttonFor("reset",layer.id,"自动",{
      disabled:layer.locked||!active,title:"恢复自动排版",
    }));
    if(layer.id!=="background"){
      actions.append(buttonFor("up",layer.id,"↑",{
        disabled:index===0,title:"将图层上移",
      }));
      actions.append(buttonFor("down",layer.id,"↓",{
        disabled:index===ordered.length-2,title:"将图层下移",
      }));
    }
    row.append(heading,actions);
    return row;
  }));
  renderFreeLayerPanel();
  $("layerStatus").textContent="基础图层 "+state.scene.layers.length+
    " 个 · 自由图层 "+ensureExtras(state.scene).layers.length+" 个";
}


async function loadFreeImage(assetId) {
  if(state.freeImageCache.has(assetId))return state.freeImageCache.get(assetId);
  state.metrics.materialRequests++;
  const response=await fetch("/api/designs/assets/"+encodeURIComponent(assetId),{cache:"force-cache"});
  if(!response.ok)throw Error("自由图层图片无法读取，请重新上传素材。");
  const loaded=await decodeImageBlob(await response.blob());
  state.freeImageCache.set(assetId,loaded);
  return loaded;
}
async function renderExtraObjects(w,h,serial){
  if(!state.scene)return;
  const compiled=await constructFreeObjects(state.scene,w,h,{
    loadFont,loadImage:loadFreeImage,
  });
  // 更改画幅或字体时旧异步图层仍可能加载完成，必须以最新渲染序号为准。
  if(serial!==state.buildVersion)return;
  state.freeGroupOrigins=compiled.groupOrigins;
  for(const item of compiled.items){
    state.objects[item.id]=item.object;
    artboard.add(item.object);
  }
}
function isFreeId(id){
  return typeof id==="string" && (id.startsWith("custom-")||id.startsWith("group-"));
}
function freeEntry(id){
  return id.startsWith("group-")?groupById(state.scene,id):layerById(state.scene,id);
}
function effectiveFreeLock(id){
  const layer=freeEntry(id);
  if(layer.locked)return true;
  if(layer.groupId)return groupById(state.scene,layer.groupId).locked;
  return false;
}
function refreshFreeSelection(){
  const eligible=ensureExtras(state.scene).layers.filter(layer=>
    !layer.groupId && !layer.locked && layer.visible);
  const active=new Set(eligible.map(layer=>layer.id));
  for(const id of state.selectedFree){
    if(!active.has(id))state.selectedFree.delete(id);
  }
  $("combineLayers").disabled=state.selectedFree.size<2;
  $("uncombineLayers").disabled=!state.inspectedFree || !state.inspectedFree.startsWith("group-");
  $("freeSelectedCount").textContent=state.selectedFree.size?
    "已选择 "+state.selectedFree.size+" 个自由图层":"勾选至少两个自由图层";
}
function freeLayerRow(entry,grouped=false){
  const isGroup=entry.type==="group",recordId=entry.id;
  const row=document.createElement("div");
  row.className="layer-control-row";
  row.dataset.layer=recordId;row.dataset.free="true";
  row.dataset.group=String(isGroup);
  row.dataset.member=String(grouped);
  row.dataset.hidden=String(entry.visible===false);
  const text=document.createElement("div");
  text.className="layer-name";
  text.textContent=entry.name;
  const desc=document.createElement("span");
  desc.className="layer-desc";
  desc.textContent=isGroup?"组合 · "+entry.members.length+" 个成员":
    (FREE_LABELS[entry.type]||"自由图层")+(grouped?" · 已加入组合":"");
  text.append(desc);
  if(!isGroup && !grouped){
    const checkbox=document.createElement("input");
    checkbox.type="checkbox";checkbox.className="group-check";
    checkbox.dataset.freeSelect=recordId;checkbox.checked=state.selectedFree.has(recordId);
    checkbox.disabled=entry.locked || entry.visible===false;
    checkbox.setAttribute("aria-label","选择 "+entry.name+" 用于组合");
    row.append(checkbox);
  }
  row.append(text);
  if(grouped)return row;
  const tools=document.createElement("div");
  tools.className="layer-actions";
  const add=(action,label,disabled=false)=>{
    tools.append(buttonFor(action,recordId,label,{disabled}));
  };
  add("free-select","选中",entry.locked||entry.visible===false||!state.objects[recordId]);
  add("free-visibility",entry.visible===false?"显示":"隐藏");
  add("free-lock",entry.locked?"解锁":"锁定");
  add("free-up","↑");
  add("free-down","↓");
  add(isGroup?"free-ungroup":"free-delete",isGroup?"解组":"删除");
  row.append(tools);
  return row;
}
function renderFreeLayerPanel(){
  const list=$("layerList");
  const extras=ensureExtras(state.scene);
  const byId=new Map(extras.layers.map(layer=>[layer.id,layer]));
  const items=[];
  for(const entry of extraEntries(state.scene)){
    items.push(freeLayerRow(entry));
    if(entry.type==="group"){
      for(const member of entry.members){
        const item=byId.get(member);
        if(item)items.push(freeLayerRow(item,true));
      }
    }
  }
  list.prepend(...items);
  refreshFreeSelection();
}
function selectFreeLayer(id){
  if(!isFreeId(id))throw Error("需要先选择自由图层");
  state.inspectedFree=id;
  state.inspectedLayer="title";
  const visual=state.objects[id];
  if(visual && visual.selectable){
    artboard.setActiveObject(visual);
    artboard.requestRenderAll();
  }
  renderFreeInspector();
  refreshFreeSelection();
}
function renderFreeInspector(){
  const panel=$("freeInspector");
  const id=state.inspectedFree;
  const extras=ensureExtras(state.scene);
  const entry=extraEntries(state.scene).find(item=>item.id===id);
  panel.hidden=!entry;
  if(!entry)return;
  const group=entry.type==="group";
  $("freeName").value=entry.name;
  $("freeTextOptions").hidden=group||entry.type!=="text";
  $("freeColorOptions").hidden=group||entry.type==="image";
  $("freeOpacity").disabled=group;
  $("freeOpacity").value=group?100:Math.round(entry.style.opacity*100);
  $("deleteFreeLayer").textContent=group?"解组":"删除图层";
  $("freeRatioCaption").textContent=state.ratio;
  $("freeGeometryFields").hidden=group;
  const ids=group?entry.members:[entry.id];
  const overrides=ids.filter(key=>hasFreeFrameOverride(state.scene,key,state.ratio));
  $("freeRatioStatus").textContent=overrides.length
    ? "本画幅独立布局（"+overrides.length+"/"+ids.length+" 个图层）"
    : "继承共享布局；本画幅修改后将独立保存。";
  $("freeResetRatio").disabled=!overrides.length;
  $("freeApplyAll").disabled=!ids.length;
  if(!group){
    const frame=getFreeFrame(state.scene,id,state.ratio);
    for(const [field,key] of [
      ["freeFrameX","x"],["freeFrameY","y"],
      ["freeFrameWidth","width"],["freeFrameHeight","height"],
      ["freeFrameAngle","angle"]
    ]){
      const actual=key==="height" && entry.type==="text" && state.objects[id]
        ? state.objects[id].getScaledHeight()/viewportSize()[1]*100
        : frame[key];
      $(field).value=Number(actual).toFixed(key==="angle"?1:2);
    }
  }
  if(entry.type==="text"){
    $("freeTextContent").value=entry.text;
    $("freeTextSize").value=entry.style.fontSize;
    const select=$("freeTextFont");
    select.replaceChildren(...state.fontCatalog.map(font=>new Option(font.name,font.id)));
    select.value=entry.fontId;
  }
  if(entry.type==="text"||entry.type==="rect"||entry.type==="ellipse"){
    $("freeFill").value=entry.style.fill;
  }
}
async function updateExtraProperty(prop,value){
  const id=state.inspectedFree;
  if(!id)return;
  const item=freeEntry(id);
  if(item.locked)throw Error("当前图层已锁定");
  if(prop==="name")item.name=String(value).slice(0,70).trim()||"自由图层";
  else if(prop==="text"&&item.type==="text"){
    const text=String(value).trim().slice(0,300);
    if(!text)throw Error("自由文字不能为空");
    item.text=text;
  }else if(prop==="fontId"&&item.type==="text"){
    if(!state.fontCatalog.some(font=>font.id===value))throw Error("字体不存在");
    item.fontId=value;
  }else if(prop==="fontSize"&&item.type==="text"){
    const number=Number(value);
    if(!Number.isFinite(number)||number<16||number>400)throw Error("字号须在 16～400 之间");
    item.style.fontSize=number;
  }else if(prop==="fill" && !["image","group"].includes(item.type)){
    if(!/^#[0-9a-f]{6}$/i.test(value))throw Error("颜色格式不正确");
    item.style.fill=value;
  }else if(prop==="opacity"&&!id.startsWith("group-")){
    const number=Number(value);
    if(!Number.isFinite(number)||number<0||number>1)throw Error("透明度须为 0～1");
    item.style.opacity=number;
  }else throw Error("当前图层不支持此属性");
  await safeRebuild();
  renderFreeInspector();
  scheduleTextHistory();
}
async function updateFreeGeometryProperty(path,value){
  const id=state.inspectedFree;
  if(!id || id.startsWith("group-"))throw Error("请选择独立的自由图层");
  const record=layerById(state.scene,id);
  if(record.locked || record.groupId)throw Error("当前自由图层已锁定或已分组");
  if(!["x","y","width","height","angle"].includes(path))throw Error("不支持的几何属性");
  const number=Number(value);
  if(!Number.isFinite(number))throw Error("几何参数必须为有限数字");
  const frame=getFreeFrame(state.scene,id,state.ratio);
  const updated={...frame,[path]:number};
  if(record.type==="text" && path==="height"){
    const visual=state.objects[id];
    if(!visual)throw Error("请等待字体图层加载完成");
    const pixelHeight=number/100*viewportSize()[1];
    const desiredScale=pixelHeight/Math.max(1,visual.height);
    if(desiredScale<.25 || desiredScale>4)throw Error("文字高度缩放需在 0.25～4 倍之间");
    updated.scaleY=desiredScale;
  }
  moveFreeFrame(state.scene,id,updated,state.ratio);
  // 快速连续操作先保存数据快照，再异步更新画布，确保撤销粒度正确。
  commitHistory();
  await safeRebuild();
  if(state.inspectedFree===id)selectFreeLayer(id);
}
async function resetCurrentFreeLayout(id=state.inspectedFree){
  if(!id)throw Error("请先选择自由图层");
  const ids=id.startsWith("group-")?groupById(state.scene,id).members:[id];
  let changed=false;
  for(const key of ids) changed=resetFreeFrame(state.scene,key,state.ratio)||changed;
  if(!changed)return false;
  commitHistory();
  await safeRebuild();
  if(state.inspectedFree===id)selectFreeLayer(id);
  return true;
}
async function applyCurrentFreeLayoutToAll(id=state.inspectedFree){
  if(!id)throw Error("请先选择自由图层");
  const ids=id.startsWith("group-")?groupById(state.scene,id).members:[id];
  let changed=false;
  for(const key of ids) changed=applyFreeFrameToAll(state.scene,key,state.ratio)||changed;
  if(!changed)return false;
  commitHistory();
  await safeRebuild();
  if(state.inspectedFree===id)selectFreeLayer(id);
  return true;
}

async function addNewFreeLayer(kind,file=null){
  if(!state.scene)throw Error("请先打开一份设计");
  let uploaded=null,loaded=null;
  if(kind==="image"){
    if(!file)throw Error("请选择需要添加的图片");
    loaded=await decodeImageBlob(file);
    const form=new FormData();
    form.set("kind","layer");form.set("file",file);
    const response=await fetch("/api/designs/assets",{method:"POST",body:form});
    if(!response.ok)throw Error((await response.json()).error||"自由图片上传失败");
    uploaded=(await response.json()).asset.id;
  }
  const newLayer=createLayer(state.scene,kind,{
    fontId:state.fontIds.title,assetId:uploaded,content:"输入文字",
  });
  if(uploaded)state.freeImageCache.set(uploaded,loaded);
  state.inspectedFree=newLayer.id;
  await safeRebuild();
  selectFreeLayer(newLayer.id);
  commitHistory();
  $("message").textContent="已添加 "+newLayer.name;
  return newLayer.id;
}
async function groupSelectedFree(){
  const ids=[...state.selectedFree];
  const group=groupLayers(state.scene,ids);
  state.selectedFree.clear();state.inspectedFree=group.id;
  await safeRebuild();
  selectFreeLayer(group.id);
  commitHistory();
  return group.id;
}
async function ungroupSelectedFree(id=state.inspectedFree){
  if(!id?.startsWith("group-"))throw Error("请先选中组合");
  ungroupLayers(state.scene,id);
  state.inspectedFree=null;
  await safeRebuild();
  commitHistory();
}
async function deleteFreeItem(id=state.inspectedFree){
  if(!id)throw Error("请先选择自由图层");
  removeFreeLayer(state.scene,id);
  state.inspectedFree=null;state.selectedFree.delete(id);
  await safeRebuild();
  commitHistory();
}
async function changeFreeLayer(id,action){
  if(!isFreeId(id))throw Error("请选择自由图层");
  if(action==="free-select"){selectFreeLayer(id);return;}
  if(action==="free-ungroup"){await ungroupSelectedFree(id);return;}
  if(action==="free-delete"){await deleteFreeItem(id);return;}
  const entry=freeEntry(id);
  let changed=false;
  if(action==="free-visibility")changed=setFreeVisibility(state.scene,id,!entry.visible);
  else if(action==="free-lock")changed=setFreeLock(state.scene,id,!entry.locked);
  else if(action==="free-up"||action==="free-down")
    changed=reorderFreeLayer(state.scene,id,action==="free-up"?1:-1);
  else throw Error("不支持的自由图层操作");
  if(!changed)return;
  await safeRebuild();
  commitHistory();
}
function commitFreeTransform(target){
  const id=target?.data?.layerId;
  if(!isFreeId(id))return false;
  const [w,h]=viewportSize();
  if(id.startsWith("group-")){
    const group=groupById(state.scene,id);
    const old=state.freeGroupOrigins[id];
    if(!old)return false;
    const deltaX=(target.left-old.x)/w*100;
    const deltaY=(target.top-old.y)/h*100;
    moveGroupInRatio(state.scene,id,state.ratio,deltaX,deltaY);
    return true;
  }
  const record=layerById(state.scene,id);
  const f=getFreeFrame(state.scene,id,state.ratio);
  const scaleW=target.getScaledWidth()/w*100;
  const scaleH=target.getScaledHeight()/h*100;
  const frame={
    x:target.left/w*100,y:target.top/h*100,
    width:Math.max(1,Math.min(scaleW,100)),
    height:Math.max(1,Math.min(scaleH,100)),
    angle:(((target.angle+180)%360)+360)%360-180,
  };
  if(record.type==="text"){
    // 宽度在当前画幅独立保存，纵向缩放不改动共用的字号设置。
    frame.width=Math.max(1,Math.min(target.width*target.scaleX/w*100,100));
    frame.height=Math.max(1,Math.min(target.height*target.scaleY/h*100,100));
    frame.scaleY=Math.max(.25,Math.min(4,target.scaleY));
  }
  moveFreeFrame(state.scene,id,frame,state.ratio);
  return true;
}

function inspectLayer(id){
  if(!["title","subtitle","account","avatar","background"].includes(id))return;
  state.inspectedLayer=id;
  $("inspectorLayer").value=id;
  renderInspector();
}

function renderInspector(){
  if(!state.scene)return;
  const id=state.inspectedLayer;
  const textLayer=TEXT_LAYER_IDS.includes(id);
  $("inspectorLayer").value=id;
  $("textInspector").hidden=!textLayer;
  $("avatarInspector").hidden=id!=="avatar";
  $("backgroundInspector").hidden=id!=="background";
  $("resetLayerStyle").disabled=textLayer && getLayer(state.scene,id).locked;
  if(textLayer){
    const style=getLayerStyle(state.scene,id);
    const locked=getLayer(state.scene,id).locked;
    $("styleSizeMode").value=style.fontSize===null?"auto":"fixed";
    const effective=id==="title"?state.layout?.titleSize:
      id==="subtitle"?state.layout?.subtitleSize:state.layout?.accountSize;
    $("styleFontSize").value=style.fontSize??effective??40;
    $("styleCharSpacing").value=style.charSpacing;
    $("styleLineHeight").value=style.lineHeight;
    $("styleFill").value=style.fill;
    $("styleOpacity").value=style.opacity*100;
    $("styleStroke").value=style.stroke;
    $("styleStrokeWidth").value=style.strokeWidth;
    $("styleAngle").value=style.angle;
    $("styleShadowEnabled").checked=style.shadow.enabled;
    $("styleShadowColor").value=style.shadow.color;
    $("styleShadowOpacity").value=style.shadow.opacity*100;
    $("styleShadowBlur").value=style.shadow.blur;
    $("styleShadowX").value=style.shadow.offsetX;
    $("styleShadowY").value=style.shadow.offsetY;
    for(const el of document.querySelectorAll("[data-style-control=text]")){
      const gated=el.id==="styleFontSize" && style.fontSize===null;
      const shadowGated=el.closest("#shadowSettings") && !style.shadow.enabled;
      el.disabled=locked||gated||Boolean(shadowGated);
    }
    $("shadowSettings").hidden=!style.shadow.enabled;
    $("propertyStatus").textContent=locked?"图层已锁定，可在图层面板解锁后编辑":"修改即在浏览器实时渲染";
  }else if(id==="avatar"){
    const style=getLayerStyle(state.scene,"avatar");
    $("avatarOpacity").value=style.opacity*100;
    $("avatarAngle").value=style.angle;
    $("avatarScale").value=style.scale;
    $("propertyStatus").textContent="头像沿用圆形裁切及画幅定位";
  }else{
    $("backgroundDarkness").value=state.settings.darkness;
    $("backgroundFocus").value=state.settings.focus_y;
    $("backgroundGlow").checked=state.settings.glow;
    $("propertyStatus").textContent="背景参数保存到当前设计";
  }
}

function updateStyleValue(id,path,value){
  if(!state.scene)throw Error("设计尚未加载");
  if(id==="background"){
    if(path==="darkness" && Number.isFinite(value) && value>=0 && value<=95){
      state.settings.darkness=value;
    }else if(path==="focus_y" && Number.isFinite(value) && value>=0 && value<=100){
      state.settings.focus_y=value;
    }else if(path==="glow" && typeof value==="boolean"){
      state.settings.glow=value;
    }else throw Error("背景属性超出范围");
    state.scene.backgroundStyle={
      darkness:state.settings.darkness,focusY:state.settings.focus_y,glow:state.settings.glow,
    };
  }else{
    if(TEXT_LAYER_IDS.includes(id) && getLayer(state.scene,id).locked){
      throw Error("当前文字图层已锁定，请先解锁");
    }
    if(!setStyleProperty(state.scene,id,path,value))return false;
  }
  // 修改样式只重建本机 Fabric 画布，不向 Python 请求图片。
  const rendered=safeRebuild();
  scheduleTextHistory();
  return rendered;
}

function resetSelectedStyle(){
  const id=state.inspectedLayer;
  if(id==="background"){
    state.settings={darkness:78,focus_y:50,glow:true};
    state.scene.backgroundStyle={darkness:78,focusY:50,glow:true};
  }else{
    if(TEXT_LAYER_IDS.includes(id) && getLayer(state.scene,id).locked){
      throw Error("当前文字图层已锁定，请先解锁");
    }
    getLayer(state.scene,id).style=defaultStyle(id);
  }
  safeRebuild();
  commitHistory();
  renderInspector();
}


function diagnosticItems(){
  if(!state.scene)return [];
  const extras=ensureExtras(state.scene);
  const free=new Map(extras.layers.map(item=>[item.id,item]));
  const output=[];
  for(const [id,object] of Object.entries(state.objects)){
    if(!object || id==="background")continue;
    const rect=object.getBoundingRect();
    let label=LAYER_NAMES[id]||id;
    let kind="graphic",fontSize=null,fill=null,opacity=object.opacity;
    if(["title","subtitle","account"].includes(id)){
      kind="text";
      fontSize=id==="title"?state.layout?.titleSize:
        id==="subtitle"?state.layout?.subtitleSize:state.layout?.accountSize;
      fill=getLayerStyle(state.scene,id).fill;
    }else if(id==="avatar"){
      kind="avatar";
    }else if(id.startsWith("group-")){
      const group=extras.groups.find(item=>item.id===id);
      if(!group)continue;
      label=group.name;
      const members=group.members.map(key=>free.get(key)).filter(Boolean);
      kind=members.some(part=>part.type==="text")?"mixed-group":
        members.some(part=>part.type==="image")?"image":"graphic";
    }else if(free.has(id)){
      const part=free.get(id);
      label=part.name;
      kind=part.type==="text"?"text":part.type==="image"?"image":"graphic";
      if(kind==="text"){
        fontSize=part.style.fontSize*(object.scaleY||1);
        fill=part.style.fill;
      }
    }
    output.push({
      id,label,kind,
      rect:{left:rect.left,top:rect.top,width:rect.width,height:rect.height},
      visible:object.visible,opacity,fontSize,fill
    });
  }
  return output;
}
function qualityFontChecks(){
  if(!state.scene)return [];
  const checks=[];
  const add=(id,fontId,value)=>{
    if(!fontId||!value?.trim())return;
    checks.push({fontId,text:value,label:id});
  };
  for(const id of ["title","subtitle","account"]){
    const layer=getLayer(state.scene,id);
    if(layer.visible===false)continue;
    add(id,state.fontIds[id==="title"?"title":"subtitle"],state.text[id]);
  }
  const extras=ensureExtras(state.scene);
  const groups=new Map(extras.groups.map(group=>[group.id,group]));
  for(const item of extras.layers){
    if(item.type!=="text" || item.visible===false)continue;
    if(item.groupId && groups.get(item.groupId)?.visible===false)continue;
    add(item.id,item.fontId,item.text);
  }
  return checks.slice(0,40);
}
function fontCheckSignature(){return JSON.stringify(qualityFontChecks());}

async function checkFontCoverage(){
  if(!state.ready)throw Error("请等待画布渲染完成。");
  const checks=qualityFontChecks();
  const signature=JSON.stringify(checks);
  if(state.fontDiagnostics?.signature===signature)return state.fontDiagnostics;
  if(state.fontChecking)throw Error("已有字体检查正在执行，请稍后重试。");
  state.fontChecking=true;
  $("runFontCheck").disabled=true;
  $("fontCoverageState").textContent="正在检查本机字体字符覆盖范围…";
  try{
    const response=await fetch("/api/fabric-poc/font-coverage",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({checks}),cache:"no-store"
    });
    if(!response.ok){
      const result=await response.json().catch(()=>({}));
      throw Error(result.error||"字体字形检查失败");
    }
    const data=await response.json();
    const problems=[];
    for(const result of data.results){
      const label=state.scene.extras?.layers?.find(x=>x.id===result.label)?.name ||
        LAYER_NAMES[result.label]||result.label;
      if(result.error){
        problems.push({
          id:"FONT_UNVERIFIED:"+result.label,code:"FONT_UNVERIFIED",
          severity:"warning",message:label+"的字体字形表无法验证："+result.error,
          layerIds:[result.label]
        });
      }else if(result.missingCount>0){
        problems.push({
          id:"FONT_MISSING:"+result.label,code:"FONT_MISSING",
          severity:"error",layerIds:[result.label],
          missingCount:result.missingCount,
          message:label+"缺少字形："+result.missing.slice(0,10).join("、")+
            (result.missingCount>10?" 等":"")
        });
      }
    }
    const scan={signature,issues:problems,checked:data.checkedCount};
    if(fontCheckSignature()===signature){
      state.fontDiagnostics=scan;
      refreshQualityReport();
    }
    return scan;
  }finally{
    state.fontChecking=false;
    $("runFontCheck").disabled=false;
    if(state.layout)refreshQualityReport();
  }
}

function sampleSceneBackground(x,y){
  const source=state.objects.background?.fill?.source;
  if(!source || typeof source.getContext!=="function")return null;
  try{
    const ctx=source.getContext("2d",{willReadFrequently:true});
    const colors=ctx.getImageData(
      Math.max(0,Math.min(source.width-1,Math.floor(x))),
      Math.max(0,Math.min(source.height-1,Math.floor(y))),1,1
    ).data;
    return Array.from(colors.slice(0,3));
  }catch{return null;}
}
function refreshQualityProfilePicker(){
  if(!state.scene)return;
  const select=$("safetyProfile");
  const options=availableSafetyProfiles(state.ratio).map(id=>
    new Option(SAFETY_PROFILES[id].name,id));
  select.replaceChildren(...options);
  select.value=getQualityProfile(state.scene,state.ratio);
}
function refreshQualityReport(){
  if(!state.scene||!state.layout)return;
  refreshQualityProfilePicker();
  const [width,height]=viewportSize();
  const profileId=getQualityProfile(state.scene,state.ratio);
  const base=diagnoseLayout({
    width,height,ratio:state.ratio,profileId,
    genericMargin:getProfile(state.ratio).safeMargin,
    items:diagnosticItems(),
    allowedOverlaps:effectiveAllowedOverlaps(state.scene,state.ratio),
    sampleBackground:sampleSceneBackground
  });
  const fontCurrent=state.fontDiagnostics?.signature===fontCheckSignature();
  const combined=[...base.issues,...(fontCurrent?state.fontDiagnostics.issues:[])];
  const counts={
    error:combined.filter(x=>x.severity==="error").length,
    warning:combined.filter(x=>x.severity==="warning").length,
    info:combined.filter(x=>x.severity==="info").length
  };
  state.qualityReport={
    ...base,counts,issues:combined,
    status:counts.error?"error":counts.warning?"warning":"pass",
    glyphCoverageChecked:Boolean(fontCurrent),
  };
  const summary=$("qualitySummary");
  summary.className="quality-summary"+
    (counts.error?" has-error":counts.warning?" has-warning":"");
  summary.textContent=counts.error+" 项错误 · "+counts.warning+
    " 项提示 · "+(fontCurrent?"字形已检查":"字形待预检");
  $("fontCoverageState").textContent=fontCurrent?
    "字体检查完成，共检查 "+state.fontDiagnostics.checked+" 个文字图层。" :
    "字形完整性在点击完整预检或下载 PNG 时检查。";
  const panel=$("qualityIssues");
  if(!combined.length){
    const empty=document.createElement("div");
    empty.className="quality-empty";
    empty.textContent=fontCurrent?"当前布局与字体检查通过。":"几何布局检查通过，可运行完整字形预检。";
    panel.replaceChildren(empty);
  }else{
    panel.replaceChildren(...combined.slice(0,36).map(issue=>{
      const row=document.createElement("div");
      row.className="quality-item";row.dataset.level=issue.severity;
      row.setAttribute("role","listitem");
      const meta=document.createElement("div");
      meta.className="quality-item-name";
      const labels={error:"错误",warning:"需要检查",info:"信息"};
      meta.textContent=(labels[issue.severity]||"提示")+" · "+issue.code;
      const body=document.createElement("div");
      body.className="quality-item-message";body.textContent=issue.message;
      row.append(meta,body);
      const controls=document.createElement("div");
      controls.className="quality-item-actions";
      const layerId=issue.layerIds.find(id=>state.objects[id]);
      if(layerId){
        const focus=document.createElement("button");
        focus.type="button";focus.textContent="定位图层";
        focus.dataset.qualityFocus=layerId;
        controls.append(focus);
      }
      if(issue.canAllow && issue.layerIds.length===2){
        const allow=document.createElement("button");
        allow.type="button";allow.textContent="确认此处允许重叠";
        allow.dataset.qualityAllow=issue.layerIds.join("|");
        controls.append(allow);
      }
      if(controls.childElementCount)row.append(controls);
      return row;
    }));
  }
  renderAcknowledgments();
  paintGuides();
}
function renderAcknowledgments(){
  const container=$("acknowledgmentList");
  const entries=state.scene?approvedPairs(state.scene,state.ratio):[];
  $("acknowledgmentCount").textContent=String(entries.length);
  if(!entries.length){
    const label=document.createElement("div");
    label.className="font-preview-note";
    label.textContent="当前画幅尚无人工确认的重叠关系。";
    container.replaceChildren(label);
    return;
  }
  container.replaceChildren(...entries.map(({pair,scope})=>{
    const row=document.createElement("div");
    row.className="quality-ack-row";
    const label=document.createElement("span");
    const resolve=id=>{
      const extra=state.scene.extras?.layers?.find(x=>x.id===id);
      const group=state.scene.extras?.groups?.find(x=>x.id===id);
      return extra?.name||group?.name||LAYER_NAMES[id]||id;
    };
    label.textContent=resolve(pair[0])+" ↔ "+resolve(pair[1])+
      (scope==="*"?" · 全部画幅":" · "+scope);
    const revoke=document.createElement("button");
    revoke.type="button";revoke.textContent="撤销确认";
    revoke.dataset.qualityRevoke=pair.join("|");
    revoke.dataset.qualityScope=scope;
    row.append(label,revoke);
    return row;
  }));
}
function setCurrentQualityProfile(id){
  if(!state.scene)throw Error("设计尚未加载");
  if(setQualityProfile(state.scene,state.ratio,id))commitHistory();
  refreshQualityReport();
}
function acceptOverlap(a,b){
  if(setAllowedOverlap(state.scene,a,b,true,state.ratio)){
    commitHistory();
    refreshQualityReport();
  }
}
function revokeOverlap(a,b,scope=state.ratio){
  if(setAllowedOverlap(state.scene,a,b,false,scope)){
    commitHistory();
    refreshQualityReport();
  }
}
function getQualitySnapshot(){
  if(!state.qualityReport)throw Error("请先完成画布布局。");
  return JSON.parse(JSON.stringify(state.qualityReport));
}
function downloadQualityReport(){
  const name=(state.scene?.name||"封面").replace(/[\\/:*?"<>|]/g,"_").slice(0,48);
  const payload={
    schemaVersion:1,
    designId:state.scene?.id||null,
    ratio:state.ratio,
    generatedAt:new Date().toISOString(),
    fontCoverageChecked:state.qualityReport?.glyphCoverageChecked??false,
    ...getQualitySnapshot()
  };
  const blob=new Blob([JSON.stringify(payload,null,2)],{type:"application/json;charset=utf-8"});
  const url=URL.createObjectURL(blob);
  const link=document.createElement("a");
  link.href=url;link.download=name+"_"+state.ratio.replace(":","x")+"_quality.json";
  document.body.append(link);link.click();link.remove();
  URL.revokeObjectURL(url);
}

function refreshWarnings(){
  if(!state.layout)return;
  const title=state.objects.title,subtitle=state.objects.subtitle,
    account=state.objects.account,avatar=state.objects.avatar;
  const isVisible=(obj)=>Boolean(obj&&obj.visible);
  const warnings=[];
  if(isVisible(title)&&isVisible(subtitle)&&overlapRect(title,subtitle))
    warnings.push("大标题与小标题可能重叠");
  if(isVisible(account)&&isVisible(subtitle)&&overlapRect(account,subtitle))
    warnings.push("账号与小标题可能重叠");
  if(isVisible(account)&&isVisible(title)&&overlapRect(account,title))
    warnings.push("账号与大标题可能重叠");
  if(isVisible(avatar)){
    for(const [obj,label] of [[account,"账号"],[title,"大标题"],[subtitle,"小标题"]]){
      if(isVisible(obj)&&overlapRect(obj,avatar))warnings.push(label+"与头像可能重叠");
    }
  }
  state.layout.warnings=warnings;
  setStatus(warnings.length?"布局提示："+warnings.join("；"):"实时编辑就绪");
  refreshQualityReport();
}

function applyLayerChange(id,action){
  if(!state.scene)throw Error("设计尚未加载");
  const layer=getLayer(state.scene,id);
  let changed=false;
  if(action==="visibility"){
    changed=setLayerVisibility(state.scene,id,layer.visible===false);
  }else if(action==="lock"){
    changed=setLayerLock(state.scene,id,!layer.locked);
  }else if(action==="up"||action==="down"){
    changed=reorderLayer(state.scene,id,action==="up"?1:-1);
  }else throw Error("不支持的图层操作："+action);
  if(!changed)return false;
  clearGuides();
  applyLayerObjects();
  renderLayerPanel();
  renderInspector();
  refreshWarnings();
  commitHistory();
  return true;
}

function markManual(obj){
  const key=obj?.data?.layerId;
  if(!["title","subtitle","account"].includes(key))return;
  const [w,h]=viewportSize();
  state.positions[key]={
    x:roundNumber(clamp(obj.left/w*100,0,100)),
    y:roundNumber(clamp(obj.top/h*100,0,100))
  };
  if(state.scene)setScenePosition(
    state.scene,state.ratio,key,state.positions[key].x,state.positions[key].y
  );
  $("layoutNote").textContent=key+" 位置已更新 · 无后端渲染请求";
}
artboard.on("object:moving",({target})=>snappedMove(target));
artboard.on("object:modified",async({target})=>{
  clearGuides();
  const key=target?.data?.layerId;
  try{
    if(isFreeId(key)){
      if(commitFreeTransform(target)){
        await safeRebuild();
        commitHistory();
      }
      return;
    }
    markManual(target);
    let updated=false;
    if(TEXT_LAYER_IDS.includes(key)){
      const style=getLayerStyle(state.scene,key);
      const normalizeAngle=value=>(((value+180)%360)+360)%360-180;
      const angle=Number(normalizeAngle(target.angle).toFixed(2));
      if(Math.abs(style.angle-angle)>.01){
        setStyleProperty(state.scene,key,"angle",angle);updated=true;
      }
      if(Math.abs(target.scaleX-1)>.025 || Math.abs(target.scaleY-1)>.025){
        const defaultPx=key==="title"?state.layout.titleSize:
          key==="subtitle"?state.layout.subtitleSize:state.layout.accountSize;
        const scale=(target.scaleX+target.scaleY)/2;
        const size=Math.max(16,Math.min(400,Math.round((style.fontSize??defaultPx)*scale)));
        setStyleProperty(state.scene,key,"fontSize",size);updated=true;
      }
    }
    if(updated)await safeRebuild();
    refreshWarnings();
    commitHistory();
  }catch(error){setStatus(error.message,true);}
});
artboard.on("selection:created",event=>{
  const id=event.selected?.[0]?.data?.layerId;
  if(TEXT_LAYER_IDS.includes(id))inspectLayer(id);
  else if(isFreeId(id))selectFreeLayer(id);
});
artboard.on("selection:updated",event=>{
  const id=event.selected?.[0]?.data?.layerId;
  if(TEXT_LAYER_IDS.includes(id))inspectLayer(id);
  else if(isFreeId(id))selectFreeLayer(id);
});
artboard.on("mouse:up",clearGuides);

async function rebuild() {
  const serial=++state.buildVersion;
  if(!state.fontIds.title||!state.fontIds.subtitle)return;
  setStatus("正在载入字形…");
  const [titleFamily,subFamily]=await Promise.all([
    loadFont(state.fontIds.title),loadFont(state.fontIds.subtitle)
  ]);
  if(serial!==state.buildVersion)return;
  const [w,h]=viewportSize();
  const portrait=h>=w;
  const profile=getProfile(state.ratio);
  const titleStyle=getLayerStyle(state.scene,"title");
  const subtitleStyle=getLayerStyle(state.scene,"subtitle");
  const accountStyle=getLayerStyle(state.scene,"account");
  const title=fitText(state.text.title,titleFamily,{
    maxWidth:w*profile.titleMaxWidth,maxHeight:h*profile.titleHeight,
    start:Math.min(w*(portrait?.175:.135),h*.215),
    min:Math.max(40,Math.round(Math.min(w,h)*.048)),
    lineGap:.15,role:"大标题",
    fontSize:titleStyle.fontSize,charSpacing:titleStyle.charSpacing,
    lineHeight:titleStyle.lineHeight,
  });
  const titleText=new FabricText(title.lines.join("\n"),{
    ...textStyle(titleFamily,title.size,"#fffcf4",titleStyle),textAlign:"center",
  });
  const titleTop=Math.round(h*profile.titleTop);
  titleText.set({
    left:Math.round((w-titleText.width)/2),top:titleTop,
  });
  clampLayerPosition(titleText,"title",w,h);

  // 自动字幕与实际大标题保持流式关系，兼容双行文字和手动移动标题。
  const activeTitleBottom=titleText.top+titleText.height;
  const subtitleTop=Math.max(
    activeTitleBottom+h*profile.flowGap,h*profile.subtitleMinTop
  );
  const subtitleRemaining=Math.max(
    Math.round(h*.13),Math.min(h*.30,h*profile.subtitleMaxBottom-subtitleTop)
  );
  const sub=fitText(state.text.subtitle,subFamily,{
    maxWidth:w*.87,maxHeight:subtitleRemaining,
    start:Math.min(w*.054,h*.08),min:Math.max(22,Math.round(Math.min(w,h)*.025)),
    lineGap:.14,role:"小标题",
    fontSize:subtitleStyle.fontSize,charSpacing:subtitleStyle.charSpacing,
    lineHeight:subtitleStyle.lineHeight,
  });
  const subText=new FabricText(sub.lines.join("\n"),{
    ...textStyle(subFamily,sub.size,"#f8f7f2",{
      ...subtitleStyle,angle:0,opacity:1
    }),textAlign:"center",selectable:false,evented:false,
  });
  const lineWidth=w*.61,contentWidth=Math.max(lineWidth,subText.width);
  subText.set({left:(contentWidth-subText.width)/2,top:0});
  const lineY=subText.height+h*.016;
  const line=new Line([
    (contentWidth-lineWidth)/2,lineY,
    (contentWidth+lineWidth)/2,lineY
  ],{stroke:"#aaaaaa",strokeWidth:Math.max(1,w/600),selectable:false,evented:false});
  const subtitleGroup=new Group([subText,line],{
    left:Math.round((w-contentWidth)/2),
    top:Math.round(subtitleTop),
    originX:"left",originY:"top",cornerColor:"#e4c9a3",objectCaching:false,
    angle:subtitleStyle.angle,opacity:subtitleStyle.opacity,
  });
  clampLayerPosition(subtitleGroup,"subtitle",w,h);

  // 自动账号出现在字幕下方左侧，宽度限制为画布一半左右，预留头像位置。
  let accountSize=accountStyle.fontSize??Math.max(18,Math.round(Math.min(w*.036,h*.046)));
  let accountText=new FabricText(state.text.account,{
    ...textStyle(subFamily,accountSize,"#939496",accountStyle),
  });
  while(accountStyle.fontSize===null && accountText.width>w*.51 && accountSize>18){
    accountSize=Math.max(18,accountSize-2);
    accountText=new FabricText(state.text.account,{
      ...textStyle(subFamily,accountSize,"#939496",accountStyle),
    });
  }
  if(accountStyle.fontSize!==null && accountText.width>w*.95){
    throw new Error("账号固定字号过大，请缩小字号或减少文字。");
  }
  const subBottom=subtitleGroup.top+subtitleGroup.height;
  const accountTop=Math.max(
    h*profile.accountMinTop,subBottom+h*profile.flowGap
  );
  accountText.set({
    left:w*.075,
    top:accountTop,
  });
  clampLayerPosition(accountText,"account",w,h);

  // Fabric.js 7 在部分 Chromium 构建中直接使用 HTMLCanvasElement 作为图片时
  // 会保留 width/height，但无法正确绘制到最终画布；先转为 HTMLImageElement。
  const backgroundPattern=new Pattern({source:offscreenBackground(w,h),repeat:"no-repeat"});
  const avatar=await circleAvatarImage(w,h,subtitleGroup.top+subtitleGroup.height);
  if(serial!==state.buildVersion)return;
  artboard.discardActiveObject();
  artboard.clear();
  artboard.setDimensions({width:w,height:h});
  artboard.backgroundColor="#060709";
  state.objects={};
  const backdrop=new Rect({
    left:0,top:0,width:w,height:h,originX:"left",originY:"top",
    fill:backgroundPattern,evented:false,selectable:false,
    objectCaching:false,data:{layerId:"background"}
  });
  artboard.add(backdrop);
  state.objects.background=backdrop;
  if(avatar){artboard.add(avatar);state.objects.avatar=avatar;}
  attachObject(titleText,"title");
  attachObject(subtitleGroup,"subtitle");
  if(state.text.account.trim())attachObject(accountText,"account");
  await renderExtraObjects(w,h,serial);
  if(serial!==state.buildVersion)return;
  applyLayerObjects();
  renderLayerPanel();
  const warnings=[];
  state.layout={
    ratio:state.ratio,titleLines:title.lines,subtitleLines:sub.lines,
    titleSize:title.size,subtitleSize:sub.size,accountSize,
    width:w,height:h,backgroundLoaded:Boolean(state.background),avatarLoaded:Boolean(state.avatar),
    warnings,profile,positions:structuredClone(state.positions)
  };
  $("resolution").textContent=w+" × "+h;
  $("layoutNote").textContent="大标题 "+title.lines.length+" 行 · "+title.size+"px · 即时绘制";
  stageScale();
  artboard.requestRenderAll();
  $("export").disabled=false;
  state.ready=true;
  state.metrics.sceneBuilds+=1;
  refreshWarnings();
  renderInspector();
  renderFreeInspector();
}
async function safeRebuild(){
  try{await rebuild();}catch(e){
    $("export").disabled=true;state.ready=false;
    setStatus(e?.message||String(e),true);
    console.error("Fabric PoC rebuild",e);
  }
}
async function switchRatio(ratio){
  if(!RATIOS[ratio])throw Error("无效画幅");
  if(state.scene){
    syncSceneData();
    state.scene.activeRatio=ratio;
  }
  state.ratio=ratio;
  state.positions=state.scene?getPositions(state.scene,ratio):state.positions;
  $("ratio").value=ratio;
  await safeRebuild();
  commitHistory();
}
async function changeText(part,value){
  state.text[part]=simplifyText(value);
  if(state.scene)setSceneContent(state.scene,{[part]:state.text[part]});
  await safeRebuild();
  scheduleTextHistory();
}
function resetPosition(name){
  state.positions[name]={x:null,y:null};
  if(state.scene)setScenePosition(state.scene,state.ratio,name,null,null);
  return safeRebuild().then(commitHistory);
}
function selectLayer(name){
  inspectLayer(name);
  const target=state.objects[name];
  if(!target)return;
  artboard.setActiveObject(target);
  artboard.requestRenderAll();
}
function exportDataUrl(){
  if(!state.ready)throw Error("画布尚未渲染完成。");
  artboard.discardActiveObject();
  artboard.requestRenderAll();
  state.metrics.exportCount++;
  return artboard.toDataURL({format:"png",multiplier:1,enableRetinaScaling:false});
}
async function downloadPng(){
  // 仅在导出时检查字体 cmap；文字编辑仍由 Fabric.js 立即完成，无 Python 绘图调用。
  await checkFontCoverage();
  if(state.qualityReport?.counts.error){
    $("qualitySummary").scrollIntoView({block:"nearest"});
    throw Error("质量预检发现 "+state.qualityReport.counts.error+
      " 项错误，请在左侧诊断列表中处理后再导出。");
  }
  const result=exportDataUrl();
  const link=document.createElement("a");
  const name=(state.text.title||"封面").replace(/[\\/:*?"<>|]/g,"_").slice(0,40);
  link.href=result;
  link.download=name+"_"+state.ratio.replace(":","x")+"_fabric.png";
  document.body.appendChild(link);link.click();link.remove();
  $("message").textContent="已经使用 Fabric.js 导出原生分辨率 PNG";
}
async function referenceLegacy(){
  $("message").textContent="正在生成旧版 Python 对照图片…";
  state.metrics.legacyReferenceRequests += 1;
  const body=new FormData();
  body.set("title",state.text.title);
  body.set("subtitle",state.text.subtitle);
  body.set("account",state.text.account);
  body.set("ratio",state.ratio);
  for(const key of ["title","subtitle"]){
    body.set(key+"_font_id",state.fontIds[key]);
    body.set(key+"_font_mode",state.fontIds[key].startsWith("local:")?"local":"system");
    for(const axis of ["x","y"]){
      const value=state.positions[key][axis];
      body.set(key+"_"+axis,value===null?"":String(value));
    }
  }
  body.set("account_x",String(state.positions.account.x));
  body.set("account_y",String(state.positions.account.y));
  body.set("darkness",String(state.settings.darkness));
  body.set("focus_y",String(state.settings.focus_y));
  body.set("glow",state.settings.glow?"true":"false");
  const response=await fetch("/api/render",{method:"POST",body});
  if(!response.ok)throw Error((await response.json()).error||"旧版生成失败");
  const previous=$("legacyImage").src;
  const url=URL.createObjectURL(await response.blob());
  $("legacyImage").src=url;
  $("legacyPanel").hidden=false;
  if(previous.startsWith("blob:"))URL.revokeObjectURL(previous);
  $("message").textContent="对照由旧版 Pillow 独立渲染，用于观察排版差异。";
}
function setupInteractions(){
  $("undoEdit").addEventListener("click",()=>undoEdit().catch(e=>setStatus(e.message,true)));
  $("redoEdit").addEventListener("click",()=>redoEdit().catch(e=>setStatus(e.message,true)));
  document.addEventListener("keydown",event=>{
    const mod=event.ctrlKey||event.metaKey;
    if(!mod||event.altKey)return;
    const target=event.target;
    if(target?.matches?.("input,textarea,[contenteditable=true]"))return;
    if(event.key.toLowerCase()==="z"){
      event.preventDefault();
      (event.shiftKey?redoEdit():undoEdit()).catch(e=>setStatus(e.message,true));
    }else if(event.key.toLowerCase()==="y"){
      event.preventDefault();
      redoEdit().catch(e=>setStatus(e.message,true));
    }
  });
  $("loadDesign").addEventListener("click",()=>{
    openDesignById($("designSelect").value).catch(e=>setStatus(e.message,true));
  });
  $("saveDesign").addEventListener("click",()=>{
    saveDesign(false).catch(e=>setStatus(e.message,true));
  });
  $("saveCopy").addEventListener("click",()=>{
    saveDesign(true).catch(e=>setStatus(e.message,true));
  });
  $("designName").addEventListener("change",()=>{
    if(state.scene)state.scene.name=$("designName").value.trim();
    commitHistory();
  });
  for(const k of ["title","subtitle","account"]){
    $(k).addEventListener("input",()=>changeText(k,$(k).value));
  }
  $("ratio").addEventListener("change",e=>switchRatio(e.target.value));
  for(const key of ["title","subtitle"]){
    $(key+"Font").addEventListener("change",async event=>{
      state.fontIds[key]=event.target.value;
      if(state.scene)state.scene.fontRefs[key]=state.fontIds[key];
      await safeRebuild();
      commitHistory();
    });
  }
  for(const [key,kind] of [["bgUpload","background"],["avatarUpload","avatar"]]){
    $(key).addEventListener("change",async event=>{
      try{
        const file=event.target.files?.[0];if(!file)return;
        const decoded=await decodeImageBlob(file);
        // 文件只上传一次入库，之后编辑、拖动及导出在浏览器本地完成。
        await uploadAsset(file,kind);
        state[kind]=decoded;
        await safeRebuild();
        commitHistory();
      }catch(e){setStatus(e.message,true);}
    });
  }
  $("snapEnabled").addEventListener("change",event=>{
    state.snapEnabled=event.target.checked;
    clearGuides();
  });
  $("showSafetyOverlay").addEventListener("change",event=>{
    state.showSafetyOverlay=event.target.checked;
    paintGuides();
  });
  $("safetyProfile").addEventListener("change",event=>{
    try{setCurrentQualityProfile(event.target.value);}
    catch(error){setStatus(error.message,true);refreshQualityProfilePicker();}
  });
  $("runFontCheck").addEventListener("click",()=>{
    checkFontCoverage().catch(error=>setStatus(error.message,true));
  });
  $("downloadQualityReport").addEventListener("click",()=>{
    checkFontCoverage().then(downloadQualityReport)
      .catch(error=>setStatus(error.message,true));
  });
  $("qualityIssues").addEventListener("click",event=>{
    const focus=event.target.closest("button[data-quality-focus]");
    const allow=event.target.closest("button[data-quality-allow]");
    try{
      if(focus){
        const id=focus.dataset.qualityFocus;
        if(isFreeId(id))selectFreeLayer(id);
        else inspectLayer(id);
      }
      if(allow){
        const [a,b]=allow.dataset.qualityAllow.split("|");
        acceptOverlap(a,b);
      }
    }catch(error){setStatus(error.message,true);}
  });
  $("acknowledgmentList").addEventListener("click",event=>{
    const button=event.target.closest("button[data-quality-revoke]");
    if(!button)return;
    try{
      const [a,b]=button.dataset.qualityRevoke.split("|");
      revokeOverlap(a,b,button.dataset.qualityScope);
    }catch(error){setStatus(error.message,true);}
  });
  $("layerList").addEventListener("change",event=>{
    const check=event.target.closest("input[data-free-select]");
    if(!check)return;
    if(check.checked)state.selectedFree.add(check.dataset.freeSelect);
    else state.selectedFree.delete(check.dataset.freeSelect);
    refreshFreeSelection();
  });
  $("layerList").addEventListener("click",event=>{
    if(event.target.closest("input[data-free-select]"))return;
    const button=event.target.closest("button[data-layer-action]");
    if(!button){
      const row=event.target.closest("[data-layer]");
      if(row){
        if(isFreeId(row.dataset.layer))selectFreeLayer(row.dataset.layer);
        else inspectLayer(row.dataset.layer);
      }
      return;
    }
    const id=button.dataset.layerId,action=button.dataset.layerAction;
    try{
      if(isFreeId(id)){
        changeFreeLayer(id,action).catch(error=>setStatus(error.message,true));
      }else{
        inspectLayer(id);
        if(action==="select")selectLayer(id);
        else if(action==="reset")resetPosition(id);
        else applyLayerChange(id,action);
      }
    }catch(error){setStatus(error.message,true);}
  });
  for(const [id,kind] of [["addFreeText","text"],["addFreeRect","rect"],["addFreeEllipse","ellipse"]]){
    $(id).addEventListener("click",()=>addNewFreeLayer(kind).catch(error=>setStatus(error.message,true)));
  }
  $("addFreeImage").addEventListener("change",event=>{
    const file=event.target.files?.[0];
    if(file)addNewFreeLayer("image",file).catch(error=>setStatus(error.message,true));
    event.target.value="";
  });
  $("combineLayers").addEventListener("click",()=>groupSelectedFree().catch(error=>setStatus(error.message,true)));
  $("uncombineLayers").addEventListener("click",()=>ungroupSelectedFree().catch(error=>setStatus(error.message,true)));
  $("deleteFreeLayer").addEventListener("click",()=>deleteFreeItem().catch(error=>setStatus(error.message,true)));
  $("closeFreeInspector").addEventListener("click",()=>{
    state.inspectedFree=null;renderFreeInspector();refreshFreeSelection();
  });
  const bindFree=(id,key,convert=x=>x)=>{
    const input=$(id);
    input.addEventListener(input.type==="color"||input.type==="range"?"input":"change",()=>{
      updateExtraProperty(key,convert(input.value)).catch(error=>setStatus(error.message,true));
    });
  };
  bindFree("freeName","name");
  bindFree("freeTextContent","text");
  bindFree("freeTextFont","fontId");
  bindFree("freeTextSize","fontSize",Number);
  bindFree("freeFill","fill");
  bindFree("freeOpacity","opacity",value=>Number(value)/100);
  for(const [control,path] of [
    ["freeFrameX","x"],["freeFrameY","y"],
    ["freeFrameWidth","width"],["freeFrameHeight","height"],
    ["freeFrameAngle","angle"]
  ]){
    $(control).addEventListener("change",event=>{
      updateFreeGeometryProperty(path,event.target.value)
        .catch(error=>{setStatus(error.message,true);renderFreeInspector();});
    });
  }
  $("freeResetRatio").addEventListener("click",()=>
    resetCurrentFreeLayout().catch(error=>setStatus(error.message,true))
  );
  $("freeApplyAll").addEventListener("click",()=>
    applyCurrentFreeLayoutToAll().catch(error=>setStatus(error.message,true))
  );
  $("inspectorLayer").addEventListener("change",event=>inspectLayer(event.target.value));
  $("resetLayerStyle").addEventListener("click",()=>{
    try{resetSelectedStyle();}catch(error){setStatus(error.message,true);}
  });
  const bindStyle=(inputId,path,convert=Number)=>{
    const node=$(inputId);
    const eventName=node.type==="color"||node.type==="range"?"input":"change";
    node.addEventListener(eventName,()=>{
      try{updateStyleValue(state.inspectedLayer,path,convert(node.value));}
      catch(error){setStatus(error.message,true);renderInspector();}
    });
  };
  const identity=value=>value;
  bindStyle("styleCharSpacing","charSpacing");
  bindStyle("styleLineHeight","lineHeight");
  bindStyle("styleFill","fill",identity);
  bindStyle("styleOpacity","opacity",v=>Number(v)/100);
  bindStyle("styleStroke","stroke",identity);
  bindStyle("styleStrokeWidth","strokeWidth");
  bindStyle("styleAngle","angle");
  bindStyle("styleShadowColor","shadow.color",identity);
  bindStyle("styleShadowOpacity","shadow.opacity",v=>Number(v)/100);
  bindStyle("styleShadowBlur","shadow.blur");
  bindStyle("styleShadowX","shadow.offsetX");
  bindStyle("styleShadowY","shadow.offsetY");
  $("styleShadowEnabled").addEventListener("change",event=>{
    try{updateStyleValue(state.inspectedLayer,"shadow.enabled",event.target.checked);}
    catch(error){setStatus(error.message,true);}
  });
  $("styleSizeMode").addEventListener("change",event=>{
    try{
      const id=state.inspectedLayer;
      const effective=id==="title"?state.layout?.titleSize:
        id==="subtitle"?state.layout?.subtitleSize:state.layout?.accountSize;
      const value=event.target.value==="auto"?null:Math.max(16,Math.min(400,effective??40));
      updateStyleValue(id,"fontSize",value);
      renderInspector();
    }catch(error){setStatus(error.message,true);}
  });
  bindStyle("styleFontSize","fontSize");
  const bindImage=(inputId,path,convert=Number)=>{
    const element=$(inputId);
    element.addEventListener(element.type==="range"?"input":"change",()=>{
      try{updateStyleValue("avatar",path,convert(element.value));}
      catch(error){setStatus(error.message,true);renderInspector();}
    });
  };
  bindImage("avatarOpacity","opacity",value=>Number(value)/100);
  bindImage("avatarAngle","angle");
  bindImage("avatarScale","scale");
  const bindBackdrop=(inputId,path,convert=Number)=>{
    const element=$(inputId);
    element.addEventListener(element.type==="range"?"input":"change",()=>{
      try{updateStyleValue("background",path,convert(element.value));}
      catch(error){setStatus(error.message,true);renderInspector();}
    });
  };
  bindBackdrop("backgroundDarkness","darkness");
  bindBackdrop("backgroundFocus","focus_y");
  $("backgroundGlow").addEventListener("change",event=>{
    updateStyleValue("background","glow",event.target.checked);
  });
  $("export").addEventListener("click",()=>{
    downloadPng().catch(e=>setStatus(e.message,true));
  });
  $("compare").addEventListener("click",()=>referenceLegacy().catch(e=>setStatus(e.message,true)));
  window.addEventListener("resize",stageScale);
}
async function initialize(){
  setupInteractions();
  try{
    const [legacyResponse,catalogResp,listResponse]=await Promise.all([
      fetch("/api/designs/legacy",{cache:"no-store"}),
      fetch("/api/fonts",{cache:"no-store"}),
      fetch("/api/designs",{cache:"no-store"}),
    ]);
    if(!legacyResponse.ok||!catalogResp.ok||!listResponse.ok)
      throw Error("无法读取当前模板、字体目录或设计库。");
    const [scene,catalog,index]=await Promise.all([
      legacyResponse.json(),catalogResp.json(),listResponse.json()
    ]);
    state.fontCatalog=catalog.fonts||[];
    state.fontNames=new Map(state.fontCatalog.map(f=>[f.id,f.name]));
    state.designs=index.designs||[];
    $("fontStatus").textContent="字体库 "+state.fontCatalog.length+
      " 个文件。选择和输入文字均使用浏览器即时绘制。";
    await applyScene(scene);
  }catch(e){
    setStatus(e.message||String(e),true);
    console.error(e);
  }
}
window.__fabricPoc={
  undo:undoEdit, redo:redoEdit, getHistory:()=>history.getStatus(),
  changeLayer:applyLayerChange,
  addFreeLayer:addNewFreeLayer,
  groupFreeLayers:async(ids)=>{
    state.selectedFree=new Set(ids);
    return groupSelectedFree();
  },
  ungroupFreeLayers:ungroupSelectedFree,
  deleteFreeLayer:deleteFreeItem,
  changeFreeLayer,
  getFreeLayerList:()=>structuredClone(ensureExtras(state.scene)),
  getFreeLayout:(id,ratio=state.ratio)=>({
    frame:getFreeFrame(state.scene,id,ratio),
    inherited:!hasFreeFrameOverride(state.scene,id,ratio),
    ratio
  }),
  setFreeLayout:async(id,frame,ratio=state.ratio)=>{
    moveFreeFrame(state.scene,id,frame,ratio);
    commitHistory();
    if(state.ratio===ratio)await safeRebuild();
    return getFreeFrame(state.scene,id,ratio);
  },
  resetFreeLayout:resetCurrentFreeLayout,
  applyFreeLayoutToAll:applyCurrentFreeLayoutToAll,
  setFreeProperty:updateExtraProperty,
  selectInspector:inspectLayer,
  setStyle:async(id,path,value)=>{
    await updateStyleValue(id,path,value);
    commitHistory();
    return id==="background"?{...state.settings}:getLayerStyle(state.scene,id);
  },
  getStyle:id=>id==="background"?{...state.settings}:getLayerStyle(state.scene,id),
  setSnapEnabled(value){state.snapEnabled=Boolean(value);$("snapEnabled").checked=state.snapEnabled;clearGuides();},
  getGuides:()=>({...state.guides}),
  getQualityReport:getQualitySnapshot,
  checkFonts:checkFontCoverage,
  setSafetyProfile:setCurrentQualityProfile,
  setSafetyOverlay:enabled=>{
    state.showSafetyOverlay=Boolean(enabled);
    $("showSafetyOverlay").checked=state.showSafetyOverlay;
    paintGuides();
  },
  allowOverlap:acceptOverlap,
  revokeOverlap,
  getAcknowledgments:()=>approvedPairs(state.scene,state.ratio),
  getLayerOrder:()=>orderedLayers(state.scene).map(item=>item.id),
  getState:()=>({
    ready:state.ready,ratio:state.ratio,positions:structuredClone(state.positions),
    text:structuredClone(state.text),fontIds:{...state.fontIds},
    layout:state.layout,metrics:{...state.metrics},objects:Object.keys(state.objects),
    scene:state.scene?structuredClone(state.scene):null,
    snapEnabled:state.snapEnabled,layerOrder:state.scene?orderedLayers(state.scene).map(x=>x.id):[],
    qualityProfile:state.scene?getQualityProfile(state.scene,state.ratio):"general",
    safetyOverlay:state.showSafetyOverlay,
    quality:state.qualityReport?{
      status:state.qualityReport.status,counts:{...state.qualityReport.counts},
      glyphCoverageChecked:state.qualityReport.glyphCoverageChecked
    }:null
  }),
  setRatio:switchRatio,
  setContent:async content=>{
    for(const k of ["title","subtitle","account"]){
      if(k in content){
        state.text[k]=simplifyText(content[k]);$(k).value=state.text[k];
        if(state.scene)setSceneContent(state.scene,{[k]:state.text[k]});
      }
    }
    await safeRebuild();
  },
  setFont:async (kind,id)=>{
    if(!["title","subtitle"].includes(kind))throw Error("未知字体用途");
    state.fontIds[kind]=id;
    if(state.scene)state.scene.fontRefs[kind]=id;
    $(kind+"Font").value=id;
    await safeRebuild();
  },
  setPosition:(key,x,y)=>{
    if(!state.objects[key])throw Error("图层不存在");
    const [w,h]=viewportSize();
    state.positions[key]={x,y};
    if(state.scene)setScenePosition(state.scene,state.ratio,key,x,y);
    const obj=state.objects[key];
    obj.set({
      left:clamp(w*x/100,0,Math.max(0,w-obj.getScaledWidth())),
      top:clamp(h*y/100,0,Math.max(0,h-obj.getScaledHeight())),
    });
    obj.setCoords();artboard.requestRenderAll();
    refreshWarnings();
    commitHistory();
  },
  exportDataUrl,
  loadDesign:openDesignById,
  saveDesign,
  resetPosition,
  getScene:()=>structuredClone(state.scene),
  getObjectRect:key=>{
    const o=state.objects[key] || artboard.getObjects().find(item=>item?.data?.layerId===key);
    const b=o?.getBoundingRect();
    return b?{x:b.left,y:b.top,width:b.width,height:b.height}:null;
  },
  compare:referenceLegacy
};
initialize();
