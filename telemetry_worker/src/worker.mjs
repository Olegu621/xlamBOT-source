import {receiveStatistics,telegramCommand} from './statistics.mjs';
const codes = new Set(['startup_failed','runtime_crash','runtime_halted','thread_crash','application_exception','ui_request_failed','gpu_fallback','gas_detector_failed','brawler_selection_failed','update_failed','manual_report','test_report']);
const modules = new Set(['bot_instance','window_controller','capture_transport','play','detect','stage_manager','lobby_automation','utils','trophy_observer','trophy_reader','app','device_manager','runtime','services','training_capture','brawler_calibration','settings_schema','update_client','main','battle_memory','gas_guard','combat_behavior','ability_buttons']);
const stages = new Set(['startup','runtime','ui','model','update','manual','unknown']);
const levels = new Set(['info','warning','error','critical']);
const hex = (bytes) => Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
const random = (size) => hex(crypto.getRandomValues(new Uint8Array(size)));
export const digest = async value => hex(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))));
const identifier = value => typeof value==='string' && /^[A-Za-z0-9_.-]{1,80}$/.test(value) ? value : 'unknown';
const json = (value,status=200) => Response.json(value,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});

export async function cleanEvent(event) {
  if (!event || typeof event!=='object' || !codes.has(event.code) || !levels.has(event.level)) throw Error('invalid');
  const out={code:event.code,level:event.level,stage:stages.has(event.stage)?event.stage:'unknown'};
  for(const key of ['id','installation']) {
    if(typeof event[key]!=='string' || !/^[a-f0-9]{32}$/.test(event[key])) throw Error('invalid');
    out[key]=event[key];
  }
  out.device=typeof event.device==='string' && /^[a-f0-9]{12}$/.test(event.device)?event.device:'';
  out.app_version=identifier(event.app_version);
  out.exception_type=identifier(event.exception_type);
  out.revision=Number.isInteger(event.revision) && event.revision>=0 && event.revision<=10000000?event.revision:0;
  for(const key of ['first_seen','last_seen']) {
    if(typeof event[key]!=='number' || !Number.isFinite(event[key]) || event[key]<0) throw Error('invalid');
    out[key]=event[key];
  }
  out.count=event.count === undefined ? 1 : event.count;
  if(!Number.isInteger(out.count) || out.count<1 || out.count>1000000000) throw Error('invalid');
  const frames=event.trace === undefined ? [] : event.trace;
  if(!Array.isArray(frames)) throw Error('invalid');
  out.trace=frames.slice(-8).filter(f=>f && modules.has(f.module) && Number.isInteger(f.line) && f.line>0 && f.line<=10000000)
    .map(f=>({module:f.module,function:identifier(f.function),line:f.line}));
  out.fingerprint=await digest(JSON.stringify([out.app_version,out.revision,out.level,out.code,out.exception_type,out.stage,out.trace]));
  return out;
}

export async function readBody(request) {
  if(Number(request.headers.get('Content-Length') || 0)>32768) throw Error('too_large');
  const reader=request.body?.getReader();
  if(!reader) return {};
  let size=0; const chunks=[];
  while(true) {
    const {done,value}=await reader.read(); if(done) break;
    size+=value.byteLength;
    if(size>32768) {await reader.cancel(); throw Error('too_large');}
    chunks.push(value);
  }
  const data=new Uint8Array(size); let offset=0;
  for(const chunk of chunks) {data.set(chunk,offset); offset+=chunk.length;}
  return JSON.parse(new TextDecoder().decode(data));
}

async function rate(db,key,limit,seconds=3600) {
  const bucket=Math.floor(Date.now()/1000/seconds);
  const row=await db.prepare(`INSERT INTO rate VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET
    count=CASE WHEN bucket=excluded.bucket THEN count+1 ELSE 1 END,bucket=excluded.bucket RETURNING count`).bind(key,bucket).first();
  return row.count<=limit;
}

async function receive(request,env,ctx) {
  const path=new URL(request.url).pathname;
  if(path==='/health' && request.method==='GET') return json({ok:true,service:'xlambot-error-receiver'});
  if(path==='/telegram' && request.method==='POST') return telegramCommand(request,env,readBody);
  if(request.method!=='POST' || !['/v1/register','/v1/events','/v1/statistics'].includes(path)) return json({error:'not_found'},404);
  if(path==='/v1/register') {
    await readBody(request);
    const ip=await digest(request.headers.get('CF-Connecting-IP') || 'unknown');
    if(!await rate(env.DB,'register:'+ip,20) || !await rate(env.DB,'register:global',1000)) return json({error:'rate_limited'},429);
    const installation=random(16),token=random(32);
    const result=await env.DB.prepare('INSERT INTO installations SELECT ?,?,? WHERE (SELECT COUNT(*) FROM installations)<100000').bind(installation,await digest(token),Date.now()/1000).run();
    if(!result.meta.changes) return json({error:'capacity'},503);
    return json({installation,token});
  }
  const auth=request.headers.get('Authorization') || '';
  if(!/^Bearer [a-f0-9]{64}$/.test(auth)) return json({error:'unauthorized'},401);
  const owner=await env.DB.prepare('SELECT id FROM installations WHERE token=?').bind(await digest(auth.slice(7))).first();
  if(!owner) return json({error:'unauthorized'},401);
  if(!await rate(env.DB,(path==='/v1/statistics'?'statistics:':'events:')+owner.id,path==='/v1/statistics'?6:120,60)) return json({error:'rate_limited'},429);
  if(path==='/v1/statistics') return receiveStatistics(await readBody(request),owner.id,env);
  const item=await cleanEvent(await readBody(request));
  if(item.installation!==owner.id) return json({error:'unauthorized'},401);
  if(item.level==='info' || (item.level==='warning' && item.count<3)) return json({error:'invalid_level'},400);
  const now=Date.now()/1000;
  if(item.last_seen<item.first_seen || item.last_seen>now+86400) return json({error:'invalid_time'},400);
  // SQL gates and fingerprint matching keep concurrent retries idempotent.
  const result=await env.DB.prepare(`INSERT INTO events
    SELECT ?,?,?,?,?,?,?,?,?,?,?,? WHERE
      EXISTS(SELECT 1 FROM events WHERE installation=? AND id=?) OR
      ((SELECT COUNT(*) FROM events WHERE installation=?)<1000 AND (SELECT COUNT(*) FROM events)<100000)
    ON CONFLICT(installation,id) DO UPDATE SET count=MAX(count,excluded.count),seen=excluded.seen
    WHERE fingerprint=excluded.fingerprint RETURNING fingerprint`).bind(
      owner.id,item.id,item.fingerprint,Math.min(item.count,1000000),item.level,item.code,item.app_version,item.revision,item.exception_type,item.stage,
      item.trace.map(f=>`${f.module}.${f.function}:${f.line}`).join('\n'),now,owner.id,item.id,owner.id).first();
  if(!result) {
    const old=await env.DB.prepare('SELECT fingerprint FROM events WHERE installation=? AND id=?').bind(owner.id,item.id).first();
    return json({error:old?'conflicting_report':'capacity'},old?409:429);
  }
  await env.DB.prepare('INSERT OR IGNORE INTO groups(fingerprint) VALUES(?)').bind(item.fingerprint).run();
  return json({accepted:item.id},202);
}

export default {
  async fetch(request,env,ctx) {
    try {return await receive(request,env,ctx);}
    catch(error) {
      const invalid=error.message==='invalid' || error instanceof SyntaxError;
      return json({error:error.message==='too_large'?'too_large':invalid?'invalid_report':'request_failed'},error.message==='too_large'?413:invalid?400:503);
    }
  },
  async scheduled(controller,env,ctx) {
    // Delete only entire inactive groups, preserving live cumulative counters.
    const cutoff=Date.now()/1000-30*86400;
    if(Math.floor(controller.scheduledTime/60000)%1440===0) await env.DB.batch([
      env.DB.prepare('DELETE FROM events WHERE fingerprint IN (SELECT fingerprint FROM events GROUP BY fingerprint HAVING MAX(seen)<?)').bind(cutoff),
      env.DB.prepare('DELETE FROM groups WHERE NOT EXISTS(SELECT 1 FROM events WHERE events.fingerprint=groups.fingerprint)'),
      env.DB.prepare("DELETE FROM rate WHERE (key LIKE 'register:%' AND bucket<?) OR ((key LIKE 'events:%' OR key LIKE 'statistics:%' OR key LIKE 'telegram:%') AND bucket<?)").bind(Math.floor(Date.now()/3600000)-48,Math.floor(Date.now()/60000)-2880),
      env.DB.prepare('DELETE FROM telegram_updates WHERE lease<?').bind(Date.now()/1000-7*86400)
    ]);
  }
};
