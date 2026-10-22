import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {WarningCircle} from '@phosphor-icons/react';
import {CoverArtwork} from '../CoverArtwork';
import {CoverDocument} from '../model';
import {prepareArtwork} from '../fonts';

/** Render the saved template snapshot, independent of the document being edited. */
export function TemplateThumbnail({id,revision,name}:{id:string;revision:number;name:string}) {
  const host=useRef<HTMLDivElement>(null);
  const [width,setWidth]=useState(0),[document,setDocument]=useState<CoverDocument|null>(null),[error,setError]=useState('');
  useLayoutEffect(()=>{
    const observer=new ResizeObserver(entries=>setWidth(entries[0].contentRect.width));
    observer.observe(host.current!);return ()=>observer.disconnect();
  },[]);
  useEffect(()=>{
    let active=true;const abort=new AbortController();setDocument(null);setError('');
    void (async()=>{
      const response=await fetch('/api/cover-templates/'+encodeURIComponent(id),{signal:AbortSignal.any([abort.signal,AbortSignal.timeout(30000)])});
      const data=await response.json();if(!response.ok)throw Error(data.error||'模板预览加载失败');
      await prepareArtwork(data.document);if(active)setDocument(data.document);
    })().catch(error=>{if(active)setError(error instanceof Error?error.message:String(error));});
    return ()=>{active=false;abort.abort();};
  },[id,revision]);
  const scale=document?Math.min(width/document.width,112/document.height):0;
  return <div ref={host} className="template-thumbnail" role="img" aria-label={'模板封面预览 '+name} aria-busy={!document&&!error}>
    {document&&width>0?<div className="thumbnail-frame" style={{width:document.width*scale,height:document.height*scale}}><div style={{width:document.width,height:document.height,transform:`scale(${scale})`,transformOrigin:'0 0'}}><CoverArtwork document={document}/></div></div>:
      error?<span className="thumbnail-error"><WarningCircle size={20}/><span>预览暂不可用</span></span>:<span className="thumbnail-loading">正在加载封面…</span>}
  </div>;
}
