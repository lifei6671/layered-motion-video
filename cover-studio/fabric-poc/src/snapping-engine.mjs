/** 浏览器编辑辅助线纯几何模块，原图像素坐标为唯一计算坐标系。 */

export function candidateAxes(width,height,safeMargin=0.055,otherRects=[]) {
  const xs=[0,width*safeMargin,width/2,width*(1-safeMargin),width];
  const ys=[0,height*safeMargin,height/2,height*(1-safeMargin),height];
  for(const r of otherRects){
    xs.push(r.left,r.left+r.width/2,r.left+r.width);
    ys.push(r.top,r.top+r.height/2,r.top+r.height);
  }
  return {x:xs.filter(Number.isFinite),y:ys.filter(Number.isFinite)};
}

function nearest(points,candidates,threshold) {
  let best=null;
  for(const from of points){
    for(const to of candidates){
      const delta=to-from;
      if(Math.abs(delta)>threshold) continue;
      if(!best || Math.abs(delta)<Math.abs(best.delta)){
        best={delta,line:to};
      }
    }
  }
  return best;
}

/** thresholdScreenPx 与画布显示倍率分离，确保不同画幅的吸附手感一致。 */
export function snapBounds(rect,axes,{scale=1,thresholdScreenPx=8}={}){
  if(!(scale>0) || !(thresholdScreenPx>=0))throw Error("吸附参数不正确");
  const threshold=thresholdScreenPx/scale;
  // 画布中心线是主要视觉锚点：当对象中心进入阈值时优先居中。
  // 否则保留最近图层边缘/安全边距吸附，避免同一方向多个参考线竞争。
  const cx=axes.x[2],cy=axes.y[2];
  const dx=cx-(rect.left+rect.width/2);
  const dy=cy-(rect.top+rect.height/2);
  const horizontal=Math.abs(dx)<=threshold ? {delta:dx,line:cx} : nearest(
    [rect.left,rect.left+rect.width/2,rect.left+rect.width],
    axes.x,threshold
  );
  const vertical=Math.abs(dy)<=threshold ? {delta:dy,line:cy} : nearest(
    [rect.top,rect.top+rect.height/2,rect.top+rect.height],
    axes.y,threshold
  );
  return {
    dx:horizontal?.delta??0,
    dy:vertical?.delta??0,
    guides:{
      x:horizontal?horizontal.line:null,
      y:vertical?vertical.line:null,
    }
  };
}

/** 钳位顺序在吸附之后，避免辅助线停留在画布外。 */
export function clampBounds(x,y,width,height,canvasWidth,canvasHeight){
  return {
    x:Math.max(0,Math.min(x,Math.max(0,canvasWidth-width))),
    y:Math.max(0,Math.min(y,Math.max(0,canvasHeight-height))),
  };
}
