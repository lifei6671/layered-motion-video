import {useRef,useState} from 'react';
import {Trash,CircleNotch} from '@phosphor-icons/react';
import {IconButton} from './controls';
import {Popover,PopoverContent,PopoverTrigger} from './ui/popover';

export function DeleteEntryButton({name,template,onDelete}:{name:string;template:boolean;onDelete:()=>Promise<void>}) {
  const [open,setOpen]=useState(false),[deleting,setDeleting]=useState(false),[error,setError]=useState('');
  const restoringFocus=useRef(false);
  const kind=template?'模板':'设计';
  async function remove(){
    if(deleting)return;setDeleting(true);setError('');
    try{await onDelete();setOpen(false);}catch(error){setError(error instanceof Error?error.message:String(error));}finally{setDeleting(false);}
  }
  return <Popover modal open={open} onOpenChange={next=>{if(!deleting){setOpen(next);setError('');}}}>
    <PopoverTrigger asChild><IconButton className={'icon-button entry-delete'+(deleting?' deleting':'')} icon={deleting?CircleNotch:Trash} label={'删除'+kind+' '+name} aria-busy={deleting} onFocus={e=>{if(restoringFocus.current)e.preventDefault();}} onKeyDown={e=>e.stopPropagation()}/></PopoverTrigger>
    <PopoverContent className="entry-delete-popover" side="right" align="center" aria-label={'删除'+kind+'确认'} onCloseAutoFocus={()=>{
      // Keep Radix focus restoration, but do not reopen the tooltip for that focus event.
      restoringFocus.current=true;queueMicrotask(()=>{restoringFocus.current=false;});
    }} onKeyDown={e=>e.stopPropagation()} onInteractOutside={e=>{if(deleting)e.preventDefault();}} onEscapeKeyDown={e=>{if(deleting)e.preventDefault();}}>
      <h3>删除这个{kind}？</h3><p>{name}</p>{error&&<p role="alert" className="delete-error">{error}</p>}
      <div className="delete-popover-actions"><button className="secondary-button" disabled={deleting} onClick={()=>setOpen(false)}>取消</button><button className="danger-button" disabled={deleting} onClick={()=>{void remove();}}>{deleting?<><CircleNotch className="delete-spinner" size={14}/>正在删除…</>:'确认删除'}</button></div>
    </PopoverContent>
  </Popover>;
}
