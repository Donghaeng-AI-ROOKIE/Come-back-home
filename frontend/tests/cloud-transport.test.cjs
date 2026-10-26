const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const {webcrypto}=require('node:crypto');
const source=ts.transpileModule(fs.readFileSync(require('node:path').join(__dirname,'../src/api/cloudTransport.ts'),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
}).outputText;
class ApiError extends Error {constructor(status,path,message){super(message);this.status=status;this.path=path}}
function harness(rpc,store=new Map()) {
  const exports={};
  const deps={
    './errors':{ApiError},
    './supabase':{cloudMe:async()=>({user_id:'owner'}),supabase:()=>({rpc})},
    '../store/safeStorage':{safeStorage:{getItem:async k=>store.get(k)??null,setItem:async(k,v)=>store.set(k,v),removeItem:async k=>store.delete(k)}}
  };
  vm.runInNewContext(source,{exports,require:n=>deps[n],crypto:webcrypto,TextEncoder,AbortSignal,Date,Map,Promise,setTimeout});
  return {request:exports.cloudRequest,store};
}
test('auth/password never enters queue',async()=>{
  const h=harness(()=>assert.fail('RPC called'));
  await assert.rejects(h.request('/auth/login',{method:'POST',body:'{"password":"dummy"}'}),{status:400});
});
test('same concurrent mutation submits once',async()=>{
  let submissions=0;
  const h=harness(async(name)=>{
    if(name==='cbh_submit') {submissions++;return {data:'id',error:null}}
    return {data:{state:'done',status_code:200,result:{ok:true}},error:null};
  });
  const init={method:'POST',body:'{"area_label":"synthetic"}'};
  const results=await Promise.all([h.request('/walk/sessions',init),h.request('/walk/sessions',init)]);
  assert.equal(submissions,1);assert.equal(results[0].ok,true);assert.equal(h.store.size,0);
});
test('page reload after timeout retrieves same job without another submit',async()=>{
  const seen=[];const store=new Map();
  const rpc=async(name,args)=>{seen.push([name,args.p_id]);return {data:name==='cbh_result'?{state:'done',status_code:200,result:{ok:true}}:'id',error:null}};
  await assert.rejects(harness(rpc,store).request('/phase2/cases/x/predict',{method:'POST',timeoutMs:0}),{status:0});
  assert.equal(store.size,1);
  const result=await harness(rpc,store).request('/phase2/cases/x/predict',{method:'POST'});
  assert.equal(result.ok,true);assert.equal(seen.filter(x=>x[0]==='cbh_submit').length,1);
  assert.equal(seen[0][1],seen[1][1]);
});
test('interrupted job cannot silently be submitted again',async()=>{
  let count=0;const store=new Map();
  const rpc=async(name)=>{if(name==='cbh_submit')count++;return {data:{state:'interrupted'},error:null}};
  for(let i=0;i<2;i++)await assert.rejects(harness(rpc,store).request('/phase2/cases/x/predict',{method:'POST'}),{status:503});
  assert.equal(count,1);
});
test('API rejection is surfaced, not rendered as success',async()=>{
  const h=harness(async name=>({data:name==='cbh_result'?{state:'done',status_code:404,result:{detail:'no own record'}}:'id',error:null}));
  await assert.rejects(h.request('/phase0/personas/x'),{status:404,message:'no own record'});
});
test('request lost before insert recovers with the same ID after reload',async()=>{
  const store=new Map();const submissions=[];let accepted=false;
  const rpc=async(name,args)=>{
    if(name==='cbh_submit') {
      submissions.push(args.p_id);
      if(submissions.length===1)return {data:null,error:{message:'network unavailable'}};
      accepted=true;return {data:args.p_id,error:null};
    }
    return {data:accepted?{state:'done',status_code:200,result:{ok:true}}:null,error:null};
  };
  await assert.rejects(harness(rpc,store).request('/phase2/cases/x/predict',{method:'POST',timeoutMs:0}),{status:0});
  const result=await harness(rpc,store).request('/phase2/cases/x/predict',{method:'POST'});
  assert.equal(result.ok,true);assert.equal(submissions.length,2);
  assert.equal(submissions[0],submissions[1]);assert.equal(store.size,0);
});
test('missing old request is never resubmitted after retention uncertainty',async()=>{
  const store=new Map();let submissions=0;
  const rpc=async(name)=>{if(name==='cbh_submit')submissions++;return {data:null,error:null}};
  await assert.rejects(harness(rpc,store).request('/phase2/cases/x/predict',{method:'POST',timeoutMs:0}),{status:0});
  for(const [key,value] of store) {
    const record=JSON.parse(value);record.createdAt=Date.now()-3*60*60*1000;
    store.set(key,JSON.stringify(record));
  }
  await assert.rejects(harness(rpc,store).request('/phase2/cases/x/predict',{method:'POST'}),{status:503});
  assert.equal(submissions,1);assert.equal(store.size,1);
});
test('expired family lookup renews once instead of being stuck after reload',async()=>{
  const ids=[];
  const h=harness(async(name,args)=>{
    if(name==='cbh_submit'){ids.push(args.p_id);return {data:args.p_id,error:null};}
    return {data:ids.length===1?{state:'expired'}:{state:'done',status_code:200,result:[{id:'synthetic'}]},error:null};
  });
  const result=await h.request('/phase0/personas');
  assert.equal(result[0].id,'synthetic');assert.equal(ids.length,2);assert.notEqual(ids[0],ids[1]);assert.equal(h.store.size,0);
});
test('stored POA can recover interrupted read but preview and guidance cannot',async()=>{
  for(const [path,expected] of [['/phase3/cases/demo/poa?top=64',2],['/phase3/cases/demo/poa?elapsed_hours=1&top=64',1],['/phase3/cases/demo/guidance',1]]){
    let submitted=0;
    const h=harness(async name=>{if(name==='cbh_submit')submitted++;return {data:{state:'interrupted'},error:null}});
    await assert.rejects(h.request(path),{status:503});assert.equal(submitted,expected);
  }
});
test('old missing family read gets a fresh id, without changing mutation recovery',async()=>{
  const store=new Map();const ids=[];let done=false;
  const rpc=async(name,args)=>{
    if(name==='cbh_submit'){ids.push(args.p_id);done=ids.length>1;return {data:args.p_id,error:null}};
    return {data:done?{state:'done',status_code:200,result:[]}:null,error:null};
  };
  await assert.rejects(harness(rpc,store).request('/phase0/personas',{timeoutMs:0}),{status:0});
  for(const [key,val] of store){const r=JSON.parse(val);r.createdAt-=3*60*60*1000;store.set(key,JSON.stringify(r));}
  assert.equal((await harness(rpc,store).request('/phase0/personas')).length,0);
  assert.equal(ids.length,2);assert.notEqual(ids[0],ids[1]);
});
