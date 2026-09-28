"use strict";

// Standalone seed generated from the fuzzer's conversion-boundary strategy.
function gcBurst() {
  if (typeof gc === "function") { gc(); gc(); }
}

function churn(n) {
  const keep = [];
  for (let i = 0; i < n; i++) {
    keep.push((i & 1) ? new Array(16).fill(i) : new ArrayBuffer(0x200));
  }
  for (let i = 0; i < keep.length; i += 2) keep[i] = null;
  gcBurst();
}

function shapeChurn(o) {
  for (let i = 0; i < 160; i++) {
    const k = "p" + i;
    o[k] = i;
    if ((i & 3) === 1) delete o[k];
  }
  return o;
}

function target(a, x) {
  return a.fill(1, x, x + 2);
}

function warm() {
  const a = new Array(64).fill(0);
  for (let i = 0; i < 2200; i++) {
    try { target(a, i & 31); } catch (_) {}
  }
}

const trigger = {
  [Symbol.toPrimitive](hint) {
    churn(32);
    shapeChurn(this);
    gcBurst();
    return hint === "string" ? "1" : 1;
  }
};

warm();

for (let round = 0; round < 8; round++) {
  const victim = new Array(96).fill(round);
  churn(24);
  shapeChurn(victim);
  try {
    target(victim, trigger);
  } catch (_) {}
  gcBurst();
}
