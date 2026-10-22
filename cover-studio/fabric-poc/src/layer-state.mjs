/** 场景级图层属性：与 Fabric 对象实例解耦，操作结果可持久化/撤销。 */
export const LAYER_NAMES = Object.freeze({
  background:"背景",avatar:"圆形头像",title:"大标题",
  subtitle:"小标题与分隔线",account:"账号名称",
});

export function orderedLayers(scene){
  return [...(scene?.layers||[])].sort((a,b)=>b.zIndex-a.zIndex);
}

export function getLayer(scene,id){
  const layer=scene?.layers?.find(x=>x.id===id);
  if(!layer)throw Error("找不到图层："+id);
  return layer;
}

export function setLayerVisibility(scene,id,visible){
  if(typeof visible!=="boolean")throw Error("可见状态必须为布尔值");
  const layer=getLayer(scene,id);
  if(layer.visible===visible)return false;
  layer.visible=visible;
  return true;
}

export function setLayerLock(scene,id,locked){
  if(!["title","subtitle","account"].includes(id))throw Error("此图层位置由模板约束管理");
  if(typeof locked!=="boolean")throw Error("锁定状态必须为布尔值");
  const layer=getLayer(scene,id);
  if(layer.locked===locked)return false;
  layer.locked=locked;
  return true;
}

/** 按相邻层交换层级，不重新分配 ID；背景始终固定在最底层。 */
export function reorderLayer(scene,id,move){
  if(id==="background")return false;
  if(move!==1 && move!==-1)throw Error("图层移动方向无效");
  const layers=orderedLayers(scene).filter(x=>x.id!=="background");
  const i=layers.findIndex(x=>x.id===id);
  if(i<0)throw Error("找不到图层："+id);
  const j=i-move; // +1 往上移动，面板从高到低排序
  if(j<0 || j>=layers.length)return false;
  [layers[i].zIndex,layers[j].zIndex]=[layers[j].zIndex,layers[i].zIndex];
  return true;
}
