import assert from "node:assert/strict";
import {test} from "node:test";
import {
  RATIO_DIMENSIONS, defaultVariant, getPosition, getPositions,
  setPosition, cloneAsNewDesign, sceneSummary
} from "../src/scene-model.mjs";
import {PROFILES, getProfile} from "../src/ratio-layout.mjs";

function baseScene(){
  return {
    schemaVersion: 2,
    id: "example-scene", revision: 3,
    name: "书法封面", activeRatio:"3:4",
    content:{title:"复利思维",subtitle:"时间的价值",account:"@测试"},
    variants:{"3:4":defaultVariant()},
  };
}

test("六种画幅均存在明确的安全布局配置",()=>{
  assert.deepEqual(Object.keys(PROFILES).sort(), Object.keys(RATIO_DIMENSIONS).sort());
  for(const [ratio, profile] of Object.entries(PROFILES)){
    assert.ok(profile.titleTop>0 && profile.titleTop<.6,ratio);
    assert.ok(profile.subtitleMinTop>profile.titleTop,ratio);
    assert.ok(profile.accountMinTop>profile.subtitleMinTop,ratio);
    assert.ok(profile.subtitleMaxBottom>profile.subtitleMinTop,ratio);
    assert.ok(profile.safeMargin>.03,ratio);
    assert.equal(getProfile(ratio),profile);
  }
});

test("从经典布局迁移后，不同画幅的位置状态独立",()=>{
  const scene=baseScene();
  setPosition(scene,"3:4","title",17.25,10.3);
  setPosition(scene,"16:9","title",11.7,25);
  setPosition(scene,"16:9","account",null,null);
  assert.deepEqual(getPosition(scene,"3:4","title"),{x:17.25,y:10.3});
  assert.deepEqual(getPosition(scene,"16:9","title"),{x:11.7,y:25});
  assert.deepEqual(getPosition(scene,"9:16","title"),{x:null,y:null});
  assert.deepEqual(getPosition(scene,"16:9","account"),{x:null,y:null});
  assert.deepEqual(Object.keys(getPositions(scene,"3:4")).sort(),["account","subtitle","title"]);
});

test("每个坐标轴可独立保持自动排版模式",()=>{
  const scene=baseScene();
  setPosition(scene,"3:4","subtitle",null,45);
  assert.deepEqual(getPosition(scene,"3:4","subtitle"),{x:null,y:45});
  assert.equal(scene.variants["3:4"].subtitle.mode,"manual");
  setPosition(scene,"3:4","subtitle",null,null);
  assert.equal(scene.variants["3:4"].subtitle.mode,"auto");
});

test("另存新设计保留独立画幅，但重置版本与标识",()=>{
  const original=baseScene();
  setPosition(original,"4:3","title",30,11);
  const copy=cloneAsNewDesign(original);
  assert.equal(copy.id,null);
  assert.equal(copy.revision,0);
  assert.equal(copy.updatedAt,null);
  assert.notEqual(copy.variants,original.variants);
  copy.variants["4:3"].title.x=13;
  assert.equal(original.variants["4:3"].title.x,30);
  assert.equal(sceneSummary(original).ratio,"3:4");
});

test("坐标和画幅输入校验",()=>{
  const scene=baseScene();
  assert.throws(()=>setPosition(scene,"3:4","title",-1,0));
  assert.throws(()=>setPosition(scene,"3:4","title",101,0));
  assert.throws(()=>setPosition(scene,"3:4","title",Number.NaN,0));
  assert.throws(()=>setPosition(scene,"3:4","random",5,6));
  assert.throws(()=>setPosition(scene,"5:7","title",5,6));
  assert.throws(()=>getProfile("5:7"));
});
