import {chromium} from "playwright-core";
import {mkdir, writeFile} from "node:fs/promises";
import {join} from "node:path";

const [baseUrl, outputFolder] = process.argv.slice(2);
if (!baseUrl || !outputFolder) throw Error("Usage: node browser-check.mjs <baseurl> <outputdir>");

const ratios = {
  "3:4": [1080,1440], "9:16": [1080,1920],
  "16:9": [1920,1080], "4:3": [1440,1080],
  "4:5": [1080,1350], "1:1": [1080,1080],
};
const samples = ["复利思维","普通人的财富积累逻辑"];
const failures = [];
const diagnostics = [];
const t0 = Date.now();
const browser = await chromium.launch({
  channel: "msedge",
  headless: true,
  args: ["--no-first-run","--disable-extensions"],
});
const page = await browser.newPage({viewport:{width:1600,height:1150},deviceScaleFactor:1,acceptDownloads:true});
page.on("pageerror", (error) => failures.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") diagnostics.push(message.text().slice(0,250));
});
try {
  await page.goto(baseUrl + "/",{waitUntil:"domcontentloaded",timeout:40000});
  await page.waitForFunction(()=>Boolean(window.__fabricPoc?.getState().ready),null,{timeout:40000});
  if(new URL(page.url()).pathname!=="/")throw Error("正式编辑器的首页地址不正确");
  const classicPage=await page.request.get(baseUrl+"/legacy");
  if(classicPage.status()!==200 || !(await classicPage.text()).includes('id="coverForm"'))
    throw Error("经典封面入口或原有编辑表单不可用");
  const bookmark=await page.request.get(baseUrl+"/fabric-poc",{maxRedirects:0});
  if(bookmark.status()!==302 || bookmark.headers().location!=="/")
    throw Error("历史浏览器书签没有跳转到正式首页");
  const pageTitle=await page.title();
  if(!pageTitle.includes("封面工坊"))throw Error("封面编辑器标题不正确");
  const initial=await page.evaluate(()=>window.__fabricPoc.getState());
  if (!initial.objects.includes("title") || !initial.objects.includes("subtitle"))
    throw Error("初始画布缺少标题图层");

  const initialCounters=initial.metrics;
  const pngs=[];
  for (const ratio of Object.keys(ratios)) {
    await page.evaluate(async ratio=>await window.__fabricPoc.setRatio(ratio),ratio);
    for (const title of samples) {
      await page.evaluate(async(title)=>window.__fabricPoc.setContent({
        title,subtitle:"存款百万不是结束而是开始",account:"@封面工坊"
      }),title);
      const scene=await page.evaluate(()=>window.__fabricPoc.getState());
      if(!scene.ready)throw Error("Scene not ready: "+ratio+" "+title);
      if(scene.layout.titleLines.join("")!==title)throw Error("标题字符丢失: "+ratio+" "+title);
      if(scene.layout.titleLines.length>2)throw Error("标题超过两行");
      const dataUrl=await page.evaluate(()=>window.__fabricPoc.exportDataUrl());
      if(!dataUrl.startsWith("data:image/png;base64,"))throw Error("PNG encoding failed");
      const buf=Buffer.from(dataUrl.slice(dataUrl.indexOf(",")+1),"base64");
      const pngSize=[buf.readUInt32BE(16),buf.readUInt32BE(20)];
      if(JSON.stringify(pngSize)!==JSON.stringify(ratios[ratio]))
        throw Error("Wrong PNG dimensions "+ratio+" "+pngSize);
      const outName=ratio.replace(":","x")+"_"+(title.length>4?"long":"short")+".png";
      if(ratio==="3:4" || title.length>4 && ratio==="16:9"){
        await mkdir(outputFolder,{recursive:true});
        await writeFile(join(outputFolder,outName),buf);
      }
      const rects=await page.evaluate(()=>
        Object.fromEntries(["title","subtitle","account"].map(id=>[id,window.__fabricPoc.getObjectRect(id)]))
      );
      pngs.push({
        ratio,title,width:pngSize[0],height:pngSize[1],bytes:buf.byteLength,
        lines:scene.layout.titleLines,
        fontSize:scene.layout.titleSize,
        subtitleLines:scene.layout.subtitleLines,
        subtitleFontSize:scene.layout.subtitleSize,
        warnings:scene.layout.warnings,
        rects,tag:outName
      });
    }
  }
  await page.evaluate(()=>window.__fabricPoc.setRatio("3:4"));
  await page.evaluate(()=>window.__fabricPoc.setContent({title:"复利思维"}));
  const catalog=await page.evaluate(async()=>(await fetch("/api/fonts")).json());
  const woff2=catalog.fonts.find(f=>f.source==="local" && f.family==="AlimamaDongFangDaKai" && f.format==="WOFF2" && f.coverage==="chinese");
  let woff2Result={available:Boolean(woff2),loaded:false};
  if(woff2){
    await page.locator("#titleFont").selectOption(woff2.id);
    await page.waitForFunction((id)=>{
      const p=window.__fabricPoc.getState();
      return p.ready && p.fontIds.title===id;
    },woff2.id,{timeout:20000});
    woff2Result={available:true,loaded:true,fontId:woff2.id};
  }
  // 改标题和拖动不得引起后端 Pillow 渲染或重新加载字体。
  const beforeEdits=await page.evaluate(()=>window.__fabricPoc.getState());
  const requests=[];
  const tracker=(request)=>requests.push(new URL(request.url()).pathname);
  page.on("request",tracker);
  await page.evaluate(()=>window.__fabricPoc.setContent({title:"长期主义"}));
  await page.evaluate(()=>window.__fabricPoc.setContent({title:"复利思维"}));
  const titleBox=await page.evaluate(()=>window.__fabricPoc.getObjectRect("title"));
  const canvasBox=await page.locator("#preview-holder").boundingBox();
  const scale=canvasBox.width/1080;
  const cx=canvasBox.x+(titleBox.x+titleBox.width*.5)*scale;
  const cy=canvasBox.y+(titleBox.y+titleBox.height*.5)*scale;
  const positionBefore=beforeEdits.positions.title;
  await page.mouse.move(cx,cy);
  await page.mouse.down();
  await page.mouse.move(cx-60,cy+30,{steps:7});
  await page.mouse.up();
  const postEdits=await page.evaluate(()=>window.__fabricPoc.getState());
  page.off("request",tracker);
  if(postEdits.metrics.fontRequests!==beforeEdits.metrics.fontRequests)
    throw Error("Editing a title unexpectedly reloaded font");
  if(postEdits.metrics.materialRequests!==beforeEdits.metrics.materialRequests)
    throw Error("Editing a title unexpectedly reloaded material");
  if(requests.filter(path=>path.startsWith("/api/render")||path.startsWith("/api/text-layers")).length)
    throw Error("Frontend interaction invoked Pillow render endpoint");
  if(postEdits.positions.title.x===positionBefore.x && postEdits.positions.title.y===positionBefore.y)
    throw Error("Mouse move did not reposition title");
  const finalUrl=await page.evaluate(()=>window.__fabricPoc.exportDataUrl());
  const output=Buffer.from(finalUrl.split(",")[1],"base64");
  await writeFile(join(outputFolder,"dragged_3x4.png"),output);
  await page.screenshot({path:join(outputFolder,"browser-editor.png"),fullPage:true});

  // 验证本地上传图片也完全由浏览器合成，不使用 Pillow 图像接口。
  await page.locator("#bgUpload").setInputFiles(join(outputFolder,"fixture-background.png"));
  await page.waitForFunction(()=>window.__fabricPoc.getState().layout?.backgroundLoaded,null,{timeout:10000});
  await page.locator("#avatarUpload").setInputFiles(join(outputFolder,"fixture-avatar.png"));
  await page.waitForFunction(()=>window.__fabricPoc.getState().layout?.avatarLoaded,null,{timeout:10000});
  const assetUrl=await page.evaluate(()=>window.__fabricPoc.exportDataUrl());
  const assetBuffer=Buffer.from(assetUrl.split(",")[1],"base64");
  await writeFile(join(outputFolder,"uploaded_3x4.png"),assetBuffer);
  const imageAssetsLoaded=await page.evaluate(()=>{
    const {layout}=window.__fabricPoc.getState();
    return layout.backgroundLoaded && layout.avatarLoaded;
  });

  // 场景模型持久化：同一封面包含多套画幅专用坐标，旧模板保持独立。
  const designLifecycle = await page.evaluate(async () => {
    const api = window.__fabricPoc;
    const originalPreset = await (await fetch("/api/preset",{cache:"no-store"})).json();
    const draft = api.getScene();
    if (draft.schemaVersion !== 2 || draft.id !== null) {
      throw Error("经典版导入草稿格式不正确");
    }
    document.getElementById("designName").value = "技术验证 · 画幅样例";
    const created = await api.saveDesign(true);
    if (!created.id || created.revision !== 1) throw Error("创建设计失败");
    const id = created.id;
    api.setPosition("title", 17.25, 12.5);
    const saved3x4 = await api.saveDesign(false);
    if (saved3x4.revision !== 2) throw Error("保存修订版本失败");
    await api.setRatio("16:9");
    const autoWide = api.getState();
    if (autoWide.positions.title.x !== null) throw Error("横版错误继承竖版坐标");
    api.setPosition("title", 23, 16);
    const savedWide = await api.saveDesign(false);
    if (savedWide.revision !== 3) throw Error("横版修订保存失败");
    const expectedWidePng = api.exportDataUrl();
    await api.setRatio("3:4");
    const remembered = api.getState();
    if (Math.abs(remembered.positions.title.x - 17.25) > .01) {
      throw Error("切换画幅未恢复竖版标题坐标");
    }
    const sceneBefore = api.getScene();
    await api.loadDesign(id);
    const restored = api.getState();
    if (restored.scene.revision !== 3) throw Error("设计重新载入版本错误");
    if (restored.ratio !== "16:9" || Math.abs(restored.positions.title.x - 23) > .01) {
      throw Error("重新打开没有恢复最后保存的横版位置");
    }
    if (api.exportDataUrl() !== expectedWidePng) {
      throw Error("重新打开后的高清 PNG 与保存前不一致");
    }
    if (!restored.layout.backgroundLoaded || !restored.layout.avatarLoaded) {
      throw Error("重新打开设计后素材未恢复");
    }
    await api.setRatio("3:4");
    if (Math.abs(api.getState().positions.title.x - 17.25) > .01) {
      throw Error("重新打开后竖版覆盖未恢复");
    }
    await api.setRatio("9:16");
    if (api.getState().positions.title.x !== null) {
      throw Error("其他画幅未保留自动布局模式");
    }
    await api.resetPosition("account");
    const automatic = api.getState();
    if (automatic.positions.account.y !== null) {
      throw Error("账号自动布局复位失败");
    }
    if (automatic.layout.warnings.length !== 0) {
      throw Error("自动布局仍存在碰撞：" + automatic.layout.warnings.join("；"));
    }
    const copy = await api.saveDesign(true);
    if (copy.id === id || copy.revision !== 1) {
      throw Error("另存设计未产生独立版本");
    }
    const currentPreset = await (await fetch("/api/preset",{cache:"no-store"})).json();
    const legacyPresetUntouched=JSON.stringify(originalPreset)===JSON.stringify(currentPreset);
    if (!legacyPresetUntouched) throw Error("旧版默认模板在保存设计时被改写");
    return {
      ok: true, id, copiedId: copy.id,
      originalRevision: 3,
      copiedRevision: copy.revision,
      variants: Object.keys(sceneBefore.variants),
      exportMatchesAfterReload: true,
      legacyPresetUntouched,
      backgroundsRestored: restored.layout.backgroundLoaded,
      avatarRestored: restored.layout.avatarLoaded,
      autoLayoutWarnings: automatic.layout.warnings.length,
    };
  });
  // 新设计草稿的自动布局在所有六种比例中应能独立重新计算。
  const autoLayouts = [];
  for(const ratio of Object.keys(ratios)){
    const record = await page.evaluate(async (ratio) => {
      const api = window.__fabricPoc;
      await api.setRatio(ratio);
      api.resetPosition("title");
      api.resetPosition("subtitle");
      api.resetPosition("account");
      await api.setContent({title:"普通人的财富积累逻辑",subtitle:"存款百万不是结束而是开始"});
      const state = api.getState();
      return {ratio, warnings:state.layout.warnings, titleLines:state.layout.titleLines,
        bounds:Object.fromEntries(["title","subtitle","account","avatar"].map(x=>[x,api.getObjectRect(x)]))};
    },ratio);
    autoLayouts.push(record);
  }
  if (autoLayouts.some(item=>item.warnings.length>0)) {
    throw Error("自动布局碰撞未通过：" +
      autoLayouts.filter(item=>item.warnings.length).map(item=>item.ratio).join("、"));
  }

  // 历史记录：图层定位与画幅切换按一次操作保存，可逐步撤销重做。
  const editHistory = await page.evaluate(async () => {
    const api = window.__fabricPoc;
    await api.loadDesign("legacy");
    await api.setRatio("3:4");
    const start = api.getState().positions.title;
    api.setPosition("title", 21, 17);
    const changed = api.getState().positions.title;
    await api.undo();
    const reverted = api.getState().positions.title;
    await api.redo();
    const redone = api.getState().positions.title;
    if (changed.x !== 21 || reverted.x !== start.x || redone.x !== 21) {
      throw Error("图层位置撤销重做不一致");
    }
    await api.setRatio("16:9");
    await api.undo();
    if (api.getState().ratio !== "3:4") throw Error("画幅撤销失败");
    await api.redo();
    if (api.getState().ratio !== "16:9") throw Error("画幅重做失败");
    return {ok:true,history:api.getHistory(),positionRestored:redone.x===21};
  });

  // 专业图层操作：锁定、隐藏、前后层级、保存与撤销重做。
  const layerChecks=await page.evaluate(async()=>{
    const api=window.__fabricPoc;
    await api.loadDesign("legacy");
    await api.setRatio("3:4");
    const first=api.getState();
    if(!document.getElementById("snapEnabled").checked) throw Error("吸附默认未启用");
    if(document.getElementById("layerList").querySelectorAll(".layer-control-row").length!==5)
      throw Error("未生成完整图层面板");
    const baseline=api.exportDataUrl();
    if(!api.changeLayer("title","visibility"))throw Error("隐藏标题失败");
    const hidden=api.exportDataUrl();
    if(hidden===baseline)throw Error("隐藏文字后 PNG 没有变化");
    if(api.getState().scene.layers.find(x=>x.id==="title").visible!==false)
      throw Error("隐藏状态未写入场景");
    await api.undo();
    if(api.exportDataUrl()!==baseline)throw Error("隐藏撤销未恢复图片");
    await api.redo();
    if(api.exportDataUrl()===baseline)throw Error("隐藏重做失败");
    api.changeLayer("title","visibility");
    api.changeLayer("subtitle","lock");
    const locked=api.getState().scene.layers.find(x=>x.id==="subtitle").locked;
    if(!locked)throw Error("锁定状态未写入场景");
    const before=api.getLayerOrder();
    api.changeLayer("title","up");
    const after=api.getLayerOrder();
    if(JSON.stringify(before)===JSON.stringify(after))throw Error("图层上移未改变层级顺序");
    if(after.at(-1)!=="background")throw Error("背景层未固定到底部");
    const created=await api.saveDesign(true);
    await api.loadDesign(created.id);
    const restored=api.getState();
    if(restored.scene.layers.find(x=>x.id==="subtitle").locked!==true ||
       restored.layerOrder.join(",")!==after.join(","))
      throw Error("图层属性保存后未恢复");
    if(!document.querySelector('[data-layer="subtitle"] [data-layer-action="select"]').disabled)
      throw Error("被锁图层仍能选中");
    api.changeLayer("subtitle","lock");
    await api.undo();
    if(api.getState().scene.layers.find(x=>x.id==="subtitle").locked!==true)
      throw Error("锁定操作撤销失败");
    await api.redo();
    if(api.getState().scene.layers.find(x=>x.id==="subtitle").locked!==false)
      throw Error("锁定操作重做失败");
    return {ok:true,savedId:created.id,initialOrder:first.layerOrder,savedOrder:after,
      hiddenExportDifferent:true,lockRestored:true,backgroundPinned:true};
  });

  // 实际鼠标拖动命中磁力中心线，拖动结束参考线立即消失。
  await page.evaluate(async()=>{
    const api=window.__fabricPoc;
    await api.loadDesign("legacy");
    await api.setRatio("3:4");
    api.setSnapEnabled(true);
    const rect=api.getObjectRect("title");
    const destinationLeft=540-rect.width/2-30;
    api.setPosition("title",destinationLeft/1080*100,29);
  });
  const rectBeforeSnap=await page.evaluate(()=>window.__fabricPoc.getObjectRect("title"));
  const holderRect=await page.locator("#preview-holder").boundingBox();
  const multiplier=holderRect.width/1080;
  const mouseStartX=holderRect.x+(rectBeforeSnap.x+rectBeforeSnap.width*.5)*multiplier;
  const mouseStartY=holderRect.y+(rectBeforeSnap.y+rectBeforeSnap.height*.5)*multiplier;
  await page.mouse.move(mouseStartX,mouseStartY);
  await page.mouse.down();
  await page.mouse.move(mouseStartX+27*multiplier,mouseStartY,{steps:5});
  const guidesDuringDrag=await page.evaluate(()=>window.__fabricPoc.getGuides());
  await page.screenshot({path:join(outputFolder,"snapping-guides.png"),fullPage:false});
  await page.mouse.up();
  const rectAfterSnap=await page.evaluate(()=>window.__fabricPoc.getObjectRect("title"));
  const guidesAfterDrag=await page.evaluate(()=>window.__fabricPoc.getGuides());
  if(guidesDuringDrag.x===null)
    throw Error("鼠标移动时未出现水平中心吸附参考线");
  if(Math.abs(rectAfterSnap.x+rectAfterSnap.width/2-540)>3)
    throw Error("标题没有吸附到画布中心："+JSON.stringify({
      before:rectBeforeSnap,after:rectAfterSnap,guides:guidesDuringDrag,multiplier
    }));
  if(guidesAfterDrag.x!==null||guidesAfterDrag.y!==null)
    throw Error("鼠标松开后参考线仍然可见");
  const snappingChecks={
    ok:true,during:guidesDuringDrag,after:guidesAfterDrag,
    titleCenter:rectAfterSnap.x+rectAfterSnap.width/2,
    overlaySeparate:await page.locator("#guide-overlay").evaluate(node=>
      node.parentElement.id==="preview-holder" && node.style.pointerEvents!=="auto"
    )
  };

  // 属性面板：字体与头像/背景的实时样式、持久化和撤销重做。
  const propertyChecks=await page.evaluate(async(savedId)=>{
    const api=window.__fabricPoc;
    // 此设计由之前的素材持久化测试建立，包含真实背景与头像。
    await api.loadDesign(savedId);
    await api.setRatio("3:4");
    await api.setContent({title:"复利思维",subtitle:"存款百万不是结束而是开始",account:"@封面工坊"});
    const before=api.exportDataUrl();
    const initialStyle=api.getStyle("title");
    if(initialStyle.fontSize!==null)throw Error("旧模板标题应使用自动字号");
    api.selectInspector("title");
    if(document.getElementById("styleSizeMode").value!=="auto")
      throw Error("字号自动模式未显示");
    document.getElementById("styleSizeMode").value="fixed";
    document.getElementById("styleSizeMode").dispatchEvent(new Event("change",{bubbles:true}));
    await new Promise(resolve=>setTimeout(resolve,120));
    if(api.getStyle("title").fontSize===null)
      throw Error("字号模式切换没有进入固定字号");
    await api.setStyle("title","fontSize",168);
    await api.setStyle("title","charSpacing",70);
    await api.setStyle("title","lineHeight",1.3);
    await api.setStyle("title","fill","#ef4572");
    await api.setStyle("title","stroke","#112233");
    await api.setStyle("title","strokeWidth",3);
    await api.setStyle("title","angle",85);
    const rotated=api.getObjectRect("title");
    if(rotated.x < -1 || rotated.y < -1 ||
       rotated.x+rotated.width > 1081 || rotated.y+rotated.height > 1441)
      throw Error("旋转文字边界超出了画布："+JSON.stringify(rotated));
    await api.setStyle("title","angle",7);
    await api.setStyle("title","shadow.enabled",true);
    await api.setStyle("title","shadow.color","#223344");
    await api.setStyle("title","shadow.blur",10);
    await api.setStyle("title","shadow.opacity",.65);
    await api.setStyle("subtitle","fill","#d2f4b5");
    await api.setStyle("subtitle","lineHeight",1.25);
    await api.setStyle("account","opacity",.7);
    await api.setStyle("avatar","opacity",.78);
    await api.setStyle("avatar","angle",12);
    await api.setStyle("avatar","scale",1.15);
    await api.setStyle("background","darkness",87);
    await api.setStyle("background","focus_y",37);
    await api.setStyle("background","glow",true);
    const updated=api.exportDataUrl();
    if(updated===before)throw Error("编辑属性后最终 PNG 未发生变化");
    const current=api.getStyle("title");
    if(current.fontSize!==168 || current.charSpacing!==70 ||
      current.strokeWidth!==3 || current.shadow.enabled!==true || current.angle!==7)
      throw Error("样式对象未正确更新");
    const userInput=document.getElementById("styleFill");
    api.selectInspector("title");
    userInput.value="#a736df";
    userInput.dispatchEvent(new Event("input",{bubbles:true}));
    await new Promise(resolve=>setTimeout(resolve,350));
    const fromUi=api.getStyle("title");
    if(fromUi.fill!=="#a736df")throw Error("颜色输入框未正确绑定属性");
    const ready=api.getState();
    if(!ready.ready)throw Error("样式修改后画布未就绪");
    const rendered=api.exportDataUrl();
    const saved=await api.saveDesign(true);
    await api.loadDesign(saved.id);
    const reopened=api.getState();
    if(JSON.stringify(api.getStyle("title"))!==JSON.stringify(fromUi))
      throw Error("重新打开后书法字体样式不一致");
    if(reopened.scene.layers.find(x=>x.id==="avatar").style.scale!==1.15)
      throw Error("头像尺寸没有保存");
    if(reopened.scene.backgroundStyle.darkness!==87)
      throw Error("背景压暗设置没有保存");
    if(api.exportDataUrl()!==rendered)
      throw Error("重新打开后的 PNG 与修改时不一致");
    await api.setStyle("title","fill","#00aa88");
    await api.undo();
    if(api.getStyle("title").fill!=="#a736df")
      throw Error("文字颜色撤销失败");
    await api.redo();
    if(api.getStyle("title").fill!=="#00aa88")
      throw Error("文字颜色重做失败");
    api.selectInspector("avatar");
    if(document.getElementById("avatarScale").value!=="1.15")
      throw Error("头像属性面板未显示当前缩放值");
    api.selectInspector("background");
    if(document.getElementById("backgroundDarkness").value!=="87")
      throw Error("背景属性面板未显示当前压暗值");
    const backdropControl=document.getElementById("backgroundDarkness");
    backdropControl.value="85";
    backdropControl.dispatchEvent(new Event("input",{bubbles:true}));
    await new Promise(resolve=>setTimeout(resolve,150));
    if(api.getStyle("background").darkness!==85)
      throw Error("背景滑块未驱动实时绘制");
    return {
      ok:true, savedId:saved.id, pngDiffers:true, exportMatchesAfterReload:true,
      fill:fromUi.fill, fontPx:fromUi.fontSize, rotation:fromUi.angle,
      avatarScale:reopened.scene.layers.find(x=>x.id==="avatar").style.scale,
      backgroundDarkness:reopened.scene.backgroundStyle.darkness,
      undoRedo:true, allRenderedInBrowser:true
    };
  },designLifecycle.copiedId);
  await page.evaluate(()=>window.__fabricPoc.selectInspector("title"));
  await page.screenshot({path:join(outputFolder,"property-inspector.png"),fullPage:true});

  // 自由图层生命周期：添加、组合、真实拖动、解组、图片入库及 PNG 稳定性。
  const freeSetup=await page.evaluate(async()=>{
    const api=window.__fabricPoc;
    await api.loadDesign("legacy");
    await api.setRatio("3:4");
    const baseline=api.exportDataUrl();
    const text=await api.addFreeLayer("text");
    await api.setFreeProperty("text","家庭经济学");
    await api.setFreeProperty("fontSize",64);
    await api.setFreeProperty("fill","#ffcc33");
    const rect=await api.addFreeLayer("rect");
    await api.setFreeProperty("fill","#4477bb");
    const ellipse=await api.addFreeLayer("ellipse");
    const data=api.getFreeLayerList();
    if(data.layers.length!==3 || data.groups.length!==0)
      throw Error("自由图层未正常创建");
    const result=api.exportDataUrl();
    if(baseline===result)throw Error("新图形未进入 PNG");
    const group=await api.groupFreeLayers([text,rect]);
    const after=api.getFreeLayerList();
    if(after.groups.length!==1 || after.groups[0].id!==group)
      throw Error("组合关系没有保存");
    if(document.querySelectorAll('#layerList [data-free="true"]').length<4)
      throw Error("自由图层未出现在编辑面板");
    return {text,rect,ellipse,group,beforeFrames:after.layers.filter(x=>[text,rect].includes(x.id)).map(x=>x.frame)};
  });
  const freeHolder=await page.locator("#preview-holder").boundingBox();
  const groupRect=await page.evaluate(id=>window.__fabricPoc.getObjectRect(id),freeSetup.group);
  if(!groupRect)throw Error("组合缺少 Fabric 对象");
  const freeScale=freeHolder.width/1080;
  const groupStartX=freeHolder.x+(groupRect.x+Math.min(22,groupRect.width*.08))*freeScale;
  const groupStartY=freeHolder.y+(groupRect.y+Math.min(22,groupRect.height*.08))*freeScale;
  await page.mouse.move(groupStartX,groupStartY);
  await page.mouse.down();
  await page.mouse.move(groupStartX+55,groupStartY+39,{steps:9});
  await page.mouse.up();
  const afterGroupDrag=await page.evaluate(()=>window.__fabricPoc.getFreeLayerList());
  const groupMembers=afterGroupDrag.layers.filter(layer=>
    layer.groupId===freeSetup.group);
  const shifted=groupMembers.some((x,index)=>Math.abs(
    (x.ratioFrames?.["3:4"]?.x ?? x.frame.x)-freeSetup.beforeFrames[index].x
  )>.5);
  const baseUnchanged=groupMembers.every((x,index)=>
    JSON.stringify(x.frame)===JSON.stringify(freeSetup.beforeFrames[index])
  );
  const uneditedRatioInherited=groupMembers.every(x=>!x.ratioFrames?.["16:9"]);
  if(!shifted || !baseUnchanged || !uneditedRatioInherited)throw Error(
    "组合拖动的当前画幅覆盖异常："+JSON.stringify({
      before:freeSetup.beforeFrames,after:groupMembers.map(x=>({
        frame:x.frame,variants:x.ratioFrames
      })),groupRect
    })
  );

  const ratioChecks=await page.evaluate(async (id)=>{
    const api=window.__fabricPoc;
    const original=api.getFreeLayout(id,"3:4");
    const originalBase=api.getFreeLayerList().layers.find(x=>x.id===id).frame;
    if(!original.inherited)throw Error("新自由图层应该继承共享布局");
    await api.setFreeLayout(id,{x:13,y:51,width:34,height:23,angle:19},"3:4");
    const portrait=api.getFreeLayout(id,"3:4");
    if(portrait.inherited || portrait.frame.angle!==19)
      throw Error("3:4 独立布局没有生效");
    await api.setRatio("16:9");
    const wideInitial=api.getFreeLayout(id,"16:9");
    if(!wideInitial.inherited ||
       JSON.stringify(wideInitial.frame)!==JSON.stringify(originalBase))
      throw Error("16:9 未继承共享布局");
    const wide={x:58,y:14,width:25,height:30,angle:-21};
    await api.setFreeLayout(id,wide,"16:9");
    await api.changeFreeLayer(id,"free-select");
    if(!document.getElementById("freeRatioStatus").textContent.includes("独立布局"))
      throw Error("属性面板未标识当前画幅独立布局");
    const input=document.getElementById("freeFrameX");
    input.value="51";input.dispatchEvent(new Event("change",{bubbles:true}));
    for(let i=0;i<30 && api.getFreeLayout(id,"16:9").frame.x!==51;i++){
      await new Promise(resolve=>setTimeout(resolve,80));
    }
    if(api.getFreeLayout(id,"16:9").frame.x!==51)
      throw Error("位置输入框没有修改当前画幅");
    const finalWide=api.getFreeLayout(id,"16:9").frame;
    if(api.getFreeLayout(id,"3:4").frame.x!==13)
      throw Error("16:9 的修改覆盖了 3:4 布局");
    if(!api.getFreeLayout(id,"9:16").inherited)
      throw Error("9:16 应继续继承共享布局");

    // 显式推广为共享布局，再撤销，必须恢复两个独立比例。
    await api.applyFreeLayoutToAll(id);
    if(api.getFreeLayout(id,"3:4").frame.x!==51 ||
      !api.getFreeLayout(id,"3:4").inherited)
      throw Error("应用全部画幅失败："+JSON.stringify({
        portrait:api.getFreeLayout(id,"3:4"),
        wide:api.getFreeLayout(id,"16:9"),
        base:api.getFreeLayerList().layers.find(x=>x.id===id)
      }));
    await api.undo();
    if(api.getFreeLayout(id,"3:4").frame.x!==13 ||
      api.getFreeLayout(id,"16:9").frame.x!==51)
      throw Error("应用全部画幅的撤销失败");

    await api.resetFreeLayout(id);
    if(!api.getFreeLayout(id,"16:9").inherited)
      throw Error("重置后未恢复共享布局");
    await api.undo();
    if(api.getFreeLayout(id,"16:9").inherited)
      throw Error("画幅布局重置的撤销失败");

    await api.setRatio("3:4");
    const portraitPng=api.exportDataUrl();
    await api.setRatio("16:9");
    const widePng=api.exportDataUrl();
    const stored=await api.saveDesign(true);
    await api.loadDesign(stored.id);
    if(api.exportDataUrl()!==widePng)
      throw Error("16:9 保存重开后 PNG 不一致");
    if(api.getFreeLayout(id,"16:9").frame.x!==51)
      throw Error("16:9 位置未从设计文件恢复");
    await api.setRatio("3:4");
    if(api.exportDataUrl()!==portraitPng)
      throw Error("3:4 保存重开后 PNG 不一致");
    if(api.getFreeLayout(id,"3:4").frame.angle!==19)
      throw Error("3:4 旋转角度未从设计文件恢复");
    if(api.getFreeLayout(id,"9:16").inherited!==true)
      throw Error("未修改的画幅不应产生覆盖");
    const afterBase=api.getFreeLayerList().layers.find(x=>x.id===id).frame;
    if(["x","y","width","height","angle"].some(key=>afterBase[key]!==originalBase[key]))
      throw Error("旧版共享布局数值不应因画幅切换改变："+JSON.stringify({
        before:originalBase,after:afterBase
      }));
    return {ok:true,id,
      portrait:api.getFreeLayout(id,"3:4"),
      wide:api.getFreeLayout(id,"16:9"),
      inheritedNineBySixteen:api.getFreeLayout(id,"9:16").inherited,
      saveReloadBothRatios:true,undoResetAndApplyAll:true
    };
  },freeSetup.ellipse);
  await page.evaluate(async id=>{
    await window.__fabricPoc.changeFreeLayer(id,"free-select");
    const panel=document.getElementById("freeRatioGeometry");
    if(!panel || panel.hidden || !document.getElementById("freeRatioStatus").textContent.includes("独立布局"))
      throw Error("画幅几何控制面板未显示当前独立布局");
  },freeSetup.ellipse);
  await page.screenshot({path:join(outputFolder,"free-ratio-editor.png"),fullPage:true});

  const groupedPersistence=await page.evaluate(async(groupId)=>{
    const api=window.__fabricPoc;
    const oldPng=api.exportDataUrl();
    const saved=await api.saveDesign(true);
    await api.loadDesign(saved.id);
    const reloaded=api.getFreeLayerList();
    if(reloaded.groups.length!==1 || reloaded.groups[0].id!==groupId)
      throw Error("组合关系未从设计文件恢复");
    if(api.exportDataUrl()!==oldPng)
      throw Error("组合保存重开后的 PNG 不一致");
    return {savedId:saved.id,pngMatches:true};
  },freeSetup.group);
  await page.evaluate(async(groupId)=>{
    await window.__fabricPoc.ungroupFreeLayers(groupId);
  },freeSetup.group);
  const afterUngroup=await page.evaluate(()=>window.__fabricPoc.getFreeLayerList());
  if(afterUngroup.groups.length!==0 ||
     afterUngroup.layers.filter(x=>x.groupId).length!==0)
    throw Error("解组未恢复单层状态");
  const perRatioTextScale=await page.evaluate(async(id)=>{
    const api=window.__fabricPoc;
    await api.setRatio("3:4");
    const first=api.getObjectRect(id);
    const firstLayout=api.getFreeLayout(id,"3:4");
    await api.setRatio("16:9");
    const before=api.getObjectRect(id);
    const base=api.getFreeLayout(id,"16:9").frame;
    if(!first||!before)throw Error("解组后文本对象不存在");
    await api.setFreeLayout(id,{...base,scaleY:1.5},"16:9");
    const scaled=api.getObjectRect(id);
    if(Math.abs(scaled.height-before.height*1.5)>4)
      throw Error("16:9 自由文字缩放未实际生效："+JSON.stringify({before,scaled}));
    await api.setRatio("3:4");
    const after=api.getObjectRect(id);
    if(Math.abs(after.height-first.height)>2)
      throw Error("16:9 的自由文字缩放影响了 3:4");
    const portraitLayout=api.getFreeLayout(id,"3:4");
    if(JSON.stringify(portraitLayout)!==JSON.stringify(firstLayout))
      throw Error("16:9 字号缩放不应更改已有的 3:4 图层布局");
    await api.setRatio("16:9");
    const wide=api.getFreeLayout(id,"16:9").frame;
    if(wide.scaleY!==1.5)throw Error("16:9 字体缩放没有保存");
    await api.setRatio("3:4");
    return {ok:true,wideScale:wide.scaleY,unchangedPortrait:true};
  },freeSetup.text);

  await page.locator("#addFreeImage").setInputFiles(join(outputFolder,"fixture-avatar.png"));
  await page.waitForFunction(()=>window.__fabricPoc.getFreeLayerList().layers.length===4,
    null,{timeout:25000});
  const imageLayer=await page.evaluate(()=>{
    const item=window.__fabricPoc.getFreeLayerList().layers.find(x=>x.type==="image");
    return item?{id:item.id,assetId:item.assetId}:null;
  });
  if(!imageLayer?.assetId)throw Error("自由图片没有保存素材库标识");

  const savedFree=await page.evaluate(async()=>{
    const api=window.__fabricPoc;
    const pngBefore=api.exportDataUrl();
    const created=await api.saveDesign(true);
    await api.loadDesign(created.id);
    const pngAfter=api.exportDataUrl();
    if(pngBefore!==pngAfter)throw Error("自由图层保存重开的 PNG 不一致");
    if(api.getFreeLayerList().layers.length!==4)
      throw Error("重开后丢失自由图层");
    return {id:created.id,pngMatches:true};
  });
  await page.screenshot({path:join(outputFolder,"free-layers-editor.png"),fullPage:true});
  const freeDelete=await page.evaluate(async id=>{
    const api=window.__fabricPoc;
    await api.deleteFreeLayer(id);
    if(api.getFreeLayerList().layers.length!==3)throw Error("删除自由图层失败");
    await api.undo();
    if(api.getFreeLayerList().layers.length!==4)throw Error("删除操作撤销失败");
    await api.redo();
    if(api.getFreeLayerList().layers.length!==3)throw Error("删除操作重做失败");
    return true;
  },freeSetup.ellipse);
  const freeLayerChecks={
    ok:true,count:4,groupDragUpdatedMembers:shifted,
    groupReopenedPngMatches:groupedPersistence.pngMatches,
    ratioOverrides:ratioChecks,perRatioTextScale,
    ungroupPreservedLayers:true,imageAssetSaved:Boolean(imageLayer.assetId),
    savedId:savedFree.id,reopenedPngMatches:savedFree.pngMatches,
    deleteUndoRedo:freeDelete,
  };

  // 质量诊断端到端：预设保存、参考遮挡区、允许重叠及字体预检。
  const qualityChecks=await page.evaluate(async()=>{
    const api=window.__fabricPoc;
    await api.loadDesign("legacy");
    await api.setRatio("9:16");
    const noOverlay=api.exportDataUrl();
    api.setSafetyOverlay(true);
    const withOverlay=api.exportDataUrl();
    if(noOverlay!==withOverlay)
      throw Error("安全区参考线混入了导出的 PNG");
    if(!api.getState().safetyOverlay)
      throw Error("安全区叠加层开关没有生效");

    api.setSafetyProfile("vertical_video");
    if(api.getState().qualityProfile!=="vertical_video" ||
       !document.getElementById("safetyProfile").value.includes("vertical_video"))
      throw Error("安全区预设未正确应用");
    api.setPosition("account",80,56);
    const blocked=api.getQualityReport();
    if(!blocked.issues.some(item=>
      item.code==="UI_OVERLAY" && item.layerIds.includes("account")))
      throw Error("竖屏操作区遮挡没有被诊断出来");
    const fontCheck=await api.checkFonts();
    if(!Number.isInteger(fontCheck.checked)||fontCheck.checked<2)
      throw Error("完整字体检查没有覆盖标题和小标题");
    if(api.getQualityReport().glyphCoverageChecked!==true)
      throw Error("字体检查结果没有合并进质量报告");
    const saved=await api.saveDesign(true);
    await api.loadDesign(saved.id);
    if(api.getState().qualityProfile!=="vertical_video")
      throw Error("重新打开设计丢失安全区预设");
    if(api.getQualityReport().issues.every(item=>item.code!=="UI_OVERLAY"))
      throw Error("重开后参考遮挡区诊断异常");
    await api.setRatio("16:9");
    if(api.getState().qualityProfile!=="general")
      throw Error("16:9 应当继续使用通用安全区");
    await api.setRatio("9:16");
    if(api.getState().qualityProfile!=="vertical_video")
      throw Error("切换比例后安全区预设未恢复");
    return {
      profilePersisted:true,exportWithoutOverlay:true,
      overlayDetected:true,fontChecks:fontCheck.checked,
      reportStatus:blocked.status,
      savedId:saved.id
    };
  });
  await page.screenshot({path:join(outputFolder,"safety-zone-editor.png"),fullPage:true});

  const overlapChecks=await page.evaluate(async()=>{
    const api=window.__fabricPoc;
    await api.loadDesign("legacy");
    await api.setRatio("3:4");
    const first=await api.addFreeLayer("text");
    const second=await api.addFreeLayer("text");
    const original=api.getQualityReport();
    const overlapped=original.issues.find(issue=>
      issue.code==="LAYER_COLLISION" &&
      issue.layerIds.includes(first) && issue.layerIds.includes(second));
    if(!overlapped)
      throw Error("重叠自由文字未触发遮挡诊断");
    const qualityPanel=document.getElementById("qualityIssues");
    if(!qualityPanel.querySelector("button[data-quality-allow]"))
      throw Error("遮挡诊断没有人工确认入口");
    api.allowOverlap(first,second);
    const accepted=api.getQualityReport();
    if(accepted.issues.some(issue=>issue.id===overlapped.id))
      throw Error("允许重叠后依然报告同一碰撞");
    const stored=await api.saveDesign(true);
    await api.loadDesign(stored.id);
    if(api.getQualityReport().issues.some(issue=>issue.id===overlapped.id))
      throw Error("允许重叠关系在重新打开后失效");
    const savedPairs=api.getScene().quality.allowedByRatio["3:4"]||[];
    if(!savedPairs.some(pair=>pair.includes(first)&&pair.includes(second)))
      throw Error("当前画幅的允许重叠关系没有持久化");
    await api.setRatio("16:9");
    if(api.getQualityReport().issues.every(issue=>
      issue.code!=="LAYER_COLLISION" ||
      !issue.layerIds.includes(first) || !issue.layerIds.includes(second)))
      throw Error("3:4 的重叠确认不应屏蔽 16:9 的遮挡");
    await api.setRatio("3:4");
    const revoke=document.querySelector('#acknowledgmentList button[data-quality-revoke]');
    if(!revoke)throw Error("已确认重叠关系没有撤销入口");
    revoke.click();
    if(api.getQualityReport().issues.every(x=>x.id!==overlapped.id))
      throw Error("撤销重叠确认后未恢复碰撞提示");
    await api.undo();
    if(api.getQualityReport().issues.some(x=>x.id===overlapped.id))
      throw Error("撤销确认操作没有恢复已允许重叠状态");
    await api.deleteFreeLayer(second);
    if((api.getScene().quality.allowedByRatio["3:4"]||[]).some(pair=>pair.includes(second)))
      throw Error("删除自由图层后没有清理失效的重叠关系");
    await api.undo();
    if(!(api.getScene().quality.allowedByRatio["3:4"]||[]).some(pair=>pair.includes(second)))
      throw Error("图层删除撤销时没有恢复已确认的重叠关系");
    return {
      detectable:true,acknowledged:true,reopened:true,cleanupOnDelete:true,
      ratioScoped:true,revocableFromUi:true,undoRestoresAcknowledgment:true
    };
  });
  await page.evaluate(()=>window.__fabricPoc.setSafetyOverlay(false));

  // 使用必定不在字库内的未分配码点，验证缺字为硬错误且导出前生效。
  const glyphChecks=await page.evaluate(async()=>{
    const api=window.__fabricPoc;
    await api.loadDesign("legacy");
    await api.setRatio("3:4");
    await api.setContent({title:"复利思维\u0378"});
    const stamp=await api.checkFonts();
    const report=api.getQualityReport();
    const issue=report.issues.find(x=>
      x.code==="FONT_MISSING"&&x.layerIds.includes("title"));
    if(!issue || !issue.message.includes("\u0378") || !stamp.checked)
      throw Error("缺字预检未发现指定字符："+JSON.stringify(stamp));
    return {detected:true,issueCount:report.counts.error,checked:stamp.checked};
  });
  await page.locator("#export").click();
  await page.waitForFunction(()=>{
    const msg=document.getElementById("message").textContent;
    return msg.includes("质量预检发现");
  },null,{timeout:15000});
  const preventedExport=await page.locator("#message").innerText();
  if(!preventedExport.includes("质量预检"))
    throw Error("缺字场景未阻止导出");

  // 诊断报告使用独立 JSON 文件保存，不包含像素数据。
  const [download]=await Promise.all([
    page.waitForEvent("download",{timeout:15000}),
    page.locator("#downloadQualityReport").click()
  ]);
  await download.saveAs(join(outputFolder,"quality-report.json"));
  const downloadedName=download.suggestedFilename();
  if(!downloadedName.endsWith("_quality.json"))
    throw Error("质量报告文件命名异常："+downloadedName);
  const checkReport=JSON.parse((await (await import("node:fs/promises")).readFile(
    join(outputFolder,"quality-report.json"),"utf8"
  )));
  if(!checkReport.issues?.some(item=>item.code==="FONT_MISSING") ||
     checkReport.fontCoverageChecked!==true)
    throw Error("结构化质量报告丢失缺字诊断信息");

  await page.evaluate(()=>window.__fabricPoc.setContent({title:"复利思维"}));
  const qualityExportChecks={
    glyphErrorDetected:glyphChecks.detected,
    downloadBlockedByGlyph:true,
    reportExported:true,
    reportContainsGlyphError:true
  };

  const result={
    ok:failures.length===0,
    homepagePromoted:true,
    classicEditorAvailable:true,
    previousEditorBookmarkRedirects:true,
    fabricVersion:"7.4.0",
    pngCases:pngs.length,
    pngs,
    firstLayout:initial.layout,
    initialFonts:initial.fontIds,
    initialPositions:initial.positions,
    woff2:woff2Result,
    noBackendRendersAfterEditing:requests.filter(x=>x.startsWith("/api/render")||x.startsWith("/api/text-layers")).length===0,
    noAdditionalFontLoads:postEdits.metrics.fontRequests===beforeEdits.metrics.fontRequests,
    titleMoved:Boolean(postEdits.positions.title.x!=null),
    uploadedAssetsRendered: Boolean(imageAssetsLoaded),
    designLifecycle,
    autoLayouts, editHistory, layerChecks, snappingChecks, propertyChecks, freeLayerChecks,
    qualityChecks, overlapChecks, qualityExportChecks,
    allAutoLayoutsCollisionFree: autoLayouts.every(item=>item.warnings.length===0),
    requestsAfterEdits:requests,
    metrics:postEdits.metrics,
    elapsedMs:Date.now()-t0,
    consoleErrors:diagnostics.slice(0,10)
  };
  console.log("FABRIC_POC_RESULT="+JSON.stringify(result));
  if(!result.ok)process.exitCode=2;
} catch(error) {
  console.error("FABRIC_POC_ERROR",String(error),error.stack);
  process.exitCode=1;
} finally {
  await browser.close();
}
