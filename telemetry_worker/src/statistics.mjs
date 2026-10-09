import {cleanPCName, savePCName} from './pc-name.mjs';
const validID = value => typeof value==='string' && /^[a-f0-9]{32}$/.test(value);
const json=(body,status=200)=>Response.json(body,{status});
export function cleanStatistics(body,now) {
  if(!body || !Array.isArray(body.devices) || body.devices.length>32 || !Array.isArray(body.matches) || body.matches.length>50) throw Error('invalid');
  const devices=body.devices.map(d=>{
    if(!d || !validID(d.id) || typeof d.active!=='boolean' || typeof d.paused!=='boolean' || !Number.isInteger(d.revision) || d.revision<0 || d.revision>10000000) throw Error('invalid');
    return {id:d.id,active:Number(d.active && !d.paused),paused:Number(d.paused),revision:d.revision};
  });
  if(new Set(devices.map(d=>d.id)).size!==devices.length) throw Error('invalid');
  const matches=body.matches.map(m=>{
    if(!m || !validID(m.id) || !Number.isFinite(m.played) || m.played<1262304000 || m.played>now+300 || !['victory','defeat','draw'].includes(m.result) || !['observed','estimated','unknown'].includes(m.source)) throw Error('invalid');
    if(m.delta!==null && (!Number.isInteger(m.delta) || Math.abs(m.delta)>1000)) throw Error('invalid');
    return {id:m.id,played:m.played,result:m.result,delta:m.source==='unknown'?null:m.delta,source:m.source};
  });
  const revision=body.revision??0;
  if(!Number.isInteger(revision)||revision<0||revision>10000000)throw Error('invalid');
  return {devices,matches,revision,pc_name:cleanPCName(body.pc_name)};
}
export async function receiveStatistics(body,owner,env) {
  const now=Date.now()/1000,{devices,matches,revision:appRevision,pc_name}=cleanStatistics(body,now);
  await savePCName(env.DB,owner,pc_name);
  const sql=[env.DB.prepare('UPDATE stats_devices SET active=0,paused=0 WHERE installation=?').bind(owner)];
  const revision=appRevision||Math.max(0,...devices.map(d=>d.revision));
  if(revision) {
    sql.push(env.DB.prepare("INSERT INTO panel_activity(installation,kind,revision,seen) SELECT ?,CASE WHEN EXISTS(SELECT 1 FROM panel_versions WHERE installation=?) THEN 'panel_updated' ELSE 'panel_seen' END,?,? WHERE NOT EXISTS(SELECT 1 FROM panel_versions WHERE installation=? AND revision=?)").bind(owner,owner,revision,now,owner,revision));
    sql.push(env.DB.prepare('INSERT INTO panel_versions VALUES(?,?,?) ON CONFLICT(installation) DO UPDATE SET revision=excluded.revision,seen=excluded.seen').bind(owner,revision,now));
  }
  for(const d of devices) sql.push(env.DB.prepare(`INSERT INTO stats_devices VALUES(?,?,?,?,?,?) ON CONFLICT(installation,device) DO UPDATE SET active=excluded.active,paused=excluded.paused,revision=excluded.revision,seen=excluded.seen`).bind(owner,d.id,d.active,d.paused,d.revision,now));
  for(const m of matches) sql.push(env.DB.prepare('INSERT OR IGNORE INTO stats_matches VALUES(?,?,?,?,?,?)').bind(owner,m.id,m.played,m.result,m.delta,m.source));
  await env.DB.batch(sql);
  return json({accepted:matches.map(m=>m.id)},202);
}
export async function statistics(db,period='alltime',now=Date.now()/1000) {
  const midnight=Math.floor((now+10800)/86400)*86400-10800;
  const since=period==='hour'?now-3600:period==='today'?midnight:0;
  const online=await db.prepare(`SELECT COALESCE(SUM(active),0) bots,COALESCE(SUM(paused),0) paused,COUNT(DISTINCT CASE WHEN active=1 THEN installation END) pcs FROM stats_devices WHERE seen>=?`).bind(now-150).first();
  const total=await db.prepare('SELECT COUNT(*) bots,COUNT(DISTINCT installation) pcs FROM stats_devices').first();
  const matches=await db.prepare(`SELECT COUNT(*) matches,COALESCE(SUM(result='victory'),0) wins,COALESCE(SUM(result='defeat'),0) losses,COALESCE(SUM(result='draw'),0) draws FROM stats_matches WHERE played>=?`).bind(since).first();
  const trophies={};
  for(const source of ['observed','estimated']) trophies[source]=await db.prepare(`SELECT COUNT(delta) measured,SUM(delta) net,SUM(CASE WHEN delta>0 THEN delta ELSE 0 END) gained,SUM(CASE WHEN delta<0 THEN -delta ELSE 0 END) lost FROM stats_matches WHERE played>=? AND source=?`).bind(since,source).first();
  return {online,total,...matches,trophies};
}
export async function onlineCount(db,now=Date.now()/1000) {
  const row=await db.prepare('SELECT COUNT(*) AS bots FROM stats_devices WHERE active=1 AND paused=0 AND seen>=?').bind(now-150).first();
  return row.bots;
}
export const formatOnline=count=>`Онлайн сейчас: ${Number(count).toLocaleString('ru-RU')}`;
function equal(a,b) {if(typeof a!=='string'||typeof b!=='string'||!b||a.length!==b.length)return false;let d=0;for(let i=0;i<a.length;i++)d|=a.charCodeAt(i)^b.charCodeAt(i);return d===0;}
export async function telegramCommand(request,env,readBody,send=fetch) {
  if(!equal(request.headers.get('X-Telegram-Bot-Api-Secret-Token'),env.TELEGRAM_WEBHOOK_SECRET))return json({error:'unauthorized'},401);
  const update=await readBody(request),message=update.message;
  if(!Number.isSafeInteger(update.update_id) || !message || !Number.isSafeInteger(message.chat?.id))return json({ok:true});
  const command=/^\/(online|stats|today|hour|alltime|start|help|panel|admin)(?:@([A-Za-z0-9_]+))?(?:\s|$)/.exec(message.text||'');
  if(!command || (command[2] && command[2].toLowerCase()!==(env.TELEGRAM_BOT_USERNAME||'xlambottt_bot').toLowerCase()))return json({ok:true});
  const now=Date.now()/1000;
  const previous=await env.DB.prepare('SELECT done FROM telegram_updates WHERE id=?').bind(update.update_id).first();
  if(previous?.done) return json({ok:true});
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(String(message.chat.id)))),v=>v.toString(16).padStart(2,'0')).join('');
  const bucket=Math.floor(now/60);
  const limit=await env.DB.prepare(`INSERT INTO rate VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN bucket=excluded.bucket THEN count+1 ELSE 1 END,bucket=excluded.bucket RETURNING count`).bind('telegram:'+hash,bucket).first();
  if(limit.count>10) return json({ok:true});
  const claimed=await env.DB.prepare(`INSERT INTO telegram_updates(id,lease) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET lease=excluded.lease WHERE done=0 AND lease<=? RETURNING id`).bind(update.update_id,now+60,now).first();
  if(!claimed) {
    const existing=await env.DB.prepare('SELECT done FROM telegram_updates WHERE id=?').bind(update.update_id).first();
    return json({ok:!!existing?.done},existing?.done?200:503);
  }
  try {
    const text=formatOnline(await onlineCount(env.DB));
    const payload={chat_id:message.chat.id,text,link_preview_options:{is_disabled:true}};
    if(['panel','admin'].includes(command[1])) {
      const admin=command[1]==='admin';
      if(message.chat.type!=='private')payload.text='Мини-панель доступна только в личных сообщениях @xlambottt_bot.';
      else if(admin&&String(message.from?.id)!==env.ADMIN_TELEGRAM_USER_ID)payload.text='Админ-панель недоступна.';
      else {
        payload.text=admin?'Твоя админ-панель xlamBOT':'Управление своим ПК · xlamBOT';
        payload.reply_markup={inline_keyboard:[[{text:admin?'Открыть админ-панель':'Открыть мини-панель',web_app:{url:new URL(admin?'/miniapp?view=admin':'/miniapp',request.url).href}}]]};
      }
    }
    if(Number.isSafeInteger(message.message_thread_id))payload.message_thread_id=message.message_thread_id;
    const response=await send('https://api.telegram.org/bot'+env.TELEGRAM_BOT_TOKEN+'/sendMessage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),redirect:'manual',signal:AbortSignal.timeout(10000)});
    if(response.status!==200 || (await response.json()).ok!==true)throw Error('telegram_failed');
    await env.DB.prepare('UPDATE telegram_updates SET done=1 WHERE id=?').bind(update.update_id).run();
    return json({ok:true});
  } catch {
    await env.DB.prepare('UPDATE telegram_updates SET lease=0 WHERE id=? AND done=0').bind(update.update_id).run();
    return json({error:'delivery_failed'},503);
  }
}
