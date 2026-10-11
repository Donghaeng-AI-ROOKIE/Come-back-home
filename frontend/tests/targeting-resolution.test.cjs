const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),ts=require('typescript'),h3=require('h3-js');
function load(file,deps={}){
 const exports={};
 const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/'+file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,{exports,require:n=>deps[n]??{},Date,Number,setTimeout});
 return exports;
}
const policy=load('utils/targetingPolicy.ts');
const grid=load('utils/h3cell.ts',{'h3-js':h3});
const {enteredTargets}=load('utils/webPushEntry.ts',{'./h3cell':grid});
const point={lat:37.6688,lng:126.7457};
for(const res of [7,8,9]) test(`server res${res} drives API registration, lookup and entry`,async()=>{
 const requests=[];
 const client=load('api/client.ts',{'../utils/targetingPolicy':policy,'./config':{USE_MOCK:false,
  api:async(url,options)=>{requests.push({url,options});return url==='/phase3/webpush/public-key'
   ?{target_res:res,coverage:.95,targeting_policy:'selected_coverage_geographic_cover_v1',location_ttl_seconds:300}:[];}}});
 const metadata=await client.getTargetingPolicy();
 const cell=grid.cellOf(point,policy.targetingResolution(metadata));
 assert.equal(h3.getResolution(cell),res);
 await client.registerDevice('synthetic-token','android',cell);
 const body=JSON.parse(requests[1].options.body);
 assert.equal(body.target_cell,cell);assert.equal('cell_res7' in body,false);
 assert.equal('lat' in body,false);assert.equal('lng' in body,false);
 await client.getActiveAlerts(cell);await client.getResolvedAlerts(cell);
 assert.equal(requests[2].url,`/phase3/alerts?target_cell=${cell}`);
 assert.equal(requests[3].url,`/phase3/alerts/resolved?target_cell=${cell}`);
 const now=Date.now(),targets=[{case_id:'synthetic-case',cells:[cell],resolution:res}];
 assert.equal(enteredTargets(point,10,now,targets,now).join(','),'synthetic-case');
 assert.equal(enteredTargets({lat:35.17,lng:129.07},10,now,targets,now).length,0);
 assert.equal(enteredTargets(point,10,now-60001,targets,now).length,0);
});
test('missing or unsupported server resolution fails closed',async()=>{
 for(const value of [null,{}, {target_res:'9'}, {target_res:6}, {target_res:10}]){
  assert.equal(policy.targetingResolution(value),null);
  const client=load('api/client.ts',{'../utils/targetingPolicy':policy,'./config':{USE_MOCK:false,api:async()=>value}});
  await assert.rejects(()=>client.getTargetingPolicy(),/Unsupported targeting resolution/);
 }
});
