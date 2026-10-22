import {test} from 'node:test';
import assert from 'node:assert/strict';
import {newDocument,contentKey,screenToDocument,resizeDocument,reorderLayer,duplicateLayer} from '../.test-build/model.mjs';
import {migrateScene} from '../.test-build/migration.mjs';
import {DocumentController} from '../.test-build/controller.mjs';
const fid='local:test';const storage={setItem(){}};
test('screen conversion includes scroll origin and never writes zoom into frames',()=>{
  for(const scale of [.1,.25,.5,1,2]){
    const point=screenToDocument({x:310+620*scale,y:-220+400*scale},{left:310,top:-220,width:1920*scale,height:1080*scale},{width:1920,height:1080});
    assert.deepEqual(point,{x:620,y:400});
  }
});
test('layer ordering, duplication and ratio dimensions preserve data',()=>{
  const doc=newDocument(fid),original=structuredClone(doc);reorderLayer(doc,'title',0);assert.equal(doc.layers[0].id,'title');
  const id=duplicateLayer(doc,'title');assert.notEqual(id,'title');assert.equal(doc.layers.at(-1).text,'认知的盲区');
  resizeDocument(doc,960,540);assert.equal(doc.layers[0].frame.x,original.layers.at(-1).frame.x/2);assert.equal(doc.width,960);
  assert.equal(contentKey({...doc,id:'server-id',revision:8,updatedAt:'today'}),contentKey(doc));
});
test('legacy v2 percent positions/styles/group state migrate without editing original',()=>{
  const style={fontSize:80,fill:'#ff0000',opacity:.7,stroke:'#ffffff',strokeWidth:3,charSpacing:100,lineHeight:1.2,shadow:{enabled:true,color:'#000000',opacity:.5,blur:10,offsetX:2,offsetY:3}};
  const scene={schemaVersion:2,name:'原设计',activeRatio:'16:9',content:{title:'原始标题',subtitle:'副标题',account:'账号'},
    fontRefs:{title:fid,subtitle:fid},backgroundStyle:{darkness:78,focusY:30},assets:{background:{source:'managed',id:'a'.repeat(64)+'.png'},avatar:{source:'none'}},
    variants:{'16:9':{title:{mode:'manual',x:20,y:30}}},layers:[{id:'background',visible:true,locked:true,zIndex:0,style:{}},
      ...['title','subtitle','account'].map((id,i)=>({id,visible:true,locked:false,zIndex:20+i*10,style}))],
    extras:{groups:[{id:'group',visible:false,locked:true}],layers:[{id:'extra',name:'额外文字',type:'text',fontId:fid,text:'文字',groupId:'group',visible:true,locked:false,zIndex:50,style:{fontSize:30,fill:'#ffffff',opacity:.8},frame:{x:10,y:10,width:30,height:20,angle:0},ratioFrames:{}}]}};
  const before=JSON.stringify(scene),doc=migrateScene(scene,(text,id,size,spacing)=>[...text].length*(size+spacing));
  const title=doc.layers.find(l=>l.id==='title');assert.equal(title.frame.x,384);assert.equal(title.frame.y,324);assert.equal(title.strokeWidth,3);assert.equal(title.letterSpacing,8);assert.equal(title.shadow.x,2);
  const extra=doc.layers.find(l=>l.id==='extra');assert.equal(extra.visible,false);assert.equal(extra.locked,true);assert.equal(extra.frame.width,576);
  assert.equal(JSON.stringify(scene),before);assert.deepEqual(doc.sourceScene,scene);
});
test('a drag including a save is exactly one history command; revisions survive undo',async()=>{
  const doc=newDocument(fid);let rev=0;
  const request=async(url,options)=>({ok:true,json:async()=>({document:{...JSON.parse(options.body),id:'a'.repeat(32),revision:++rev,updatedAt:'now'}})});
  const c=new DocumentController(doc,request,storage);c.begin();
  for(let i=0;i<20;i++)c.change(d=>{d.layers.at(-1).frame.x=400+i;},false);
  await c.save();assert.equal(c.getSnapshot().historyLength,1);c.commit();assert.equal(c.getSnapshot().historyLength,2);
  c.undo();assert.equal(c.getSnapshot().document.layers.at(-1).frame.x,300);assert.equal(c.getSnapshot().document.revision,1);c.redo();assert.equal(c.getSnapshot().document.layers.at(-1).frame.x,419);c.dispose();
});
test('save response cannot overwrite newer edits and next save uses latest revision',async()=>{
  let resolve;const calls=[];
  const request=(url,options)=>{calls.push(JSON.parse(options.body));return new Promise(r=>{resolve=()=>r({ok:true,json:async()=>({document:{...calls.at(-1),id:'b'.repeat(32),revision:calls.length,updatedAt:'now'}})});});};
  const c=new DocumentController(newDocument(fid),request,storage);
  c.change(d=>{d.name='第一版';});const save=c.save();c.change(d=>{d.name='保存期间的新编辑';});resolve();await save;
  assert.equal(c.getSnapshot().document.name,'保存期间的新编辑');assert.equal(c.dirty(),true);
  const next=c.save();assert.equal(calls[1].revision,1);assert.equal(calls[1].name,'保存期间的新编辑');resolve();await next;assert.equal(c.dirty(),false);c.dispose();
});
test('save failure preserves draft, allows retry, and conflict can be saved as a new copy',async()=>{
  let fail=true;const draft=[];
  const request=async(url,options)=>({ok:!fail,json:async()=>fail?{error:'文档版本已更新'}:{document:{...JSON.parse(options.body),id:'c'.repeat(32),revision:1,updatedAt:'now'}}});
  const c=new DocumentController(newDocument(fid),request,{setItem(k,v){draft.push(v);}});c.change(d=>{d.name='必须保留的编辑';});
  await assert.rejects(c.save(),/版本已更新/);assert.equal(c.getSnapshot().saveStatus,'error');assert.equal(JSON.parse(draft.at(-1)).document.name,'必须保留的编辑');
  const copy=structuredClone(c.getSnapshot().document);copy.id=null;copy.revision=0;await c.replace(copy,false,false);fail=false;await c.save();assert.equal(c.getSnapshot().saveStatus,'saved');c.dispose();
});
test('redo cannot discard a pending continuous edit after undo',()=>{
  const c=new DocumentController(newDocument(fid),async()=>{throw Error('unused');},storage,true);
  c.change(d=>{d.name='B';});c.undo();c.change(d=>{d.name='C';},false);c.scheduleCommit();c.redo();
  assert.equal(c.getSnapshot().document.name,'C');assert.equal(c.getSnapshot().canRedo,false);c.undo();assert.equal(c.getSnapshot().document.name,'认知盲区 - 叙事封面');c.redo();assert.equal(c.getSnapshot().document.name,'C');c.dispose();
});
test('long layer names duplicate inside the server limit',()=>{
  const doc=newDocument(fid);doc.layers.at(-1).name='长'.repeat(70);duplicateLayer(doc,'title');assert.equal(doc.layers.at(-1).name.length,70);
  doc.layers.find(l=>l.id==='title').name='字'.repeat(66)+'😀末尾';duplicateLayer(doc,'title');assert.ok(!doc.layers.at(-1).name.includes('\ud83d 副本'));assert.equal(Array.from(doc.layers.at(-1).name).length,70);
});

test('repeated landscape/portrait changes preserve valid reversible font sizes',()=>{
  const doc=newDocument(fid),before=doc.layers.map(l=>l.fontSize);
  for(let i=0;i<12;i++){resizeDocument(doc,1080,1920);resizeDocument(doc,1920,1080);}
  assert.deepEqual(doc.layers.map(l=>l.fontSize),before);
  resizeDocument(doc,100,100);assert.ok(doc.layers.every(l=>l.fontSize>=8));
});
test('legacy migration preserves extreme spacing and free-layer semantics',()=>{
  const scene={schemaVersion:2,name:'长'.repeat(70),activeRatio:'16:9',content:{title:'标题',subtitle:'副标题',account:''},fontRefs:{title:fid,subtitle:fid},backgroundStyle:{darkness:0,focusY:50,glow:true},
    assets:{background:{source:'none'},avatar:{source:'managed',id:'a'.repeat(64)+'.png'}},variants:{'16:9':{}},layers:[{id:'background',visible:true,locked:true,zIndex:0},{id:'avatar',visible:true,locked:true,zIndex:10},{id:'title',visible:true,locked:false,zIndex:20,style:{fontSize:400,charSpacing:1000}},{id:'subtitle',visible:true,locked:false,zIndex:30,style:{fontSize:36}},{id:'account',visible:true,locked:false,zIndex:40}],
    extras:{groups:[],layers:[{id:'custom',name:'文字',type:'text',text:'自由文字',fontId:fid,visible:true,locked:false,zIndex:50,frame:{x:0,y:0,width:50,height:30,angle:0,scaleY:2},ratioFrames:{},style:{fontSize:58,fill:'#ffffff',opacity:1}}]}};
  const doc=migrateScene(scene,(s,f,size,spacing)=>s.length*size);assert.ok(doc.name.length<=70);assert.equal(doc.layers.find(l=>l.id==='title').letterSpacing,400);
  const free=doc.layers.find(l=>l.id==='custom');assert.equal(free.textScaleY,2);assert.equal(free.align,'left');assert.equal(free.lineHeight,1.1);
  const avatar=doc.layers.find(l=>l.id==='avatar');assert.equal(avatar.frame.width,252);assert.equal(avatar.frame.x,1524);assert.equal(avatar.frame.y,788);
});

test('legacy left/top rotation pivots and subtitle group offsets migrate into center frames',()=>{
  const scene={schemaVersion:2,name:'旋转',activeRatio:'16:9',content:{subtitle:'短'},fontRefs:{subtitle:fid},backgroundStyle:{darkness:0,focusY:50},assets:{},
    variants:{'16:9':{subtitle:{mode:'manual',x:20,y:20}}},layers:[{id:'subtitle',visible:true,locked:false,zIndex:30,style:{fontSize:36,angle:0}}],
    extras:{groups:[],layers:[{id:'rotated',name:'矩形',type:'rect',visible:true,locked:false,zIndex:50,frame:{x:20,y:20,width:30,height:20,angle:90},ratioFrames:{},style:{fill:'#ffffff',opacity:1}}]}};
  const measured=(text,font,size)=>text.length*size;
  const doc=migrateScene(scene,measured),rect=doc.layers.find(l=>l.id==='rotated'),sub=doc.layers.find(l=>l.id==='subtitle'),rule=doc.layers.find(l=>l.id==='subtitle-rule');
  assert.ok(Math.abs(rect.frame.x-(-12))<1e-8);assert.ok(Math.abs(rect.frame.y-396)<1e-8);
  assert.ok(Math.abs(sub.frame.x-(384+(1171.2-38)/2+1.6))<1e-8);assert.equal(sub.frame.y,216);
  assert.ok(Math.abs(rule.frame.x-384)<1e-8);assert.ok(Math.abs(rule.frame.width-1174.4)<1e-8);
  scene.layers[0].style.angle=20;
  const rotated=migrateScene(scene,measured),text=rotated.layers.find(l=>l.id==='subtitle');
  const a=20*Math.PI/180,dx=(1171.2-38)/2+1.6;
  assert.ok(Math.abs((text.frame.x+text.frame.width/2)-(384+(dx+19)*Math.cos(a)-text.frame.height/2*Math.sin(a)))<1e-8);
});


test('paused slider gesture and autosave remain one undo command',async()=>{
  const request=async(url,options)=>({ok:true,json:async()=>({document:{...JSON.parse(options.body),id:'d'.repeat(32),revision:1,updatedAt:'now'}})});
  const c=new DocumentController(newDocument(fid),request,storage,true);
  c.begin();c.change(d=>{d.layers.at(-1).opacity=.5;},false);c.scheduleCommit();
  await new Promise(resolve=>setTimeout(resolve,560));assert.equal(c.getSnapshot().historyLength,1);
  await c.save();assert.equal(c.getSnapshot().historyLength,1);
  c.change(d=>{d.layers.at(-1).opacity=.7;},false);c.commit();assert.equal(c.getSnapshot().historyLength,2);
  c.undo();assert.equal(c.getSnapshot().document.layers.at(-1).opacity,1);c.dispose();
});
test('circle images stay square on aspect ratio changes',()=>{
  const doc=newDocument(fid),l=doc.layers[0];l.imageShape='circle';l.frame.width=l.frame.height=300;
  for(let i=0;i<5;i++){resizeDocument(doc,1080,1920);assert.equal(l.frame.width,300);assert.equal(l.frame.height,300);resizeDocument(doc,1920,1080);assert.equal(l.frame.width,300);assert.equal(l.frame.height,300);}
  resizeDocument(doc,960,540);assert.equal(l.frame.width,150);resizeDocument(doc,1920,1080);assert.equal(l.frame.width,300);
});
test('reset after deleting active design does not recreate it automatically',async()=>{
  let saves=0;const c=new DocumentController(newDocument(fid),async()=>{saves++;throw Error('unwanted save');},storage,true);
  const empty=newDocument(fid);empty.layers=[];await c.replace(empty,false,false,false);
  await new Promise(resolve=>setTimeout(resolve,800));assert.equal(saves,0);assert.equal(c.getSnapshot().document.id,null);c.dispose();
});
