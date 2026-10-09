const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),ts=require('typescript'),h3=require('h3-js');
function load(file,deps){
 const exports={};
 const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/'+file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,{exports,require:n=>deps[n],Date,Number});
 return exports;
}
const grid=load('utils/h3cell.ts',{'h3-js':h3});
const {enteredTargets}=load('utils/webPushEntry.ts',{'./h3cell':grid});
const point={lat:37.6688,lng:126.7457},now=Date.now(),cell=h3.latLngToCell(point.lat,point.lng,7);
const targets=[{case_id:'case-a',cells:[cell],resolution:7}];
test('existing server-selected notification cells match at their declared resolution',()=>{
 assert.equal(enteredTargets(point,10,now,targets,now).join(','),'case-a');
 assert.equal(enteredTargets({lat:37.70,lng:126.80},10,now,targets,now).length,0);
});
test('missing, stale, future and imprecise positions never trigger entry',()=>{
 for(const [p,a,t] of [[null,10,now],[point,null,now],[point,NaN,now],[point,81,now],[point,10,now-60001],[point,10,now+1]])
  assert.equal(enteredTargets(p,a,t,targets,now).length,0);
});
function worker(windows=[]){
 const events={},opened=[],shown=[];
 const self={addEventListener:(name,fn)=>events[name]=fn,skipWaiting:()=>{},
 clients:{claim:async()=>{},matchAll:async()=>windows,openWindow:async url=>opened.push(url)},
 registration:{showNotification:async(title,options)=>shown.push({title,options})}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../public/sw.js'),'utf8'),{self});
 return {events,opened,shown};
}
test('push shows title/body and click focuses existing app and routes to the case',async()=>{
 const messages=[];let focused=0;
 const w=worker([{focus:async()=>focused++,postMessage:m=>messages.push(m)}]);
 let pending;
 w.events.push({data:{json:()=>({title:'synthetic',body:'test',data:{case_id:'case-a'}})},waitUntil:p=>pending=p});
 await pending; assert.equal(w.shown[0].options.data.case_id,'case-a');
 w.events.notificationclick({notification:{close(){},data:{case_id:'case-a'}},waitUntil:p=>pending=p});
 await pending;assert.equal(focused,1);assert.equal(messages[0].case_id,'case-a');assert.equal(w.opened.length,0);
});
test('cold notification click preserves case without allowing arbitrary redirect',async()=>{
 for(const [id,want] of [['case-a','/?case_id=case-a'],['https://evil.test','/']]){
  const w=worker();let pending;
  w.events.notificationclick({notification:{close(){},data:{case_id:id}},waitUntil:p=>pending=p});
  await pending;assert.equal(w.opened[0],want);
 }
});
