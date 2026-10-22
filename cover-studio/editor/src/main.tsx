import React from 'react';
import {createRoot} from 'react-dom/client';
import {Editor,jsonRequest} from './Editor';
import {DocumentController,DRAFT_KEY,RECOVERY_KEY} from './controller';
import {newDocument,contentKey,FontCatalog,CoverDocument} from './model';
import {prepareArtwork} from './fonts';
import {CoverArtwork} from './CoverArtwork';
import {TooltipProvider} from './components/ui/tooltip';
import './editor.css';

declare global {interface Window {__coverEditor:{controller:DocumentController;ready:()=>Promise<void>};__coverArtworkReady?:boolean;}}
const root=createRoot(document.getElementById('root')!);
async function start(recover=false){
  root.render(<div className="boot-screen">正在打开 Cover Studio…</div>);
  if(location.pathname.startsWith('/artwork/')){
    const doc=(await jsonRequest('/api/cover-documents/'+location.pathname.split('/').at(-1))).document as CoverDocument;
    await prepareArtwork(doc);root.render(<CoverArtwork document={doc}/>);
    requestAnimationFrame(()=>requestAnimationFrame(()=>{window.__coverArtworkReady=true;}));return;
  }
  const catalog=await jsonRequest('/api/fonts') as FontCatalog;
  const defaultId=catalog.fonts.find(f=>f.family==='AlimamaShuHeiTi'&&f.format==='WOFF2')?.id||catalog.defaults.local||catalog.defaults.title;
  let doc=newDocument(defaultId,catalog.fonts.find(f=>f.id===defaultId)?.weight??400),saved=false;
  const raw=localStorage.getItem(DRAFT_KEY);
  if(raw&&!recover){
    const draft=JSON.parse(raw);
    doc=(await jsonRequest('/api/cover-validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(draft.document)})).document as CoverDocument;
    if(doc.id&&contentKey(doc)===draft.savedKey){doc=(await jsonRequest('/api/cover-documents/'+doc.id)).document;saved=true;}
  }else{
    const {documents}=await jsonRequest('/api/cover-documents');
    if(documents.length){doc=(await jsonRequest('/api/cover-documents/'+documents[0].id)).document;saved=true;}
    if(recover&&raw){
      localStorage.setItem(RECOVERY_KEY,JSON.stringify({capturedAt:new Date().toISOString(),rawDraft:raw,previousRecovery:localStorage.getItem(RECOVERY_KEY)}));
      localStorage.removeItem(DRAFT_KEY);
    }
  }
  const controller=new DocumentController(doc,fetch,localStorage,saved);
  window.__coverEditor={controller,ready:()=>prepareArtwork(controller.getSnapshot().document)};
  root.render(<TooltipProvider delayDuration={350} skipDelayDuration={120}><Editor controller={controller} catalog={catalog}/></TooltipProvider>);
}
function BootError({error}:{error:Error}){
  const [busy,setBusy]=React.useState(false),[failure,setFailure]=React.useState('');
  const raw=localStorage.getItem(DRAFT_KEY);
  return <div className="boot-screen"><h1>暂时无法打开编辑器</h1><p>{failure||error.message}</p><button onClick={()=>location.reload()}>重试</button>
    {raw&&<><button disabled={busy} onClick={()=>{setBusy(true);void start(true).catch(e=>{setBusy(false);setFailure(e.message);root.render(<BootError error={e}/>);});}}>打开已保存版本（保留草稿副本）</button><button onClick={()=>{const url=URL.createObjectURL(new Blob([raw],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='cover-studio-original-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}}>下载原始草稿</button></>}
    <p>本地草稿仍保留。也可以打开 <a href="/fabric-legacy" target="_blank" rel="noreferrer">原编辑器</a> 或 <a href="/legacy" target="_blank" rel="noreferrer">经典编辑器</a>。</p></div>;
}
start().catch(error=>root.render(<BootError error={error}/>));
