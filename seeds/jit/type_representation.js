"use strict";
function hot(x) {
  const a = [1,2,3,4];
  for (let i=0;i<400;i++) {
    a[0] = (i & 3) === 0 ? x : i;
    a[1] = i + 0.5;
    if ((i & 31) === 0) a[2] = {};
  }
  return a[0];
}
for (const x of [1, 1.5, "x", null, {}, true]) {
  try { for (let i=0;i<10;i++) hot(x); } catch (_) {}
}
