import {cleanPCName, savePCName} from './pc-name.mjs';
import {miniPage} from './mini-page.mjs';
const hex=bytes=>Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
const random=()=>hex(crypto.getRandomValues(new Uint8Array(32)));
const sha=async text=>hex(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))));
const json=(data,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
const equal=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.length===b.length&&a.length>0&&Array.from(a).reduce((d,c,i)=>d|(c.charCodeAt(0)^b.charCodeAt(i)),0)===0;
async function hmac(key,text) {
  const k=await crypto.subtle.importKey('raw',key,{name:'HMAC',hash:'SHA-256'},false,['sign']);
  return new Uint8Array(await crypto.subtle.sign('HMAC',k,new TextEncoder().encode(text)));
}
export async function telegramIdentity(data,token,now=Date.now()/1000) {
  if(typeof data!=='string'||data.length>8192||!token)throw Error('unauthorized');
  const params=new URLSearchParams(data),keys=[...params.keys()];
  if(new Set(keys).size!==keys.length)throw Error('unauthorized');
  const hash=params.get('hash'),auth=Number(params.get('auth_date'));
  if(!Number.isInteger(auth)||auth>now+30||auth<now-600)throw Error('unauthorized');
  params.delete('hash');
  const check=[...params.entries()].sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>k+'='+v).join('\n');
  const secret=await hmac(new TextEncoder().encode('WebAppData'),token);
  if(!equal(hash,hex(await hmac(secret,check))))throw Error('unauthorized');
  const user=JSON.parse(params.get('user')||'{}'),chat=JSON.parse(params.get('chat')||'null');
  if(!Number.isSafeInteger(user.id)||user.id<=0||user.is_bot||
      (chat&&chat.type!=='private')||(params.has('chat_type')&&!['private','sender'].includes(params.get('chat_type'))))throw Error('private_only');
  return String(user.id);
}
export function permitted(method,path,body) {
  if(typeof path!=='string'||path.length>2048||!['GET','POST','DELETE'].includes(method))return false;
  let decoded;try{decoded=decodeURIComponent(path.split('?')[0]);}catch{return false;}
  if(!decoded.startsWith('/')||decoded.includes('\\')||decoded.includes('\0')||decoded.split('/').some(p=>p==='.'||p==='..'))return false;
  if(method==='GET')return /^\/(panel|training(?:\/[^/]+)?|statistics|calibration\/[^/]+)$/.test(decoded)||
    /^\/static\/(?:js|css|fonts)\/[A-Za-z0-9_./-]+\.(?:js|css|woff2?|ttf)$/.test(decoded)||
    /^\/api\/(?:assets\/(?:brawlers|support)\/[^/]+|ui\/preferences|statistics|history|bootstrap|devices(?:\/(?:status|brawlers|modes|[^/]+\/(?:settings|queue|brawler|history|logs|telemetry|snapshot|training)))?|brawler-calibration\/[^/]+(?:\/snapshot)?|training\/(?:trash|sessions(?:\/[^/]+(?:\/(?:images\/[^/]+|export\.zip))?)?))$/.test(decoded);
  if(method==='DELETE')return /^\/api\/(?:devices\/[^/]+\/logs|training\/sessions\/[^/]+)$/.test(decoded);
  if(/^\/api\/devices\/[^/]+\/settings$/.test(decoded)) {
    if(!body||typeof body!=='object'||!body.values||typeof body.values!=='object'||Array.isArray(body.values))return false;
    const fields=body.section==='cfg/general_config.toml'?['thinking_mode']:body.section==='cfg/bot_config.toml'?['work_mode','brawler_switch_after_games','brawler_pick_mode']:[];
    return Object.keys(body).every(k=>['section','values'].includes(k))&&Object.keys(body.values).length>0&&Object.keys(body.values).every(k=>fields.includes(k));
  }
  return /^\/api\/(?:devices\/(?:connect|disconnect|prepare|reset-display|stop-all|[^/]+\/(?:start|pause|resume|stop|queue|brawler|mode(?:\/calibrate)?|training\/(?:start|stop)))|brawler-calibration\/[^/]+(?:\/(?:tap|reset))?|training\/(?:sessions\/[^/]+\/labels|trash\/[^/]+\/restore))$/.test(decoded);
}
async function owner(request,env) {
  const auth=request.headers.get('Authorization')||'';
  if(!/^Bearer [a-f0-9]{64}$/.test(auth))return null;
  return (await env.DB.prepare('SELECT id FROM installations WHERE token=?').bind(await sha(auth.slice(7))).first())?.id;
}
async function session(request,env) {
  const raw=request.headers.get('Cookie')?.match(/(?:^|;\s*)xlam_mini=([a-f0-9]{64})(?:;|$)/)?.[1];
  if(!raw)return null;
  return env.DB.prepare('SELECT user_id FROM mini_sessions WHERE token=? AND expires>?').bind(await sha(raw),Date.now()/1000).first();
}
async function readRemoteBody(request) {
  if(Number(request.headers.get('Content-Length')||0)>2*1024*1024)throw Error('too_large');
  const reader=request.body?.getReader();if(!reader)return {};let size=0,chunks=[];
  while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>2*1024*1024){await reader.cancel();throw Error('too_large');}chunks.push(value);}
  const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}return JSON.parse(new TextDecoder().decode(bytes));
}
async function activity(env,installation,kind,revision=0) {
  await env.DB.prepare('INSERT INTO panel_activity(installation,kind,revision,seen) VALUES(?,?,?,?)').bind(installation,kind,revision,Date.now()/1000).run();
}
export async function remoteRoute(request,env,readBody) {
  const url=new URL(request.url),path=url.pathname,now=Date.now()/1000;
  const scoped=/^\/pc\/([a-f0-9]{32})(\/.*)$/.exec(path);
  const cors=response=>{if(scoped&&request.headers.get('Origin')==='null'){
    // Fetched relay responses have immutable headers. Copy before adding CORS.
    response=new Response(response.body,response);
    response.headers.set('Access-Control-Allow-Origin','null');response.headers.set('Access-Control-Allow-Methods','GET, POST, DELETE');response.headers.set('Access-Control-Allow-Headers','Content-Type, X-Xlam-UI-Token');response.headers.set('Access-Control-Expose-Headers','X-Preview-Interval-Ms, Content-Disposition');}return response;};
  if(scoped&&request.method==='OPTIONS'&&request.headers.get('Origin')==='null')return cors(new Response(null,{status:204}));
  if(path==='/miniapp'&&request.method==='GET')return new Response(miniPage,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}});
  if(path==='/mini/auth'&&request.method==='POST') {
    if(request.headers.get('Origin')!==url.origin)return json({error:'invalid_origin'},403);
    let user;try{user=await telegramIdentity((await readBody(request)).initData,env.TELEGRAM_BOT_TOKEN);}catch{return json({error:'private_telegram_required'},401);}
    const bucket=Math.floor(now/60),rate=await env.DB.prepare('INSERT INTO rate VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN bucket=excluded.bucket THEN count+1 ELSE 1 END,bucket=excluded.bucket RETURNING count').bind('mini:'+user,bucket).first();
    if(rate.count>20)return json({error:'rate_limited'},429);
    const token=random();await env.DB.prepare('INSERT INTO mini_sessions VALUES(?,?,?)').bind(await sha(token),user,now+3600).run();
    const response=json({ok:true,admin:user===env.ADMIN_TELEGRAM_USER_ID});response.headers.set('Set-Cookie','xlam_mini='+token+'; HttpOnly; Secure; SameSite=None; Path=/; Max-Age=3600');return response;
  }
  if(path.startsWith('/v1/remote/')) {
    const installation=await owner(request,env);if(!installation)return json({error:'unauthorized'},401);
    if(path==='/v1/remote/key'&&request.method==='POST') {
      const key=random();await env.DB.prepare('INSERT INTO remote_links VALUES(?,NULL,?,?) ON CONFLICT(installation) DO UPDATE SET user_id=NULL,key_hash=excluded.key_hash,expires=excluded.expires').bind(installation,await sha(key),now+600).run();
      await activity(env,installation,'pairing_key_created');return json({key,expires:now+600});
    }
    if(path==='/v1/remote/status'&&request.method==='GET')return json({paired:!!(await env.DB.prepare('SELECT user_id FROM remote_links WHERE installation=?').bind(installation).first())?.user_id});
    if(path==='/v1/remote/status'&&request.method==='POST') {
      const body=await readBody(request);
      await savePCName(env.DB,installation,cleanPCName(body.pc_name));
      return json({paired:!!(await env.DB.prepare('SELECT user_id FROM remote_links WHERE installation=?').bind(installation).first())?.user_id});
    }
    if(path==='/v1/remote/revoke'&&request.method==='POST') {
      await env.DB.prepare('DELETE FROM remote_links WHERE installation=?').bind(installation).run();
      if(env.REMOTE)await env.REMOTE.get(env.REMOTE.idFromName(installation)).fetch(new Request('https://relay/revoke',{method:'POST'}));
      await activity(env,installation,'access_revoked');return json({ok:true});
    }
    if(path==='/v1/remote/socket'&&request.headers.get('Upgrade')?.toLowerCase()==='websocket') {
      const forwarded=new Request('https://relay/connect',request);forwarded.headers.set('X-Relay-Installation',installation);
      return env.REMOTE.get(env.REMOTE.idFromName(installation)).fetch(forwarded);
    }
    return json({error:'not_found'},404);
  }
  let auth;
  if(scoped) {
    const grant=url.searchParams.get('grant');
    if(!/^[a-f0-9]{64}$/.test(grant||''))return cors(json({error:'pc_grant_required'},401));
    auth=await env.DB.prepare('SELECT user_id FROM mini_grants WHERE token=? AND installation=? AND expires>?').bind(await sha(grant),scoped[1],now).first();
  }else auth=await session(request,env);
  if(!auth)return cors(json({error:'open_in_private_telegram'},401));
  if(request.method!=='GET'&&request.headers.get('Origin')!==url.origin&&!(scoped&&request.headers.get('Origin')==='null'))return cors(json({error:'invalid_origin'},403));
  if(path==='/mini/status'&&request.method==='GET') {
    const links=(await env.DB.prepare('SELECT remote_links.installation,installation_names.name FROM remote_links LEFT JOIN installation_names USING(installation) WHERE user_id=? ORDER BY installation').bind(auth.user_id).all()).results;
    const pcs=[];for(const r of links){const grant=random();await env.DB.prepare('INSERT INTO mini_grants VALUES(?,?,?,?)').bind(await sha(grant),auth.user_id,r.installation,now+3600).run();pcs.push({id:r.installation,name:r.name||'ПК '+r.installation.slice(0,6),grant});}
    return json({pcs,admin:auth.user_id===env.ADMIN_TELEGRAM_USER_ID});
  }
  if(path==='/mini/pair'&&request.method==='POST') {
    const key=(await readBody(request)).key;if(typeof key!=='string'||!/^[a-f0-9]{64}$/.test(key))return json({error:'invalid_key'},400);
    const rate=await env.DB.prepare('INSERT INTO rate VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN bucket=excluded.bucket THEN count+1 ELSE 1 END,bucket=excluded.bucket RETURNING count').bind('pair:'+auth.user_id,Math.floor(now/60)).first();
    if(rate.count>10)return json({error:'rate_limited'},429);
    const bound=await env.DB.prepare('UPDATE remote_links SET user_id=?,key_hash=NULL,expires=0 WHERE key_hash=? AND expires>? AND user_id IS NULL RETURNING installation').bind(auth.user_id,await sha(key),now).first();
    if(!bound)return json({error:'expired_or_used_key'},409);
    await activity(env,bound.installation,'pc_paired');return json({ok:true,pc:bound.installation});
  }
  if(path.startsWith('/mini/admin/')) {
    if(auth.user_id!==env.ADMIN_TELEGRAM_USER_ID)return json({error:'admin_only'},403);
    if(request.method!=='GET')return json({error:'method_not_allowed'},405);
    const cursor=(url.searchParams.get('before')||'').split(':');
    const before=Number(cursor[0])||now+1,lastId=Number(cursor[1])||Number.MAX_SAFE_INTEGER;
    const page=rows=>json({rows:rows.map(({cursor_id,...r})=>({...r,installation:r.installation.slice(0,8)})),next:rows.length?rows.at(-1).seen+':'+rows.at(-1).cursor_id:''});
    if(path==='/mini/admin/errors') {
      const level=url.searchParams.get('level'),params=[before,before,lastId];let filter='(seen<? OR (seen=? AND rowid<?))';
      if(['critical','error','warning'].includes(level)){filter+=' AND level=?';params.push(level);}
      const rows=(await env.DB.prepare('SELECT rowid cursor_id,installation,code,level,revision,exception,stage,trace,count,seen FROM events WHERE '+filter+' ORDER BY seen DESC,rowid DESC LIMIT 100').bind(...params).all()).results;
      return page(rows);
    }
    if(path==='/mini/admin/activity')return page((await env.DB.prepare('SELECT id cursor_id,installation,kind,revision,seen FROM panel_activity WHERE seen<? OR (seen=? AND id<?) ORDER BY seen DESC,id DESC LIMIT 100').bind(before,before,lastId).all()).results);
    if(path==='/mini/admin/versions')return page((await env.DB.prepare('SELECT rowid cursor_id,installation,revision,seen FROM panel_versions WHERE seen<? OR (seen=? AND rowid<?) ORDER BY seen DESC,rowid DESC LIMIT 100').bind(before,before,lastId).all()).results);
    return json({error:'not_found'},404);
  }
  // Every page, image and command carries the PC scope, including parallel tabs.
  const route=scoped,pc=route?.[1];
  if(!pc||!(await env.DB.prepare('SELECT installation FROM remote_links WHERE installation=? AND user_id=?').bind(pc,auth.user_id).first()))return cors(json({error:'pc_not_linked'},403));
  let body=null;if(request.method!=='GET')body=await readRemoteBody(request);
  if(!permitted(request.method,route[2],body))return cors(json({error:'not_available_in_mini_panel'},403));
  url.pathname=route[2];
  const pcGrant=url.searchParams.get('grant');
  url.searchParams.delete('pc');url.searchParams.delete('t');url.searchParams.delete('grant');
  const response=await env.REMOTE.get(env.REMOTE.idFromName(pc)).fetch(new Request('https://relay/proxy',{method:'POST',body:JSON.stringify({method:request.method,path:url.pathname+url.search,body})}));
  if(response.headers.get('Content-Type')?.includes('text/html')) {
    const text=await response.text();
    const html=text.replace('<head>','<head><meta name="xlam-remote-grant" content="'+pcGrant+'">').replace(/((?:href|src|action)=["'])(\/pc\/[a-f0-9]{32}[^"']*)(["'])/g,(_,start,value,end)=>start+value+(value.includes('?')?'&amp;':'?')+'grant='+pcGrant+end);
    return cors(new Response(html,response));
  }
  if(response.headers.get('Content-Type')?.includes('text/css')) {
    const css=(await response.text()).replace(/url\((["']?)(\/pc\/[a-f0-9]{32}[^)'" ]*)(["']?)\)/g,(_,q,value,end)=>'url('+q+value+(value.includes('?')?'&':'?')+'grant='+pcGrant+end+')');
    return cors(new Response(css,response));
  }
  if(request.method!=='GET') {
    const parts=route[2].split('/').filter(Boolean);let kind='control_'+parts.at(-1);
    if(parts[1]==='training')kind=request.method==='DELETE'?'training_deleted':parts.at(-1)==='labels'?'training_labels_saved':'training_restored';
    await activity(env,pc,kind).catch(()=>{});
  }
  return cors(response);
}

/** Per-PC relay; sockets hibernate between requests and never expose local ports. */
export class PanelRelay {
  constructor(ctx,env){this.ctx=ctx;this.env=env;this.pending=new Map();}
  sockets(){return this.ctx.getWebSockets('pc');}
  async fetch(request) {
    const path=new URL(request.url).pathname;
    if(path==='/revoke'){for(const ws of this.sockets())ws.close(1000,'revoked');return json({ok:true});}
    if(path==='/connect') {
      for(const ws of this.sockets())ws.close(1000,'replaced');
      const [client,server]=Object.values(new WebSocketPair());this.ctx.acceptWebSocket(server,['pc']);
      server.serializeAttachment({installation:request.headers.get('X-Relay-Installation')});
      await activity(this.env,request.headers.get('X-Relay-Installation'),'relay_connected');
      return new Response(null,{status:101,webSocket:client});
    }
    if(path!=='/proxy')return json({error:'not_found'},404);
    const ws=this.sockets()[0];if(!ws)return json({error:'pc_offline'},503);
    if(this.pending.size>=64)return json({error:'busy'},429);
    const call=await request.json();if(!permitted(call.method,call.path,call.body))return json({error:'forbidden'},403);
    const id=random();
    return new Promise(resolve=>{
      const timer=setTimeout(()=>{this.pending.delete(id);resolve(json({error:'pc_request_expired'},504));},25000);
      this.pending.set(id,{resolve,timer,chunks:[],size:0,ws});
      try{ws.send(JSON.stringify({id,deadline:Date.now()/1000+22,...call}));}catch{clearTimeout(timer);this.pending.delete(id);resolve(json({error:'pc_offline'},503));}
    });
  }
  webSocketMessage(ws,message) {
    try {
      const data=JSON.parse(message),pending=this.pending.get(data.id);if(!pending||pending.ws!==ws)return;
      if(typeof data.chunk==='string') {
        if(data.chunk.length>100000)throw Error('too_large');
        const bytes=Uint8Array.from(atob(data.chunk),c=>c.charCodeAt(0));pending.size+=bytes.length;
        if(pending.size>32*1024*1024)throw Error('too_large');pending.chunks.push(bytes);
      }
      if(data.done) {
        clearTimeout(pending.timer);this.pending.delete(data.id);
        const bytes=new Uint8Array(pending.size);let offset=0;for(const chunk of pending.chunks){bytes.set(chunk,offset);offset+=chunk.length;}
        const headers={'Content-Type':data.type||'application/json','Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','X-Frame-Options':'SAMEORIGIN'};
        if(data.disposition)headers['Content-Disposition']=data.disposition;
        if(data.preview)headers['X-Preview-Interval-Ms']=String(data.preview);
        pending.resolve(new Response(bytes,{status:Number.isInteger(data.status)&&data.status>=200&&data.status<=599?data.status:502,headers}));
      }
    }catch{ws.close(1009,'invalid response');this.webSocketClose(ws);}
  }
  webSocketClose(ws){for(const [id,p] of this.pending){if(p.ws!==ws)continue;clearTimeout(p.timer);p.resolve(json({error:'pc_disconnected'},503));this.pending.delete(id);}}
  webSocketError(ws){this.webSocketClose(ws);}
}
