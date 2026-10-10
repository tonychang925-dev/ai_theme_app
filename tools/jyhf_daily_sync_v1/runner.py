"""Controlled JYHF normal-App daily capture and date-scoped append-only DB admission.

Production admission is restricted to exact checked-out canonical main. Candidate
branches support plan/capture/verification only, never live writes.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import os
import subprocess
import sys
import traceback
from .model import SyncContractError,validate_list,choose_targets,validate_quote,digest,effective_date
from .cdp import AppSession

CN=ZoneInfo('Asia/Shanghai')
BATCH_VERSION='jyhf-ui-daily-v1'
ROOT=Path(__file__).resolve().parents[2]
DEFAULT_STATE=Path.home()/'rea-analysis'/'jiuyinghengfeng'/'daily_sync_state'

async def existing_ids(dbname):
    import asyncpg
    c=await asyncpg.connect(database=dbname,timeout=10)
    try:
        async with c.transaction(readonly=True):
            rows=await c.fetch("SELECT subject_key FROM subject_node_staging")
            return {r['subject_key'] for r in rows}
    finally:await c.close()

def main_sha_guard():
    try:
        branch=subprocess.check_output(['git','-C',str(ROOT),'branch','--show-current'],text=True).strip()
        head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        ref=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','origin/main'],text=True).strip()
    except (OSError,subprocess.CalledProcessError):
        raise SyncContractError('git_canonical_main_unverifiable') from None
    if branch!='main' or head!=ref:
        raise SyncContractError('NOT_CANONICAL_MAIN_FOR_DATABASE_WRITE')
    status=subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain=v1','--untracked-files=no'],text=True)
    if status.strip():
        raise SyncContractError('DIRTY_CANONICAL_MAIN_FOR_DATABASE_WRITE')
    return head

def market_date_guard(trade_date, mode, allow_historical_capture=False):
    selected=effective_date(trade_date)
    now=datetime.now(CN).date()
    if selected.weekday()>4 and not allow_historical_capture:
        raise SyncContractError('weekend_is_not_a_trade_session')
    if mode=='apply' and (selected!=now or selected.weekday()>4):
        raise SyncContractError('live_apply_requires_current_cn_weekday')
    if mode in ('plan','capture') and not allow_historical_capture and selected!=now:
        raise SyncContractError('capture_date_not_today_without_explicit_historical_preview')
    return selected

def atomic_json(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    if temp.exists():
        raise SyncContractError('unclosed_temp_file')
    with temp.open('x',encoding='utf-8') as f:
        json.dump(content,f,ensure_ascii=False,indent=2)
        f.flush();os.fsync(f.fileno())
    temp.rename(path)

def update_cursor_state(path,content):
    # Unlike evidence snapshots, the successful run pointer is intentionally mutable.
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.new')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(content,f,ensure_ascii=False,indent=2)
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def load_json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as e:raise SyncContractError(f'input_unavailable:{path.name}') from e

def _root_for_date(state,trade_date):
    return state/'captures'/trade_date

def choose_output(state,trade_date,mode):
    d=_root_for_date(state,trade_date)
    if mode in ('plan','capture'):
        # explicit run id prevents silently replacing earlier evidence.
        stamp=datetime.now(CN).strftime('%Y%m%dT%H%M%S%f')
        return d/stamp
    raise SyncContractError('capture_only_output')

def verify_capture_document(doc):
    if doc.get('version')!=BATCH_VERSION:raise SyncContractError('snapshot_version_mismatch')
    trade_date=doc.get('trade_date')
    effective_date(trade_date)
    subjects=validate_list(doc.get('subject_list'))
    captures=doc.get('captures')
    if not isinstance(captures,list) or not captures:raise SyncContractError('zero_captures')
    seen=set()
    for item in captures:
        sid=item.get('subject_key')
        if sid in seen or sid not in subjects:raise SyncContractError('duplicate_or_unknown_capture_subject')
        seen.add(sid)
        pairs=item.get('pairs')
        if not isinstance(pairs,list) or not pairs:raise SyncContractError('empty_capture_pairs')
        if item.get('trade_date')!=trade_date or item.get('expected_total')!=len(pairs):
            raise SyncContractError('capture_day_or_total_mismatch')
        if item.get('roster_sha256')!=digest(sorted(pairs,key=lambda x:x['stock_id'])):
            raise SyncContractError('capture_hash_mismatch')
        if len({x['stock_id'] for x in pairs})!=len(pairs):
            raise SyncContractError('duplicate_capture_stock')
        import re
        if any(not re.fullmatch(r'[0-9]{6}',str(x.get('stock_id',''))) or
               not isinstance(x.get('stock_name'),str) or
               not x['stock_name'].strip() or x['stock_name']=='****' for x in pairs):
            raise SyncContractError('invalid_capture_member')
    return subjects

def capture(args):
    trade_date=args.trade_date
    market_date_guard(trade_date,args.mode,args.historical_preview)
    state=Path(args.state_dir).expanduser().resolve()
    existing=asyncio.run(existing_ids(args.database))
    prior=state/'last_success.json'
    cursor=int(load_json(prior).get('next_cursor',0)) if prior.exists() else 0
    session=AppSession(args.cdp_port)
    try:
        themes_list=session.read_list()
        themes=validate_list(themes_list)
        plan=choose_targets(themes,existing,cursor,args.top,args.rotate)
        if args.max_targets>0 and len(plan['targets'])>args.max_targets:
            if args.mode=='apply':raise SyncContractError('target_limit_cannot_apply')
            plan['targets']=plan['targets'][:args.max_targets]
        destination=choose_output(state,trade_date,args.mode)
        manifest={'version':BATCH_VERSION,'mode':args.mode,
          'trade_date':trade_date,'captured_at':datetime.now(CN).isoformat(),
          'status':'PLAN_ONLY' if args.mode=='plan' else 'CAPTURE_IN_PROGRESS',
          'source':'JYHF ordinary authenticated App Vue subject list + normal quote response',
          'root_subject_count':len(themes),'previous_known_count':len(existing),
          'new_subject_ids':plan['new'],'targets':plan['targets'],
          'previous_cursor':cursor,'next_cursor':plan['next_cursor'],
          'subject_list_hash':digest(themes_list),'git_candidate_head':_read_sha()}
        destination.mkdir(parents=True,exist_ok=False)
        atomic_json(destination/'plan.json',manifest)
        if args.mode=='plan':
            print('PLAN_ONLY',json.dumps({k:v for k,v in manifest.items() if k not in ('targets','new_subject_ids')},ensure_ascii=False))
            print('PLAN_TARGET_IDS',json.dumps(plan['targets'],ensure_ascii=False))
            print('PLAN_FILE',destination/'plan.json')
            return 0
        captures=[]
        for index,sid in enumerate(plan['targets'],1):
            name=themes[sid]['subjectName']
            proof=session.read_stock(sid,name,trade_date)
            captures.append(proof)
            if index%10==0 or index==len(plan['targets']):
                print('CAPTURE',index,'/',len(plan['targets']),'last',sid,'stocks',len(proof['pairs']),flush=True)
        branches={}
        for sid in plan['new']:
            if sid not in plan['targets']:raise SyncContractError('new_theme_not_in_capture')
            branches[sid]=session.read_branches(sid,themes[sid]['subjectName'])
        full={'version':BATCH_VERSION,'trade_date':trade_date,'captured_at':datetime.now(CN).isoformat(),
           'subject_list':themes_list,'captures':captures,'branches_new_subjects':branches,
           'next_cursor':plan['next_cursor'],'source_plan_sha256':digest(manifest),
           'source':'JYHF ordinary authenticated App session, no token inspection'}
        verify_capture_document(full)
        atomic_json(destination/'capture.json',full)
        args.result_capture_file=str(destination/'capture.json')
        atomic_json(destination/'capture_status.json',
                    {'status':'VALIDATED_CAPTURE','root_count':len(themes),'theme_count':len(captures),
                     'membership_edges':sum(len(v['pairs']) for v in captures),'file_sha256':digest(full),
                     'date':trade_date,'source':full['source']})
        print('CAPTURE_VALIDATED',json.dumps({
             'themes':len(captures),'pairs':sum(len(v['pairs']) for v in captures),
             'new':len(plan['new']),'branch_roots':len(branches),
             'file':str(destination/'capture.json')},ensure_ascii=False),flush=True)
        return 0
    finally:
        try:
            result=session.restore_selection()
            if result is not None:print('APP_SELECTION_RESTORE',result,flush=True)
        except Exception as e:
            print('APP_SELECTION_RESTORE_WARNING',type(e).__name__,flush=True)
        session.close()

def _read_sha():
    return subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()

async def apply_capture(args):
    date=market_date_guard(args.trade_date,'apply')
    sha=main_sha_guard()
    cap=Path(args.capture_file).resolve()
    doc=load_json(cap)
    subjects=verify_capture_document(doc)
    if doc['trade_date']!=str(date):raise SyncContractError('current_date_source_mismatch')
    captures=doc['captures']
    day=effective_date(doc['trade_date'])
    observed=[(day,c['subject_key'],item['stock_id'],item['stock_name'],
               c['roster_sha256']) for c in captures for item in c['pairs']]
    if len(observed)!=len(set((x[1],x[2]) for x in observed)):raise SyncContractError('duplicate_member_pair')
    import asyncpg
    conn=await asyncpg.connect(database=args.database,timeout=10)
    try:
        async with conn.transaction(isolation='serializable'):
            await conn.execute("SET LOCAL statement_timeout='120000ms'")
            await conn.execute("SELECT pg_advisory_xact_lock(20261010,9018144)")
            await conn.execute("""CREATE TABLE IF NOT EXISTS jyhf_subject_member_observation (
                trade_date date NOT NULL, subject_key varchar(80) NOT NULL, stock_id varchar(20) NOT NULL,
                stock_name varchar(100) NOT NULL, roster_sha256 char(64) NOT NULL,
                observed_at timestamptz NOT NULL DEFAULT now(), source_type varchar(50) NOT NULL,
                PRIMARY KEY(trade_date,subject_key,stock_id))""")
            await conn.execute("""CREATE TABLE IF NOT EXISTS jyhf_subject_member_capture (
                trade_date date NOT NULL, subject_key varchar(80) NOT NULL,
                observed_count integer NOT NULL, roster_sha256 char(64) NOT NULL,
                captured_at timestamptz NOT NULL DEFAULT now(), source_type varchar(50) NOT NULL,
                PRIMARY KEY(trade_date,subject_key))""")
            for c in captures:
                prior=await conn.fetchrow("""SELECT roster_sha256,observed_count FROM jyhf_subject_member_capture
                    WHERE trade_date=$1::date AND subject_key=$2""",day,c['subject_key'])
                if prior and (prior['roster_sha256'].strip()!=c['roster_sha256'] or prior['observed_count']!=c['expected_total']):
                    raise SyncContractError('IMMUTABLE_DAILY_ROSTER_CONFLICT')
            await conn.execute("""CREATE TEMP TABLE daily_pairs(
                trade_date date,subject_key text,stock_id text,stock_name text,roster_hash text) ON COMMIT DROP""")
            await conn.copy_records_to_table('daily_pairs',records=observed,columns=['trade_date','subject_key','stock_id','stock_name','roster_hash'])
            current=await conn.fetchval('SELECT count(*) FROM daily_pairs')
            if current!=len(observed):raise SyncContractError('source_copy_incomplete')
            new_nodes=0
            for theme_id,meta in subjects.items():
                if theme_id not in {c['subject_key'] for c in captures}:continue
                src=json.dumps({'source':'jyhf_ui_daily','captured_at':doc['captured_at'],
                    'source_sha256':digest(meta),'quote_trade_date':doc['trade_date'],'subject':meta},ensure_ascii=False)
                n=await conn.fetchval("""INSERT INTO subject_node_staging
                    (subject_key,subject_name,node_level,source_type,raw_json,ingest_batch_id)
                    VALUES($1,$2,1,'jyhf_ui_daily',$3::jsonb,$4)
                    ON CONFLICT(subject_key) DO NOTHING RETURNING id""",
                    theme_id,meta['subjectName'],src,f"jyhf_ui_{doc['trade_date'].replace('-','')}")
                new_nodes+=n is not None
            new_branches=0
            for sid,names in doc.get('branches_new_subjects',{}).items():
                if sid not in subjects:raise SyncContractError('unknown_branch_parent')
                for name in names:
                    child=f'{sid}_{name}'
                    if len(child)>80:child=sid+'_branch_'+digest(name)[:20]
                    src=json.dumps({'source':'jyhf_ui_visible_dom','captured_at':doc['captured_at'],
                        'root_subject_id':sid,'branch_name':name,'official_child_id':None},ensure_ascii=False)
                    n=await conn.fetchval("""INSERT INTO subject_children_staging
                      (parent_subject_key,child_subject_key,child_name,full_name,depth,source_type,raw_json,ingest_batch_id)
                      VALUES($1,$2,$3,$4,1,'jyhf_ui_visible_dom',$5::jsonb,$6)
                      ON CONFLICT(parent_subject_key,child_subject_key) DO NOTHING RETURNING id""",
                      sid,child,name,subjects[sid]['subjectName']+'/'+name,src,f"jyhf_ui_{doc['trade_date'].replace('-','')}")
                    new_branches+=n is not None
            source=f"'jyhf_ui_daily'"
            result={}
            result['observations']=await conn.fetchval("""WITH inserted AS (
                 INSERT INTO jyhf_subject_member_observation(trade_date,subject_key,stock_id,stock_name,roster_sha256,source_type)
                 SELECT trade_date,subject_key,stock_id,stock_name,roster_hash,'jyhf_ui_daily' FROM daily_pairs
                 ON CONFLICT DO NOTHING RETURNING 1) SELECT count(*)::int FROM inserted""")
            counts=await conn.fetch("""SELECT subject_key,count(*)::int AS n,max(roster_hash) AS h
                                      FROM daily_pairs GROUP BY subject_key""")
            for row in counts:
                await conn.execute("""INSERT INTO jyhf_subject_member_capture
                  (trade_date,subject_key,observed_count,roster_sha256,source_type)
                  VALUES($1::date,$2,$3,$4,'jyhf_ui_daily')
                  ON CONFLICT DO NOTHING""",day,row['subject_key'],row['n'],row['h'])
            for table,stockname,colname,typcol in [
                ('subject_stock_map','name','source_type',None),
                ('subject_stock_staging','stock_name','source_type','relation_type_candidate'),
                ('theme_stock_map','stock_name','source_type','relation_type')]:
                if table=='subject_stock_map':
                    cols="subject_key,stock_id,name,top,start_date,source_type,evidence_json"
                    expr="""p.subject_key,p.stock_id,p.stock_name,FALSE,p.trade_date,'jyhf_ui_daily',
                             jsonb_build_object('capture_date',p.trade_date::text,'source','jyhf_ui_daily',
                               'historical_membership_proven',FALSE,'roster_sha256',p.roster_hash)"""
                elif table=='subject_stock_staging':
                    cols="subject_key,stock_id,stock_name,relation_type_candidate,top,source_type,evidence_json,ingest_batch_id"
                    expr="""p.subject_key,p.stock_id,p.stock_name,'member',FALSE,'jyhf_ui_daily',
                         jsonb_build_object('capture_date',p.trade_date::text,'source','jyhf_ui_daily',
                         'roster_sha256',p.roster_hash),'jyhf_ui_'||replace(p.trade_date::text,'-','')"""
                else:
                    cols="subject_key,theme_name,stock_id,stock_name,relation_type,evidence_source,source_type,evidence_json"
                    expr="""p.subject_key,n.subject_name,p.stock_id,p.stock_name,'member','jyhf_ui_daily','jyhf_ui_daily',
                         jsonb_build_object('capture_date',p.trade_date::text,'source','jyhf_ui_daily',
                         'roster_sha256',p.roster_hash)"""
                fromstr="daily_pairs p" + (" JOIN subject_node_staging n ON n.subject_key=p.subject_key" if table=='theme_stock_map' else "")
                sql=f"""WITH inserted AS (INSERT INTO {table}({cols}) SELECT {expr} FROM {fromstr}
                    ON CONFLICT(subject_key,stock_id) DO NOTHING RETURNING 1)
                    SELECT count(*)::int FROM inserted"""
                result[table]=await conn.fetchval(sql)
                missed=await conn.fetchval(f"""SELECT count(*)::int FROM daily_pairs p LEFT JOIN {table} t
                     ON t.subject_key=p.subject_key AND t.stock_id=p.stock_id WHERE t.id IS NULL""")
                if missed:raise SyncContractError(f'{table}_postwrite_missing:{missed}')
            missing=await conn.fetchval("""SELECT count(*)::int FROM daily_pairs p LEFT JOIN
                jyhf_subject_member_observation a ON a.trade_date=p.trade_date AND
                a.subject_key=p.subject_key AND a.stock_id=p.stock_id
                WHERE a.stock_id IS NULL""")
            if missing:raise SyncContractError('dated_observation_postwrite_incomplete')
        return {'status':'COMMITTED_VERIFIED','trade_date':doc['trade_date'],'git_main_sha':sha,
                'subject_count':len(captures),'subject_stock_pairs':len(observed),
                'new_subject_nodes':new_nodes,'new_visible_branches':new_branches,'inserted':result,
                'existing_rows_updated':0,'source_capture':str(cap),'source_sha256':digest(doc)}
    finally:await conn.close()

def run():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['plan','capture','apply','daily'],default='plan')
    p.add_argument('--trade-date',default=datetime.now(CN).strftime('%Y-%m-%d'))
    p.add_argument('--historical-preview',action='store_true',help='Only plan/capture, never apply')
    p.add_argument('--database',default='stock_data_test')
    p.add_argument('--state-dir',default=str(DEFAULT_STATE))
    p.add_argument('--cdp-port',type=int,default=9223)
    p.add_argument('--top',type=int,default=25)
    p.add_argument('--rotate',type=int,default=35)
    p.add_argument('--max-targets',type=int,default=0)
    p.add_argument('--capture-file',help='Required for apply; must be immutable validated source JSON')
    a=p.parse_args()
    try:
        if a.mode=='daily':
            if a.historical_preview or a.max_targets:
                raise SyncContractError('daily_cannot_be_historical_or_target_limited')
            market_date_guard(a.trade_date,'apply')
            main_sha_guard()
            a.mode='capture'
            captured=capture(a)
            if captured!=0 or not getattr(a,'result_capture_file',None):
                raise SyncContractError('daily_capture_incomplete')
            a.mode='apply'
            a.capture_file=a.result_capture_file
        if a.mode=='apply':
            if not a.capture_file:raise SyncContractError('apply_requires_capture_file')
            filename=Path(a.capture_file).parent/'apply_result.json'
            if filename.exists():raise SyncContractError('apply_result_preexists_no_overwrite')
            result=asyncio.run(apply_capture(a))
            atomic_json(filename,result)
            print('APPLY_VERIFIED',json.dumps(result,ensure_ascii=False))
            state=Path(a.state_dir).expanduser()/'last_success.json'
            update_cursor_state(state,{'trade_date':a.trade_date,'next_cursor':load_json(Path(a.capture_file)).get('next_cursor',0),
                                       'apply_sha256':digest(result),'status':'COMMITTED_VERIFIED'})
            return 0
        return capture(a)
    except SyncContractError as e:
        print(f'BLOCKED_FAIL_CLOSED:{e}',file=sys.stderr,flush=True)
        return 2
    except Exception as e:
        print(f'UNEXPECTED_FAILURE:{type(e).__name__}:{e}',file=sys.stderr,flush=True)
        return 3

if __name__=='__main__':
    sys.exit(run())
