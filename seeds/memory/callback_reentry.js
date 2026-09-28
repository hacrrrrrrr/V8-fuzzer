"use strict";
const a = new Array(128).fill(1);
const x = {
  valueOf() {
    const garbage = [];
    for (let i=0;i<64;i++) garbage.push(new ArrayBuffer(256+i));
    if (typeof gc === "function") gc();
    a.length = 1 + (a.length & 127);
    a[0] = "transition";
    return 1;
  }
};
function target() { return a.fill(7, x, x); }
for (let i=0;i<300;i++) { try { target(); } catch (_) {} }
