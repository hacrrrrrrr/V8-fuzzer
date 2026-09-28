"use strict";
function run() {
  const a = new Array(32).fill(0);
  const indices = [-1, 0, 1, 31, 32, 33, 0x7fffffff, -0x80000000];
  for (const i of indices) {
    try { a[i] = i; void a[i]; } catch (_) {}
  }
  const u = new Uint8Array(64);
  for (const i of indices) {
    try { u[i] = 0x41; void u[i]; } catch (_) {}
  }
}
run();
