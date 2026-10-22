import {useEffect,useState,useSyncExternalStore,useRef} from 'react';
import {X,DownloadSimple,CheckCircle,WarningCircle,Keyboard,SlidersHorizontal} from '@phosphor-icons/react';
import {DocumentController,EditorSnapshot,RECOVERY_KEY} from './controller';
import {CoverDocument,FontCatalog,FontEntry,Layer,clone,createLayer,duplicateLayer,newDocument,reorderLayer} from './model';
import {CoverArtwork} from './CoverArtwork';
import {loadFont,prepareArtwork,artworkResources,artworkIsReady,checkFontCoverage,measureTextLayer,fontFamily} from './fonts';
import {migrateScene} from './migration';
import {EditorHeader} from './components/EditorHeader';
import {ToolSidebar,Tool} from './components/ToolSidebar';
import {ResourcePanel,DesignSummary} from './components/ResourcePanel';
import {CanvasWorkspace} from './components/CanvasWorkspace';
import {InspectorPanel} from './components/InspectorPanel';
import {IconButton} from './components/controls';

export async function jsonRequest(url:string,options:RequestInit={}) {
  const response=await fetch(url,{...options,signal:options.signal||AbortSignal.timeout(30000)});
  const data=await response.json();if(!response.ok)throw Error(data.error||`请求失败 (${response.status})`);return data;
}
function defaultFont(catalog:FontCatalog) {
  return catalog.fonts.find(f=>f.family==='AlimamaShuHeiTi'&&f.format==='WOFF2')?.id||catalog.defaults.local||catalog.defaults.title;
}
type Modal='export'|'preview'|'help'|'settings'|'save-template'|null;
const modalTitles={export:'导出封面',preview:'封面预览',help:'快捷键一览',settings:'画布偏好设置','save-template':'保存为模板'};
export function Editor({controller,catalog:initialCatalog}:{controller:DocumentController;catalog:FontCatalog}) {
  const snapshot=useSyncExternalStore(controller.subscribe,controller.getSnapshot);
  const doc=snapshot.document,selected=doc.layers.find(l=>l.id===snapshot.selectedId);
  const [catalog,setCatalog]=useState(initialCatalog),[tool,setTool]=useState<Tool>('layers');
  const [snap,setSnap]=useState(true),[grid,setGrid]=useState(false),[ready,setReady]=useState(false);
  const [modal,setModal]=useState<Modal>(null),[format,setFormat]=useState<'png'|'jpeg'>('png'),[busy,setBusy]=useState(false);
  const [toast,setToast]=useState<{text:string;error:boolean}|null>(null),[designs,setDesigns]=useState<DesignSummary[]>([]),[legacyDesigns,setLegacyDesigns]=useState<DesignSummary[]>([]);
  const [templates,setTemplates]=useState<DesignSummary[]>([]),[templateName,setTemplateName]=useState('');
  const fontRequest=useRef(0),documentEpoch=useRef(0);
  const previewScale=Math.min(900/doc.width,600/doc.height,(window.innerWidth-100)/doc.width,(window.innerHeight-160)/doc.height);
  const thumbnailScale=Math.min(360/doc.width,240/doc.height);
  const notify=(text:string,error=false)=>setToast({text,error});
  const run=(task:Promise<unknown>)=>{void task.catch(e=>notify(e.message||String(e),true));};
  const resourceKey=JSON.stringify(artworkResources(doc));
  useEffect(()=>{let active=true;setReady(artworkIsReady(doc));prepareArtwork(doc).then(()=>{if(active)setReady(true);}).catch(e=>{if(active)notify(e.message,true);});return ()=>{active=false;};},[resourceKey]);
  useEffect(()=>{if(toast&&!toast.error){const id=setTimeout(()=>setToast(null),4500);return ()=>clearTimeout(id);}},[toast]);
  useEffect(()=>{
    if(!modal)return;
    const previous=document.activeElement as HTMLElement|null;
    const dialog=document.querySelector<HTMLElement>('.modal')!;
    (dialog.querySelector<HTMLElement>('[data-autofocus]')??dialog).focus();
    return ()=>previous?.focus();
  },[modal]);
  useEffect(()=>{
    const dialog=document.querySelector<HTMLElement>('.modal');
    if(dialog&&!dialog.contains(document.activeElement))dialog.focus();
  },[busy]);
  function modalKeyboard(e:React.KeyboardEvent<HTMLElement>){
    if(e.key==='Escape'&&!busy){e.preventDefault();setModal(null);}
    if(e.key==='Tab'){
      const dialog=e.currentTarget,elements=Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled)')).filter(el=>el.getClientRects().length>0),first=elements[0],last=elements.at(-1);
      if(document.activeElement===dialog){e.preventDefault();(e.shiftKey?last:first)?.focus();}
      else if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
    }
  }
  async function refreshDesigns(){const [a,b,c]=await Promise.all([jsonRequest('/api/cover-documents'),jsonRequest('/api/designs'),jsonRequest('/api/cover-templates')]);setDesigns(a.documents);setLegacyDesigns(b.designs);setTemplates(c.templates);}
  useEffect(()=>{run(refreshDesigns());},[doc.id,doc.revision]);
  useEffect(()=>{
    const onUnload=(e:BeforeUnloadEvent)=>{if(controller.dirty()){e.preventDefault();e.returnValue='';}};
    const keyboard=(e:KeyboardEvent)=>{
      if(e.isComposing||e.defaultPrevented||(e.target as HTMLElement).closest('[role="combobox"],[role="listbox"],[role="option"],[role="slider"]'))return;
      const input=(e.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"]');
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();run(controller.save());return;}
      if(input||modal)return;
      const current=controller.getSnapshot(),layer=current.document.layers.find(l=>l.id===current.selectedId);
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();if(e.shiftKey)controller.redo();else controller.undo();}
      else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();controller.redo();}
      else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='d'){e.preventDefault();copyLayer();}
      else if(['Delete','Backspace'].includes(e.key)){e.preventDefault();deleteLayer();}
      else if(e.key==='Escape')controller.select(null);
      else if(layer&&!layer.locked&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){
        e.preventDefault();const step=e.shiftKey?10:1;controller.change(d=>{const l=d.layers.find(l=>l.id===layer.id)!;l.frame.x+=e.key==='ArrowLeft'?-step:e.key==='ArrowRight'?step:0;l.frame.y+=e.key==='ArrowUp'?-step:e.key==='ArrowDown'?step:0;},false);controller.scheduleCommit();
      }else if(layer&&!layer.locked&&(e.ctrlKey||e.metaKey)&&['[',']'].includes(e.key)){e.preventDefault();moveOrder(e.key===']'?1:-1);}
    };
    window.addEventListener('beforeunload',onUnload);window.addEventListener('keydown',keyboard);
    return ()=>{window.removeEventListener('beforeunload',onUnload);window.removeEventListener('keydown',keyboard);};
  },[controller,modal,snapshot.selectedId]);
  function patch(values:Partial<Layer>,continuous=false) {
    if(!selected||selected.locked)return;
    controller.change(d=>{const l=d.layers.find(l=>l.id===selected.id)!,oldWidth=l.frame.width,oldHeight=l.frame.height;Object.assign(l,values);
      if(l.type==='image'&&l.imageShape==='circle'){
        const diameter=values.imageShape==='circle'?Math.min(oldWidth,oldHeight):l.frame.width!==oldWidth?l.frame.width:l.frame.height!==oldHeight?l.frame.height:l.frame.width;
        if(values.imageShape==='circle'){l.frame.x+=(oldWidth-diameter)/2;l.frame.y+=(oldHeight-diameter)/2;}
        l.frame.width=diameter;l.frame.height=diameter;
      }
      if(l.type==='text'){
        if(['fontId','fontSize','lineHeight','letterSpacing','text'].some(k=>k in values)||l.frame.width!==oldWidth)l.frame.height=measureTextLayer(l);
        else if(l.frame.height!==oldHeight){l.textScaleY=Math.max(.1,Math.min(10,l.frame.height/measureTextLayer({...l,textScaleY:1})));l.frame.height=measureTextLayer(l);}
      }
    },!continuous);
    if(continuous)controller.scheduleCommit();
  }
  async function changeFont(font:FontEntry) {
    const id=selected?.id;if(!id||selected?.locked)return;
    const request=++fontRequest.current;
    notify('正在加载字体 '+(font.family||font.name)+'…');
    await loadFont(font.id);
    if(request!==fontRequest.current)return;
    controller.change(d=>{const l=d.layers.find(l=>l.id===id);if(l&&!l.locked){l.fontId=font.id;l.fontWeight=font.weight??400;l.frame.height=measureTextLayer(l);}});
    notify('字体已切换。');
  }
  function copyLayer(){const id=controller.getSnapshot().selectedId;if(!id)return;let newId:string|null=null;controller.change(d=>{newId=duplicateLayer(d,id);});if(newId)controller.select(newId);}
  function deleteLayer(){const id=controller.getSnapshot().selectedId;const l=controller.getSnapshot().document.layers.find(l=>l.id===id);if(!l||l.locked)return;controller.change(d=>{d.layers=d.layers.filter(l=>l.id!==id);});controller.select(null);}
  function moveOrder(delta:number){const id=controller.getSnapshot().selectedId;if(!id)return;controller.change(d=>reorderLayer(d,id,d.layers.findIndex(l=>l.id===id)+delta));}
  function addLayer(type:Layer['type']) {
    if(doc.layers.length>=60){notify('每个封面最多支持 60 个图层。',true);return;}
    const fontId=defaultFont(catalog);
    const layer=createLayer(type,fontId,{fontWeight:catalog.fonts.find(f=>f.id===fontId)?.weight??400});
    if(type!=='text'){layer.frame={x:doc.width*.3,y:doc.height*.3,width:doc.width*.25,height:doc.height*.25,rotation:0};layer.color='#2563eb';}
    else {layer.frame.x=(doc.width-layer.frame.width)/2;layer.frame.y=(doc.height-layer.frame.height)/2;}
    controller.change(d=>d.layers.push(layer));controller.select(layer.id);setTool('layers');
  }
  async function uploadAsset(file:File,background=false) {
    if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>18*1024*1024)throw Error('请上传 18 MB 以内的 PNG、JPEG 或 WebP。');
    const fd=new FormData();fd.set('file',file);fd.set('kind',background?'background':'layer');
    return jsonRequest('/api/designs/assets',{method:'POST',body:fd});
  }
  async function fillImage(file:File) {
    const id=selected?.id,context=documentEpoch.current;
    if(!id||selected?.locked||selected?.type==='text')return;
    const data=await uploadAsset(file);
    if(context!==documentEpoch.current)return;
    controller.change(d=>{const layer=d.layers.find(l=>l.id===id);if(layer&&!layer.locked&&layer.type!=='text')layer.assetId=data.asset.id;});
    notify('图片填充已更新。');
  }
  async function upload(file:File,background:boolean) {
    const context=documentEpoch.current,data=await uploadAsset(file,background);
    if(context!==documentEpoch.current)return;
    const doc=controller.getSnapshot().document;
    const layer=createLayer('image','',{assetId:data.asset.id,name:Array.from(file.name).slice(0,70).join(''),
      frame:background?{x:0,y:0,width:doc.width,height:doc.height,rotation:0}:{x:doc.width*.25,y:doc.height*.25,width:doc.width*.5,height:doc.height*.5,rotation:0}});
    if(background){layer.id='background';layer.locked=true;controller.change(d=>{d.layers=d.layers.filter(l=>l.id!=='background');d.layers.unshift(layer);});}
    else {if(doc.layers.length>=60)throw Error('每个封面最多支持 60 个图层。');controller.change(d=>d.layers.push(layer));}
    controller.select(layer.id);notify('图片已导入本机素材库。');
  }
  async function openDesign(id:string,legacy=false) {
    let next:CoverDocument;
    if(legacy){
      const {scene}=await jsonRequest('/api/cover-migration/'+encodeURIComponent(id));
      const fontIds=new Set<string>([...Object.values(scene.fontRefs) as string[],...scene.extras.layers.filter((l:Layer)=>l.type==='text').map((l:Layer)=>l.fontId)]);
      await Promise.all([...fontIds].map(fid=>loadFont(fid)));
      const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d')!;
      next=migrateScene(scene,(text,fid,size,spacing)=>{ctx.font=`${size}px "${fontFamily(fid)}"`;return ctx.measureText(text).width+Math.max(0,Array.from(text).length-1)*spacing;},measureTextLayer);
    }else next=(await jsonRequest('/api/cover-documents/'+id)).document;
    await prepareArtwork(next);fontRequest.current++;documentEpoch.current++;await controller.replace(next,!legacy);fontRequest.current++;documentEpoch.current++;notify(legacy?'旧模板已迁移为独立文档，原模板保留。':'已打开 '+next.name);
  }
  async function newDesign(theme='noir') {
    const fontId=defaultFont(catalog);
    const next=newDocument(fontId,catalog.fonts.find(f=>f.id===fontId)?.weight??400);
    if(theme==='tech'){next.name='科技洞察 - 封面设计';next.layers[0].assetId='builtin:tech';}
    fontRequest.current++;documentEpoch.current++;await controller.replace(next);fontRequest.current++;documentEpoch.current++;
  }
  async function copyDesign(){const next=clone(controller.getSnapshot().document);next.id=null;next.revision=0;next.updatedAt=null;next.name=Array.from(next.name).slice(0,67).join('')+' 副本';fontRequest.current++;documentEpoch.current++;await controller.replace(next,false,false);fontRequest.current++;documentEpoch.current++;await controller.save();notify('已另存完整设计副本。');}
  async function saveTemplate(){
    if(busy)return;const name=templateName.trim();if(!name){notify('请输入模板名称。',true);return;}
    setBusy(true);
    try{const next=clone(controller.getSnapshot().document);next.id=null;next.revision=0;next.updatedAt=null;next.name=name;
      await jsonRequest('/api/cover-templates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(next)});
      await refreshDesigns();setModal(null);notify('已保存完整模板，可重复创建新设计。');
    }finally{setBusy(false);}
  }
  async function applyTemplate(id:string){
    const next=(await jsonRequest('/api/cover-templates/'+id)).document as CoverDocument;
    next.id=null;next.revision=0;next.updatedAt=null;await prepareArtwork(next);
    fontRequest.current++;documentEpoch.current++;await controller.replace(next);fontRequest.current++;documentEpoch.current++;notify('已从模板创建独立设计。');
  }
  async function deleteEntry(entry:DesignSummary,template:boolean){
    let revision=entry.revision;
    const deletingCurrent=!template&&controller.getSnapshot().document.id===entry.id;
    if(deletingCurrent){await controller.save();revision=controller.getSnapshot().document.revision;}
    await Promise.all([jsonRequest((template?'/api/cover-templates/':'/api/cover-documents/')+entry.id,{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision})}),new Promise(resolve=>setTimeout(resolve,350))]);
    if(template)setTemplates(items=>items.filter(item=>item.id!==entry.id));
    else setDesigns(items=>items.filter(item=>item.id!==entry.id));
    if(deletingCurrent){
      fontRequest.current++;documentEpoch.current++;
      const empty=newDocument(defaultFont(catalog));empty.name='未命名设计';empty.layers=[];
      await controller.replace(empty,false,false,false);fontRequest.current++;documentEpoch.current++;
    }
    try{await refreshDesigns();notify(template?'模板已删除。':'设计已删除，图片素材仍保留。');}
    catch(error){notify((template?'模板':'设计')+'已删除，但设计库刷新失败，请点击刷新本机设计库重试。'+(error instanceof Error?error.message:String(error)),true);}
  }
  async function exportImage() {
    if(busy)return;setBusy(true);
    try{
      const frozen=clone(controller.getSnapshot().document);await prepareArtwork(frozen);await checkFontCoverage(frozen);
      const response=await fetch('/api/cover-export?format='+format,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(frozen),signal:AbortSignal.timeout(180000)});
      if(!response.ok)throw Error((await response.json()).error||'导出失败');
      const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=frozen.name.replace(/[<>:"/\\|?*]/g,'_')+'.'+(format==='jpeg'?'jpg':'png');link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
      setModal(null);notify(`已导出 ${frozen.width}×${frozen.height} ${format.toUpperCase()} 封面。`);
    }finally{setBusy(false);}
  }
  return <div className="editor-shell">
    <EditorHeader controller={controller} snapshot={snapshot} onExport={()=>setModal('export')} onPreview={()=>setModal('preview')} onGrid={()=>setGrid(v=>!v)} grid={grid} busy={busy}/>
    <div className="editor-body"><ToolSidebar tool={tool} onTool={setTool} onHelp={()=>setModal('help')} onSettings={()=>setModal('settings')}/>
      <ResourcePanel tool={tool} controller={controller} snapshot={snapshot} fonts={catalog.fonts} onAdd={addLayer} onUpload={(f,b)=>run(upload(f,b))} onOpen={(id,l)=>run(openDesign(id,l))} onNew={theme=>run(newDesign(theme))} onCopy={()=>run(copyDesign())} designs={designs} legacyDesigns={legacyDesigns} onRefresh={refreshDesigns} templates={templates} onSaveTemplate={()=>{setTemplateName(doc.name);setModal('save-template');}} onApplyTemplate={id=>run(applyTemplate(id))} onDeleteEntry={deleteEntry}/>
      <CanvasWorkspace controller={controller} snapshot={snapshot} snap={snap} grid={grid} onSnap={()=>setSnap(v=>!v)} onGrid={()=>setGrid(v=>!v)} onDuplicate={copyLayer} onDelete={deleteLayer} ready={ready}/>
      <InspectorPanel layer={selected} document={doc} fonts={catalog.fonts} patch={patch} onFont={f=>run(changeFont(f))} onRefresh={()=>run(jsonRequest('/api/fonts').then(setCatalog))} onDuplicate={copyLayer} onDelete={deleteLayer} onOrder={moveOrder} onImageFile={file=>run(fillImage(file))} onBegin={controller.begin} onCommit={controller.commit}/>
    </div>
    <footer className="editor-footer"><span>画布尺寸 {doc.width} × {doc.height} px <b>·</b> 逻辑像素 <b>·</b> sRGB</span><span>按住空格拖动画布 <b>·</b> 双击文本图层即可编辑 <b>·</b><button onClick={()=>setModal('help')}>快捷键一览</button></span></footer>
    {snapshot.saveStatus==='error'&&<div className="save-error-banner" role="alert"><WarningCircle size={18}/>{snapshot.saveError}<button onClick={()=>run(controller.save())}>重试保存</button><button onClick={()=>run(copyDesign())}>另存副本</button></div>}
    {toast&&<div role={toast.error?'alert':'status'} className={'toast'+(toast.error?' error':'')}>{toast.error?<WarningCircle size={20}/>:<CheckCircle size={20}/>}<span>{toast.text}</span><IconButton icon={X} label="关闭提示" onClick={()=>setToast(null)}/></div>}
    {modal&&<div className="modal-backdrop" onPointerDown={e=>{if(e.target===e.currentTarget&&!busy)setModal(null);}}><section role="dialog" aria-modal="true" tabIndex={-1} onKeyDown={modalKeyboard} aria-label={modalTitles[modal]} className={'modal '+(modal==='preview'?'preview-modal':'')}>
      <div className="modal-heading"><h2>{modalTitles[modal]}</h2><IconButton icon={X} label="关闭对话框" disabled={busy} onClick={()=>setModal(null)}/></div>
      {modal==='save-template'&&<form onSubmit={e=>{e.preventDefault();run(saveTemplate());}}><label className="stack-field"><span>模板名称</span><input data-autofocus aria-label="模板名称" value={templateName} maxLength={70} disabled={busy} onChange={e=>setTemplateName(e.target.value)}/></label><p className="muted">保存背景、文字、字体、图层位置和所有样式。使用模板时会创建独立设计。</p><button className="primary-button export-confirm" disabled={busy||!templateName.trim()}>{busy?'正在保存…':'保存模板'}</button></form>}
      {modal==='export'&&<><div className="export-thumbnail" style={{height:doc.height*thumbnailScale}}><div style={{position:'absolute',left:(360-doc.width*thumbnailScale)/2,width:doc.width,height:doc.height,transform:`scale(${thumbnailScale})`,transformOrigin:'0 0'}}><CoverArtwork document={doc}/></div></div><p>{doc.width} × {doc.height} 像素 · 高清原图</p><label className="stack-field"><span>图片格式</span><select aria-label="导出格式" value={format} onChange={e=>setFormat(e.target.value as 'png'|'jpeg')}><option value="png">PNG · 无损画质</option><option value="jpeg">JPEG · 高质量</option></select></label><p className="muted">导出前将检查字形和素材。图片仅包含封面内容。</p><button className="primary-button export-confirm" disabled={busy||!ready} onClick={()=>run(exportImage())}><DownloadSimple size={18}/>{busy?'正在渲染原图…':'下载 '+format.toUpperCase()}</button></>}
      {modal==='preview'&&<div className="clean-preview" style={{width:doc.width*previewScale,height:doc.height*previewScale}}><div style={{width:doc.width,height:doc.height,transform:`scale(${previewScale})`,transformOrigin:'0 0'}}><CoverArtwork document={doc}/></div></div>}
      {modal==='help'&&<div className="shortcut-list">{[['撤销','Ctrl / ⌘ + Z'],['重做','Ctrl + Shift + Z / Ctrl + Y'],['立即保存','Ctrl / ⌘ + S'],['复制选中图层','Ctrl / ⌘ + D'],['删除选中图层','Delete / Backspace'],['移动 1 / 10 像素','方向键 / Shift + 方向键'],['上移 / 下移图层','Ctrl + ] / ['],['画布缩放 / 适应','Ctrl + + / − / 0'],['平移画布','空格 + 拖动 / 鼠标中键'],['临时关闭吸附','拖动时按住 Alt'],['编辑文字','双击文字 · Ctrl + Enter 完成'],['退出文字编辑','Esc 取消 · 点击外部完成']].map(([a,b])=><div key={a}><span>{a}</span><kbd>{b}</kbd></div>)}</div>}
      {modal==='settings'&&<div className="settings-content"><label className="check-field"><input type="checkbox" checked={snap} onChange={e=>setSnap(e.target.checked)}/>智能吸附与参考线</label><label className="check-field"><input type="checkbox" checked={grid} onChange={e=>setGrid(e.target.checked)}/>显示辅助网格</label><p className="muted">封面与图层坐标以原图像素保存；缩放只改变显示大小。</p>{localStorage.getItem(RECOVERY_KEY)&&<button className="secondary-button" onClick={()=>{const url=URL.createObjectURL(new Blob([localStorage.getItem(RECOVERY_KEY)!],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='cover-studio-recovered-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}}>下载保留的异常草稿</button>}<a href="/fabric-legacy" target="_blank" rel="noreferrer">打开原 Fabric 编辑器</a><a href="/legacy" target="_blank" rel="noreferrer">打开经典 Pillow 编辑器</a></div>}
    </section></div>}
  </div>;
}
