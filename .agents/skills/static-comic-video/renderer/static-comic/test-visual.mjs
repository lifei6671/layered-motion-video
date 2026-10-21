import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import {motionAt, fadeBlackOpacity} from './dist/motion.js';
import {checkedProps} from './dist/Root.js';
const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url)));
for (const [name,root] of [
  ['clock-360','../../fixtures/visual/clock-360/'],
  ['showcase','../../fixtures/visual/showcase/'],
  ['all-cuts','../../fixtures/visual/all-cuts/'],
]) {
  const props=read(root+'props.json');
  const geometry=read(root+'geometry.json');
  test(name + ': TS motion matches every physical frame in Python geometry', () => {
    checkedProps(props,true);
    for (let i=0;i<props.shots.length;i++) {
      const shot=props.shots[i], expected=geometry.shots[i];
      expected.frames.forEach((frame,local) => {
        const state=motionAt(shot,local);
        assert.equal(state.logicalFrame,frame.logical_frame);
        assert.ok(Math.abs(state.scale-frame.scale)<1e-10);
        state.anchor.forEach((a,axis) => assert.ok(Math.abs(a-frame.anchor[axis])<1e-10));
        const [w,h]=expected.prepared_size;
        const crop=[(w-w/state.scale)*state.anchor[0],(h-h/state.scale)*state.anchor[1],w/state.scale,h/state.scale];
        crop.forEach((v,j)=>assert.ok(Math.abs(v-frame.crop[j])<1e-7));
      });
    }
  });
  test(name + ': production entry rejects technical artifacts', () => {
    assert.throws(()=>checkedProps(props,false),/Technical fixture/);
  });
}
test('fade black has old/black/new endpoints for odd and even durations',()=>{
  for (const n of [3,4,11,12,31,32]) {
    const mid=Math.floor((n-1)/2);
    assert.equal(fadeBlackOpacity('exiting',0,n),1);
    assert.equal(fadeBlackOpacity('entering',0,n),0);
    assert.equal(fadeBlackOpacity('exiting',mid/n,n),0);
    assert.equal(fadeBlackOpacity('entering',mid/n,n),0);
    assert.equal(fadeBlackOpacity('entering',(n-1)/n,n),1);
    assert.equal(fadeBlackOpacity('exiting',1,n),0);
    assert.equal(fadeBlackOpacity('entering',1,n),1);
  }
  for(const n of [1,2]) assert.throws(()=>fadeBlackOpacity('entering',.5,n),/at least 3/);
});
test('holds and one-frame shot remain at the expected discrete endpoints',()=>{
  const props=read('../../fixtures/visual/clock-360/props.json');
  const middle=props.shots[1];
  assert.deepEqual(motionAt(middle,0),motionAt(middle,12));
  assert.equal(motionAt(middle,13).logicalFrame,1);
  assert.deepEqual(motionAt(middle,161),motionAt(middle,173));
  const one=structuredClone(middle);
  one.logical_frames=1;one.head_hold_frames=0;
  assert.equal(motionAt(one,0).scale,one.motion.scale_from);
  assert.equal(motionAt(one,200).scale,one.motion.scale_from);
});
test('composition rejects undersized fade_black before rendering',()=>{
  for (const length of [1,2]) {
    const props=read('../../fixtures/visual/clock-360/props.json');
    props.shots=props.shots.slice(0,2);props.video.total_frames=270;
    const first=props.shots[0],last=props.shots[1];
    Object.assign(first.transition_out,{type:'fade_black',duration_frames:length,pre_frames:length,
      post_frames:0,transition_start_frame:120-length,transition_end_frame:120});
    Object.assign(last,{sequence_start_frame:120-length,head_hold_frames:length,tail_hold_frames:0,
      physical_frames:150+length,transition_out:null});
    assert.throws(()=>checkedProps(props,true),/fade_black requires at least 3 frames/);
  }
});
