import test from "node:test";
import assert from "node:assert/strict";
import {
  availableSafetyProfiles,resolveSafetyArea,diagnoseLayout,contrastRatio,
  canonicalPair
} from "../src/layout-diagnostics.mjs";
import {
  ensureQuality,setQualityProfile,getQualityProfile,
  setAllowedOverlap,isAllowedOverlap,forgetQualityLayer
} from "../src/quality-state.mjs";

function item(id,kind,rect,extra={}) {
  return {id,kind,label:id,visible:true,rect,...extra};
}
function report(items,additional={}){
  return diagnoseLayout({
    width:1080,height:1440,ratio:"3:4",profileId:"general",
    items,allowedOverlaps:[],...additional
  });
}

test("预设按画幅过滤，安全区域采用原图像素且非官方界面坐标",()=>{
  assert.deepEqual(availableSafetyProfiles("16:9"),["general","landscape_video"]);
  assert.ok(availableSafetyProfiles("9:16").includes("vertical_video"));
  const zone=resolveSafetyArea("9:16",1080,1920,"vertical_video");
  assert.equal(zone.inner.left,75.60000000000001);
  assert.equal(zone.inner.bottom,1920*.81);
  assert.equal(zone.blocked.length,1);
  assert.throws(()=>resolveSafetyArea("16:9",1920,1080,"vertical_video"));
});

test("位置越界属于错误，安全留白及竖屏操作区属于可确认警告",()=>{
  const outside=report([item("title","text",{left:-24,top:100,width:240,height:140},{
    fontSize:110,fill:"#ffffff",opacity:1
  })]);
  assert.ok(outside.issues.some(x=>x.code==="OUT_OF_CANVAS"&&x.severity==="error"));
  const safe=report([item("title","text",{left:20,top:400,width:260,height:90},{
    fontSize:80,fill:"#ffffff",opacity:1
  })]);
  assert.ok(safe.issues.some(x=>x.code==="SAFE_MARGIN"));
  const overlay=diagnoseLayout({
    width:1080,height:1920,ratio:"9:16",profileId:"vertical_video",
    items:[item("account","text",{left:915,top:1000,width:140,height:100},{
      fontSize:34,fill:"#ffffff",opacity:1
    })]
  });
  assert.ok(overlay.issues.some(x=>x.code==="UI_OVERLAY"));
  assert.equal(overlay.safeArea.id,"vertical_video");
});

test("显著的文字遮挡会报告，装饰图层叠放不误报",()=>{
  const title=item("title","text",{left:250,top:400,width:440,height:150},{
    fontSize:100,fill:"#ffffff"
  });
  const account=item("account","text",{left:310,top:470,width:230,height:90},{
    fontSize:40,fill:"#ffffff"
  });
  const rect=item("custom-a","graphic",{left:260,top:410,width:250,height:140});
  const image=item("avatar","avatar",{left:260,top:415,width:100,height:100});
  const collision=report([title,account,rect,image]);
  const warnings=collision.issues.filter(x=>x.code==="LAYER_COLLISION");
  assert.ok(warnings.some(x=>x.layerIds.includes("title")&&x.layerIds.includes("account")));
  assert.ok(warnings.some(x=>x.layerIds.includes("title")&&x.layerIds.includes("avatar")));
  assert.ok(!warnings.some(x=>x.layerIds.includes("custom-a")));
  assert.ok(warnings.every(x=>x.canAllow));
  const hidden=report([{...title,visible:false},account]);
  assert.ok(!hidden.issues.some(x=>x.code==="LAYER_COLLISION"));
  const waived=report([title,account],{
    allowedOverlaps:[["account","title"]]
  });
  assert.ok(!waived.issues.some(x=>x.code==="LAYER_COLLISION"));
});

test("低字号、低透明度与背景对比度只给建议，不推断画面必然不可读",()=>{
  const small=item("custom-x","text",{left:400,top:400,width:100,height:35},{
    fontSize:16,fill:"#ffffff",opacity:.3
  });
  const low=report([small],{
    sampleBackground:()=>[245,245,245]
  });
  assert.ok(low.issues.some(x=>x.code==="SMALL_TEXT"));
  assert.ok(low.issues.some(x=>x.code==="LOW_OPACITY"));
  assert.ok(low.issues.some(x=>x.code==="LOW_CONTRAST"&&x.heuristic));
  assert.ok(contrastRatio("#ffffff",[0,0,0])>20);
  assert.ok(contrastRatio("#fafafa",[255,255,255])<1.1);
});

test("安全区方案与人工允许重叠按设计独立保存，排序规范化",()=>{
  const scene={
    activeRatio:"3:4",
    layers:[{id:"background"},{id:"title"},{id:"subtitle"}],
    extras:{layers:[{id:"custom-a"}],groups:[]}
  };
  assert.deepEqual(ensureQuality(scene),{profilesByRatio:{},allowedOverlaps:[],allowedByRatio:{}});
  assert.equal(setQualityProfile(scene,"9:16","vertical_video"),true);
  assert.equal(getQualityProfile(scene,"9:16"),"vertical_video");
  assert.equal(getQualityProfile(scene,"16:9"),"general");
  assert.equal(setQualityProfile(scene,"9:16","vertical_video"),false);
  assert.throws(()=>setQualityProfile(scene,"16:9","vertical_video"));
  assert.deepEqual(canonicalPair("title","custom-a"),["custom-a","title"]);
  assert.equal(setAllowedOverlap(scene,"title","custom-a",true),true);
  assert.equal(isAllowedOverlap(scene,"custom-a","title"),true);
  assert.equal(isAllowedOverlap(scene,"custom-a","title","16:9"),false);
  assert.deepEqual(scene.quality.allowedByRatio["3:4"],[["custom-a","title"]]);
  assert.equal(setAllowedOverlap(scene,"custom-a","title",true),false);
  assert.throws(()=>setAllowedOverlap(scene,"background","title",true));
  forgetQualityLayer(scene,"custom-a");
  assert.deepEqual(scene.quality.allowedOverlaps,[]);
  assert.deepEqual(scene.quality.allowedByRatio,{});
  assert.equal(setQualityProfile(scene,"9:16","general"),true);
  assert.deepEqual(scene.quality.profilesByRatio,{});
});


test("旧版全画幅重叠确认继续生效，当前画幅专用确认支持撤销",()=>{
  const scene={
    activeRatio:"16:9",
    layers:[{id:"background"},{id:"title"},{id:"subtitle"},{id:"account"}],
    extras:{layers:[],groups:[]},
    quality:{
      profilesByRatio:{},
      allowedOverlaps:[["account","title"]],
      allowedByRatio:{"16:9":[["subtitle","title"]]}
    }
  };
  assert.equal(isAllowedOverlap(scene,"title","account","3:4"),true);
  assert.equal(isAllowedOverlap(scene,"title","subtitle","3:4"),false);
  assert.equal(isAllowedOverlap(scene,"title","subtitle","16:9"),true);
  assert.equal(setAllowedOverlap(scene,"title","subtitle",false,"16:9"),true);
  assert.equal(isAllowedOverlap(scene,"title","subtitle","16:9"),false);
  assert.equal(setAllowedOverlap(scene,"title","account",false,"*"),true);
  assert.deepEqual(scene.quality.allowedOverlaps,[]);
  assert.deepEqual(scene.quality.allowedByRatio,{});
});
