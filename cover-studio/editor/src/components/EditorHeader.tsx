import {ArrowCounterClockwise,ArrowClockwise,Stack,DownloadSimple,Eye,FloppyDisk,GridFour,CircleNotch,Check,WarningCircle} from '@phosphor-icons/react';
import {DocumentController,EditorSnapshot} from '../controller';
import {RATIOS,resizeDocument} from '../model';
import {IconButton,Hint} from './controls';
import {Select,SelectContent,SelectGroup,SelectItem,SelectLabel,SelectTrigger,SelectValue} from './ui/select';
import {useEffect,useState} from 'react';
import {measureTextLayer} from '../fonts';
function RatioPreview({width,height}:{width:number;height:number}) {
  const scale=28/Math.max(width,height);
  return <span className="ratio-preview" aria-hidden="true"><span className="ratio-rectangle" style={{width:width*scale,height:height*scale}}/></span>;
}
export function EditorHeader({controller,snapshot,onExport,onPreview,onGrid,grid,busy}:{controller:DocumentController;snapshot:EditorSnapshot;onExport:()=>void;onPreview:()=>void;onGrid:()=>void;grid:boolean;busy:boolean}) {
  const doc=snapshot.document;
  const [name,setName]=useState(doc.name);
  const [saveFeedback,setSaveFeedback]=useState<'idle'|'saving'|'saved'|'error'>('idle');
  useEffect(()=>setName(doc.name),[doc.name]);
  useEffect(()=>{if(saveFeedback==='saved'||saveFeedback==='error'){const timer=setTimeout(()=>setSaveFeedback('idle'),1600);return ()=>clearTimeout(timer);}},[saveFeedback]);
  const ratio=Object.keys(RATIOS).find(r=>RATIOS[r][0]===doc.width&&RATIOS[r][1]===doc.height)||'custom';
  const labels={unsaved:'待保存',saving:'保存中…',saved:'已保存',error:'保存失败 · 点击重试'};
  const savePhase=saveFeedback==='saving'||snapshot.saveStatus==='saving'?'saving':snapshot.saveStatus==='error'?'error':saveFeedback;
  const SaveIcon=savePhase==='saving'?CircleNotch:savePhase==='saved'?Check:savePhase==='error'?WarningCircle:FloppyDisk;
  const saveHint=savePhase==='saving'?'正在保存到本机…':savePhase==='saved'?'已保存到本机':savePhase==='error'?(snapshot.saveError||'保存失败，点击重试'):'保存到本机（Ctrl+S）';
  async function save(){
    if(savePhase==='saving')return;
    setSaveFeedback('saving');
    try{await Promise.all([controller.save(),new Promise(resolve=>setTimeout(resolve,350))]);setSaveFeedback('saved');}
    catch{setSaveFeedback('error');}
  }
  return <header className="editor-header">
    <div className="header-start"><div className="brand-mark"><Stack size={24}/></div><strong className="brand-name">Cover Studio</strong><i className="divider"/>
      <input className="document-name" aria-label="设计名称" maxLength={70} value={name} onBlur={()=>setName(controller.getSnapshot().document.name)} onChange={e=>{const value=e.target.value;setName(value);if(value.trim()){controller.change(d=>{d.name=value;},false);controller.scheduleCommit();}}}/>
      <Hint content={snapshot.saveError||'Ctrl+S 立即保存'} side="bottom"><button className={'save-status '+snapshot.saveStatus} onClick={()=>{void controller.save().catch(()=>{});}}><span/>{labels[snapshot.saveStatus]}</button></Hint>
    </div>
    <div className="header-center"><div className="button-group"><IconButton icon={ArrowCounterClockwise} label="撤销 (Ctrl+Z)" disabled={!snapshot.canUndo} onClick={controller.undo}/><IconButton icon={ArrowClockwise} label="重做 (Ctrl+Shift+Z)" disabled={!snapshot.canRedo} onClick={controller.redo}/></div>
      <Select value={ratio} onValueChange={value=>{const dimensions=RATIOS[value];if(dimensions)controller.change(d=>resizeDocument(d,...dimensions,measureTextLayer));}}>
        <SelectTrigger className="ratio-picker" aria-label="画布比例"><SelectValue><span className="ratio-current"><RatioPreview width={doc.width} height={doc.height}/><span>{ratio==='custom'?'自定义':ratio+' 封面'} <small>({doc.width}×{doc.height})</small></span></span></SelectValue></SelectTrigger>
        <SelectContent align="start"><SelectGroup><SelectLabel>封面画幅</SelectLabel>
          {ratio==='custom'&&<SelectItem value="custom" textValue="自定义画幅"><span className="ratio-option"><RatioPreview width={doc.width} height={doc.height}/><span><strong>自定义</strong><small>{doc.width} × {doc.height} px</small></span></span></SelectItem>}
          {Object.entries(RATIOS).map(([r,[w,h]])=><SelectItem key={r} value={r} textValue={r+' 封面'}><span className="ratio-option"><RatioPreview width={w} height={h}/><span><strong>{r} <em>{w===h?'方形':w>h?'横版':'竖版'}</em></strong><small>{w} × {h} px</small></span></span></SelectItem>)}
        </SelectGroup></SelectContent>
      </Select><IconButton icon={GridFour} label="辅助网格" active={grid} onClick={onGrid}/>
    </div>
    <div className="header-end"><button className="text-button" onClick={onPreview}><Eye size={19}/>预览</button><button className="primary-button" onClick={onExport} disabled={busy}><DownloadSimple size={19}/>{busy?'导出中…':'导出封面'}</button><i className="divider"/><Hint content={saveHint} disabled={savePhase==='saving'} side="bottom"><button className="local-badge" data-feedback={savePhase} aria-label="本机存储" aria-busy={savePhase==='saving'} disabled={savePhase==='saving'} onClick={()=>{void save();}}><span key={savePhase} className="save-glyph"><SaveIcon size={19}/></span></button></Hint></div>
  </header>;
}
