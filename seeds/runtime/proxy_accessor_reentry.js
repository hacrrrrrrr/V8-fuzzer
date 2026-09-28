"use strict";
let n=0;
const target={a:1,b:2};
const p=new Proxy(target,{
  get(t,k,r){n++;if(n&1)t["p"+n]=n;return Reflect.get(t,k,r)},
  set(t,k,v,r){if(n>16)delete t.b;return Reflect.set(t,k,v,r)}
});
for(let i=0;i<128;i++){try{void p.a;p["k"+i]=i}catch(_){}}
