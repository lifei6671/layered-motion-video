export class HistoryManager {
  constructor(limit = 80) { this.limit = limit; this.records = []; this.cursor = -1; }
  reset(scene) { this.records = [JSON.stringify(scene)]; this.cursor = 0; }
  commit(scene) {
    const value = JSON.stringify(scene);
    if (value === this.records[this.cursor]) return false;
    this.records = this.records.slice(0, this.cursor + 1);
    this.records.push(value);
    if (this.records.length > this.limit) this.records.shift();
    this.cursor = this.records.length - 1;
    return true;
  }
  canUndo() { return this.cursor > 0; }
  canRedo() { return this.cursor >= 0 && this.cursor < this.records.length - 1; }
  undo() { return this.canUndo() ? JSON.parse(this.records[--this.cursor]) : null; }
  redo() { return this.canRedo() ? JSON.parse(this.records[++this.cursor]) : null; }
  getStatus() { return { canUndo:this.canUndo(), canRedo:this.canRedo(), length:this.records.length, cursor:this.cursor }; }
}
