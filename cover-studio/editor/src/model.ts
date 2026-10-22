export type Frame = {x:number; y:number; width:number; height:number; rotation:number};
export type Shadow = {enabled:boolean; color:string; opacity:number; blur:number; x:number; y:number};
export type LayerType = 'text'|'image'|'rect'|'ellipse';
export type Layer = {
  id:string; name:string; type:LayerType; frame:Frame; visible:boolean; locked:boolean;
  opacity:number; text:string; fontId:string; fontSize:number; fontWeight:number;
  align:'left'|'center'|'right'|'justify'; lineHeight:number; letterSpacing:number;
  color:string; stroke:string; strokeWidth:number; shadow:Shadow;
  assetId:string; fit:'cover'|'contain'|'fill'; focusY:number; darkness:number; radius:number;
  textScaleY?:number; glow?:boolean; imageShape?:'rectangle'|'circle';
};
export type CoverDocument = {
  schemaVersion:3; kind:'cover-document'; id:string|null; revision:number;
  name:string; width:number; height:number; background:string;
  layers:Layer[]; updatedAt:string|null; sourceScene?:Record<string,unknown>;
};
export type FontEntry = {
  id:string; name:string; source:string; family?:string; weight?:number; variant?:string;
  format?:string; webFormat?:string; filename?:string; sample?:string; coverage?:string; italic?:boolean;label?:string;
};
export type FontCatalog = {fonts:FontEntry[]; defaults:{title:string; subtitle:string; local:string}};
export const RATIOS:Record<string,[number,number]> = {
  '16:9':[1920,1080], '3:4':[1080,1440], '9:16':[1080,1920],
  '4:3':[1440,1080], '4:5':[1080,1350], '1:1':[1080,1080],
};
export const clone = <T,>(value:T):T => structuredClone(value);
export const clamp = (n:number,min:number,max:number) => Math.max(min,Math.min(max,n));
export function createLayer(type:LayerType, fontId='', patch:Partial<Layer>={}):Layer {
  return {
    id:crypto.randomUUID(), name:type==='text'?'新建文字':type==='image'?'图片素材':'形状', type,
    frame:{x:480,y:440,width:960,height:140,rotation:0}, visible:true, locked:false,
    opacity:1,text:type==='text'?'双击输入文字':'',fontId,fontSize:88,fontWeight:400,
    align:'center',lineHeight:1.15,letterSpacing:0,color:'#ffffff',stroke:'#0f1216',strokeWidth:0,
    shadow:{enabled:false,color:'#000000',opacity:.8,blur:24,x:8,y:8},
    assetId:'',fit:'cover',focusY:50,darkness:0,radius:0,...patch,
  };
}
export function newDocument(fontId:string,fontWeight=400):CoverDocument {
  return {schemaVersion:3,kind:'cover-document',id:null,revision:0,
    name:'认知盲区 - 叙事封面',width:1920,height:1080,background:'#0f1216',updatedAt:null,
    layers:[
      createLayer('image','',{id:'background',name:'黑白漫画特写插画',locked:true,
        assetId:'builtin:noir',frame:{x:0,y:0,width:1920,height:1080,rotation:0},darkness:30}),
      createLayer('text',fontId,{id:'eyebrow',name:'栏目名称',text:'THINKING LAB RESEARCH',fontSize:22,
        align:'left',letterSpacing:2,frame:{x:70,y:55,width:900,height:40,rotation:0},opacity:.75}),
      createLayer('text',fontId,{id:'account',name:'思考实验室 胶囊组',text:'思考实验室 · VOL.42 · 认知科学特辑',fontSize:24,
        align:'left',frame:{x:70,y:970,width:1100,height:48,rotation:0}}),
      createLayer('text',fontId,{id:'subtitle',name:'大脑如何悄悄欺骗我们',text:'— 大脑如何悄悄欺骗我们 —',fontSize:36,
        letterSpacing:4,frame:{x:260,y:745,width:1400,height:64,rotation:0}}),
      createLayer('text',fontId,{id:'title',name:'认知的盲区',text:'认知的盲区',fontSize:124,letterSpacing:8,
        strokeWidth:2,shadow:{enabled:true,color:'#000000',opacity:.8,blur:24,x:8,y:8},
        frame:{x:300,y:480,width:1320,height:170,rotation:0}}),
    ].map(l=>l.type==='text'?{...l,fontWeight}:l)};
}
// History compares content; server metadata never becomes an undoable edit.
export function contentKey(doc:CoverDocument):string {
  const {id,revision,updatedAt,...content}=doc;
  return JSON.stringify(content);
}
export function screenToDocument(client:{x:number;y:number},bounds:{left:number;top:number;width:number;height:number},doc:{width:number;height:number}) {
  return {x:(client.x-bounds.left)*doc.width/bounds.width,
    y:(client.y-bounds.top)*doc.height/bounds.height};
}
export function resizeDocument(doc:CoverDocument,width:number,height:number,measureHeight?:(layer:Layer)=>number) {
  const sx=width/doc.width,sy=height/doc.height;
  const typeScale=Math.min(width,height)/Math.min(doc.width,doc.height);
  doc.layers.forEach(l=>{const circle=l.type==='image'&&l.imageShape==='circle';
    l.frame={...l.frame,x:clamp(l.frame.x*sx,-16384,16384),y:clamp(l.frame.y*sy,-16384,16384),
    width:clamp(l.frame.width*(circle?typeScale:sx),1,16384),height:clamp(l.frame.height*(circle?typeScale:sy),1,16384)};l.fontSize=clamp(l.fontSize*typeScale,8,500);
    if(l.type==='text'&&measureHeight)l.frame.height=measureHeight(l);
  });
  doc.width=width;doc.height=height;
}
export function reorderLayer(doc:CoverDocument,id:string,target:number) {
  const i=doc.layers.findIndex(l=>l.id===id);
  if(i<0)return;
  const [layer]=doc.layers.splice(i,1);
  doc.layers.splice(clamp(target,0,doc.layers.length),0,layer);
}
export function duplicateLayer(doc:CoverDocument,id:string):string|null {
  const original=doc.layers.find(l=>l.id===id);
  if(!original || original.locked || doc.layers.length>=60)return null;
  const layer=clone(original);layer.id=crypto.randomUUID();layer.name=Array.from(layer.name).slice(0,67).join('')+' 副本';
  layer.frame.x+=24;layer.frame.y+=24;doc.layers.push(layer);return layer.id;
}
