import {HistoryManager} from '../../fabric-poc/src/history-manager.mjs';
import {CoverDocument,clone,contentKey} from './model';

export type SaveStatus = 'unsaved'|'saving'|'saved'|'error';
export type EditorSnapshot = {document:CoverDocument; selectedId:string|null; saveStatus:SaveStatus;
  saveError:string; canUndo:boolean; canRedo:boolean; historyLength:number};
export const DRAFT_KEY='cover-studio-v3-draft';
export const RECOVERY_KEY='cover-studio-v3-recovery';
const historyValue=(doc:CoverDocument)=>({...clone(doc),id:null,revision:0,updatedAt:null});
export class DocumentController {
  private history=new HistoryManager(80);
  private listeners=new Set<()=>void>();
  private snapshot:EditorSnapshot;
  private savedKey:string;
  private timer:ReturnType<typeof setTimeout>|undefined;
  private historyTimer:ReturnType<typeof setTimeout>|undefined;
  private inFlight:Promise<void>|null=null;
  private disposed=false;
  private transaction=false;
  constructor(doc:CoverDocument,private request:typeof fetch=fetch,private storage:Pick<Storage,'setItem'>=localStorage,alreadySaved=false) {
    this.savedKey=alreadySaved?contentKey(doc):'';
    this.snapshot={document:doc,selectedId:doc.layers.find(l=>l.id==='title')?.id??null,
      saveStatus:alreadySaved?'saved':'unsaved',saveError:'',canUndo:false,canRedo:false,historyLength:1};
    this.history.reset(historyValue(doc));
  }
  getSnapshot=()=>this.snapshot;
  subscribe=(callback:()=>void)=>{this.listeners.add(callback);return ()=>this.listeners.delete(callback);};
  private emit() {for(const listener of this.listeners)listener();}
  select=(selectedId:string|null)=>{this.snapshot={...this.snapshot,selectedId};this.emit();};
  private draft() {
    try{this.storage.setItem(DRAFT_KEY,JSON.stringify({document:this.snapshot.document,savedKey:this.savedKey}));}
    catch {this.snapshot={...this.snapshot,saveError:'浏览器草稿空间不可用，请等待本机保存完成后关闭。'};}
  }
  private scheduleSave() {
    clearTimeout(this.timer);
    this.timer=setTimeout(()=>{void this.save().catch(()=>{});},750);
  }
  private changed(doc:CoverDocument) {
    this.snapshot={...this.snapshot,document:doc,
      saveStatus:contentKey(doc)===this.savedKey?'saved':'unsaved',saveError:''};
    this.draft();this.emit();this.scheduleSave();
  }
  change=(mutate:(doc:CoverDocument)=>void,record=true)=>{
    const next=clone(this.snapshot.document);mutate(next);
    if(contentKey(next)===contentKey(this.snapshot.document))return;
    this.changed(next);if(record)this.commit();
  };
  commit=()=>{
    this.transaction=false;
    clearTimeout(this.historyTimer);
    this.history.commit(historyValue(this.snapshot.document));
    const status=this.history.getStatus();
    this.snapshot={...this.snapshot,canUndo:status.canUndo,canRedo:status.canRedo,historyLength:status.length};this.emit();
  };
  scheduleCommit=()=>{clearTimeout(this.historyTimer);this.historyTimer=setTimeout(()=>{if(!this.transaction)this.commit();},500);};
  begin=()=>{this.commit();this.transaction=true;};
  undo=()=>{
    this.commit();const value=this.history.undo() as CoverDocument|null;if(!value)return;
    this.restore(value);
  };
  redo=()=>{this.commit();const value=this.history.redo() as CoverDocument|null;if(value)this.restore(value);};
  private restore(value:CoverDocument) {
    const current=this.snapshot.document;
    this.changed({...value,id:current.id,revision:current.revision,updatedAt:current.updatedAt});
    const status=this.history.getStatus();
    this.snapshot={...this.snapshot,canUndo:status.canUndo,canRedo:status.canRedo,historyLength:status.length};this.emit();
  }
  dirty=()=>contentKey(this.snapshot.document)!==this.savedKey;
  save=async():Promise<void>=>{
    clearTimeout(this.timer);if(!this.transaction)this.commit();
    if(this.inFlight){await this.inFlight;if(this.dirty())return this.save();return;}
    if(!this.dirty())return;
    const sent=clone(this.snapshot.document),key=contentKey(sent);
    this.snapshot={...this.snapshot,saveStatus:'saving',saveError:''};this.emit();
    const operation=(async()=>{
      try {
        const request=this.request;
        const response=await request('/api/cover-documents'+(sent.id?'/'+sent.id:''),{
          method:sent.id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(sent),signal:AbortSignal.timeout(30000)});
        const payload=await response.json();if(!response.ok)throw Error(payload.error||'保存失败，请重试。');
        const saved=payload.document as CoverDocument;
        this.savedKey=key;
        // Keep edits made while this request was in flight.
        this.snapshot={...this.snapshot,document:{...this.snapshot.document,id:saved.id,revision:saved.revision,updatedAt:saved.updatedAt},
          saveStatus:contentKey(this.snapshot.document)===key?'saved':'unsaved',saveError:''};
        this.draft();this.emit();
      } catch(error) {
        this.snapshot={...this.snapshot,saveStatus:'error',saveError: error instanceof Error?error.message:String(error)};
        this.draft();this.emit();throw error;
      }
    })();
    this.inFlight=operation;
    try{await operation;}finally{this.inFlight=null;}
    if(this.dirty()&&!this.disposed)this.scheduleSave();
  };
  replace=async(doc:CoverDocument,saved=false,saveCurrent=true,autoSave=true)=>{
    if(saveCurrent){while(this.dirty())await this.save();}
    else if(this.inFlight)await this.inFlight.catch(()=>{});
    clearTimeout(this.timer);clearTimeout(this.historyTimer);
    this.savedKey=saved?contentKey(doc):'';
    this.history.reset(historyValue(doc));
    this.snapshot={document:doc,selectedId:doc.layers.find(l=>l.type==='text')?.id??null,
      saveStatus:saved?'saved':'unsaved',saveError:'',canUndo:false,canRedo:false,historyLength:1};
    this.draft();this.emit();
    if(!saved&&autoSave)this.scheduleSave();
  };
  dispose=()=>{this.disposed=true;clearTimeout(this.timer);clearTimeout(this.historyTimer);this.listeners.clear();};
}
