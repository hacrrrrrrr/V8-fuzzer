"use strict";
const locales=["fa-IR-u-ca-persian","en-US-u-ca-gregory","ar-EG-u-nu-arab"];
const dates=[0,-62135596800000,2147483647,4102444800000];
for(const locale of locales)for(const t of dates){
  try{
    const d=new Date(t);
    const f=new Intl.DateTimeFormat(locale,{year:"numeric",month:"long",day:"numeric",weekday:"long"});
    f.format(d);f.resolvedOptions();f.formatRange(d,new Date(t+86400000));
  }catch(_){}
}