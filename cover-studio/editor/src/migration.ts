import {CoverDocument,Layer,createLayer,RATIOS,clone} from './model';
import {getProfile} from '../../fabric-poc/src/ratio-layout.mjs';
import {clampBounds} from '../../fabric-poc/src/snapping-engine.mjs';

// v2 is validated by the existing scene API before reaching this adapter.
export function migrateScene(scene:any, measure:(text:string,fontId:string,size:number,spacing:number)=>number,measureHeight?:(layer:Layer)=>number):CoverDocument {
  if(scene.schemaVersion!==2)throw Error('只支持迁移 scene v2；经典模板请先通过旧模板导入接口读取。');
  const [w,h]=RATIOS[scene.activeRatio];
  const profile=getProfile(scene.activeRatio);
  const definitions:Layer[]=[];
  const frame=(x:number,y:number,width:number,height:number,rotation=0)=>({x,y,width,height,rotation});
  const boundedFrame=(x:number,y:number,width:number,height:number,rotation=0)=>{
    const a=rotation*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
    const left=x+Math.min(0,c*width,-s*height,c*width-s*height),top=y+Math.min(0,s*width,c*height,s*width+c*height);
    const next=clampBounds(left,top,Math.abs(c)*width+Math.abs(s)*height,Math.abs(s)*width+Math.abs(c)*height,w,h);
    return frame(x+next.x-left,y+next.y-top,width,height,rotation);
  };
  let subtitleBottom=0;
  const asset=(value:any)=>value?.source==='managed'?value.id:'';
  for(const spec of scene.layers){
    const s=spec.style||{};
    const common={id:spec.id,name:spec.name||({title:'大标题',subtitle:'小标题',account:'账号',background:'背景',avatar:'头像'} as Record<string,string>)[spec.id],
      visible:spec.visible,locked:spec.locked,opacity:s.opacity??1};
    if(spec.id==='background') {
      if(asset(scene.assets.background))definitions.push(createLayer('image','',{...common,
        assetId:asset(scene.assets.background),frame:frame(0,0,w,h),darkness:scene.backgroundStyle.darkness,focusY:scene.backgroundStyle.focusY,glow:scene.backgroundStyle.glow}));
      else definitions.push(createLayer('rect','',{...common,color:'#07080a',frame:frame(0,0,w,h),glow:scene.backgroundStyle.glow}));
      continue;
    }
    if(spec.id==='avatar') {
      continue;
    }
    const role=spec.id;const fontId=scene.fontRefs[role==='title'?'title':'subtitle'];
    const maxWidth=w*(role==='title'?profile.titleMaxWidth:role==='subtitle'?.87:.51);
    const maxHeight=h*(role==='title'?profile.titleHeight:.22);
    let size=s.fontSize??(role==='title'?Math.min(w*(h>=w?.175:.135),h*.215):role==='subtitle'?Math.min(w*.054,h*.08):Math.max(18,Math.round(Math.min(w*.036,h*.046))));
    const layout=(px:number)=>{
      const spacing=px*(s.charSpacing??0)/1000;
      const text=scene.content[role]||'';
      const lines:string[]=[];
      for(const paragraph of text.split('\n')){
        let line='';
        for(const ch of paragraph){
          if(line&&measure(line+ch,fontId,px,spacing)>maxWidth){lines.push(line);line=ch;}else line+=ch;
        }
        lines.push(line);
      }
      return {lines,width:Math.min(maxWidth,Math.max(1,...lines.map(l=>measure(l,fontId,px,spacing)))+2),height:lines.length*px*(s.lineHeight??1.15)};
    };
    let box=layout(size);
    while(s.fontSize==null && size>22 && (box.height>maxHeight||box.lines.length>2)){size-=2;box=layout(size);}
    let x=role==='account'?w*.075:(w-box.width)/2;
    const title=definitions.find(l=>l.id==='title');
    let y=role==='title'?h*profile.titleTop:role==='subtitle'?Math.max(h*profile.subtitleMinTop,(title?title.frame.y+title.frame.height:0)+h*profile.flowGap):h*profile.accountMinTop;
    const position=scene.variants[scene.activeRatio]?.[role];
    if(position?.mode==='manual'){if(position.x!=null)x=w*position.x/100;if(position.y!=null)y=h*position.y/100;}
    let textFrame=boundedFrame(x,y,box.width,box.height,s.angle??0);
    let ruleFrame:Layer['frame']|null=null;
    if(role==='subtitle'){
      // v2 stores the Group origin, not its centered text's origin.
      const lineWidth=w*.61,lineHeight=Math.max(1,w/600),contentWidth=Math.max(lineWidth,box.width);
      const rawTextX=(contentWidth-box.width)/2,rawLineX=(contentWidth-lineWidth)/2,lineY=box.height+h*.016;
      const left=Math.min(rawTextX,rawLineX-lineHeight/2),groupWidth=Math.max(rawTextX+box.width+(s.strokeWidth??0),rawLineX+lineWidth+lineHeight/2)-left;
      const groupHeight=Math.max(box.height+(s.strokeWidth??0),lineY+lineHeight/2);
      const groupX=position?.mode==='manual'&&position.x!=null?x:Math.round((w-contentWidth)/2);
      const group=boundedFrame(groupX,y,groupWidth,groupHeight,s.angle??0);
      const a=group.rotation*Math.PI/180,c=Math.cos(a),sin=Math.sin(a),textX=rawTextX-left;
      textFrame=frame(group.x+textX*c,group.y+textX*sin,box.width,box.height,group.rotation);
      const lineX=rawLineX-lineHeight/2-left,lineTop=lineY-lineHeight/2;
      ruleFrame=frame(group.x+lineX*c-lineTop*sin,group.y+lineX*sin+lineTop*c,lineWidth+lineHeight,lineHeight,group.rotation);
      subtitleBottom=group.y+groupHeight;
    }
    const shadow=s.shadow||{};
    definitions.push(createLayer('text',fontId,{...common,text:box.lines.join('\n'),fontSize:size,
      frame:textFrame,
      align:role==='account'?'left':'center',lineHeight:s.lineHeight??1.15,letterSpacing:size*(s.charSpacing??0)/1000,
      color:s.fill??'#ffffff',stroke:s.stroke??'#000000',strokeWidth:s.strokeWidth??0,
      shadow:{enabled:shadow.enabled??false,color:shadow.color??'#000000',opacity:shadow.opacity??.45,
        blur:shadow.blur??0,x:shadow.offsetX??0,y:shadow.offsetY??0}}));
    // The v2 subtitle separator was part of a Fabric Group; retain it as an editable layer.
    if(ruleFrame)definitions.push(createLayer('rect','',{id:'subtitle-rule',name:'小标题分隔线',
      visible:spec.visible,locked:spec.locked,opacity:common.opacity,color:'#aaaaaa',
      frame:ruleFrame}));
  }
  const avatar=scene.layers.find((l:any)=>l.id==='avatar');
  if(avatar&&asset(scene.assets.avatar)){
    const style=avatar.style||{},size=(Math.round(Math.min(w*.245,h*.23))+4)*(style.scale??1);
    const y=Math.min(h-size-2,Math.max(Math.round(h*profile.avatarMinTop),subtitleBottom+Math.round(h*profile.flowGap)));
    definitions.push(createLayer('image','',{id:'avatar',name:'头像',visible:avatar.visible,locked:avatar.locked,opacity:style.opacity??1,
      assetId:asset(scene.assets.avatar),radius:w,stroke:'#e1e0d8',strokeWidth:2,
      frame:frame(Math.max(0,w-Math.round(w*.075)-size),Math.max(0,y),size,size,style.angle??0)}));
  }
  const entries=definitions.map((l,i)=>({layer:l,z:scene.layers.find((x:any)=>x.id===l.id)?.zIndex??(l.id==='subtitle-rule'?30:i)}));
  for(const extra of scene.extras?.layers||[]) {
    const f=extra.ratioFrames?.[scene.activeRatio]||extra.frame;
    const group=scene.extras.groups?.find((g:any)=>g.id===extra.groupId);
    const layer=createLayer(extra.type,extra.fontId||'',{id:extra.id,name:extra.name,text:extra.text||'',
      assetId:extra.assetId||'',visible:extra.visible&&(group?.visible??true),locked:extra.locked||(group?.locked??false),
      frame:frame(w*f.x/100,h*f.y/100,w*f.width/100,h*f.height/100,f.angle),
      align:'left',lineHeight:1.1,textScaleY:f.scaleY??1,fit:'fill',
      fontSize:extra.style.fontSize??58,color:extra.style.fill??'#ffffff',opacity:extra.style.opacity,
      stroke:extra.style.stroke??'#ffffff',strokeWidth:extra.style.strokeWidth??0});
    if(extra.type==='text')layer.frame.height=measureHeight?measureHeight(layer):layer.fontSize*layer.lineHeight*(f.scaleY??1)*extra.text.split('\n').length;
    entries.push({layer,z:group?Math.max(...scene.extras.layers.filter((l:any)=>l.groupId===group.id).map((l:any)=>l.zIndex)):extra.zIndex});
  }
  // Fabric rotates around the stored left/top; CSS rotates around the frame center.
  // Convert once, after text measurement, so both engines paint at the same origin.
  for(const {layer} of entries){
    const f=layer.frame,a=f.rotation*Math.PI/180,c=Math.cos(a),s=Math.sin(a),cx=f.width/2,cy=f.height/2;
    f.x+=cx*(c-1)-cy*s;f.y+=cx*s+cy*(c-1);
  }
  return {schemaVersion:3,kind:'cover-document',id:null,revision:0,name:Array.from(scene.name as string).slice(0,64).join('')+' · 已迁移',
    width:w,height:h,background:'#060709',updatedAt:null,
    layers:entries.sort((a,b)=>a.z-b.z).map(e=>e.layer),sourceScene:clone(scene)};
}
