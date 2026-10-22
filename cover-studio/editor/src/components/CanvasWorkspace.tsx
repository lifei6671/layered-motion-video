import {useEffect,useRef,useState,useLayoutEffect} from 'react';
import {FrameCorners,ArrowsOut,ArrowsIn} from '@phosphor-icons/react';
import {CoverArtwork} from '../CoverArtwork';
import {DocumentController,EditorSnapshot} from '../controller';
import {clamp} from '../model';
import {InteractionOverlay} from './InteractionOverlay';
import {FloatingToolbar,SelectionToolbar} from './FloatingToolbar';
import {IconButton} from './controls';
import {Slider} from './ui/slider';
import {Tooltip,TooltipTrigger,TooltipContent} from './ui/tooltip';
type Props={controller:DocumentController;snapshot:EditorSnapshot;snap:boolean;grid:boolean;
  onSnap:()=>void;onGrid:()=>void;onDuplicate:()=>void;onDelete:()=>void;ready:boolean;};
export function CanvasWorkspace({controller,snapshot,snap,grid,onSnap,onGrid,onDuplicate,onDelete,ready}:Props) {
  const viewport=useRef<HTMLDivElement>(null),artboard=useRef<HTMLDivElement>(null),workspace=useRef<HTMLElement>(null);
  const pan=useRef<{x:number;y:number;left:number;top:number}|null>(null);
  const [size,setSize]=useState({width:800,height:700}),[manualZoom,setManualZoom]=useState<number|null>(null),[space,setSpace]=useState(false);
  const [guides,setGuides]=useState<{x:number|null;y:number|null}>({x:null,y:null}),[editing,setEditing]=useState<string|null>(null);
  const [fullscreen,setFullscreen]=useState(false),[zoomHover,setZoomHover]=useState(false),[zoomFocus,setZoomFocus]=useState(false);
  const doc=snapshot.document,selected=doc.layers.find(l=>l.id===snapshot.selectedId);
  const fit=Math.min((size.width-80)/doc.width,(size.height-84)/doc.height,1);
  const scale=manualZoom??Math.max(.05,fit);
  useLayoutEffect(()=>{const el=viewport.current!;const observer=new ResizeObserver(entries=>{const r=entries[0].contentRect;setSize({width:r.width,height:r.height});});observer.observe(el);return ()=>observer.disconnect();},[]);
  useEffect(()=>{setEditing(null);},[doc.id]);
  useEffect(()=>{const update=()=>setFullscreen(document.fullscreenElement===workspace.current);update();document.addEventListener('fullscreenchange',update);return ()=>document.removeEventListener('fullscreenchange',update);},[]);
  useEffect(()=>{
    const down=(e:KeyboardEvent)=>{
      if(e.defaultPrevented||(e.target as HTMLElement).closest('input,textarea,[contenteditable="true"],[role="combobox"],[role="listbox"],[role="option"],[role="slider"]'))return;
      if(e.code==='Space'){e.preventDefault();setSpace(true);}
      if((e.ctrlKey||e.metaKey)&&['=','+','-','0'].includes(e.key)){e.preventDefault();if(e.key==='0')setManualZoom(null);else setManualZoom(v=>clamp((v??scale)+(e.key==='-'?-.1:.1),.05,2));}
    };
    const up=(e:KeyboardEvent)=>{if(e.code==='Space')setSpace(false);};
    const blur=()=>{setSpace(false);pan.current=null;};
    window.addEventListener('keydown',down);window.addEventListener('keyup',up);window.addEventListener('blur',blur);
    return ()=>{window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);window.removeEventListener('blur',blur);};
  },[scale]);
  const align=(align:'left'|'center'|'right')=>{if(!selected||selected.locked)return;controller.change(d=>{const l=d.layers.find(l=>l.id===selected.id)!;l.frame.x=align==='left'?0:align==='center'?(d.width-l.frame.width)/2:d.width-l.frame.width;});};
  const toolbarLeft=selected?clamp((selected.frame.x+selected.frame.width/2)*scale,155,doc.width*scale-155):0;
  return <main ref={workspace} className={'canvas-workspace'+(grid?' show-grid':'')}>
    <FloatingToolbar onAlign={align} snap={snap} onSnap={onSnap} grid={grid} onGrid={onGrid} disabled={!selected||selected.locked}/>
    <div ref={viewport} className={'canvas-viewport'+(space?' panning':'')} data-testid="canvas-viewport"
      onPointerDown={e=>{if(space||e.button===1){e.preventDefault();viewport.current!.setPointerCapture(e.pointerId);pan.current={x:e.clientX,y:e.clientY,left:viewport.current!.scrollLeft,top:viewport.current!.scrollTop};}else if(e.target===e.currentTarget||(e.target as HTMLElement).classList.contains('stage-space'))controller.select(null);}}
      onPointerMove={e=>{if(pan.current){viewport.current!.scrollLeft=pan.current.left+pan.current.x-e.clientX;viewport.current!.scrollTop=pan.current.top+pan.current.y-e.clientY;}}}
      onPointerUp={()=>pan.current=null} onPointerCancel={()=>pan.current=null}>
      <div className="stage-space" style={{width:doc.width*scale+80,height:doc.height*scale+84}}>
        <div ref={artboard} className="artboard" data-testid="artboard" data-scale={scale} style={{width:doc.width*scale,height:doc.height*scale}}>
          <div className="logical-canvas" style={{width:doc.width,height:doc.height,transform:`scale(${scale})`}}>
            {editing&&<style>{`.logical-canvas [data-art-layer="${editing}"]{visibility:hidden}`}</style>}
            <CoverArtwork document={doc}/>
            {ready&&<div style={{pointerEvents:space?'none':undefined}}><InteractionOverlay controller={controller} snapshot={snapshot} artboard={artboard} scale={scale} snap={snap} editing={editing} setEditing={setEditing} onGuides={setGuides}/></div>}
            {guides.x!=null&&<div className="guide vertical" style={{left:guides.x,width:1/scale}}/>}{guides.y!=null&&<div className="guide horizontal" style={{top:guides.y,height:1/scale}}/>}
          </div>
          {selected?.visible&&!editing&&<div className="selection-toolbar-position" style={{left:toolbarLeft,top:Math.max(-46,selected.frame.y*scale-48)}}><SelectionToolbar layer={selected} onCopy={onDuplicate} onDelete={onDelete} onCenter={()=>align('center')} onColor={color=>controller.change(d=>{d.layers.find(l=>l.id===selected.id)!.color=color;})} onText={()=>{if(selected.type==='text'&&!selected.locked)setEditing(selected.id);}}/></div>}
          {!ready&&<div className="canvas-loading">正在加载字体与图片…</div>}
        </div>
      </div>
    </div>
    <div className="zoom-toolbar"><Tooltip open={zoomHover||zoomFocus}><TooltipTrigger asChild><Slider className="zoom-slider" aria-label="画布缩放滑块" min={5} max={200} step={1} value={[Math.round(scale*100)]} onValueChange={([value])=>setManualZoom(value/100)} onPointerEnter={()=>setZoomHover(true)} onPointerLeave={()=>setZoomHover(false)} onFocus={e=>setZoomFocus(e.target.matches(':focus-visible'))} onBlur={()=>setZoomFocus(false)}/></TooltipTrigger><TooltipContent>{Math.round(scale*100)}%</TooltipContent></Tooltip><i className="divider"/><button className="fit-button" onClick={()=>{setManualZoom(null);viewport.current!.scrollTo(0,0);}}><FrameCorners size={18}/>适应窗口</button><IconButton icon={fullscreen?ArrowsIn:ArrowsOut} label={fullscreen?'退出全屏':'全屏编辑'} active={fullscreen} onClick={()=>{if(document.fullscreenElement)void document.exitFullscreen();else void workspace.current?.requestFullscreen();}}/></div>
    <div className="canvas-caption">{doc.width} × {doc.height} <span>·</span> {manualZoom===null?'适应窗口':'自由缩放'} <span>·</span> {Math.round(scale*100)}%</div>
  </main>;
}
