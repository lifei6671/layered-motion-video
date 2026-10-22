import {Stack,Images,TextT,Shapes,Keyboard,SlidersHorizontal,SquareHalf} from '@phosphor-icons/react';
import {Hint} from './controls';
export type Tool='templates'|'background'|'text'|'assets'|'layers';
const tools=[['templates','模板',SquareHalf],['background','背景',Images],['text','文字',TextT],['assets','素材',Shapes],['layers','图层',Stack]] as const;
export function ToolSidebar({tool,onTool,onHelp,onSettings}:{tool:Tool;onTool:(v:Tool)=>void;onHelp:()=>void;onSettings:()=>void}) {
  return <nav className="tool-sidebar" aria-label="编辑工具"><div>{tools.map(([id,name,Icon])=><button key={id} className={tool===id?'selected':''} aria-current={tool===id?'page':undefined} onClick={()=>onTool(id)}><Icon size={24}/><span>{name}</span></button>)}</div>
    <div><Hint content="快捷键帮助" side="right"><button aria-label="快捷键帮助" onClick={onHelp}><Keyboard size={22}/></button></Hint><Hint content="画布偏好设置" side="right"><button aria-label="画布偏好设置" onClick={onSettings}><SlidersHorizontal size={22}/></button></Hint></div></nav>;
}
