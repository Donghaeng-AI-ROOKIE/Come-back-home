const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const {QueryClient}=require('@tanstack/react-query');
test('actual guardian query hook cannot reuse another account cache',()=>{
 let owner='account-a';const m={exports:{}};
 const mocks={react:{},'@tanstack/react-query':{useQuery:options=>options},
 '../store/guardianCaseStore':{useGuardianCaseStore:s=>s({caseIds:['synthetic-a']})},
 '../store/authStore':{useAuthStore:s=>s({userId:owner})}};
 const source=fs.readFileSync(path.join(__dirname,'../src/hooks/queries.ts'),'utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,
  {module:m,exports:m.exports,require:n=>mocks[n]??{}});
 const cache=new QueryClient();const a=m.exports.useGuardianCases();
 cache.setQueryData(a.queryKey,[{id:'synthetic-a'}]);owner='account-b';
 assert.equal(cache.getQueryData(m.exports.useGuardianCases().queryKey),undefined);
 owner=null;assert.equal(m.exports.useGuardianCases().enabled,false);cache.clear();
});
