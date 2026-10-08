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
  return {devices,matches};
}
export async function receiveStatistics(body,owner,env) {
  const now=Date.now()/1000,{devices,matches}=cleanStatistics(body,now);
  const sql=[env.DB.prepare('UPDATE stats_devices SET active=0,paused=0 WHERE installation=?').bind(owner)];
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
const n = value => Number(value).toLocaleString('ru-RU');
export function formatStatistics(data,period) {
  const labels={stats:'Сводка',today:'Сегодня (МСК)',hour:'Последний час',alltime:'За всё время'};
  const lines=[`xlamBOT · ${labels[period]||labels.alltime}`,`В игре сейчас: ${n(data.online.bots)} ботов на ${n(data.online.pcs)} ПК`,`На паузе: ${n(data.online.paused)}`,`Всего подключались: ${n(data.total.bots)} ботов на ${n(data.total.pcs)} ПК`,'',`Боёв: ${n(data.matches)}`,`Победы: ${n(data.wins)} · Поражения: ${n(data.losses)} · Ничьи: ${n(data.draws)}`,`Побед: ${data.matches?(100*data.wins/data.matches).toFixed(1)+'%':'нет данных'}`];
  for(const [source,title] of [['observed','Подтверждённые трофеи'],['estimated','Расчётные трофеи']]) {
    const t=data.trophies[source];
    lines.push('',title,t.measured?`Получено: +${n(t.gained)} · Потеряно: −${n(t.lost)} · Итог: ${t.net>=0?'+':''}${n(t.net)}`:'Нет измерений');
  }
  lines.push('',`Боёв без измерения трофеев: ${n(data.matches-data.trophies.observed.measured-data.trophies.estimated.measured)}`);
  lines.push('','Только добровольно подключённые ПК. Расчётные трофеи определяются по результату боя. Онлайн обновляется раз в минуту.');
  return lines.join('\n');
}
function equal(a,b) {if(typeof a!=='string'||typeof b!=='string'||!b||a.length!==b.length)return false;let d=0;for(let i=0;i<a.length;i++)d|=a.charCodeAt(i)^b.charCodeAt(i);return d===0;}
export async function telegramCommand(request,env,readBody,send=fetch) {
  if(!equal(request.headers.get('X-Telegram-Bot-Api-Secret-Token'),env.TELEGRAM_WEBHOOK_SECRET))return json({error:'unauthorized'},401);
  const update=await readBody(request),message=update.message;
  if(!Number.isSafeInteger(update.update_id) || !message || !Number.isSafeInteger(message.chat?.id))return json({ok:true});
  const command=/^\/(stats|today|hour|alltime|start|help)(?:@([A-Za-z0-9_]+))?(?:\s|$)/.exec(message.text||'');
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
    let text;
    if(['help','start'].includes(command[1]))text='xlamBOT · статистика ПК-ботов\n/stats — сводка\n/today — сегодня (МСК)\n/hour — последний час\n/alltime — всё время\n\nДобавьте бота в чат. Данные поступают от пользователей, использующих «Общую статистику» в настройках ПК-бота. Ошибки в Telegram не отправляются.';
    else {
      text=formatStatistics(await statistics(env.DB,command[1]),command[1]);
      if(command[1]==='stats')for(const period of ['today','hour']) {
        const s=await statistics(env.DB,period);
        const t=s.trophies.estimated,o=s.trophies.observed;
        text+='\n\n'+(period==='today'?'Сегодня (МСК)':'Последний час')+`: ${n(s.matches)} боёв, ${n(s.wins)} побед.\nПодтверждённый прирост: ${o.measured?'+'+n(o.gained):'нет измерений'}; расчётный: ${t.measured?'+'+n(t.gained):'нет измерений'}`;
      }
    }
    const payload={chat_id:message.chat.id,text,link_preview_options:{is_disabled:true}};
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
