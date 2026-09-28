"use strict";
function stress() {
  const refs = [];
  for (let i=0; i<256; i++) {
    let o = {i, buf:new ArrayBuffer(256 + (i & 127))};
    if (typeof WeakRef === "function") refs.push(new WeakRef(o));
    if ((i & 7) === 0) {
      o = null;
      if (typeof gc === "function") gc();
    }
  }
  if (typeof gc === "function") for (let i=0;i<8;i++) gc();
  return refs.length;
}
try { stress(); } catch (_) {}
