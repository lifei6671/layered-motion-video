import {useState} from 'react';
import {MagnifyingGlass,CaretDown,Check,ArrowClockwise} from '@phosphor-icons/react';
import {FontEntry} from '../model';
import {Hint,IconButton} from './controls';
export function FontPicker({fonts,value,onSelect,onRefresh,disabled=false}:{fonts:FontEntry[];value:string;onSelect:(font:FontEntry)=>void;onRefresh:()=>void;disabled?:boolean}) {
  const [open,setOpen]=useState(false),[search,setSearch]=useState('');
  const current=fonts.find(f=>f.id===value);
  const families=new Map<string,FontEntry>();
  for(const f of fonts){const key=f.family||f.name;if(!families.has(key)||f.id===value||(f.weight===400&&families.get(key)!.weight!==400))families.set(key,f);}
  const matches=[...families.values()].filter(f=>(f.family+' '+f.name).toLowerCase().includes(search.toLowerCase())).sort((a,b)=>Number(b.source==='local')-Number(a.source==='local'));
  return <div className="font-picker"><Hint content={current?.family||current?.name||'选择字体家族'} disabled={disabled}><button className="font-trigger" disabled={disabled} aria-expanded={open} aria-label="选择字体家族" onClick={()=>setOpen(!open)}>
    {current?<>{current.sample!==''&&<img alt={current.family||current.name} src={'/api/font-preview?compact=1&id='+encodeURIComponent(current.id)}/>}<span>{current.family||current.name.split(' · ')[0]}</span><small>{current.source==='local'?'内置':'系统'}</small></>:<span>选择可用字体</span>}<CaretDown size={14}/></button></Hint>
    {open&&<><button className="popover-backdrop" aria-label="关闭字体列表" onClick={()=>setOpen(false)}/><div className="font-popover" role="dialog" aria-label="字体列表">
      <div className="font-search"><MagnifyingGlass size={16}/><input autoFocus aria-label="搜索字体" placeholder="搜索字体家族…" value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')setOpen(false);}}/><IconButton icon={ArrowClockwise} label="刷新字体目录" onClick={onRefresh}/></div>
      <div className="font-results">{matches.map(f=><button key={f.id} disabled={f.sample===''} className={(current?.family?current.family===f.family:current?.id===f.id)?'chosen':''} onClick={()=>{onSelect(f);setOpen(false);}}>
        {f.sample!==''?<img loading="lazy" alt={f.sample||f.name} src={'/api/font-preview?compact=1&id='+encodeURIComponent(f.id)}/>:<small>无法预览</small>}<span>{f.family||f.name}<small>{f.source==='local'?'内置字体':'系统字体'}{f.sample===''?' · '+f.label:''}</small></span>{value===f.id&&<Check size={16}/>}</button>)}{!matches.length&&<p className="empty-state">没有匹配的字体</p>}</div>
    </div></>}
  </div>;
}
