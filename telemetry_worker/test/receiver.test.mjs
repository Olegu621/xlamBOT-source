import {test,beforeEach,afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import worker,{cleanEvent} from '../src/worker.mjs';

// Execute production SQL against SQLite, not canned responses.
let sqlite,env,pending;
function dbAdapter(sqlite) {
  const statement=(sql,args=[])=>({bind(...values){return statement(sql,values);},async first(){return sqlite.prepare(sql).get(...args) || null;},async all(){return {results:sqlite.prepare(sql).all(...args)};},async run(){return {meta:{changes:Number(sqlite.prepare(sql).run(...args).changes)}};}});
  return {prepare:statement,async batch(items){sqlite.exec('BEGIN');try{const results=[];for(const item of items)results.push(await item.run());sqlite.exec('COMMIT');return results;}catch(error){sqlite.exec('ROLLBACK');throw error;}}};
}
beforeEach(()=>{sqlite=new DatabaseSync(':memory:');sqlite.exec(readFileSync(new URL('../migrations/0001.sql',import.meta.url),'utf8'));sqlite.exec(readFileSync(new URL('../migrations/0002_statistics.sql',import.meta.url),'utf8'));env={DB:dbAdapter(sqlite)};pending=[];});
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
test('error reports remain private even when Telegram secrets are configured',async()=>{
  telegram();const a=await register();assert.equal((await call('/v1/events',event(a),a.token)).status,202);
  assert.equal(pending.length,0);await worker.scheduled({scheduledTime:1},env,ctx);assert.equal(pending.length,0);
  assert.equal(sqlite.prepare('SELECT notified FROM groups').get().notified,0);
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

import {statistics,formatStatistics,telegramCommand} from '../src/statistics.mjs';
function metrics(overrides={}) {return {devices:[{id:'d'.repeat(32),active:true,paused:false,revision:76}],matches:[{id:'e'.repeat(32),played:Date.now()/1000,result:'victory',delta:10,source:'estimated'}],...overrides};}
test('statistics uses authenticated ownership, deduplicates matches and expires online',async()=>{
  const a=await register();assert.equal((await call('/v1/statistics',metrics())).status,401);
  for(let i=0;i<2;i++)assert.equal((await call('/v1/statistics',metrics(),a.token)).status,202);
  let s=await statistics(env.DB);assert.equal(s.matches,1);assert.equal(s.online.bots,1);assert.equal(s.trophies.estimated.net,10);assert.equal(s.trophies.observed.net,null);
  s=await statistics(env.DB,'alltime',Date.now()/1000+151);assert.equal(s.online.bots,0);assert.equal(s.total.bots,1);
  assert.equal((await call('/v1/statistics',metrics({devices:[]}),a.token)).status,202);
  assert.equal((await statistics(env.DB)).online.bots,0);
});
test('invalid batch is atomic and estimates are separate from observed trophies',async()=>{
  const a=await register();const m=metrics();m.matches.push({...m.matches[0],id:'f'.repeat(32),delta:1.5});
  assert.equal((await call('/v1/statistics',m,a.token)).status,400);assert.equal((await statistics(env.DB)).matches,0);
  const good=metrics();good.matches.push({...good.matches[0],id:'f'.repeat(32),source:'observed',delta:-5,result:'defeat'});
  await call('/v1/statistics',good,a.token);const s=await statistics(env.DB);assert.equal(s.trophies.estimated.net,10);assert.equal(s.trophies.observed.net,-5);
  const text=formatStatistics(s,'alltime');assert.ok(!text.includes(a.installation));assert.ok(!text.includes('runtime_crash'));
});
test('today uses Moscow midnight and hour is rolling',async()=>{
  const a=await register(),now=Date.now()/1000,midnight=Math.floor((now+10800)/86400)*86400-10800;
  await call('/v1/statistics',metrics({matches:[{id:'e'.repeat(32),played:midnight-1,result:'draw',delta:null,source:'unknown'}]}),a.token);
  assert.equal((await statistics(env.DB,'today',now)).matches,0);assert.equal((await statistics(env.DB,'alltime',now)).matches,1);
  assert.equal((await statistics(env.DB,'hour',midnight+3600)).matches,0);
});
function hook(update,secret='test-secret'){return new Request('https://test.example/telegram',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':secret},body:JSON.stringify(update)});}
test('Telegram commands authenticate, reply in same topic and deduplicate retries',async()=>{
  env.TELEGRAM_WEBHOOK_SECRET='test-secret';env.TELEGRAM_BOT_TOKEN='fake';let sent=0,payload;
  const u={update_id:12,message:{chat:{id:-100123},message_thread_id:4,text:'/stats@xlambottt_bot'}};
  const send=async(url,o)=>{sent++;payload=JSON.parse(o.body);return Response.json({ok:true});};
  assert.equal((await telegramCommand(hook(u,'wrong'),env,r=>r.json(),send)).status,401);
  for(let i=0;i<2;i++)assert.equal((await telegramCommand(hook(u),env,r=>r.json(),send)).status,200);
  assert.equal(sent,1);assert.equal(payload.chat_id,-100123);assert.equal(payload.message_thread_id,4);
  assert.equal((await telegramCommand(hook({...u,update_id:13,message:{...u.message,text:'/stats@other_bot'}}),env,r=>r.json(),send)).status,200);assert.equal(sent,1);
});
test('failed Telegram command is retryable and concurrent command delivery is leased',async()=>{
  env.TELEGRAM_WEBHOOK_SECRET='test-secret';const u={update_id:1,message:{chat:{id:123},text:'/hour'}};
  assert.equal((await telegramCommand(hook(u),env,r=>r.json(),async()=>new Response(null,{status:302}))).status,503);
  let release,entered;const gate=new Promise(r=>release=r),ready=new Promise(r=>entered=r);
  const first=telegramCommand(hook(u),env,r=>r.json(),async()=>{entered();await gate;return Response.json({ok:true});});await ready;
  assert.equal((await telegramCommand(hook(u),env,r=>r.json(),()=>{throw Error('second send');})).status,503);
  release();assert.equal((await first).status,200);
});
