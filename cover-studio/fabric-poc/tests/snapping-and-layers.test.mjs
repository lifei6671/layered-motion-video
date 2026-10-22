import test from "node:test";
import assert from "node:assert/strict";
import {candidateAxes,snapBounds,clampBounds} from "../src/snapping-engine.mjs";
import {getLayer,orderedLayers,setLayerVisibility,setLayerLock,reorderLayer} from "../src/layer-state.mjs";

test("画布中心与安全边距的吸附距离按屏幕像素换算",()=>{
  const axes=candidateAxes(1080,1440,.05,[]);
  const result=snapBounds({left:335,top:264,width:400,height:100},axes,{scale:.5,thresholdScreenPx:7});
  assert.equal(result.guides.x,540); // rect center=535
  assert.equal(result.dx,5);
  assert.equal(result.guides.y,null); // expected no y match
  const miss=snapBounds({left:320,top:264,width:400,height:100},axes,{scale:2,thresholdScreenPx:7});
  assert.equal(miss.guides.x,null);
  assert.equal(miss.dx,0);
});

test("画布中心线优先于几乎重合的其它图层边缘",()=>{
  const axes=candidateAxes(1080,1440,.05,[{left:889,top:20,width:20,height:40}]);
  const hit=snapBounds({left:149,top:400,width:757,height:210},axes,{scale:.53,thresholdScreenPx:7});
  assert.equal(hit.guides.x,540);
  assert.ok(Math.abs(hit.dx)<=7/.53);
});

test("图层相互对齐时吸附到边缘，超出边界时钳位",()=>{
  const axes=candidateAxes(1080,1440,.05,[{left:200,top:400,width:150,height:80}]);
  const snap=snapBounds({left:342,top:500,width:80,height:40},axes,{scale:1,thresholdScreenPx:10});
  assert.equal(snap.dx,8);
  assert.equal(snap.guides.x,350);
  const clamped=clampBounds(1040,-50,100,60,1080,1440);
  assert.deepEqual(clamped,{x:980,y:0});
});

test("图层属性按场景数据编辑、背景层固定",()=>{
  const scene={layers:[
    {id:"background",visible:true,locked:true,zIndex:0},
    {id:"avatar",visible:true,locked:true,zIndex:10},
    {id:"title",visible:true,locked:false,zIndex:20},
    {id:"subtitle",visible:true,locked:false,zIndex:30},
    {id:"account",visible:true,locked:false,zIndex:40}
  ]};
  assert.deepEqual(orderedLayers(scene).map(l=>l.id),["account","subtitle","title","avatar","background"]);
  assert.equal(setLayerVisibility(scene,"subtitle",false),true);
  assert.equal(getLayer(scene,"subtitle").visible,false);
  assert.equal(setLayerVisibility(scene,"subtitle",false),false);
  assert.equal(setLayerLock(scene,"title",true),true);
  assert.equal(getLayer(scene,"title").locked,true);
  assert.throws(()=>setLayerLock(scene,"background",false));
  assert.equal(reorderLayer(scene,"title",1),true);
  assert.deepEqual(orderedLayers(scene).map(l=>l.id),["account","title","subtitle","avatar","background"]);
  assert.equal(reorderLayer(scene,"account",1),false);
  assert.equal(reorderLayer(scene,"background",-1),false);
  assert.equal(getLayer(scene,"background").zIndex,0);
});
