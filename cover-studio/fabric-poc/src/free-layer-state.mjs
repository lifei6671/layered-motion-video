/** Cover Studio 自由图层、组合与图层列表的纯场景状态操作。 */
import {RATIO_DIMENSIONS} from "./scene-model.mjs";
import {forgetQualityLayer} from "./quality-state.mjs";

const TYPES = new Set(["text", "image", "rect", "ellipse"]);
export const FREE_MAX_LAYERS = 40;
export const FREE_MAX_GROUPS = 12;
export const FREE_LABELS = {
  text:"自由文字",image:"图片",rect:"矩形",ellipse:"椭圆",
};
export function ensureExtras(scene) {
  if (!scene) throw Error("场景尚未加载");
  scene.extras ||= {layers:[],groups:[]};
  scene.extras.layers ||= [];
  scene.extras.groups ||= [];
  return scene.extras;
}
export function makeId(prefix) {
  return prefix+"-"+crypto.randomUUID().replaceAll("-","").slice(0,12);
}
function nextZ(extras){
  const next=Math.max(49,...extras.layers.map(x=>x.zIndex))+1;
  if(next>999)throw Error("图层层级已达到上限，请先清理不再使用的图层");
  return next;
}
export function createLayer(scene,kind,{fontId=null,assetId=null,content="输入文字"}={}) {
  if(!TYPES.has(kind))throw Error("不支持的自由图层类型");
  const extras=ensureExtras(scene);
  if(extras.layers.length>=FREE_MAX_LAYERS)throw Error("每个设计最多添加 40 个自由图层");
  const ident=makeId("custom");
  const common={
    id:ident,name:FREE_LABELS[kind]+" "+(extras.layers.filter(x=>x.type===kind).length+1),
    type:kind,zIndex:nextZ(extras),visible:true,locked:false,groupId:null,
    ratioFrames:{},
    frame:{
      x:kind==="text"?26:35,y:kind==="text"?35:40,
      width:kind==="text"?48:30,height:kind==="text"?11:22,angle:0,
    }
  };
  if(kind==="text") {
    if(!fontId)throw Error("请先选择一个可用字体");
    common.fontId=fontId;
    common.text=content;
    common.style={fontSize:58,fill:"#ffffff",opacity:1};
  }else if(kind==="image") {
    if(!assetId)throw Error("请先选择图片文件");
    common.assetId=assetId;
    common.style={opacity:1};
  }else {
    common.style={fill:"#c8ac86",stroke:"#ffffff",strokeWidth:0,opacity:1};
  }
  extras.layers.push(common);
  return common;
}
export function layerById(scene,id) {
  const layer=ensureExtras(scene).layers.find(x=>x.id===id);
  if(!layer)throw Error("自由图层不存在："+id);
  return layer;
}
export function groupById(scene,id) {
  const group=ensureExtras(scene).groups.find(x=>x.id===id);
  if(!group)throw Error("组合不存在："+id);
  return group;
}
export function groupLayers(scene,ids) {
  const extras=ensureExtras(scene);
  const unique=[...new Set(ids)];
  if(unique.length<2 || unique.length>20)throw Error("每个组合需要 2～20 个图层");
  if(extras.groups.length>=FREE_MAX_GROUPS)throw Error("一个设计最多允许 12 个组合");
  const members=unique.map(id=>layerById(scene,id));
  if(members.some(x=>x.groupId))throw Error("已分组图层需要先解组");
  const id=makeId("group");
  const group={
    id,name:"组合 "+(extras.groups.length+1),
    members:members.map(x=>x.id),visible:true,locked:false,
  };
  for(const member of members)member.groupId=id;
  extras.groups.push(group);
  return group;
}
export function ungroupLayers(scene,gid) {
  const extras=ensureExtras(scene);
  const group=groupById(scene,gid);
  for(const id of group.members)layerById(scene,id).groupId=null;
  extras.groups=extras.groups.filter(x=>x.id!==gid);
  forgetQualityLayer(scene,gid);
  return group.members;
}
export function removeFreeLayer(scene,id) {
  const extras=ensureExtras(scene);
  if(id.startsWith("group-")){
    ungroupLayers(scene,id);
    return {groupRemoved:true};
  }
  const layer=layerById(scene,id);
  extras.layers=extras.layers.filter(x=>x.id!==id);
  forgetQualityLayer(scene,id);
  if(layer.groupId){
    const group=groupById(scene,layer.groupId);
    group.members=group.members.filter(member=>member!==id);
    if(group.members.length<2)ungroupLayers(scene,group.id);
  }
  return {groupRemoved:false};
}
function normalizedFrame(frame,kind) {
  const required=["x","y","width","height","angle"];
  if(!frame || typeof frame!=="object" || !required.every(key=>Number.isFinite(frame[key])))
    throw Error("自由图层位置与尺寸必须是有限数字");
  const valid=new Set(kind==="text"?[...required,"scaleY"]:required);
  if(Object.keys(frame).some(key=>!valid.has(key)))
    throw Error("自由图层包含未知的几何参数");
  const {width,height,angle}=frame;
  if(width<1||width>100||height<1||height>100)
    throw Error("自由图层大小需在 1～100% 之间");
  if(angle < -180 || angle > 180)throw Error("旋转角度须在 -180～180 度之间");
  const x=Math.max(0,Math.min(frame.x,100-width));
  const y=Math.max(0,Math.min(frame.y,100-height));
  const base={x,y,width,height,angle};
  if(Object.prototype.hasOwnProperty.call(frame,"scaleY")){
    if(!Number.isFinite(frame.scaleY)||frame.scaleY<.25||frame.scaleY>4)
      throw Error("文字高度缩放需在 0.25～4 倍之间");
    base.scaleY=frame.scaleY;
  }
  return Object.fromEntries(
    Object.entries(base).map(([key,value])=>
      [key,Math.round(value*10000)/10000]
    )
  );
}
/** 未配置画幅时继承初始 frame；不存在隐式跨画幅覆盖。 */
export function getFreeFrame(scene,id,ratio) {
  if(!RATIO_DIMENSIONS[ratio])throw Error("画幅比例无效");
  const part=layerById(scene,id);
  return {...(part.ratioFrames?.[ratio]??part.frame)};
}
export function hasFreeFrameOverride(scene,id,ratio) {
  if(!RATIO_DIMENSIONS[ratio])throw Error("画幅比例无效");
  return Object.prototype.hasOwnProperty.call(layerById(scene,id).ratioFrames??{},ratio);
}
/** 默认写入当前画幅独立覆盖；省略 ratio 仅用于向后兼容/初始化。 */
export function moveFreeFrame(scene,id,frame,ratio=null) {
  const layer=layerById(scene,id);
  const next=normalizedFrame(frame,layer.type);
  if(ratio===null){
    layer.frame=next;
  }else{
    if(!RATIO_DIMENSIONS[ratio])throw Error("画幅比例无效");
    layer.ratioFrames ||= {};
    layer.ratioFrames[ratio]=next;
  }
  return next;
}
/** 清除某画幅的独立坐标，使其重新继承全局布局。 */
export function resetFreeFrame(scene,id,ratio) {
  if(!RATIO_DIMENSIONS[ratio])throw Error("画幅比例无效");
  const layer=layerById(scene,id);
  if(!Object.prototype.hasOwnProperty.call(layer.ratioFrames??{},ratio))return false;
  delete layer.ratioFrames[ratio];
  return true;
}
/** 将指定画幅的有效布局提升为共享基线，并清除其他画幅的独立配置。 */
export function applyFreeFrameToAll(scene,id,ratio) {
  const layer=layerById(scene,id);
  const next=getFreeFrame(scene,id,ratio);
  const changed=JSON.stringify(next)!==JSON.stringify(layer.frame) ||
    Object.keys(layer.ratioFrames??{}).length>0;
  if(!changed)return false;
  layer.frame=normalizedFrame(next,layer.type);
  layer.ratioFrames={};
  return true;
}
/** 组合拖动应用到当前画幅所有成员，不修改基础构图或其他画幅。 */
export function moveGroupInRatio(scene,groupId,ratio,dx,dy) {
  if(!Number.isFinite(dx)||!Number.isFinite(dy))throw Error("组合位移须为数字");
  const group=groupById(scene,groupId);
  const frames=group.members.map(id=>({id,frame:getFreeFrame(scene,id,ratio)}));
  // 用组整体的边界裁剪位移，成员之间的距离不会在边缘被单独钳位破坏。
  const left=Math.min(...frames.map(item=>item.frame.x));
  const right=Math.max(...frames.map(item=>item.frame.x+item.frame.width));
  const top=Math.min(...frames.map(item=>item.frame.y));
  const bottom=Math.max(...frames.map(item=>item.frame.y+item.frame.height));
  const boundedX=Math.max(-left,Math.min(dx,100-right));
  const boundedY=Math.max(-top,Math.min(dy,100-bottom));
  const updated=frames.map(({id,frame})=>({
    id,frame:normalizedFrame({
      ...frame,x:frame.x+boundedX,y:frame.y+boundedY
    },layerById(scene,id).type)
  }));
  for(const item of updated)moveFreeFrame(scene,item.id,item.frame,ratio);
  return updated;
}

export function setFreeVisibility(scene,id,value){
  const item=id.startsWith("group-")?groupById(scene,id):layerById(scene,id);
  if(typeof value!=="boolean")throw Error("显隐状态必须是布尔值");
  if(item.visible===value)return false;
  item.visible=value;return true;
}
export function setFreeLock(scene,id,value){
  const item=id.startsWith("group-")?groupById(scene,id):layerById(scene,id);
  if(typeof value!=="boolean")throw Error("锁定状态必须是布尔值");
  if(item.locked===value)return false;
  item.locked=value;return true;
}
export function extraEntries(scene){
  const extras=ensureExtras(scene);
  const byId=new Map(extras.layers.map(item=>[item.id,item]));
  const included=new Set;
  const items=[];
  for(const group of extras.groups){
    const members=group.members.map(id=>byId.get(id)).filter(Boolean);
    members.forEach(member=>included.add(member.id));
    items.push({
      ...group,type:"group",
      zIndex:Math.max(...members.map(member=>member.zIndex),50),
      display:"组合",memberCount:members.length,
    });
  }
  for(const layer of extras.layers){
    if(!included.has(layer.id))items.push(layer);
  }
  return items.sort((a,b)=>b.zIndex-a.zIndex);
}
/** 组合层级不单独占用文件级 zIndex。组与相邻项交换后重新分配全部自由图层 zIndex。 */
export function reorderFreeLayer(scene,id,direction){
  const extras=ensureExtras(scene);
  const entries=extraEntries(scene);
  const from=entries.findIndex(entry=>entry.id===id);
  const to=from-direction;
  if(from<0||to<0||to>=entries.length)return false;
  [entries[from],entries[to]]=[entries[to],entries[from]];
  let z=50;
  for(const entry of entries.toReversed()){
    const members=entry.type==="group"?
      entry.members.map(key=>layerById(scene,key)).sort((a,b)=>a.zIndex-b.zIndex):
      [layerById(scene,entry.id)];
    for(const layer of members) layer.zIndex=z++;
  }
  return true;
}
