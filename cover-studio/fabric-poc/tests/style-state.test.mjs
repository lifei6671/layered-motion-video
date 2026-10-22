import test from "node:test";
import assert from "node:assert/strict";
import {defaultStyle,normalizeStyle,setStyleProperty,getLayerStyle} from "../src/style-state.mjs";

function scene(){
  return {layers:["title","subtitle","account","avatar"].map(id=>({id,style:defaultStyle(id)}))};
}

test("默认文字样式保持自动字号及既有封面配色",()=>{
  const data=scene();
  assert.equal(getLayerStyle(data,"title").fontSize,null);
  assert.equal(getLayerStyle(data,"title").fill,"#fffcf4");
  assert.equal(getLayerStyle(data,"subtitle").lineHeight,1.15);
  assert.equal(getLayerStyle(data,"account").fill,"#939496");
  assert.equal(getLayerStyle(data,"avatar").scale,1);
});

test("文字样式变更包括嵌套阴影且重复操作去重",()=>{
  const data=scene();
  assert.equal(setStyleProperty(data,"title","fontSize",180),true);
  assert.equal(setStyleProperty(data,"title","fontSize",180),false);
  assert.equal(setStyleProperty(data,"title","charSpacing",95),true);
  assert.equal(setStyleProperty(data,"title","shadow.enabled",true),true);
  assert.equal(setStyleProperty(data,"title","shadow.color","#FFAA11"),true);
  assert.equal(setStyleProperty(data,"subtitle","lineHeight",1.35),true);
  assert.equal(getLayerStyle(data,"title").fontSize,180);
  assert.equal(getLayerStyle(data,"title").shadow.color,"#ffaa11");
  assert.equal(getLayerStyle(data,"title").charSpacing,95);
  assert.equal(getLayerStyle(data,"subtitle").lineHeight,1.35);
});

test("无效颜色/字距/角度和头像缩放不能进入场景",()=>{
  const data=scene();
  const before=JSON.stringify(data);
  for(const [id,path,value] of [
    ["title","fill","url(script)"],
    ["title","fontSize",401],
    ["title","opacity",Number.NaN],
    ["account","shadow.blur",-5],
    ["subtitle","angle",-250],
    ["avatar","scale",2.7],
    ["avatar","angle",181],
  ]){
    assert.throws(()=>setStyleProperty(data,id,path,value));
  }
  assert.equal(JSON.stringify(data),before);
  assert.throws(()=>normalizeStyle("title",{...defaultStyle("title"),unknown:true}));
});
