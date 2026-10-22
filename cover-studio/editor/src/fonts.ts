import type {CoverDocument,Layer} from './model';
import type {CSSProperties} from 'react';
export const fontFamily = (id:string) => 'CoverFont_'+id.replace(/[^a-zA-Z0-9]/g,'_');
const loaded = new Map<string,Promise<void>>();
const readyFonts=new Set<string>(),readyImages=new Set<string>(),images=new Map<string,Promise<void>>();
export function loadFont(id:string,base=''):Promise<void> {
  if(!id)return Promise.reject(Error('文字图层缺少字体，请重新选择。'));
  const key=base+'|'+id;
  if(!loaded.has(key)) {
    const task=(async()=>{
      const face=new FontFace(fontFamily(id),`url("${base}/api/cover-font?id=${encodeURIComponent(id)}") format("woff2")`);
      await face.load();document.fonts.add(face);
      await document.fonts.load(`32px "${fontFamily(id)}"`);
      if(face.status!=='loaded')throw Error('字体未加载完成：'+id);
      readyFonts.add(key);
    })().catch(error=>{loaded.delete(key);throw Error('字体加载失败，请刷新字体目录后重新选择。'+String(error));});
    loaded.set(key,task);
  }
  return loaded.get(key)!;
}
export function assetUrl(id:string,base=''):string {
  if(id==='builtin:noir')return base+'/static/editor/noir.jpg';
  if(id==='builtin:tech')return base+'/static/editor/tech.jpg';
  return base+'/api/designs/assets/'+encodeURIComponent(id);
}
export function artworkResources(doc:CoverDocument) {
  return {fonts:[...new Set(doc.layers.filter(l=>l.type==='text'&&l.visible).map(l=>l.fontId))].sort(),
    images:[...new Set(doc.layers.filter(l=>l.type!=='text'&&l.assetId&&l.visible).map(l=>l.assetId))].sort()};
}
export function artworkIsReady(doc:CoverDocument,base='') {
  const resources=artworkResources(doc);
  return resources.fonts.every(id=>readyFonts.has(base+'|'+id))&&resources.images.every(id=>readyImages.has(base+'|'+id));
}
export async function prepareArtwork(doc:CoverDocument,base='') {
  const resources=artworkResources(doc);
  await Promise.all(resources.fonts.map(id=>loadFont(id,base)));
  await Promise.all(resources.images.map(id=>{
    const key=base+'|'+id;
    if(!images.has(key))images.set(key,(async()=>{const img=new Image();img.src=assetUrl(id,base);await img.decode();readyImages.add(key);})().catch(error=>{images.delete(key);throw error;}));
    return images.get(key)!;
  }));
  await document.fonts.ready;
}
export async function checkFontCoverage(doc:CoverDocument) {
  const checks=doc.layers.filter(l=>l.type==='text'&&l.visible&&l.text.trim()).map(l=>({fontId:l.fontId,text:l.text,label:l.name}));
  // Existing endpoint accepts 40 entries per request.
  for(let i=0;i<checks.length;i+=40){
    const response=await fetch('/api/fabric-poc/font-coverage',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({checks:checks.slice(i,i+40)}),signal:AbortSignal.timeout(30000)});
    const payload=await response.json();if(!response.ok)throw Error(payload.error||'字形检查失败');
    const problem=payload.results.find((r:{error?:string;missingCount:number})=>r.error||r.missingCount>0);
    if(problem)throw Error(`${problem.label}：${problem.error||'字体缺少字符 '+problem.missing.join('、')}，请选择完整字体。`);
  }
}
export function textStyle(layer:Layer):CSSProperties {
  const shadow=layer.shadow;
  const rgb=shadow.color.match(/\w\w/g)!.map(v=>parseInt(v,16));
  return {fontFamily:`"${fontFamily(layer.fontId)}"`,fontSize:layer.fontSize,
    // Each ID identifies the actual weight file. Disable synthetic bold/italic.
    fontWeight:400,fontSynthesis:'none',lineHeight:layer.lineHeight,letterSpacing:layer.letterSpacing,
    color:layer.color,textAlign:layer.align,whiteSpace:'pre-wrap',overflowWrap:'anywhere',
    WebkitTextStroke:layer.strokeWidth?`${layer.strokeWidth}px ${layer.stroke}`:undefined,
    paintOrder:'stroke fill',textShadow:shadow.enabled?`${shadow.x}px ${shadow.y}px ${shadow.blur}px rgba(${rgb.join(',')},${shadow.opacity})`:undefined};
}
export function measureTextLayer(layer:Layer):number {
  const node=document.createElement('div');
  Object.assign(node.style,textStyle(layer),{position:'fixed',left:'-20000px',top:'0',visibility:'hidden',
    width:layer.frame.width+'px',fontSize:layer.fontSize+'px',letterSpacing:layer.letterSpacing+'px',height:'auto',padding:'0',border:'0'});
  node.textContent=layer.text||'\u200b';document.body.append(node);
  const height=Math.max(1,Math.min(16384,Math.ceil(node.getBoundingClientRect().height*(layer.textScaleY??1))));node.remove();return height;
}
