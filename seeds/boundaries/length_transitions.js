"use strict";
const a = [];
for (let i = 0; i < 512; i++) {
  try {
    a.length = i;
    if ((i & 7) === 0) a.push(i);
    if ((i & 15) === 0) a.length = i >>> 1;
    Object.defineProperty(a, "x", {value:i, configurable:true, writable:true});
    delete a.x;
  } catch (_) {}
}
