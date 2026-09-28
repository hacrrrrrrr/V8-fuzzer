"use strict";
function C(){this.x=1}
const a=new C(), b=new C();
for(let i=0;i<500;i++){
  try {
    if(i&1){ C.prototype.y=i; } else { delete C.prototype.y; }
    if(i%3===0) Object.setPrototypeOf(a,{x:i});
    a.x=i; b.x=i;
    void a.y; void b.y;
  } catch(_){}
}
