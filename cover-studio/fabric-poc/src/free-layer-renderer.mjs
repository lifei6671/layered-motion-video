/** 将扩展层的声明式场景模型渲染成 Fabric 对象。
 *  组内成员仍使用画布绝对坐标保存；组合实体负责交互，移动完成后更新成员坐标。
 */
import {Rect, Ellipse, Group, Textbox, Pattern} from "fabric";
import {getFreeFrame} from "./free-layer-state.mjs";

const pct = (value, whole) => whole * value / 100;

function framePixel(layer,width,height,ratio,scene){
  const f=getFreeFrame(scene,layer.id,ratio);
  return {
    left:pct(f.x,width),top:pct(f.y,height),
    width:pct(f.width,width),height:pct(f.height,height),
    angle:f.angle,scaleY:f.scaleY??1,
  };
}
async function imagePattern(assetId, size, loadImage){
  const original=await loadImage(assetId);
  const ctxCanvas=document.createElement("canvas");
  ctxCanvas.width=Math.max(1,Math.round(size.width));
  ctxCanvas.height=Math.max(1,Math.round(size.height));
  const ctx=ctxCanvas.getContext("2d");
  ctx.drawImage(original,0,0,ctxCanvas.width,ctxCanvas.height);
  return new Pattern({source:ctxCanvas,repeat:"no-repeat"});
}
export async function createFreeObject(layer,width,height,{loadFont,loadImage,ratio,scene}){
  const pos=framePixel(layer,width,height,ratio,scene);
  const common={
    left:pos.left,top:pos.top,angle:pos.angle,originX:"left",originY:"top",
    opacity:layer.style.opacity,objectCaching:false,
    selectable:!layer.locked,evented:!layer.locked,
    data:{layerId:layer.id,freeType:layer.type},
    cornerColor:"#e2c5a0",borderColor:"#edbb83",cornerSize:14,
  };
  let obj;
  if(layer.type==="text"){
    const family=await loadFont(layer.fontId);
    obj=new Textbox(layer.text,{
      ...common,width:pos.width,fontFamily:family,
      fontSize:layer.style.fontSize,fill:layer.style.fill,
      lineHeight:1.1,splitByGrapheme:false,
      scaleY:pos.scaleY,
    });
  }else if(layer.type==="image"){
    obj=new Rect({
      ...common,width:pos.width,height:pos.height,
      fill:await imagePattern(layer.assetId,pos,loadImage),
    });
  }else {
    const options={
      ...common,width:pos.width,height:pos.height,
      fill:layer.style.fill,stroke:layer.style.stroke,
      strokeWidth:layer.style.strokeWidth,strokeUniform:true,
    };
    obj=layer.type==="ellipse"?new Ellipse({
      ...options,rx:pos.width/2,ry:pos.height/2,
    }):new Rect(options);
  }
  obj.set({visible:layer.visible});
  obj.setControlsVisibility({mtr:true});
  obj.setCoords();
  return obj;
}

export async function constructFreeObjects(scene,width,height,{loadFont,loadImage}){
  const extra=scene?.extras||{layers:[],groups:[]};
  const ratio=scene.activeRatio;
  const objects=new Map;
  for(const layer of extra.layers){
    objects.set(layer.id,await createFreeObject(layer,width,height,{
      loadFont,loadImage,ratio,scene
    }));
  }
  const actual=[],origins={};
  const byId=new Map(extra.layers.map(l=>[l.id,l]));
  const alreadyGrouped=new Set;
  for(const group of extra.groups){
    const members=group.members.map(id=>objects.get(id)).filter(Boolean);
    for(const member of group.members)alreadyGrouped.add(member);
    const visual = new Group(members,{
      name:group.name,originX:"left",originY:"top",objectCaching:false,
      subTargetCheck:false,selectable:!group.locked,evented:!group.locked,
      data:{layerId:group.id,freeType:"group"},visible:group.visible,
      cornerColor:"#e5c59d",borderColor:"#efba86",
    });
    visual.setControlsVisibility({tl:false,tr:false,bl:false,br:false,ml:false,mr:false,mt:false,mb:false,mtr:false});
    visual.setCoords();
    origins[group.id]={x:visual.left,y:visual.top};
    actual.push({id:group.id,zIndex:Math.max(...group.members.map(id=>byId.get(id)?.zIndex??50)),object:visual});
  }
  for(const layer of extra.layers){
    if(!alreadyGrouped.has(layer.id)){
      actual.push({id:layer.id,zIndex:layer.zIndex,object:objects.get(layer.id)});
    }
  }
  actual.sort((a,b)=>a.zIndex-b.zIndex);
  return {items:actual,groupOrigins:origins};
}
