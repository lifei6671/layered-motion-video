import React from 'react';
import type {CoverDocument,Layer} from './model';
import {assetUrl,textStyle} from './fonts';
export function ArtworkLayer({layer:l,assetBase=''}:{layer:Layer;assetBase?:string}) {
  const f=l.frame;
  const style:React.CSSProperties={position:'absolute',left:f.x,top:f.y,width:f.width,height:f.height,
    transform:`rotate(${f.rotation}deg)`,opacity:l.opacity,boxSizing:'border-box'};
  const glow=l.glow?<div style={{position:'absolute',left:0,top:0,width:'100%',height:'29%',overflow:'hidden',pointerEvents:'none'}}>{[[12,29,.29],[45,27,.19],[87,31,.26]].map(([x,spread,strength])=><div key={x} style={{position:'absolute',inset:0,background:`radial-gradient(circle ${l.frame.width*spread/100}px at ${x}% 0,rgba(239,240,237,${strength}),rgba(239,240,237,0))`}}/>)}</div>:null;
  if(l.type==='text')return <div data-art-layer={l.id} style={style}><div style={{...textStyle(l),transform:`scaleY(${l.textScaleY??1})`,transformOrigin:'0 0'}}>{l.text}</div></div>;
  if(l.assetId)return <div data-art-layer={l.id} style={{...style,overflow:'hidden',background:l.color,borderRadius:l.type==='ellipse'||l.imageShape==='circle'?'50%':l.radius,border:l.strokeWidth?`${l.strokeWidth}px solid ${l.stroke}`:undefined}}>
    <img alt="" draggable={false} src={assetUrl(l.assetId,assetBase)} style={{width:'100%',height:'100%',display:'block',objectFit:l.fit,objectPosition:`50% ${l.focusY}%`}}/>
    {l.darkness>0&&<div style={{position:'absolute',inset:0,background:`rgba(0,0,0,${l.darkness/100})`}}/>}
    {glow}
  </div>;
  return <div data-art-layer={l.id} style={{...style,background:l.color,border:`${l.strokeWidth}px solid ${l.stroke}`,
    borderRadius:l.type==='ellipse'?'50%':l.radius}}>{glow}</div>;
}
/** Pure picture only: used unchanged by editor, clean preview, templates and Remotion. */
export function CoverArtwork({document:doc,assetBase=''}:{document:CoverDocument;assetBase?:string}) {
  return <div data-testid="cover-artwork" style={{position:'relative',width:doc.width,height:doc.height,
    background:doc.background,overflow:'hidden',isolation:'isolate',colorScheme:'light'}}>
    {doc.layers.filter(l=>l.visible).map(l=><ArtworkLayer key={l.id} layer={l} assetBase={assetBase}/>)}
  </div>;
}
