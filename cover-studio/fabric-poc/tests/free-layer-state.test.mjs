import test from "node:test";
import assert from "node:assert/strict";
import {
  ensureExtras,createLayer,layerById,groupById,groupLayers,ungroupLayers,
  removeFreeLayer,moveFreeFrame,reorderFreeLayer,extraEntries,
  getFreeFrame,hasFreeFrameOverride,resetFreeFrame,applyFreeFrameToAll,
  moveGroupInRatio
} from "../src/free-layer-state.mjs";

const scene=()=>({extras:{layers:[],groups:[]}});
test("新增自由文字、椭圆、矩形和图片保留独立稳定 ID",()=>{
  const s=scene();
  const t=createLayer(s,"text",{fontId:"local:test",content:"复利思维"});
  const r=createLayer(s,"rect");
  const e=createLayer(s,"ellipse");
  const i=createLayer(s,"image",{assetId:"a".repeat(64)+".png"});
  assert.equal(new Set(s.extras.layers.map(x=>x.id)).size,4);
  assert.deepEqual(s.extras.layers.map(x=>x.type),["text","rect","ellipse","image"]);
  assert.deepEqual(s.extras.layers.map(x=>x.zIndex),[50,51,52,53]);
  assert.equal(t.text,"复利思维");
  assert.equal(i.assetId,"a".repeat(64)+".png");
  assert.equal(extraEntries(s).at(0).id,i.id);
  assert.equal(reorderFreeLayer(s,t.id,1),true);
  assert.equal(extraEntries(s)[2].id,t.id);
});

test("组合关系被持久化，解组保留各图层身份",()=>{
  const s=scene();
  const a=createLayer(s,"rect");
  const b=createLayer(s,"text",{fontId:"test-font"});
  const c=createLayer(s,"ellipse");
  const g=groupLayers(s,[a.id,b.id]);
  assert.deepEqual(groupById(s,g.id).members,[a.id,b.id]);
  assert.equal(layerById(s,a.id).groupId,g.id);
  assert.equal(extraEntries(s).length,2);
  assert.throws(()=>groupLayers(s,[a.id,c.id]),/先解组/);
  ungroupLayers(s,g.id);
  assert.equal(s.extras.groups.length,0);
  assert.equal(layerById(s,a.id).groupId,null);
  assert.equal(extraEntries(s).length,3);
});

test("组内删除剩余单个成员时自动解组",()=>{
  const s=scene();
  const a=createLayer(s,"rect"),b=createLayer(s,"ellipse");
  groupLayers(s,[a.id,b.id]);
  removeFreeLayer(s,b.id);
  assert.equal(s.extras.groups.length,0);
  assert.equal(layerById(s,a.id).groupId,null);
});

test("位置变换约束到画布，越界时钳位",()=>{
  const s=scene();
  const a=createLayer(s,"rect");
  moveFreeFrame(s,a.id,{x:90,y:80,width:20,height:30,angle:35});
  const f=layerById(s,a.id).frame;
  assert.equal(f.x,80);
  assert.equal(f.y,70);
  assert.equal(f.angle,35);
  assert.throws(()=>moveFreeFrame(s,a.id,{x:0,y:0,width:0,height:20,angle:0}));
});

test("不同画幅具有独立的位置、尺寸和角度覆盖，未编辑比例继续继承基线",()=>{
  const data=scene();
  const layer=createLayer(data,"rect");
  const base={...layer.frame};
  const wide={x:10,y:16,width:48,height:27,angle:-22};
  moveFreeFrame(data,layer.id,wide,"16:9");
  assert.deepEqual(getFreeFrame(data,layer.id,"16:9"),wide);
  assert.deepEqual(getFreeFrame(data,layer.id,"3:4"),base);
  assert.deepEqual(getFreeFrame(data,layer.id,"9:16"),base);
  assert.equal(hasFreeFrameOverride(data,layer.id,"16:9"),true);
  assert.equal(hasFreeFrameOverride(data,layer.id,"3:4"),false);
  moveFreeFrame(data,layer.id,{x:65,y:55,width:32,height:21,angle:9},"3:4");
  assert.deepEqual(getFreeFrame(data,layer.id,"16:9"),wide);
  assert.deepEqual(getFreeFrame(data,layer.id,"9:16"),base);
});

test("恢复继承仅删除当前画幅覆盖；应用全部则统一共享基线",()=>{
  const data=scene();
  const layer=createLayer(data,"rect");
  const old={...layer.frame};
  const wide={x:22,y:28,width:42,height:31,angle:13};
  moveFreeFrame(data,layer.id,wide,"16:9");
  moveFreeFrame(data,layer.id,{x:3,y:4,width:20,height:19,angle:6},"3:4");
  assert.equal(resetFreeFrame(data,layer.id,"3:4"),true);
  assert.deepEqual(getFreeFrame(data,layer.id,"3:4"),old);
  assert.deepEqual(getFreeFrame(data,layer.id,"16:9"),wide);
  assert.equal(resetFreeFrame(data,layer.id,"3:4"),false);
  assert.equal(applyFreeFrameToAll(data,layer.id,"16:9"),true);
  assert.deepEqual(getFreeFrame(data,layer.id,"9:16"),wide);
  assert.deepEqual(getFreeFrame(data,layer.id,"3:4"),wide);
  assert.deepEqual(layer.ratioFrames,{});
  assert.equal(applyFreeFrameToAll(data,layer.id,"16:9"),false);
});

test("组合拖动只更新当前画幅，接近边界仍保持成员相对距离",()=>{
  const data=scene();
  const a=createLayer(data,"rect");
  const b=createLayer(data,"ellipse");
  const group=groupLayers(data,[a.id,b.id]);
  const untouchedA={...getFreeFrame(data,a.id,"9:16")};
  const untouchedB={...getFreeFrame(data,b.id,"9:16")};
  const baseXDiff=b.frame.x-a.frame.x;
  moveGroupInRatio(data,group.id,"3:4",70,60);
  const currentA=getFreeFrame(data,a.id,"3:4");
  const currentB=getFreeFrame(data,b.id,"3:4");
  assert.ok(currentA.x>untouchedA.x);
  assert.ok(currentB.y>untouchedB.y);
  assert.equal(Math.round((currentB.x-currentA.x)*100)/100,baseXDiff);
  assert.deepEqual(getFreeFrame(data,a.id,"9:16"),untouchedA);
  assert.deepEqual(getFreeFrame(data,b.id,"9:16"),untouchedB);
  moveGroupInRatio(data,group.id,"16:9",-10,6);
  assert.deepEqual(getFreeFrame(data,a.id,"9:16"),untouchedA);
});

test("画幅覆盖拒绝非法比例、非有限数字和越界尺寸",()=>{
  const data=scene();
  const layer=createLayer(data,"rect");
  for(const ratio of ["0:1","2:3","test"]) {
    assert.throws(()=>moveFreeFrame(data,layer.id,layer.frame,ratio));
  }
  assert.throws(()=>moveFreeFrame(data,layer.id,{...layer.frame,x:NaN},"16:9"));
  assert.throws(()=>moveFreeFrame(data,layer.id,{...layer.frame,width:120},"16:9"));
  assert.throws(()=>moveFreeFrame(data,layer.id,{...layer.frame,angle:181},"16:9"));
  assert.throws(()=>resetFreeFrame(data,layer.id,"2:3"));
});
