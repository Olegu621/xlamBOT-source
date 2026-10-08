"""Read-only statistics across device histories; no fabricated observations."""
import csv
import math
import io
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict
import utils


def number(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None


def build(root, period='7', device='', account='', brawler='', now=None):
    if period not in {'today','7','30','all'}:raise ValueError('Invalid period')
    now=now or datetime.now();today=now.date()
    start=None if period=='all' else today-timedelta(days=0 if period=='today' else int(period)-1)
    paths=[('default',Path(root)/'cfg'/'match_history.csv')]
    paths += [(p.parent.parent.name,p) for p in sorted((Path(root)/'devices').glob('*/cfg/match_history.csv'))]
    rows=[];skipped=0;unreadable=[]
    for key,path in paths:
        if not path.is_file():continue
        try:
            records = list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
        except (OSError, UnicodeError, csv.Error):
            unreadable.append(key)
            continue
        for row in records:
                try:stamp=datetime.fromisoformat(row.get('date_time','').replace('Z','+00:00'))
                except (ValueError,TypeError):skipped+=1;continue
                if stamp.tzinfo is not None:stamp=stamp.astimezone()
                name=str(row.get('brawler_name') or '').strip()
                if not name:skipped+=1;continue
                # Old rows did not record account identity. Never assign them
                # retrospectively to the account currently configured on a device.
                tag=str(row.get('account_tag') or '').strip()
                acct=tag if tag and tag!='#' else 'unknown:'+key
                rows.append({'device':key,'account':acct,'brawler':name,'day':stamp.date(),
                             'result':row.get('result','').lower(),'delta':number(row.get('trophy_delta')),
                             'source':row.get('trophy_source') or 'legacy'})
    options={k:sorted({row[k] for row in rows}) for k in ['device','account','brawler']}
    selected=[r for r in rows if (not device or r['device']==device) and
              (not account or r['account']==account) and (not brawler or r['brawler']==brawler) and
              (start is None or r['day']>=start) and r['day']<=today]
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
    return {'ok':True,'updated_at':now.isoformat(),'options':options,'series':series,'bucket_days':step,
            'summary':{'matches':total,'wins':outcomes['victory'],'losses':outcomes['defeat'],'draws':outcomes['draw'],
                       'unknown':total-classified,'win_rate':100*outcomes['victory']/classified if classified else None,
                       'trophy_delta':sum(known) if known else None,'trophies_per_match':sum(known)/len(known) if known else None,
                       'measured_matches':len(known),'estimated_matches':sum(r['source']!='observed' and r['delta'] is not None for r in selected)},
            'fighters':sorted(fighters,key=lambda r:r['matches'],reverse=True),'skipped_rows':skipped,
            'unreadable_devices':unreadable}


def payload(**filters):
    return build(utils.DATA_ROOT,**filters)
