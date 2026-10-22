import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import path from 'node:path';
const [base,output]=process.argv.slice(2);
if(!base||!output)throw Error('node tests/browser.mjs <baseurl> <output>');
await mkdir(output,{recursive:true});
const results=[],errors=[],consoleErrors=[],requests=[];
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--no-first-run','--disable-extensions','--force-color-profile=srgb']});
const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1,acceptDownloads:true});
const page=await context.newPage();
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
const state=()=>page.evaluate(()=>window.__coverEditor.controller.getSnapshot());
const doc=async()=>(await state()).document;
async function ready(){await page.waitForFunction(()=>!!window.__coverEditor);await page.evaluate(()=>window.__coverEditor.ready());await page.locator('.canvas-loading').waitFor({state:'hidden'});}
async function saved(){await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().saveStatus==='saved');}
async function check(name,fn){const start=Date.now();try{await fn();results.push({name,status:'PASS',ms:Date.now()-start});console.log('PASS',name);}catch(e){results.push({name,status:'FAIL',error:e.message});await page.screenshot({path:path.join(output,'failure.png')});throw e;}}
const layer=async(id='title')=>(await doc()).layers.find(l=>l.id===id);
async function chooseRatio(value){await page.getByRole('combobox',{name:'画布比例',exact:true}).click();await page.getByRole('option',{name:new RegExp('^'+value+' ')}).click();await page.waitForFunction(()=>document.activeElement===document.querySelector('.ratio-picker')&&!document.querySelector('[data-slot=select-content]'));}
async function zoomCanvas(value){const slider=page.getByRole('slider',{name:'画布缩放滑块',exact:true});await slider.press('Home');for(let i=0;i<Math.floor((value-5)/10);i++)await slider.press('PageUp');for(let i=0;i<(value-5)%10;i++)await slider.press('ArrowRight');await page.waitForFunction(value=>Number(document.querySelector('[data-testid=artboard]').dataset.scale)===value/100,value);}
async function expectDeleteDismissed(trigger,dialog){await dialog.waitFor({state:'hidden'});await page.mouse.move(500,140);await page.waitForTimeout(450);assert.equal(await trigger.evaluate(el=>el===document.activeElement),true,'dismissal lost keyboard focus');assert.equal(await page.locator('[data-slot=tooltip-content]').count(),0,'delete tooltip reopened after automatic focus restoration');}
try {
  await page.goto(base,{waitUntil:'networkidle'});await ready();
  const original=structuredClone(await doc());
  await check('M2 responsive layouts and full 16:9 fit',async()=>{
    for(const [width,height] of [[1366,768],[1440,900],[1920,1080]]){
      await page.setViewportSize({width,height});await page.getByRole('button',{name:'适应窗口',exact:true}).click();
      const a=await page.getByTestId('artboard').boundingBox(),v=await page.getByTestId('canvas-viewport').boundingBox();
      assert.ok(a.width>600&&a.height>330);assert.ok(Math.abs(a.width/a.height-16/9)<.002);
      assert.ok(a.x>=v.x&&a.y>=v.y&&a.x+a.width<=v.x+v.width+1&&a.y+a.height<=v.y+v.height+1,'canvas clipped');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'page horizontal overflow');
      for(const selector of ['.editor-header','.tool-sidebar','.resource-panel','.inspector-panel','.zoom-toolbar'])assert.ok(await page.locator(selector).isVisible());
      const caption=await page.locator('.canvas-caption').boundingBox(),zoom=await page.locator('.zoom-toolbar').boundingBox();assert.ok(caption&&caption.x+caption.width+8<=zoom.x,'zoom status hidden or overlaps toolbar');
      await page.screenshot({path:path.join(output,`M2-${width}x${height}.png`)});
    }
    const referenceContext=await browser.newContext({viewport:{width:1280,height:1052},deviceScaleFactor:1.25});
    const referencePage=await referenceContext.newPage();await referencePage.goto(base,{waitUntil:'networkidle'});await referencePage.waitForFunction(()=>!!window.__coverEditor);await referencePage.evaluate(()=>window.__coverEditor.ready());await referencePage.locator('.canvas-loading').waitFor({state:'hidden'});
    await referencePage.screenshot({path:path.join(output,'M2-reference-density.png')});await referenceContext.close();
    await page.setViewportSize({width:1440,height:900});
  });
  await check('shadcn ratio Select has true rectangle previews and isolated keyboard navigation',async()=>{
    const trigger=page.getByRole('combobox',{name:'画布比例',exact:true});assert.equal(await trigger.evaluate(el=>el.tagName),'BUTTON');
    await trigger.click();const options=page.getByRole('option');assert.equal(await options.count(),6);
    for(const [ratio,w,h] of [['16:9',1920,1080],['3:4',1080,1440],['9:16',1080,1920],['4:3',1440,1080],['4:5',1080,1350],['1:1',1080,1080]]){
      const shape=await page.getByRole('option',{name:new RegExp('^'+ratio+' ')}).locator('.ratio-rectangle').boundingBox();assert.ok(Math.abs(shape.width/shape.height-w/h)<.01,ratio+' rectangle ratio mismatch');
    }
    await page.locator('[data-slot=select-content]').evaluate(async el=>{await Promise.all(el.getAnimations().map(animation=>animation.finished));});
    await page.screenshot({path:path.join(output,'shadcn-ratio-menu.png')});
    const before=await doc(),selection=(await state()).selectedId;
    await page.keyboard.press('End');await page.keyboard.press('ArrowUp');assert.deepEqual(await doc(),before,'Select navigation moved a layer');
    await page.keyboard.press('Escape');assert.equal((await state()).selectedId,selection);assert.deepEqual(await doc(),before);
    await chooseRatio('9:16');assert.equal((await doc()).width,1080);assert.equal((await doc()).height,1920);
    await chooseRatio('16:9');assert.equal((await doc()).width,1920);assert.equal((await doc()).height,1080);
  });
  await check('shadcn tooltips replace native titles, support disabled controls and avoid viewport edges',async()=>{
    assert.equal(await page.locator('.editor-shell [title]').count(),0);
    for(const [label,expected] of [['本机存储','保存到本机'],['全屏编辑','全屏编辑'],['画布偏好设置','画布偏好设置'],['显示网格','显示网格']]){
      await page.getByRole('button',{name:label,exact:true}).hover();const tooltip=page.locator('[data-slot=tooltip-content]');await tooltip.waitFor({state:'visible'});
      assert.ok((await tooltip.innerText()).includes(expected));const box=await tooltip.boundingBox(),size=page.viewportSize();assert.ok(box.x>=7&&box.y>=7&&box.x+box.width<=size.width-7&&box.y+box.height<=size.height-7,label+' tooltip clipped');
      if(label==='本机存储')assert.equal(await tooltip.getAttribute('data-side'),'bottom');if(label==='全屏编辑')assert.equal(await tooltip.getAttribute('data-side'),'top');
      if(label==='本机存储')await page.screenshot({path:path.join(output,'shadcn-tooltip-edge.png')});
      await page.mouse.move(400,150,{steps:8});await tooltip.waitFor({state:'hidden'});
    }
    await page.locator('.button-group .disabled-tooltip-trigger').first().hover();await page.locator('[data-slot=tooltip-content]').waitFor({state:'visible'});assert.ok((await page.locator('[data-slot=tooltip-content]').innerText()).includes('重做'));await page.mouse.move(400,150,{steps:8});await page.locator('[data-slot=tooltip-content]').waitFor({state:'hidden'});
    await page.getByRole('button',{name:'预览',exact:true}).click();await page.getByRole('button',{name:'关闭对话框',exact:true}).hover();await page.locator('[data-slot=tooltip-content]').waitFor({state:'visible'});assert.ok((await page.locator('[data-slot=tooltip-content]').innerText()).includes('关闭对话框'));await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'全屏编辑',exact:true}).click();await page.waitForFunction(()=>!!document.fullscreenElement);
    await page.mouse.move(400,150);await page.getByRole('button',{name:'退出全屏',exact:true}).hover();const fullscreenTip=page.locator('[data-slot=tooltip-content]');await fullscreenTip.waitFor({state:'visible'});
    await fullscreenTip.evaluate(async el=>{await Promise.all(el.getAnimations().map(animation=>animation.finished));});
    assert.equal(await fullscreenTip.evaluate(el=>{const r=el.getBoundingClientRect();return document.fullscreenElement.contains(el)&&el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}),true,'fullscreen tooltip hidden behind top layer');
    await page.screenshot({path:path.join(output,'shadcn-tooltip-fullscreen.png')});await page.getByRole('button',{name:'退出全屏',exact:true}).click();await page.waitForFunction(()=>!document.fullscreenElement);
    await page.getByRole('button',{name:'本机存储',exact:true}).hover();await page.locator('[data-slot=tooltip-content]').waitFor({state:'visible'});assert.equal(await page.locator('[data-slot=tooltip-content]').evaluate(el=>!!el.closest('.canvas-workspace')),false,'tooltip host did not reset after fullscreen');await page.mouse.move(400,150,{steps:8});await page.locator('[data-slot=tooltip-content]').waitFor({state:'hidden'});
  });
  await check('compact zoom slider shows hover values and fullscreen restores its icon',async()=>{
    assert.equal(await page.locator('.zoom-toolbar input').count(),0);assert.equal(await page.getByRole('button',{name:/^(缩小画布|放大画布)$/}).count(),0);
    await page.getByRole('button',{name:'预览',exact:true}).focus();await page.mouse.move(400,150);await page.locator('[data-slot=tooltip-content]').waitFor({state:'hidden'});
    const slider=page.getByRole('slider',{name:'画布缩放滑块',exact:true});await slider.hover();await page.locator('[data-slot=tooltip-content]').waitFor();assert.equal(await page.locator('[data-slot=tooltip-content]').innerText(),Math.round(Number(await page.getByTestId('artboard').getAttribute('data-scale'))*100)+'%');
    const frame=structuredClone((await layer()).frame);await zoomCanvas(65);assert.deepEqual((await layer()).frame,frame);assert.match(await page.locator('.canvas-caption').innerText(),/自由缩放\s*·\s*65%/);assert.equal(await page.locator('[data-slot=tooltip-content]').innerText(),'65%');
    await page.screenshot({path:path.join(output,'zoom-slider-hover.png')});await page.getByRole('button',{name:'预览',exact:true}).focus();await page.mouse.move(400,150);await page.locator('[data-slot=tooltip-content]').waitFor({state:'hidden'});
    assert.equal(await page.locator('.fit-button').evaluate(el=>getComputedStyle(el).fontSize),'14px');
    const full=page.getByRole('button',{name:'全屏编辑',exact:true}),normalIcon=await full.locator('svg').innerHTML();await full.click();await page.waitForFunction(()=>!!document.fullscreenElement);const restore=page.getByRole('button',{name:'退出全屏',exact:true});await restore.waitFor();assert.notEqual(await restore.locator('svg').innerHTML(),normalIcon);assert.equal(await restore.getAttribute('aria-pressed'),'true');await restore.click();await page.waitForFunction(()=>!document.fullscreenElement);assert.equal(await full.locator('svg').innerHTML(),normalIcon);
    await full.click();await page.waitForFunction(()=>!!document.fullscreenElement);await page.evaluate(()=>document.exitFullscreen());await page.waitForFunction(()=>!document.fullscreenElement);await full.waitFor();assert.equal(await full.locator('svg').innerHTML(),normalIcon);
    await page.getByRole('button',{name:'适应窗口',exact:true}).click();assert.match(await page.locator('.canvas-caption').innerText(),/适应窗口\s*·\s*\d+%/);
  });
  await check('modal initial focus does not open close tooltips and keyboard focus stays contained',async()=>{
    for(const [label,name] of [['画布偏好设置','画布偏好设置'],['快捷键帮助','快捷键一览'],['预览','封面预览'],['导出封面','导出封面']]){
      await page.getByRole('button',{name:label,exact:true}).click();const dialog=page.locator('.modal');await dialog.waitFor();await page.mouse.move(400,150);await page.waitForTimeout(450);
      assert.equal(await page.locator('[data-slot=tooltip-content]').count(),0,name+' opened an automatic tooltip');
      assert.equal(await dialog.evaluate(el=>document.activeElement===el),true);
      await page.keyboard.press('Shift+Tab');assert.equal(await dialog.evaluate(el=>el.contains(document.activeElement)),true);
      await page.keyboard.press('Tab');assert.equal(await dialog.evaluate(el=>el.contains(document.activeElement)),true);
      await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});await page.mouse.move(400,150);await page.waitForTimeout(150);
    }
  });
  await check('save icon animates while saving, confirms success and recovers from failure',async()=>{
    await page.evaluate(()=>window.__coverEditor.controller.save());await saved();
    const button=page.getByRole('button',{name:'本机存储',exact:true});await button.click();
    await page.waitForFunction(()=>document.querySelector('.local-badge').dataset.feedback==='saving');assert.equal(await button.isDisabled(),true);
    assert.equal(await button.locator('svg').evaluate(el=>getComputedStyle(el).animationName),'save-spin');
    await page.screenshot({path:path.join(output,'save-icon-saving.png')});
    await page.waitForFunction(()=>document.querySelector('.local-badge').dataset.feedback==='saved');assert.equal(await button.isDisabled(),false);await button.locator('.save-glyph').evaluate(async el=>{await Promise.all(el.getAnimations().map(animation=>animation.finished));});await page.waitForFunction(()=>getComputedStyle(document.querySelector('.local-badge')).backgroundColor==='rgb(19, 132, 91)');await page.screenshot({path:path.join(output,'save-icon-success.png')});
    await page.route('**/api/cover-documents/**',route=>route.request().method()==='PUT'?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'保存动画验收：测试失败'})}):route.continue());
    await page.getByLabel('设计名称',{exact:true}).fill('组件交互验收');await button.click();await page.waitForFunction(()=>document.querySelector('.local-badge').dataset.feedback==='error');assert.ok(await page.locator('.save-error-banner').isVisible());await page.waitForFunction(()=>getComputedStyle(document.querySelector('.local-badge')).backgroundColor==='rgb(186, 26, 26)');await page.screenshot({path:path.join(output,'save-icon-error.png')});
    await page.unroute('**/api/cover-documents/**');await button.click();await saved();await page.waitForFunction(()=>document.querySelector('.local-badge').dataset.feedback==='saved');
  });
  await check('delete dismissal keeps focus without sticky tooltips and preserves hover/keyboard hints',async()=>{
    await page.getByRole('button',{name:'模板',exact:true}).click();const trigger=page.getByRole('button',{name:/^删除设计 /}).first(),dialog=page.getByRole('dialog',{name:'删除设计确认',exact:true}),before=structuredClone(await doc()),deletes=requests.filter(r=>r.method==='DELETE').length;
    for(const dismissal of ['cancel','escape','outside']){
      await trigger.hover();const tooltip=page.locator('[data-slot=tooltip-content]');await tooltip.waitFor({state:'visible'});assert.equal(await tooltip.innerText(),await trigger.getAttribute('aria-label'));
      await trigger.click();await dialog.waitFor();
      if(dismissal==='cancel')await dialog.getByRole('button',{name:'取消',exact:true}).click();else if(dismissal==='escape')await page.keyboard.press('Escape');else await page.mouse.click(500,140);
      await expectDeleteDismissed(trigger,dialog);if(dismissal==='cancel')await page.screenshot({path:path.join(output,'delete-tooltip-dismissed.png')});
    }
    await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab');assert.equal(await trigger.evaluate(el=>el===document.activeElement),true);await page.locator('[data-slot=tooltip-content]').waitFor({state:'visible'});
    await page.keyboard.press('Enter');await dialog.waitFor();await page.keyboard.press('Escape');await expectDeleteDismissed(trigger,dialog);
    assert.deepEqual(await doc(),before);assert.equal(requests.filter(r=>r.method==='DELETE').length,deletes,'cancel sent a delete request');await page.getByRole('button',{name:'图层',exact:true}).click();
  });
  await check('M3 drag coordinates at 25%, 50%, 100% with scroll and one undo command',async()=>{
    for(const zoom of ['25','50','100']){
      await zoomCanvas(Number(zoom));
      await page.getByTestId('hit-title').scrollIntoViewIfNeeded();
      const a=await page.getByTestId('hit-title').boundingBox(),before=await layer(),history=(await state()).historyLength;
      const scale=Number(zoom)/100,dx=44*scale,dy=32*scale;
      await page.keyboard.down('Alt');await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(a.x+a.width/2+dx,a.y+a.height/2+dy,{steps:12});
      await page.evaluate(()=>window.__coverEditor.controller.save()); // Saving a paused drag must not split history.
      await page.mouse.up();await page.keyboard.up('Alt');
      const after=await layer();assert.ok(Math.abs(after.frame.x-before.frame.x-44)<.15);assert.ok(Math.abs(after.frame.y-before.frame.y-32)<.15);
      assert.equal((await state()).historyLength,history+1);
      await page.keyboard.press('Control+z');assert.ok(Math.abs((await layer()).frame.x-before.frame.x)<.15);
      await page.keyboard.press('Control+Shift+z');assert.ok(Math.abs((await layer()).frame.x-after.frame.x)<.15);
    }
    await page.getByRole('button',{name:'适应窗口',exact:true}).click();
  });
  await check('M3 smart snapping, resizing, selection and layer state',async()=>{
    await page.getByTestId('hit-subtitle').click();assert.equal((await state()).selectedId,'subtitle');
    await page.getByTestId('layer-subtitle').getByLabel('锁定图层 大脑如何悄悄欺骗我们',{exact:true}).click();assert.equal((await layer('subtitle')).locked,true);assert.equal(await page.getByTestId('hit-subtitle').count(),0);
    await page.getByTestId('layer-subtitle').getByLabel('解锁图层 大脑如何悄悄欺骗我们',{exact:true}).click();
    await page.getByTestId('layer-subtitle').getByLabel('隐藏图层 大脑如何悄悄欺骗我们',{exact:true}).click();assert.equal(await page.locator('[data-art-layer=subtitle]').count(),0);
    await page.getByTestId('layer-subtitle').getByLabel('显示图层 大脑如何悄悄欺骗我们',{exact:true}).click();
    await page.getByTestId('layer-title').getByLabel('选择图层 认知的盲区',{exact:true}).click();
    await page.getByRole('button',{name:'对象水平居中',exact:true}).click();assert.equal((await layer()).frame.x,(1920-(await layer()).frame.width)/2);
    await page.evaluate(()=>window.__coverEditor.controller.change(d=>{const l=d.layers.find(l=>l.id==='title');l.frame.x=(d.width-l.frame.width)/2-60;}));
    const hit=await page.getByTestId('hit-title').boundingBox(),scale=Number(await page.getByTestId('artboard').getAttribute('data-scale'));
    await page.mouse.move(hit.x+hit.width/2,hit.y+hit.height/2);await page.mouse.down();await page.mouse.move(hit.x+hit.width/2+55*scale,hit.y+hit.height/2,{steps:8});
    assert.ok(await page.locator('.guide.vertical').isVisible(),'snapping guide not shown');assert.ok(Math.abs((await layer()).frame.x-(1920-(await layer()).frame.width)/2)<.1);await page.mouse.up();assert.equal(await page.locator('.guide').count(),0);
    await page.evaluate(()=>window.__coverEditor.controller.change(d=>{const l=d.layers.find(l=>l.id==='title');l.frame={x:400,y:300,width:480,height:160,rotation:0};l.fontSize=50;}));
    const before=await layer();const handle=page.getByTestId('resize-se');await handle.scrollIntoViewIfNeeded();const box=await handle.boundingBox();
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+50,box.y+box.height/2+20,{steps:10});await page.mouse.up();assert.ok((await layer()).fontSize>before.fontSize);
    const order=(await doc()).layers.map(l=>l.id);await page.getByRole('button',{name:'下移一层',exact:true}).click();assert.notDeepEqual((await doc()).layers.map(l=>l.id),order);
    await page.getByTestId('layer-title').dragTo(page.getByTestId('layer-subtitle'));assert.equal((await doc()).layers.findIndex(l=>l.id==='title'),(await doc()).layers.findIndex(l=>l.id==='subtitle')+1);
    await page.screenshot({path:path.join(output,'M3-layer-interactions.png')});
  });
  await check('M3 inline Chinese composition and undo/redo',async()=>{
    const previous=(await layer()).text;
    await page.getByTestId('hit-title').dblclick();const input=page.getByLabel('画布文字编辑',{exact:true});await input.waitFor();
    await input.dispatchEvent('compositionstart',{data:''});await input.fill('中文输入测试\n第二行');
    assert.equal((await layer()).text,previous,'composition was committed before compositionend');
    await page.keyboard.press('Enter');assert.ok(await input.isVisible());
    await input.dispatchEvent('compositionend',{data:'中文输入测试'});
    await input.fill('中文输入测试\n第二行');await page.screenshot({path:path.join(output,'M3-inline-composition.png')});
    await page.keyboard.press('Control+Enter');assert.equal((await layer()).text,'中文输入测试\n第二行');
    await page.keyboard.press('Control+z');assert.equal((await layer()).text,previous);
    await page.keyboard.press('Control+Shift+z');assert.equal((await layer()).text,'中文输入测试\n第二行');
  });
  await check('M4 actual font family previews, weight files and complete text styles',async()=>{
    assert.equal(await page.locator('.font-trigger>small').innerText(),'内置');await page.getByLabel('选择字体家族',{exact:true}).click();
    const sources=await page.locator('.font-results>button>span>small').allTextContents(),firstSystem=sources.findIndex(text=>text.startsWith('系统字体'));assert.ok(firstSystem>0);assert.ok(sources.slice(0,firstSystem).every(text=>text.startsWith('内置字体')));assert.ok(sources.slice(firstSystem).every(text=>!text.startsWith('内置字体')));
    await page.getByLabel('搜索字体',{exact:true}).fill('LXGWWenKai');
    const options=page.locator('.font-results>button');assert.ok(await options.count()>0);await options.first().locator('img').evaluate(img=>img.decode());
    await page.screenshot({path:path.join(output,'M4-font-picker.png')});await page.evaluate(()=>window.__testPreviousFont=window.__coverEditor.controller.getSnapshot().document.layers.find(l=>l.id==='title').fontId);await options.first().click();await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().document.layers.find(l=>l.id==='title').fontId!==window.__testPreviousFont,null,{timeout:180000});await ready();
    const fontData=await (await page.request.get(base+'/api/fonts')).json();const light=fontData.fonts.find(f=>f.family==='LXGWWenKai'&&f.weight===300&&!f.monospace);assert.ok(light);
    const weight=page.getByRole('combobox',{name:'字重',exact:true});assert.equal(await weight.evaluate(el=>el.tagName),'BUTTON');const selectedFont=(await layer()).fontId;await weight.click();const labels=await page.getByRole('option').allTextContents();assert.ok(labels.every(label=>!/(?:WOFF|TTF|OTF|TTC|OTC)/i.test(label)));assert.equal(new Set(labels).size,labels.length);const previousFrame=structuredClone((await layer()).frame);await page.keyboard.press('End');assert.deepEqual((await layer()).frame,previousFrame);await page.keyboard.press('Escape');assert.equal((await layer()).fontId,selectedFont);
    await weight.click();await page.getByRole('option',{name:light.variant.replace(/\s*·\s*(?:WOFF2?|TTF|OTF|TTC|OTC)$/i,''),exact:true}).click();await page.waitForFunction(fid=>window.__coverEditor.controller.getSnapshot().document.layers.find(l=>l.id==='title').fontId===fid,light.id,{timeout:180000});await ready();assert.equal((await layer()).fontId,light.id);
    await page.getByLabel('字号',{exact:true}).fill('88');await page.getByLabel('描边宽度',{exact:true}).fill('4');
    await page.getByLabel('文字颜色 #ffe338',{exact:true}).click();
    await page.getByText('高级排版设置',{exact:true}).click();await page.getByLabel('行高',{exact:true}).fill('1.2');await page.getByLabel('字距',{exact:true}).fill('4');
    await page.getByLabel('X 坐标',{exact:true}).fill('320');await page.getByLabel('Y 坐标',{exact:true}).fill('420');await page.getByLabel('宽度',{exact:true}).fill('1280');
    await page.getByLabel('图层透明度',{exact:true}).fill('90');await page.getByLabel('内容文本',{exact:true}).fill('认知的盲区\n中文字体预览');
    await page.getByText('投影详细设置',{exact:true}).click();await page.getByLabel('偏移 X',{exact:true}).fill('12');await page.getByLabel('偏移 Y',{exact:true}).fill('16');await page.getByLabel('模糊',{exact:true}).fill('30');await page.getByLabel('阴影透明度',{exact:true}).fill('65');
    const l=await layer();assert.equal(l.fontSize,88);assert.equal(l.strokeWidth,4);assert.equal(l.opacity,.9);assert.equal(l.color,'#ffe338');assert.equal(l.lineHeight,1.2);assert.equal(l.letterSpacing,4);
    assert.equal(l.shadow.x,12);assert.equal(l.shadow.y,16);assert.equal(l.shadow.blur,30);assert.equal(l.shadow.opacity,.65);
    assert.equal(await page.locator('[data-art-layer=title]>div').evaluate(el=>document.fonts.check('32px '+getComputedStyle(el).fontFamily)),true);
    await page.screenshot({path:path.join(output,'M4-font-and-properties.png')});
  });
  await check('inspector label alignment, distinct effect fields and scoped hover/focus borders',async()=>{
    const outside=await page.locator('.zoom-toolbar .zoom-slider').evaluate(el=>getComputedStyle(el).borderWidth);
    for(const [width,height] of [[1366,768],[1440,900],[1920,1080]]){
      await page.setViewportSize({width,height});
      const weight=await page.getByLabel('字重',{exact:true}).boundingBox(),size=await page.locator('.inspector-panel .number-stepper').filter({has:page.getByLabel('字号',{exact:true})}).boundingBox();
      assert.equal(weight.height,34);assert.equal(size.height,34);assert.ok(Math.abs(weight.y-size.y)<.1,'weight and size fields are misaligned');
    }
    await page.setViewportSize({width:1440,height:900});
    const effect=page.locator('.effect-card .number-stepper').first();
    assert.equal(await effect.evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(255, 255, 255)');
    assert.notEqual(await effect.evaluate(el=>getComputedStyle(el).backgroundColor),await effect.locator('xpath=ancestor::*[contains(@class,"effect-card")]').evaluate(el=>getComputedStyle(el).backgroundColor));
    for(const selector of ['.inspector-panel .number-stepper:has(input[aria-label="字号"])','.inspector-panel [role="combobox"][aria-label="字重"]','.inspector-panel .font-trigger','.inspector-panel textarea[aria-label="内容文本"]','.inspector-panel .effect-card .color-field','.inspector-panel .number-field:has(input[aria-label="图层透明度"])']){
      const field=page.locator(selector).first();await field.scrollIntoViewIfNeeded();await page.mouse.move(400,150);await page.waitForTimeout(170);
      const before=await field.evaluate(el=>({border:getComputedStyle(el).borderColor,height:el.getBoundingClientRect().height}));
      await field.hover();await page.waitForTimeout(170);
      const after=await field.evaluate(el=>({border:getComputedStyle(el).borderColor,height:el.getBoundingClientRect().height}));
      assert.notEqual(after.border,before.border,selector+' has no hover border');assert.equal(after.height,before.height,'hover changed field layout');
    }
    await page.getByLabel('字号',{exact:true}).focus();await page.waitForTimeout(170);
    assert.equal(await page.locator('.number-stepper').filter({has:page.getByLabel('字号',{exact:true})}).evaluate(el=>getComputedStyle(el).borderColor),'rgb(37, 99, 235)');
    await page.getByRole('button',{name:'预览',exact:true}).focus();
    assert.equal(await page.locator('.zoom-toolbar .zoom-slider').evaluate(el=>getComputedStyle(el).borderWidth),outside,'inspector styling leaked to workspace');
    assert.equal(await page.getByRole('link',{name:'下载 Web 字体 · WOFF2',exact:true}).count(),0);
    await page.getByLabel('字号',{exact:true}).scrollIntoViewIfNeeded();await page.mouse.move(400,150);await page.screenshot({path:path.join(output,'inspector-font-alignment.png')});
    await effect.scrollIntoViewIfNeeded();await effect.hover();await page.waitForTimeout(170);await page.screenshot({path:path.join(output,'inspector-effect-hover.png')});
    for(const label of ['字号','描边宽度','宽度','偏移 X']){
      const field=page.locator('.number-stepper').filter({has:page.getByLabel(label,{exact:true})});await field.scrollIntoViewIfNeeded();const outer=await field.boundingBox();
      for(const button of await field.locator('button').all()){await button.hover();const b=await button.boundingBox();assert.ok(b.x-outer.x>=3&&outer.x+outer.width-b.x-b.width>=3&&b.y-outer.y>=3&&outer.y+outer.height-b.y-b.height>=3,label+' stepper hover touches border');}
    }
    await page.getByRole('button',{name:'增大描边宽度',exact:true}).hover();await page.screenshot({path:path.join(output,'stepper-hover-inset.png')});
  });
  await check('bounded shadcn sliders, isolated keys and paused drag single undo',async()=>{
    await page.evaluate(()=>window.__coverEditor.controller.save());await saved();
    const before=await layer(),history=(await state()).historyLength;
    const slider=page.getByRole('slider',{name:'图层透明度滑块',exact:true});await slider.scrollIntoViewIfNeeded();
    const box=await page.locator('[data-slot=slider]').filter({has:slider}).boundingBox();
    await page.mouse.move(box.x+box.width*.45,box.y+box.height/2);await page.mouse.down();
    await page.waitForTimeout(620);await page.evaluate(()=>window.__coverEditor.controller.save());
    assert.equal((await state()).historyLength,history,'paused slider gesture split history');
    await page.mouse.move(box.x+box.width*.65,box.y+box.height/2,{steps:8});await page.mouse.up();
    assert.equal((await state()).historyLength,history+1);assert.ok((await layer()).opacity>.5&&(await layer()).opacity<.8);
    await page.getByRole('button',{name:'撤销 (Ctrl+Z)',exact:true}).click();assert.equal((await layer()).opacity,before.opacity);
    const frame=structuredClone((await layer()).frame);await slider.focus();await page.keyboard.press('Home');assert.equal((await layer()).opacity,0);
    await page.keyboard.press('End');assert.equal((await layer()).opacity,1);assert.deepEqual((await layer()).frame,frame,'slider arrow keys moved layer');
    await page.getByLabel('图层透明度',{exact:true}).fill('101');assert.equal((await layer()).opacity,1);await page.getByLabel('图层透明度',{exact:true}).press('Tab');
    await page.getByLabel('图层透明度',{exact:true}).fill(String(before.opacity*100));await page.getByLabel('图层透明度',{exact:true}).press('Tab');
    assert.equal(await page.locator('.inspector-panel [data-slot=slider]').count(),2);assert.equal(await page.getByRole('slider',{name:'宽度滑块',exact:true}).count(),0);const width=(await layer()).frame.width;await page.getByRole('button',{name:'增大宽度',exact:true}).click();assert.equal((await layer()).frame.width,width+1);await page.getByRole('button',{name:'减小宽度',exact:true}).click();assert.equal((await layer()).frame.width,width);
    await page.screenshot({path:path.join(output,'shadcn-properties-sliders.png')});
  });
  await check('adding and deleting text retains ready canvas and mounted interaction overlay',async()=>{
    await ready();await page.evaluate(()=>{
      window.__flashCount=0;window.__overlayBefore=document.querySelector('[data-testid=interaction-overlay]');
      window.__flashObserver=new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node instanceof Element&&(node.matches('.canvas-loading')||node.querySelector('.canvas-loading')))window.__flashCount++;});
      window.__flashObserver.observe(document.querySelector('.canvas-workspace'),{childList:true,subtree:true});
    });
    await page.getByRole('button',{name:'文字',exact:true}).click();await page.getByRole('button',{name:'添加大标题',exact:true}).click();
    await page.locator('.inspector-panel').getByRole('button',{name:'删除图层',exact:true}).click();
    assert.equal(await page.evaluate(()=>window.__flashCount),0);
    assert.equal(await page.evaluate(()=>window.__overlayBefore===document.querySelector('[data-testid=interaction-overlay]')),true);
    await page.evaluate(()=>window.__flashObserver.disconnect());await page.getByTestId('layer-title').locator('.layer-select').click();
  });
  await check('M3/M5 blank names, text reflow handles, repeated ratio changes and draft recovery',async()=>{
    const name=(await doc()).name;
    await page.getByLabel('设计名称',{exact:true}).fill('  ');await page.getByLabel('设计名称',{exact:true}).press('Tab');assert.equal((await doc()).name,name);assert.equal(await page.getByLabel('设计名称',{exact:true}).inputValue(),name);
    await page.getByLabel('内容文本',{exact:true}).fill('   ');assert.equal((await layer()).name,'文字');await page.getByLabel('内容文本',{exact:true}).fill('缩窄文字仍能点击末行');
    await page.getByLabel('Y 坐标',{exact:true}).fill('180');await page.getByLabel('宽度',{exact:true}).fill('300');
    async function assertCovered(){
      const l=await layer(),scale=Number(await page.getByTestId('artboard').getAttribute('data-scale'));
      const painted=await page.locator('[data-art-layer=title]>div').evaluate(el=>el.getBoundingClientRect().height);
      assert.ok(l.frame.height>=painted/scale-1,'text paint is outside hit frame');
      await page.getByTestId('hit-title').click({position:{x:20,y:painted-5}});assert.equal((await state()).selectedId,'title');
    }
    await assertCovered();
    await page.getByLabel('宽度',{exact:true}).fill('800');
    const e=await page.getByTestId('resize-e').boundingBox(),scale=Number(await page.getByTestId('artboard').getAttribute('data-scale'));
    await page.mouse.move(e.x+e.width/2,e.y+e.height/2);await page.mouse.down();await page.mouse.move(e.x+e.width/2-500*scale,e.y+e.height/2,{steps:12});await page.mouse.up();await assertCovered();
    const fontSize=(await layer()).fontSize;
    for(let i=0;i<5;i++){await chooseRatio('9:16');await chooseRatio('16:9');}
    assert.equal((await layer()).fontSize,fontSize);assert.ok((await doc()).layers.every(l=>l.fontSize>=8));
    await page.getByTestId('hit-title').dblclick();await page.getByLabel('画布文字编辑',{exact:true}).fill('   ');await page.keyboard.press('Control+Enter');assert.equal((await layer()).name,'文字');
    await page.getByLabel('内容文本',{exact:true}).fill('缩窄文字仍能点击末行');await page.getByLabel('内容文本',{exact:true}).press('Tab');await page.evaluate(()=>window.__coverEditor.controller.save());await saved();
    await page.reload();await ready();assert.equal((await layer()).fontSize,fontSize);await assertCovered();await page.screenshot({path:path.join(output,'M3-text-reflow.png')});
    const recoveryContext=await browser.newContext({viewport:{width:1440,height:900}}),recovery=await recoveryContext.newPage();
    await recovery.goto(base,{waitUntil:'networkidle'});await recovery.waitForFunction(()=>!!window.__coverEditor);
    const invalid=JSON.stringify({document:{...await doc(),name:''},savedKey:''});
    await recovery.evaluate(raw=>localStorage.setItem('cover-studio-v3-draft',raw),invalid);await recovery.reload();await recovery.getByRole('heading',{name:'暂时无法打开编辑器'}).waitFor();
    const downloadWait=recovery.waitForEvent('download');await recovery.getByRole('button',{name:'下载原始草稿',exact:true}).click();assert.ok(await downloadWait);
    await recovery.getByRole('button',{name:'打开已保存版本（保留草稿副本）',exact:true}).click();await recovery.waitForFunction(()=>!!window.__coverEditor);
    assert.equal(await recovery.evaluate(()=>JSON.parse(localStorage.getItem('cover-studio-v3-recovery')).rawDraft),invalid);
    await recovery.screenshot({path:path.join(output,'M5-recovered-draft.png')});await recoveryContext.close();
  });
  await check('M5 debounce, save failure/retry, reopen and copy template',async()=>{
    await page.getByLabel('设计名称',{exact:true}).fill('浏览器验收设计');await page.getByLabel('设计名称',{exact:true}).press('Tab');await saved();
    const before=await doc();await page.reload();await ready();assert.deepEqual((await doc()).layers,before.layers);assert.equal((await doc()).id,before.id);
    await page.route('**/api/cover-documents/**',route=>route.request().method()==='PUT'?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'测试保存失败'})}):route.continue());
    await page.getByLabel('设计名称',{exact:true}).fill('保存失败后恢复');await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().saveStatus==='error');assert.ok(await page.locator('.save-error-banner').isVisible());
    await page.screenshot({path:path.join(output,'M5-save-failure.png')});await page.unroute('**/api/cover-documents/**');await page.locator('.save-error-banner').getByRole('button',{name:'重试保存'}).click();await saved();
    const originalId=(await doc()).id;
    await page.getByRole('button',{name:'模板',exact:true}).click();await page.getByRole('button',{name:'另存副本',exact:true}).click();await page.waitForFunction(id=>window.__coverEditor.controller.getSnapshot().document.id!==id&&window.__coverEditor.controller.getSnapshot().saveStatus==='saved',originalId);
    assert.notEqual((await doc()).id,originalId);
    await page.getByRole('button',{name:'刷新本机设计库',exact:true}).click();await page.locator('.saved-design').filter({hasText:'保存失败后恢复'}).filter({hasNotText:'副本'}).click();await page.waitForFunction(id=>window.__coverEditor.controller.getSnapshot().document.id===id,originalId);await ready();assert.equal((await doc()).id,originalId);
    await page.screenshot({path:path.join(output,'M5-templates.png')});
  });
  await check('M5 legacy migration keeps assets and pixel positions',async()=>{
    await page.getByRole('button',{name:'模板',exact:true}).click();await page.locator('.saved-design').filter({hasText:'经典默认模板'}).click();
    await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().document.sourceScene?.schemaVersion===2);await ready();
    const migrated=await doc();assert.equal(migrated.width,1920);assert.equal(migrated.layers.find(l=>l.id==='title').frame.x,384);assert.ok(migrated.layers.find(l=>l.id==='background').assetId.match(/^[a-f0-9]{64}\.png$/));
    await page.evaluate(()=>window.__coverEditor.controller.save());await saved();await page.reload();await ready();assert.equal((await doc()).sourceScene.schemaVersion,2);
    await page.getByRole('button',{name:'模板',exact:true}).click();await page.locator('.saved-design').filter({hasText:'自动折行迁移基准'}).click();
    await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().document.layers.some(l=>l.id==='custom-abcdef123456'));await ready();
    const text=(await doc()).layers.find(l=>l.id==='custom-abcdef123456');
    const scale=Number(await page.getByTestId('artboard').getAttribute('data-scale'));
    const painted=await page.locator('[data-art-layer=custom-abcdef123456]>div').evaluate(el=>el.getBoundingClientRect().height);
    assert.ok(text.frame.height>400);assert.ok(text.frame.height>=painted/scale-1,'wrapped text not fully covered by selection');
    const target=page.getByTestId('hit-custom-abcdef123456');await target.click({position:{x:10,y:Math.min(painted-10,200)}});assert.equal((await state()).selectedId,'custom-abcdef123456');
    await page.screenshot({path:path.join(output,'M5-wrapped-migration.png')});
  });
  await check('M5 rotated legacy frames retain the actual Fabric visual bounds',async()=>{
    const list=await (await page.request.get(base+'/api/designs')).json(),legacyId=list.designs.find(d=>d.name==='旋转迁移基准').id;
    const old=await context.newPage();await old.goto(base+'/fabric-legacy',{waitUntil:'domcontentloaded'});await old.waitForFunction(()=>window.__fabricPoc?.getState().ready);
    await old.evaluate(id=>window.__fabricPoc.loadDesign(id),legacyId);
    const rects=await old.evaluate(()=>Object.fromEntries(['custom-111111111111','custom-222222222222'].map(id=>[id,window.__fabricPoc.getObjectRect(id)])));await old.close();
    await page.getByRole('button',{name:'模板',exact:true}).click();await page.locator('.saved-design').filter({hasText:'旋转迁移基准'}).click();
    await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().document.layers.some(l=>l.id==='custom-111111111111'));await ready();
    const a=await page.getByTestId('artboard').boundingBox(),scale=Number(await page.getByTestId('artboard').getAttribute('data-scale'));
    for(const [id,expected] of Object.entries(rects)){
      const actual=await page.locator(`[data-art-layer="${id}"]`).boundingBox();
      assert.ok(Math.abs((actual.x-a.x)/scale-expected.x)<.1,`${id} rotated x mismatch`);assert.ok(Math.abs((actual.y-a.y)/scale-expected.y)<.1,`${id} rotated y mismatch`);
      assert.ok(Math.abs(actual.width/scale-expected.width)<.1);assert.ok(Math.abs(actual.height/scale-expected.height)<.1);
    }
    await page.screenshot({path:path.join(output,'M5-rotated-migration.png')});
  });
  await check('M3/M4 upload, shape/text creation, shortcuts, pan and clean preview',async()=>{
    await page.getByRole('button',{name:'素材',exact:true}).click();await page.getByLabel('上传图片文件',{exact:true}).setInputFiles(path.join(output,'fixture-upload.png'));
    await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().document.layers.some(l=>l.name==='fixture-upload.png'));
    const image=(await doc()).layers.find(l=>l.name==='fixture-upload.png');assert.equal(image.type,'image');assert.ok(image.assetId.match(/^[a-f0-9]{64}\.png$/));
    await page.getByRole('button',{name:'矩形',exact:true}).click();assert.equal((await doc()).layers.at(-1).type,'rect');
    await page.keyboard.press('Control+d');const copied=(await state()).selectedId;assert.ok(copied);await page.keyboard.press('Delete');assert.equal((await doc()).layers.some(l=>l.id===copied),false);
    await page.getByRole('button',{name:'文字',exact:true}).click();await page.getByRole('button',{name:'添加大标题',exact:true}).click();assert.equal((await doc()).layers.at(-1).type,'text');
    await page.getByRole('button',{name:'背景',exact:true}).click();await page.getByLabel('上传图片文件',{exact:true}).setInputFiles(path.join(output,'fixture-upload.png'));
    await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().document.layers.find(l=>l.id==='background').assetId.length>30);assert.equal((await layer('background')).locked,true);
    await zoomCanvas(100);const viewport=page.getByTestId('canvas-viewport');const before=await viewport.evaluate(el=>({x:el.scrollLeft,y:el.scrollTop}));
    const v=await viewport.boundingBox();await viewport.click({position:{x:8,y:8}});await page.keyboard.down('Space');await page.mouse.move(v.x+v.width/2,v.y+v.height/2);await page.mouse.down();await page.mouse.move(v.x+v.width/2-100,v.y+v.height/2-60,{steps:10});await page.mouse.up();await page.keyboard.up('Space');
    const after=await viewport.evaluate(el=>({x:el.scrollLeft,y:el.scrollTop}));assert.ok(after.x>before.x||after.y>before.y,'Space pan did not scroll');
    await page.getByRole('button',{name:'适应窗口',exact:true}).click();await page.getByRole('button',{name:'预览',exact:true}).click();await page.getByRole('dialog',{name:'封面预览'}).waitFor();await page.screenshot({path:path.join(output,'M3-clean-preview.png')});await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
  });
  await check('image circle masks and rectangle/ellipse image fills persist and resize',async()=>{
    await page.getByRole('button',{name:'素材',exact:true}).click();await page.getByLabel('上传图片文件',{exact:true}).setInputFiles(path.join(output,'fixture-upload.png'));
    await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().document.layers.at(-1).type==='image');await ready();
    const id=(await state()).selectedId;
    await page.getByRole('combobox',{name:'图片形状',exact:true}).click();await page.getByRole('option',{name:'圆形',exact:true}).click();
    let l=await layer(id);assert.equal(l.imageShape,'circle');assert.equal(l.frame.width,l.frame.height);
    await page.getByLabel('宽度',{exact:true}).fill('360');assert.equal((await layer(id)).frame.height,360);
    assert.equal(await page.locator(`[data-art-layer="${id}"]`).evaluate(el=>getComputedStyle(el).borderRadius),'50%');
    const handle=page.getByTestId('resize-e');await handle.scrollIntoViewIfNeeded();const h=await handle.boundingBox();
    await page.mouse.move(h.x+h.width/2,h.y+h.height/2);await page.mouse.down();await page.mouse.move(h.x+h.width/2+35,h.y+h.height/2,{steps:8});await page.mouse.up();
    l=await layer(id);assert.equal(l.frame.width,l.frame.height);assert.ok(l.frame.width>360);
    for(const [type,label] of [['rect','矩形'],['ellipse','椭圆']]){
      await page.getByRole('button',{name:'素材',exact:true}).click();await page.getByRole('button',{name:label,exact:true}).click();
      await page.getByLabel('图片填充文件',{exact:true}).setInputFiles(path.join(output,'fixture-upload.png'));
      await page.waitForFunction(()=>!!window.__coverEditor.controller.getSnapshot().document.layers.at(-1).assetId);await ready();
      const filled=(await doc()).layers.at(-1);assert.equal(filled.type,type);assert.equal(await page.locator(`[data-art-layer="${filled.id}"]>img`).count(),1);
      if(type==='rect'){await page.getByRole('button',{name:'移除图片填充',exact:true}).click();assert.equal((await doc()).layers.at(-1).assetId,'');await page.getByLabel('图片填充文件',{exact:true}).setInputFiles(path.join(output,'fixture-upload.png'));await page.waitForFunction(()=>!!window.__coverEditor.controller.getSnapshot().document.layers.at(-1).assetId);}
    }
    await page.evaluate(()=>window.__coverEditor.controller.save());await saved();const before=structuredClone((await doc()).layers);
    await page.reload();await ready();assert.deepEqual((await doc()).layers,before);
    await page.getByRole('button',{name:'图层',exact:true}).click();await page.getByTestId('layer-'+id).locator('.layer-select').click();
    const diameter=(await layer(id)).frame.width;for(let i=0;i<3;i++){await chooseRatio('9:16');assert.equal((await layer(id)).frame.width,diameter);assert.equal((await layer(id)).frame.width,(await layer(id)).frame.height);await chooseRatio('16:9');assert.equal((await layer(id)).frame.width,diameter);}
    await page.screenshot({path:path.join(output,'image-circle-and-shape-fills.png')});
  });
  await check('pending image fill survives font selection within the same document',async()=>{
    const rect=(await doc()).layers.find(l=>l.type==='rect'&&l.assetId),title=(await doc()).layers.find(l=>l.id==='title');assert.ok(rect&&title);
    await page.getByTestId('layer-'+rect.id).locator('.layer-select').click();await page.getByRole('button',{name:'移除图片填充',exact:true}).click();
    const uploaded=await page.request.post(base+'/api/designs/assets',{multipart:{file:{name:'fixture.png',mimeType:'image/png',buffer:await readFile(path.join(output,'fixture-upload.png'))},kind:'layer'}});
    assert.equal(uploaded.status(),201);const assetPayload=await uploaded.json();
    let release,arrived;const hold=new Promise(resolve=>release=resolve),pending=new Promise(resolve=>arrived=resolve);
    await page.route('**/api/designs/assets',async route=>{arrived();await hold;await route.fulfill({status:201,contentType:'application/json',body:JSON.stringify(assetPayload)});});
    await page.getByLabel('图片填充文件',{exact:true}).setInputFiles(path.join(output,'fixture-upload.png'));await pending;
    await page.getByTestId('layer-title').locator('.layer-select').click();await page.getByLabel('选择字体家族',{exact:true}).click();await page.locator('.font-results>button.chosen').click();await page.locator('.toast').filter({hasText:'字体已切换'}).waitFor();
    release();await page.waitForFunction(id=>!!window.__coverEditor.controller.getSnapshot().document.layers.find(l=>l.id===id).assetId,rect.id);await page.unroute('**/api/designs/assets');
    assert.equal((await layer(rect.id)).assetId,rect.assetId);assert.equal((await state()).selectedId,'title');
  });
  await check('complete template save/apply/delete and saved design deletion without recreation',async()=>{
    await page.evaluate(()=>window.__coverEditor.controller.save());await saved();const originalId=(await doc()).id,source=structuredClone((await doc()).layers);
    await page.getByRole('button',{name:'模板',exact:true}).click();await page.getByRole('button',{name:'保存为新模板',exact:true}).click();
    await page.getByLabel('模板名称',{exact:true}).fill('完整图片填充模板');await page.getByRole('button',{name:'保存模板',exact:true}).click();
    const template=page.locator('.saved-template').filter({hasText:'完整图片填充模板'});await template.waitFor();
    const thumbnail=template.locator('.template-thumbnail');await expectReadyThumbnail();
    async function expectReadyThumbnail(){await thumbnail.locator('[data-testid=cover-artwork]').waitFor();assert.equal(await thumbnail.getAttribute('aria-busy'),'false');}
    const titlePreview=await thumbnail.locator('[data-art-layer=title]').innerText();
    await page.evaluate(()=>window.__coverEditor.controller.change(d=>{d.layers.find(l=>l.id==='title').text='当前封面临时修改';}));assert.equal(await thumbnail.locator('[data-art-layer=title]').innerText(),titlePreview,'thumbnail changed with current design');await page.evaluate(()=>window.__coverEditor.controller.undo());
    assert.equal(await thumbnail.locator('[data-testid=interaction-overlay]').count(),0);
    await page.screenshot({path:path.join(output,'template-thumbnail-snapshot.png')});await template.click();
    await page.waitForFunction(id=>window.__coverEditor.controller.getSnapshot().document.id!==id,originalId);await page.evaluate(()=>window.__coverEditor.controller.save());await saved();
    const created=await doc();assert.notEqual(created.id,originalId);assert.deepEqual(created.layers,source);assert.equal(await page.getByRole('heading',{name:'模板与设计'}).isVisible(),true);
    const templateDelete=page.getByRole('button',{name:'删除模板 完整图片填充模板',exact:true});await templateDelete.click();const confirm=page.getByRole('dialog',{name:'删除模板确认',exact:true});await confirm.waitFor();await confirm.evaluate(el=>Promise.all(el.getAnimations().map(animation=>animation.finished)));assert.equal(await page.locator('.modal-backdrop').count(),0);const confirmBox=await confirm.boundingBox(),viewport=page.viewportSize();assert.ok(confirmBox.width<=220&&confirmBox.x>=7&&confirmBox.x+confirmBox.width<=viewport.width-7);await page.screenshot({path:path.join(output,'template-delete-popover.png')});await page.getByRole('button',{name:'取消',exact:true}).click();await expectDeleteDismissed(templateDelete,confirm);assert.equal(await template.count(),1);
    await page.route('**/api/cover-templates/**',route=>route.request().method()==='DELETE'?route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:'模板版本冲突验收'})}):route.continue());
    await page.getByRole('button',{name:'删除模板 完整图片填充模板',exact:true}).click();await page.getByRole('button',{name:'确认删除',exact:true}).click();await confirm.getByRole('alert').waitFor();assert.equal(await template.count(),1);await page.unroute('**/api/cover-templates/**');
    await page.route('**/api/cover-templates',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'删除后的列表刷新失败验收'})}));
    const deletion=page.waitForResponse(response=>response.request().method()==='DELETE'&&response.url().includes('/api/cover-templates/'));await page.getByRole('button',{name:'确认删除',exact:true}).click();assert.equal(await page.getByRole('button',{name:'删除模板 完整图片填充模板',exact:true,includeHidden:true}).getAttribute('aria-busy'),'true');await deletion;await template.waitFor({state:'hidden'});
    await page.locator('.toast').filter({hasText:'已删除，但设计库刷新失败'}).waitFor();await confirm.waitFor({state:'hidden'});await page.unroute('**/api/cover-templates');
    await page.getByRole('button',{name:'删除设计 '+created.name,exact:true}).click();await page.getByRole('button',{name:'确认删除',exact:true}).click();
    await page.waitForFunction(()=>window.__coverEditor.controller.getSnapshot().document.id===null&&window.__coverEditor.controller.getSnapshot().document.layers.length===0);
    await page.waitForTimeout(1000);const entries=(await (await page.request.get(base+'/api/cover-documents')).json()).documents;
    assert.equal(entries.some(d=>d.id===created.id),false,'deleted design was recreated');assert.ok(entries.some(d=>d.id===originalId));
    for(const l of source.filter(l=>l.assetId&&!l.assetId.startsWith('builtin:')))assert.equal((await page.request.get(base+'/api/designs/assets/'+l.assetId)).status(),200);
    await page.screenshot({path:path.join(output,'template-save-and-design-delete.png')});
    await page.locator('.resource-content').getByRole('button',{name:'新建设计',exact:true}).click();assert.equal(await page.getByRole('heading',{name:'模板与设计'}).isVisible(),true,'new design unexpectedly switched menu');await ready();
  });
  await check('design library refresh animates and recovers from errors',async()=>{
    await page.getByRole('button',{name:'模板',exact:true}).click();const refresh=page.getByRole('button',{name:'刷新本机设计库',exact:true});await refresh.click();assert.equal(await refresh.getAttribute('aria-busy'),'true');assert.equal(await refresh.locator('svg').evaluate(el=>getComputedStyle(el).animationName),'save-spin');
    await page.waitForFunction(()=>document.querySelector('.refresh-library').dataset.state==='done');await page.screenshot({path:path.join(output,'template-library-refreshed.png')});
    await page.route('**/api/cover-templates',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'设计库刷新测试失败'})}));await refresh.click();await page.locator('.resource-error').waitFor();assert.equal(await refresh.getAttribute('data-state'),'error');await page.unroute('**/api/cover-templates');await refresh.click();await page.waitForFunction(()=>document.querySelector('.refresh-library').dataset.state==='done');
  });
  await check('web fonts are actual WOFF2 and automatically loaded without a download action',async()=>{
    const fonts=(await (await page.request.get(base+'/api/fonts')).json()).fonts;
    const ttf=fonts.find(f=>f.source==='local'&&f.format==='TTF');assert.ok(ttf);assert.equal(ttf.webFormat,'WOFF2');
    const response=await page.request.get(base+'/api/cover-font?id='+encodeURIComponent(ttf.id));assert.equal(response.status(),200);assert.equal((await response.body()).subarray(0,4).toString(),'wOF2');assert.ok(response.headers()['content-type'].includes('font/woff2'));
    const download=await page.request.get(base+'/api/cover-font?id='+encodeURIComponent(ttf.id)+'&download=1');assert.ok(download.headers()['content-disposition'].includes('.woff2'));
    await page.getByRole('button',{name:'图层',exact:true}).click();await page.getByTestId('layer-title').locator('.layer-select').click();assert.equal(await page.getByRole('link',{name:'下载 Web 字体 · WOFF2',exact:true}).count(),0);assert.equal(await page.locator('[data-art-layer=title]>div').evaluate(el=>document.fonts.check('32px '+getComputedStyle(el).fontFamily)),true);
  });
  await check('M5 actual PNG/JPEG export and shared-picture browser baseline',async()=>{
    const exportDoc=structuredClone(original);exportDoc.name='正式导出基准';exportDoc.layers.find(l=>l.id==='title').strokeWidth=4;
    exportDoc.layers.find(l=>l.id==='title').letterSpacing=4;exportDoc.layers.find(l=>l.id==='title').fontSize=112;
    exportDoc.layers.find(l=>l.id==='title').shadow={enabled:true,color:'#001a42',opacity:.75,blur:24,x:8,y:12};
    const fonts=(await (await page.request.get(base+'/api/fonts')).json()).fonts;exportDoc.layers.find(l=>l.id==='title').fontId=fonts.find(f=>f.family==='LXGWWenKai'&&f.weight===400&&!f.monospace).id;
    const assetResponse=await page.evaluate(async base64=>{const blob=await(await fetch('data:image/png;base64,'+base64)).blob();const fd=new FormData();fd.set('file',blob,'fixture.png');fd.set('kind','layer');return(await(await fetch('/api/designs/assets',{method:'POST',body:fd})).json()).asset.id;},(await readFile(path.join(output,'fixture-upload.png'))).toString('base64'));
    for(const [i,type] of ['image','rect','ellipse'].entries()){
      const l=structuredClone(exportDoc.layers[0]);l.id='export-fill-'+type;l.name=type;l.type=type;l.locked=false;l.assetId=assetResponse;l.darkness=0;l.strokeWidth=type==='rect'?6:0;l.stroke='#ffffff';l.frame={x:40+i*350,y:50,width:280,height:280,rotation:type==='rect'?12:0};if(type==='image')l.imageShape='circle';exportDoc.layers.push(l);
    }
    await page.evaluate(async d=>{await window.__coverEditor.controller.replace(d);await window.__coverEditor.controller.save();},exportDoc);await ready();
    const frozen=await doc();await writeFile(path.join(output,'export-document.json'),JSON.stringify(frozen,null,2));
    const clean=await context.newPage();await clean.setViewportSize({width:1920,height:1080});await clean.goto(base+'/artwork/'+frozen.id,{waitUntil:'networkidle'});await clean.waitForFunction(()=>window.__coverArtworkReady);
    assert.equal(await clean.locator('[data-testid=interaction-overlay]').count(),0);await clean.screenshot({path:path.join(output,'browser-artwork.png')});await clean.close();
    for(const format of ['png','jpeg']){
      await page.getByRole('button',{name:'导出封面',exact:true}).click();await page.getByLabel('导出格式',{exact:true}).selectOption(format);
      const wait=page.waitForEvent('download',{timeout:180000});await page.getByRole('button',{name:'下载 '+format.toUpperCase(),exact:true}).click();const download=await wait;await download.saveAs(path.join(output,'formal.'+(format==='jpeg'?'jpg':'png')));
      await page.getByRole('dialog',{name:'导出封面'}).waitFor({state:'hidden',timeout:180000});
    }
    const png=await readFile(path.join(output,'formal.png'));assert.equal(png.readUInt32BE(16),1920);assert.equal(png.readUInt32BE(20),1080);
    await page.screenshot({path:path.join(output,'M5-export-success.png')});
  });
  await check('M6 clean runtime and zero edit-triggered backend rendering',async()=>{
    assert.deepEqual(errors,[]);assert.equal(requests.filter(r=>r.method==='POST'&&/\/api\/(render|text-layers|account-layer)/.test(r.url)).length,0);
    assert.deepEqual(consoleErrors.filter(e=>!e.includes('503')&&!e.includes('409')),[]);
  });
} finally {
  await writeFile(path.join(output,'browser-results.json'),JSON.stringify({results,errors,consoleErrors},null,2));await browser.close();
}
