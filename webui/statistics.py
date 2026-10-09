"""Read-only statistics across device histories; no fabricated observations."""
import csv
import math
import io
import hashlib
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict
import utils

_history_cache = OrderedDict()
_cache_lock = threading.RLock()
_payload_cache = OrderedDict()


def history(path, key):
    """Reuse parsed histories, invalidate on atomic replacement or append."""
    stat = path.stat()
    signature = (stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns)
    cache_key = str(path.resolve())
    with _cache_lock:
        cached = _history_cache.get(cache_key)
        if cached and cached[0] == signature:
            _history_cache.move_to_end(cache_key)
            return cached[1:]
    records = csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig')))
    rows, skipped = [], 0
    for index, row in enumerate(records):
        try:
            stamp = datetime.fromisoformat(row.get('date_time', '').replace('Z', '+00:00'))
            if stamp.tzinfo is not None:
                stamp = stamp.astimezone().replace(tzinfo=None)
        except (ValueError, TypeError, OverflowError):
            skipped += 1
            continue
        name = str(row.get('brawler_name') or '').strip()
        if not name:
            skipped += 1
            continue
        tag = str(row.get('account_tag') or '').strip()
        ident = hashlib.sha256(f'{key}:{index}:{stamp.isoformat()}'.encode()).hexdigest()[:20]
        rows.append({'id': ident, 'device': key, 'account': tag if tag and tag != '#' else 'unknown:' + key,
                     'brawler': name, 'day': stamp.date(), 'time': stamp,
                     'result': str(row.get('result') or '').lower(),
                     'delta': number(row.get('trophy_delta')), 'source': row.get('trophy_source') or 'legacy'})
    # Never cache an inconsistent read while another process replaces the CSV.
    after = path.stat()
    if signature == (after.st_mtime_ns, after.st_size, after.st_ctime_ns):
        with _cache_lock:
            _history_cache[cache_key] = (signature, rows, skipped)
            _history_cache.move_to_end(cache_key)
            while len(_history_cache) > 128:
                _history_cache.popitem(last=False)
    return rows, skipped


def number(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None


def build(root, period='7', device='', account='', brawler='', now=None):
    if period not in {'today','7','30','all'}:raise ValueError('Invalid period')
    now=now or datetime.now()
    if now.tzinfo is not None:
        now=now.astimezone().replace(tzinfo=None)
    today=now.date()
    start=None if period=='all' else today-timedelta(days=0 if period=='today' else int(period)-1)
    paths=[('default',Path(root)/'cfg'/'match_history.csv')]
    paths += [(p.parent.parent.name,p) for p in sorted((Path(root)/'devices').glob('*/cfg/match_history.csv'))]
    rows=[];skipped=0;unreadable=[]
    for key,path in paths:
        if not path.is_file():continue
        try:
            records, damaged = history(path, key)
            rows.extend(records)
            skipped += damaged
        except (OSError, UnicodeError, csv.Error):
            unreadable.append(key)
            continue
    options={k:sorted({row[k] for row in rows}) for k in ['device','account','brawler']}
    filtered=[r for r in rows if (not device or r['device']==device) and
              (not account or r['account']==account) and (not brawler or r['brawler']==brawler) and r['time']<=now]
    selected=[r for r in filtered if start is None or r['day']>=start]
    outcomes=Counter(r['result'] for r in selected);known=[r['delta'] for r in selected if r['delta'] is not None]
    by_day=defaultdict(list)
    for row in selected:by_day[row['day']].append(row)
    first=start or min(by_day,default=today);span=(today-first).days
    # Bound long histories without dropping matches: aggregate older ranges weekly.
    step=max(1,math.ceil((span+1)/120));series=[];cumulative=0.
    buckets=defaultdict(list)
    for row in selected:
        buckets[(row['day']-first).days//step].append(row)
    day=first
    while day<=today:
        bucket=buckets[(day-first).days//step]
        measured=[r['delta'] for r in bucket if r['delta'] is not None]
        delta=sum(measured) if measured or not bucket else None
        cumulative+=delta or 0.
        series.append({'date':day.isoformat(),'delta':delta,'cumulative':cumulative if delta is not None else None,'matches':len(bucket)})
        day+=timedelta(days=step)
    groups=defaultdict(list)
    for row in selected:groups[row['brawler']].append(row)
    fighters=[]
    for name,items in groups.items():
        measured=[r['delta'] for r in items if r['delta'] is not None]
        fighters.append({'brawler':name,'matches':len(items),'wins':sum(r['result']=='victory' for r in items),
                         'delta':sum(measured) if measured else None,'measured_matches':len(measured)})
    total=len(selected);classified=sum(outcomes[k] for k in ('victory','defeat','draw'))
    previous = None
    if start is not None:
        days = (today-start).days+1
        previous_rows=[r for r in filtered if start-timedelta(days=days)<=r['day']<start]
        previous_known=[r['delta'] for r in previous_rows if r['delta'] is not None]
        previous={'matches':len(previous_rows),'trophy_delta':sum(previous_known) if previous_known else None,
                  'days':days}
    recent=[{k:(v.astimezone().isoformat() if k=='time' else v) for k,v in row.items() if k!='day'}
            for row in sorted(selected,key=lambda r:r['time'],reverse=True)[:50]]
    observed=[r['delta'] for r in selected if r['source']=='observed' and r['delta'] is not None]
    estimated=[r['delta'] for r in selected if r['source']!='observed' and r['delta'] is not None]
    return {'ok':True,'updated_at':now.isoformat(),'options':options,'series':series,'bucket_days':step,
            'recent':recent,'previous':previous,
            'summary':{'matches':total,'wins':outcomes['victory'],'losses':outcomes['defeat'],'draws':outcomes['draw'],
                       'unknown':total-classified,'win_rate':100*outcomes['victory']/classified if classified else None,
                       'trophy_delta':sum(known) if known else None,'trophies_per_match':sum(known)/len(known) if known else None,
                       'measured_matches':len(known),'observed_matches':len(observed),
                       'observed_delta':sum(observed) if observed else None,
                       'estimated_delta':sum(estimated) if estimated else None,
                       'estimated_matches':len(estimated)},
            'fighters':sorted(fighters,key=lambda r:r['matches'],reverse=True),'skipped_rows':skipped,
            'unreadable_devices':unreadable}


def payload(**filters):
    root=Path(utils.DATA_ROOT)
    paths=[root/'cfg'/'match_history.csv', *sorted((root/'devices').glob('*/cfg/match_history.csv'))]
    fingerprint=[]
    for path in paths:
        try:
            stat=path.stat()
            fingerprint.append((str(path),stat.st_mtime_ns,stat.st_size,stat.st_ctime_ns))
        except OSError:
            fingerprint.append((str(path),None))
    now=datetime.now()
    key=(str(root.resolve()),tuple(sorted(filters.items())))
    signature=(now.date(),tuple(fingerprint))
    with _cache_lock:
        cached=_payload_cache.get(key)
        if cached and cached[0]==signature and time.monotonic()-cached[1]<30:
            _payload_cache.move_to_end(key)
            return {**cached[2],'updated_at':now.isoformat()}
    result=build(root,now=now,**filters)
    with _cache_lock:
        _payload_cache[key]=(signature,time.monotonic(),result)
        _payload_cache.move_to_end(key)
        while len(_payload_cache)>64:
            _payload_cache.popitem(last=False)
    return dict(result)
