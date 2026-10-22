import {useRef,useState,useEffect} from 'react';
import type React from 'react';
import {ArrowClockwise} from '@phosphor-icons/react';
import {DocumentController,EditorSnapshot} from '../controller';
import {Frame,Layer,clamp,screenToDocument} from '../model';
import {textStyle,measureTextLayer} from '../fonts';
import {candidateAxes,snapBounds} from '../../../fabric-poc/src/snapping-engine.mjs';
import {Hint} from './controls';
type Gesture={id:string;start:{x:number;y:number};frame:Frame;fontSize:number;spacing:number;textScaleY:number;handle:string;pointer:number};
type Props={controller:DocumentController;snapshot:EditorSnapshot;artboard:React.RefObject<HTMLDivElement|null>;
  scale:number;snap:boolean;editing:string|null;setEditing:(v:string|null)=>void;onGuides:(v:{x:number|null;y:number|null})=>void;};
export function InteractionOverlay({controller,snapshot,artboard,scale,snap,editing,setEditing,onGuides}:Props) {
  const gesture=useRef<Gesture|null>(null),composing=useRef(false),originalText=useRef({text:'',name:'',height:0});
  const [draftText,setDraftText]=useState('');
  const doc=snapshot.document;
  const selected=doc.layers.find(l=>l.id===snapshot.selectedId);
  const point=(e:{clientX:number;clientY:number})=>screenToDocument({x:e.clientX,y:e.clientY},artboard.current!.getBoundingClientRect(),doc);
  useEffect(()=>{
    if(editing){const l=controller.getSnapshot().document.layers.find(l=>l.id===editing)!;originalText.current={text:l.text,name:l.name,height:l.frame.height};setDraftText(l.text);controller.begin();}
  },[editing,controller]);
  const finish=()=>{if(gesture.current){gesture.current=null;document.documentElement.classList.remove('text-rotation-active');controller.commit();onGuides({x:null,y:null});}};
  useEffect(()=>()=>document.documentElement.classList.remove('text-rotation-active'),[]);
  useEffect(()=>{window.addEventListener('blur',finish);return ()=>window.removeEventListener('blur',finish);});
  function start(e:React.PointerEvent,id:string,handle='move') {
    if(e.button!==0||editing)return;
    e.stopPropagation();controller.select(id);
    const layer=doc.layers.find(l=>l.id===id)!;if(layer.locked)return;
    controller.begin();e.currentTarget.setPointerCapture(e.pointerId);
    if(handle==='rotate')document.documentElement.classList.add('text-rotation-active');
    gesture.current={id,start:point(e),frame:{...layer.frame},fontSize:layer.fontSize,spacing:layer.letterSpacing,textScaleY:layer.textScaleY??1,handle,pointer:e.pointerId};
  }
  function move(e:React.PointerEvent) {
    const g=gesture.current;if(!g||e.pointerId!==g.pointer)return;
    const p=point(e),dx=p.x-g.start.x,dy=p.y-g.start.y;
    let frame={...g.frame},fontSize=g.fontSize,letterSpacing=g.spacing,textScaleY=g.textScaleY;
    if(g.handle==='rotate') {
      const cx=g.frame.x+g.frame.width/2,cy=g.frame.y+g.frame.height/2;
      const delta=(Math.atan2(p.y-cy,p.x-cx)-Math.atan2(g.start.y-cy,g.start.x-cx))*180/Math.PI;
      const angle=g.frame.rotation+delta;
      frame.rotation=Math.round((((angle+180)%360+360)%360-180)*100)/100;
    }else if(g.handle==='move') {
      frame.x+=dx;frame.y+=dy;
      if(snap&&!e.altKey) {
        const other=doc.layers.filter(l=>l.id!==g.id&&l.visible).map(l=>({left:l.frame.x,top:l.frame.y,width:l.frame.width,height:l.frame.height}));
        const axes=candidateAxes(doc.width,doc.height,.05,other);
        const result=snapBounds({left:frame.x,top:frame.y,width:frame.width,height:frame.height},axes,{scale,thresholdScreenPx:6});
        frame.x+=result.dx;frame.y+=result.dy;onGuides(result.guides);
      }else onGuides({x:null,y:null});
      frame.x=clamp(frame.x,0,Math.max(0,doc.width-frame.width));frame.y=clamp(frame.y,0,Math.max(0,doc.height-frame.height));
    }else {
      // Resize in object-local axes; keep the opposite edge anchored even when rotated.
      const a=g.frame.rotation*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
      const lx=dx*c+dy*s,ly=-dx*s+dy*c;
      const west=g.handle.includes('w'),north=g.handle.includes('n');
      const horizontal=g.handle.includes('w')||g.handle.includes('e'),vertical=g.handle.includes('n')||g.handle.includes('s');
      let dw=horizontal?(west?-lx:lx):0,dh=vertical?(north?-ly:ly):0;
      if((horizontal&&vertical&&(selected?.type==='text'||e.shiftKey))||selected?.imageShape==='circle') {
        const factor=clamp(1+(Math.abs(dw/g.frame.width)>=Math.abs(dh/g.frame.height)?dw/g.frame.width:dh/g.frame.height),.1,5);
        dw=g.frame.width*(factor-1);dh=g.frame.height*(factor-1);
        if(selected?.type==='text'){fontSize=clamp(g.fontSize*factor,8,500);letterSpacing=clamp(g.spacing*factor,-75,500);}
      }
      frame.width=clamp(g.frame.width+dw,16,16384);frame.height=clamp(g.frame.height+dh,16,16384);
      const layer=doc.layers.find(l=>l.id===g.id)!;
      if(layer.type==='text'){
        const natural=measureTextLayer({...layer,frame,fontSize,letterSpacing,textScaleY:1});
        if(vertical&&!horizontal)textScaleY=clamp(frame.height/natural,.1,10);
        frame.height=measureTextLayer({...layer,frame,fontSize,letterSpacing,textScaleY});
      }
      const cx=(frame.width-g.frame.width)*(west?-1:1)/2,cy=(frame.height-g.frame.height)*(north?-1:1)/2;
      frame.x=g.frame.x+g.frame.width/2+cx*c-cy*s-frame.width/2;
      frame.y=g.frame.y+g.frame.height/2+cx*s+cy*c-frame.height/2;
    }
    controller.change(d=>{const l=d.layers.find(l=>l.id===g.id)!;l.frame=frame;l.fontSize=fontSize;l.letterSpacing=letterSpacing;l.textScaleY=textScaleY;},false);
  }
  function editChange(text:string) {
    setDraftText(text);if(composing.current)return;
    controller.change(d=>{const l=d.layers.find(l=>l.id===editing);if(l){l.text=text;l.name=Array.from(text.replaceAll('\n',' ').trim()).slice(0,70).join('')||'文字';l.frame.height=measureTextLayer(l);}},false);
  }
  function endText(cancel=false) {
    if(!editing)return;
    const value=cancel?originalText.current.text:draftText;
    controller.change(d=>{const l=d.layers.find(l=>l.id===editing);if(l){l.text=value;l.name=cancel?originalText.current.name:Array.from(value.replaceAll('\n',' ').trim()).slice(0,70).join('')||'文字';l.frame.height=cancel?originalText.current.height:measureTextLayer(l);}},false);
    composing.current=false;controller.commit();setEditing(null);
  }
  return <div className="interaction-overlay" data-testid="interaction-overlay" onPointerMove={move} onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish}>
    {doc.layers.filter(l=>l.visible&&!l.locked).map(l=><div key={l.id} className={'layer-hit'+(l.id===snapshot.selectedId?' is-selected':'')} data-testid={'hit-'+l.id}
      style={{left:l.frame.x,top:l.frame.y,width:l.frame.width,height:l.frame.height,transform:`rotate(${l.frame.rotation}deg)`}}
      onPointerDown={e=>start(e,l.id)} onDoubleClick={e=>{e.stopPropagation();if(l.type==='text')setEditing(l.id);}}/>) }
    {selected?.visible&&!editing&&<div className={'selection-frame'+(selected.locked?' locked':'')} style={{left:selected.frame.x,top:selected.frame.y,width:selected.frame.width,height:selected.frame.height,transform:`rotate(${selected.frame.rotation}deg)`,'--inv-scale':1/scale} as React.CSSProperties}>
      {!selected.locked&&['nw','n','ne','e','se','s','sw','w'].map(handle=><button key={handle} className={'resize-handle '+handle} aria-label={'缩放 '+handle} data-testid={'resize-'+handle} onPointerDown={e=>start(e,selected.id,handle)}/>)}
      {!selected.locked&&selected.type==='text'&&<><span className="rotation-stem" aria-hidden="true"/><Hint content={'拖动旋转文字 · '+selected.frame.rotation+'°'}><button type="button" className="rotation-handle" aria-label="旋转文字" data-testid="rotation-handle" onPointerDown={e=>start(e,selected.id,'rotate')}><ArrowClockwise/></button></Hint></>}
      <span className="size-label">{Math.round(selected.frame.width)} × {Math.round(selected.frame.height)} px{selected.type==='text'&&<> · {selected.frame.rotation}°</>}</span>
    </div>}
    {editing&&(()=>{const l=doc.layers.find(l=>l.id===editing);if(!l)return null;return <div key={editing} style={{position:'absolute',left:l.frame.x,top:l.frame.y,width:l.frame.width,height:l.frame.height,transform:`rotate(${l.frame.rotation}deg)`}}><textarea autoFocus aria-label="画布文字编辑" data-testid="inline-text" maxLength={500} className="inline-text" value={draftText}
      style={{...textStyle(l),left:0,top:0,width:l.frame.width,height:Math.max(l.frame.height/(l.textScaleY??1),l.fontSize*l.lineHeight+8),transform:`scaleY(${l.textScaleY??1})`,transformOrigin:'0 0'}}
      onChange={e=>editChange(e.target.value)} onCompositionStart={()=>{composing.current=true;}}
      onCompositionEnd={e=>{composing.current=false;editChange(e.currentTarget.value);}}
      onBlur={()=>endText()} onPointerDown={e=>e.stopPropagation()} onKeyDown={e=>{e.stopPropagation();if(e.nativeEvent.isComposing||composing.current)return;if(e.key==='Escape'){e.preventDefault();endText(true);}else if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();endText();}}}/></div>;})()}
  </div>;
}
