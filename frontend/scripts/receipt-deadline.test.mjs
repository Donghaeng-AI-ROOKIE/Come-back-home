import assert from 'node:assert/strict';
import test from 'node:test';
import { receiptDeadline } from '../src/utils/receiptDeadline.ts';
test('a never-finishing connection cannot leave the button pending forever', async () => {
  let started=0;
  const request=new Promise(() => {started++;});
  await assert.rejects(receiptDeadline(request,15),/같은 요청/);
  assert.equal(started,1);
});
test('receipt success does not wait for the analysis and a late original can finish',async()=>{
  assert.deepEqual(await receiptDeadline(Promise.resolve({id:'saved'}),100),{id:'saved'});
  let finish;
  const request=new Promise(resolve=>{finish=resolve;});
  await assert.rejects(receiptDeadline(request,5));
  finish({id:'original'});
  assert.deepEqual(await request,{id:'original'});
});
