/** 场景 v2 的图层样式属性与输入约束，与 Python 服务端校验范围一致。 */
const colors = {title:"#fffcf4",subtitle:"#f8f7f2",account:"#939496"};
const isNumber = v=>typeof v==="number" && Number.isFinite(v);
const isColor = v=>typeof v==="string" && /^#[0-9a-f]{6}$/i.test(v);

export function defaultStyle(id) {
  if(id==="avatar")return {opacity:1,angle:0,scale:1};
  if(!(id in colors))throw Error("未知样式图层："+id);
  return {
    fontSize:null,charSpacing:0,lineHeight:1.15,fill:colors[id],opacity:1,
    stroke:"#000000",strokeWidth:0,angle:0,
    shadow:{enabled:false,color:"#000000",opacity:.45,blur:0,offsetX:0,offsetY:0}
  };
}

const TEXT_RANGES = {
  fontSize:[16,400],charSpacing:[-150,1000],lineHeight:[.8,2.5],
  opacity:[0,1],strokeWidth:[0,16],angle:[-180,180],
  "shadow.opacity":[0,1],"shadow.blur":[0,60],
  "shadow.offsetX":[-60,60],"shadow.offsetY":[-60,60]
};
const AVATAR_RANGES = {opacity:[0,1],angle:[-180,180],scale:[.5,2.5]};

export function normalizeStyle(id,style=null) {
  const defaults=defaultStyle(id);
  const supplied=style??{};
  if(!supplied || typeof supplied!=="object" || Array.isArray(supplied))throw Error("图层样式须为对象");
  if(Object.keys(supplied).some(k=>!(k in defaults)))throw Error("图层样式包含未知字段");
  const result={...defaults,...supplied};
  if(id!=="avatar"){
    const shadow={...defaults.shadow,...(supplied.shadow??{})};
    if(!supplied.shadow || typeof supplied.shadow==="object" && !Array.isArray(supplied.shadow)){
      if(supplied.shadow && Object.keys(supplied.shadow).some(k=>!(k in defaults.shadow)))throw Error("阴影包含未知字段");
    }else throw Error("阴影必须是对象");
    if(typeof shadow.enabled!=="boolean")throw Error("阴影开关必须是布尔值");
    if(!isColor(shadow.color))throw Error("阴影颜色格式错误");
    result.shadow=shadow;
  }
  const ranges=id==="avatar"?AVATAR_RANGES:TEXT_RANGES;
  for(const [path,[min,max]] of Object.entries(ranges)){
    const value=path.startsWith("shadow.")?result.shadow[path.slice(7)]:result[path];
    if(path==="fontSize" && value===null)continue;
    if(!isNumber(value)||value<min||value>max)throw Error(path+" 超出允许范围");
  }
  if(id!=="avatar" && (!isColor(result.fill)||!isColor(result.stroke)))throw Error("颜色须为 #RRGGBB");
  for(const key of ["fill","stroke"]){
    if(result[key])result[key]=result[key].toLowerCase();
  }
  if(result.shadow)result.shadow.color=result.shadow.color.toLowerCase();
  return result;
}

export function getLayerStyle(scene,id){
  const layer=scene?.layers?.find(entry=>entry.id===id);
  if(!layer)throw Error("图层不存在："+id);
  return normalizeStyle(id,layer.style??null);
}

export function setStyleProperty(scene,id,path,value){
  const layer=scene?.layers?.find(entry=>entry.id===id);
  if(!layer)throw Error("图层不存在："+id);
  const original=normalizeStyle(id,layer.style??null);
  const cloned={...original};
  if(original.shadow)cloned.shadow={...original.shadow};
  if(path.startsWith("shadow.")){
    if(!cloned.shadow)throw Error("该图层不支持阴影");
    cloned.shadow[path.slice(7)]=value;
  }else cloned[path]=value;
  const normalized=normalizeStyle(id,cloned);
  if(JSON.stringify(original)===JSON.stringify(normalized))return false;
  layer.style=normalized;
  return true;
}
