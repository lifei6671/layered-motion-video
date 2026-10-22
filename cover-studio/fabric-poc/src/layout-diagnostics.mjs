/**
 * 多画幅编辑安全区与质量诊断（非平台官方坐标）。
 * 坐标均为原图画布像素；编辑层叠加并不进入导出图像。
 */
export const SAFETY_PROFILES=Object.freeze({
  general:{
    name:"通用封面安全区",
    ratios:["3:4","9:16","16:9","4:3","4:5","1:1"],
    margins:null,blocked:[]
  },
  vertical_video:{
    name:"竖屏视频界面参考",
    ratios:["3:4","9:16","4:5"],
    margins:{left:.07,right:.18,top:.10,bottom:.19},
    blocked:[{id:"interaction",name:"右侧操作区参考",rect:{x:.83,y:.41,width:.17,height:.40}}]
  },
  graphic_post:{
    name:"图文封面参考",
    ratios:["3:4","9:16","4:5","1:1"],
    margins:{left:.07,right:.07,top:.08,bottom:.10},blocked:[]
  },
  landscape_video:{
    name:"横屏视频播放参考",
    ratios:["16:9","4:3"],
    margins:{left:.07,right:.07,top:.07,bottom:.14},
    blocked:[{id:"player",name:"底部播放控件参考",rect:{x:0,y:.87,width:1,height:.13}}]
  }
});
export const PROFILE_IDS=Object.freeze(Object.keys(SAFETY_PROFILES));

export function availableSafetyProfiles(ratio){
  return PROFILE_IDS.filter(id=>SAFETY_PROFILES[id].ratios.includes(ratio));
}
export function resolveSafetyArea(ratio,width,height,profileId="general",genericMargin=.055){
  const profile=SAFETY_PROFILES[profileId];
  if(!profile || !profile.ratios.includes(ratio))throw Error("此画幅不支持该安全区参考方案");
  if(!(width>0&&height>0))throw Error("画幅尺寸无效");
  const margin=profile.margins??{
    left:genericMargin,right:genericMargin,
    top:genericMargin,bottom:genericMargin
  };
  const inner={
    left:width*margin.left,top:height*margin.top,
    right:width*(1-margin.right),bottom:height*(1-margin.bottom)
  };
  return {
    id:profileId,label:profile.name,ratio,width,height,inner,
    blocked:profile.blocked.map(item=>({
      id:item.id,label:item.name,
      rect:{
        left:item.rect.x*width,top:item.rect.y*height,
        width:item.rect.width*width,height:item.rect.height*height
      }
    }))
  };
}
function bounds(rect){
  return {
    left:rect.left,top:rect.top,
    right:rect.left+rect.width,bottom:rect.top+rect.height
  };
}
export function intersection(a,b) {
  const ra=bounds(a),rb=bounds(b);
  const w=Math.max(0,Math.min(ra.right,rb.right)-Math.max(ra.left,rb.left));
  const h=Math.max(0,Math.min(ra.bottom,rb.bottom)-Math.max(ra.top,rb.top));
  return {width:w,height:h,area:w*h};
}
export function canonicalPair(first,second){
  if(typeof first!=="string"||typeof second!=="string"||first===second)throw Error("重叠图层标识无效");
  return [first,second].sort();
}
function pairKey(a,b){return canonicalPair(a,b).join("|");}
function makeIssue(code,severity,text,layerIds,more={}){
  const ids=[...layerIds].sort();
  return {
    code,severity,message:text,layerIds:ids,
    id:code+":"+ids.join("~")+(more.zoneId?":"+more.zoneId:""),
    ...more,
  };
}
function overlapSignificant(first,second) {
  const cross=intersection(first.rect,second.rect);
  const smaller=Math.min(first.rect.width*first.rect.height,second.rect.width*second.rect.height);
  const xRatio=cross.width/Math.max(1,Math.min(first.rect.width,second.rect.width));
  const yRatio=cross.height/Math.max(1,Math.min(first.rect.height,second.rect.height));
  return smaller>0 && cross.area/smaller>=.12 && xRatio>=.18 && yRatio>=.18;
}
function luminance(rgb){
  const linear=rgb.map(v=>{
    const x=v/255;
    return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;
  });
  return .2126*linear[0]+.7152*linear[1]+.0722*linear[2];
}
export function contrastRatio(hex,rgb){
  if(!/^#[0-9a-f]{6}$/i.test(hex)||!Array.isArray(rgb)||rgb.length<3)
    throw Error("对比度输入无效");
  const foreground=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
  const x=luminance(foreground),y=luminance(rgb.slice(0,3));
  return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
}

export function diagnoseLayout({
  width,height,ratio,profileId="general",genericMargin=.055,
  items=[],allowedOverlaps=[],sampleBackground=null
}){
  const safe=resolveSafetyArea(ratio,width,height,profileId,genericMargin);
  const allowed=new Set(allowedOverlaps.map(pair=>pairKey(pair[0],pair[1])));
  const issues=[];
  const visible=items.filter(item=>item.visible!==false && item.id!=="background");
  const inner=safe.inner;
  for(const item of visible){
    const r=item.rect;
    if(!r || [r.left,r.top,r.width,r.height].some(value=>!Number.isFinite(value)) ||
       r.width<=0 || r.height<=0)continue;
    const critical=item.kind==="text"||item.kind==="avatar"||item.kind==="mixed-group";
    const name=item.label||item.id;
    if(r.left < -1 || r.top < -1 || r.left+r.width > width+1 || r.top+r.height > height+1){
      issues.push(makeIssue("OUT_OF_CANVAS","error",name+"超出画布边界",[item.id]));
    }else if(critical && (
      r.left < inner.left-2 || r.top < inner.top-2 ||
      r.left+r.width > inner.right+2 || r.top+r.height > inner.bottom+2
    )){
      issues.push(makeIssue("SAFE_MARGIN","warning",name+"超出当前安全留白范围",[item.id]));
    }
    if(critical)for(const zone of safe.blocked){
      const cross=intersection(r,zone.rect);
      const fraction=cross.area/Math.max(1,r.width*r.height);
      if(fraction>.06){
        issues.push(makeIssue("UI_OVERLAY","warning",name+"与"+zone.label+"重叠",[item.id],{
          zoneId:zone.id,overlapRatio:Number(fraction.toFixed(3))
        }));
      }
    }
    if(item.kind==="text"){
      const threshold=item.id==="title"?.045:item.id==="subtitle"?.024:
        item.id==="account"?.018:.02;
      if(item.fontSize!=null && item.fontSize < Math.min(width,height)*threshold){
        issues.push(makeIssue("SMALL_TEXT","warning",name+"字号偏小，建议检查实际设备可读性",[item.id]));
      }
      if(item.opacity!=null && item.opacity<.45){
        issues.push(makeIssue("LOW_OPACITY","warning",name+"透明度较低，可能影响阅读",[item.id]));
      }
      if(typeof sampleBackground==="function" && typeof item.fill==="string"){
        const point={x:Math.min(width-1,Math.max(0,r.left+r.width/2)),
          y:Math.min(height-1,Math.max(0,r.top+r.height/2))};
        const bg=sampleBackground(point.x,point.y);
        if(bg){
          const ratioValue=contrastRatio(item.fill,bg);
          if(ratioValue<3.0){
            issues.push(makeIssue("LOW_CONTRAST","warning",
              name+"与背景颜色对比可能不足（约 "+ratioValue.toFixed(1)+":1）",[item.id],{
                contrast:Number(ratioValue.toFixed(2)),heuristic:true
              }));
          }
        }
      }
    }
  }

  // 仅对重要文字和图片之间的显著重叠报告问题；纯装饰图形重叠默认允许。
  for(let i=0;i<visible.length;i++){
    for(let j=i+1;j<visible.length;j++){
      const a=visible[i],b=visible[j];
      if(allowed.has(pairKey(a.id,b.id)) || !a.rect || !b.rect)continue;
      const isText=k=>k==="text"||k==="mixed-group";
      const isImage=k=>k==="avatar"||k==="image";
      const check=(isText(a.kind)&&(isText(b.kind)||isImage(b.kind))) ||
        (isText(b.kind)&&isImage(a.kind));
      if(!check || !overlapSignificant(a,b))continue;
      issues.push(makeIssue("LAYER_COLLISION","warning",
        (a.label||a.id)+"与"+(b.label||b.id)+"发生明显遮挡",[a.id,b.id],{
          canAllow:true,overlapRatio:Number((
            intersection(a.rect,b.rect).area/
            Math.max(1,Math.min(a.rect.width*a.rect.height,b.rect.width*b.rect.height))
          ).toFixed(3))
        }));
    }
  }
  const severityOrder={error:0,warning:1,info:2};
  issues.sort((a,b)=>severityOrder[a.severity]-severityOrder[b.severity]||
    a.code.localeCompare(b.code)||a.id.localeCompare(b.id));
  const counts={
    error:issues.filter(issue=>issue.severity==="error").length,
    warning:issues.filter(issue=>issue.severity==="warning").length,
    info:issues.filter(issue=>issue.severity==="info").length
  };
  return {
    ratio,profileId,profileName:safe.label,
    status:counts.error?"error":counts.warning?"warning":"pass",
    counts,issues,safeArea:safe
  };
}
