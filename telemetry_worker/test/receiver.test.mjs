import {test,beforeEach,afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import worker,{cleanEvent,deliver} from '../src/worker.mjs';

// Execute production SQL against SQLite, not canned responses.
let sqlite,env,pending;
function dbAdapter(sqlite) {
  const statement=(sql,args=[])=>({bind(...values){return statement(sql,values);},async first(){return sqlite.prepare(sql).get(...args) || null;},async run(){return {meta:{changes:Number(sqlite.prepare(sql).run(...args).changes)}};}});
  return {prepare:statement,async batch(items){sqlite.exec('BEGIN');try{const results=[];for(const item of items)results.push(await item.run());sqlite.exec('COMMIT');return results;}catch(error){sqlite.exec('ROLLBACK');throw error;}}};
}
beforeEach(()=>{sqlite=new DatabaseSync(':memory:');sqlite.exec(readFileSync(new URL('../migrations/0001.sql',import.meta.url),'utf8'));env={DB:dbAdapter(sqlite)};pending=[];});
afterEach(()=>sqlite.close());
const ctx={waitUntil(p){pending.push(p);}};
async function call(path,data,token,extra={}) {
  const headers={'Content-Type':'application/json','CF-Connecting-IP':'192.0.2.1',...extra};
  if(token)headers.Authorization='Bearer '+token;
  return worker.fetch(new Request('https://test.example'+path,{method:'POST',headers,body:JSON.stringify(data)}),env,ctx);
}
async function register(){const r=await call('/v1/register',{});assert.equal(r.status,200);return r.json();}
function event(owner,overrides={}) {const now=Date.now()/1000;return {installation:owner.installation,id:'a'.repeat(32),code:'runtime_crash',level:'critical',stage:'runtime',app_version:'0.8.20',revision:73,exception_type:'RuntimeError',count:1,first_seen:now,last_seen:now,trace:[{module:'play',function:'tick',line:12}],...overrides};}
function telegram(){env.TELEGRAM_BOT_TOKEN='FAKE_TEST_TOKEN';env.TELEGRAM_CHAT_ID='TEST_CHAT';}
test('sanitizes private data, rejects malformed counts and forbidden modules',async()=>{
  const owner=await register(),clean=await cleanEvent(event(owner,{message:'password',trace:[{module:'private',line:1,function:'secret'}]}));
  assert.equal(clean.message,undefined);assert.deepEqual(clean.trace,[]);
  for(const count of [null,true,0,NaN,1.5]) await assert.rejects(cleanEvent(event(owner,{count})));
  await assert.rejects(cleanEvent(event(owner,{trace:null})));
});
test('auth binds event ownership and rejects forged reports',async()=>{
  const a=await register(),b=await register();
  assert.equal((await call('/v1/events',event(a))).status,401);
  assert.equal((await call('/v1/events',event(a),b.token)).status,401);
  assert.equal((await call('/v1/events',event(a,{count:null}),a.token)).status,400);
  assert.equal(sqlite.prepare('SELECT COUNT(*) n FROM events').get().n,0);
});
test('cumulative retries are idempotent; conflicting event id is rejected',async()=>{
  const a=await register();
  for(const count of [1,3,2])assert.equal((await call('/v1/events',event(a,{count}),a.token)).status,202);
  assert.equal(sqlite.prepare('SELECT count FROM events').get().count,3);
  assert.equal((await call('/v1/events',event(a,{code:'gpu_fallback'}),a.token)).status,409);
});
test('real outbox SQL groups users and acknowledges only delivered snapshot',async()=>{
  const a=await register(),b=await register();
  await call('/v1/events',event(a),a.token);await call('/v1/events',event(b),b.token);telegram();
  let sent;
  assert.equal(await deliver(env,async(url,options)=>{sent=JSON.parse(options.body);assert.equal(options.redirect,'manual');return Response.json({ok:true});}),true);
  assert.match(sent.text,/Reports: 2 · installations: 2/);
  assert.equal(sqlite.prepare('SELECT notified FROM groups').get().notified,2);
  assert.equal(await deliver(env,()=>{throw Error('must not retry');}),false);
});
test('Telegram failure and redirects remain queued with backoff',async()=>{
  const a=await register();await call('/v1/events',event(a),a.token);telegram();
  assert.equal(await deliver(env,async()=>new Response(null,{status:302})),false);
  const row=sqlite.prepare('SELECT * FROM groups').get();assert.equal(row.notified,0);assert.equal(row.failures,1);assert.ok(row.retry_at>Date.now()/1000);
});
test('concurrent delivery is protected by a database lease',async()=>{
  const a=await register();await call('/v1/events',event(a),a.token);telegram();
  let release,entered;const ready=new Promise(resolve=>entered=resolve),gate=new Promise(resolve=>release=resolve);
  const first=deliver(env,async()=>{entered();await gate;return Response.json({ok:true});});await ready;
  assert.equal(await deliver(env,()=>{throw Error('second sender');}),false);release();assert.equal(await first,true);
});
test('registration limits and body caps cannot be bypassed',async()=>{
  for(let i=0;i<20;i++)await register();assert.equal((await call('/v1/register',{})).status,429);
  assert.equal((await call('/v1/register',{blob:'x'.repeat(32769)})).status,413);
});
test('retention removes idle groups, preserves active groups and their counters',async()=>{
  const a=await register();await call('/v1/events',event(a),a.token);
  const b=await register();await call('/v1/events',event(b,{id:'b'.repeat(32),code:'gpu_fallback'}),b.token);
  sqlite.prepare('UPDATE events SET seen=? WHERE id=?').run(Date.now()/1000-31*86400,'a'.repeat(32));
  await worker.scheduled({scheduledTime:0},env,ctx);assert.equal(sqlite.prepare('SELECT COUNT(*) n FROM events').get().n,1);assert.equal(sqlite.prepare('SELECT COUNT(*) n FROM groups').get().n,1);
});
test('info and unrepeated warnings are not accepted; public setup is absent',async()=>{
  const a=await register();for(const level of ['info','warning'])assert.equal((await call('/v1/events',event(a,{level}),a.token)).status,400);
  assert.equal((await worker.fetch(new Request('https://test.example/'),env,ctx)).status,404);
  assert.equal((await worker.fetch(new Request('https://test.example/health'),env,ctx)).status,200);
});
