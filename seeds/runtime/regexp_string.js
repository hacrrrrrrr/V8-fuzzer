"use strict";
const strings=["a".repeat(64)+"!","0123456789".repeat(64),"\uD800".repeat(32)];
const patterns=[/(a+)+$/,(?:\uD800)+/g,/(.+)+$/];
for(const s of strings)for(const r of patterns){try{r.test(s);s.replace(r,"x");s.match(r)}catch(_){}}
