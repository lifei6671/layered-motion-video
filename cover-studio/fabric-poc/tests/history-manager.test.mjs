import test from "node:test";
import assert from "node:assert/strict";
import {HistoryManager} from "../src/history-manager.mjs";

test("单步提交、重复操作去重和撤销重做",()=>{
  const history=new HistoryManager(5);
  history.reset({title:"甲",ratio:"3:4"});
  assert.equal(history.commit({title:"甲",ratio:"3:4"}),false);
  assert.equal(history.commit({title:"乙",ratio:"3:4"}),true);
  assert.equal(history.getStatus().length,2);
  assert.equal(history.undo().title,"甲");
  assert.equal(history.redo().title,"乙");
});

test("撤销后出现新操作，旧的重做分支失效",()=>{
  const history=new HistoryManager(5);
  history.reset({title:"甲"});
  history.commit({title:"乙"});
  history.commit({title:"丙"});
  assert.equal(history.undo().title,"乙");
  history.commit({title:"丁"});
  assert.equal(history.canRedo(),false);
  assert.equal(history.undo().title,"乙");
  assert.equal(history.redo().title,"丁");
});

test("历史容量限制与深度快照隔离",()=>{
  const history=new HistoryManager(3);
  const scene={content:{title:"开始"}};
  history.reset(scene);
  scene.content.title="第二版";
  history.commit(scene);
  scene.content.title="第三版";
  history.commit(scene);
  scene.content.title="第四版";
  history.commit(scene);
  assert.equal(history.getStatus().length,3);
  assert.equal(history.undo().content.title,"第三版");
  assert.equal(history.undo().content.title,"第二版");
  assert.equal(history.undo(),null);
});
