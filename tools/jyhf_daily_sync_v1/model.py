"""Pure validation and deterministic candidate selection, no network or database operations."""
from __future__ import annotations
from datetime import date
import hashlib
import json
import re

class SyncContractError(RuntimeError):
    """Missing canonical evidence; do not write."""

def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

def digest(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def validate_list(items: list[dict]) -> dict[str, dict]:
    if not isinstance(items, list) or len(items) < 1:
        raise SyncContractError('empty_theme_list')
    output = {}
    for r in items:
        if not isinstance(r, dict):
            raise SyncContractError('non_dict_theme')
        key = str(r.get('subjectId', ''))
        name = r.get('subjectName')
        if not re.fullmatch(r'[0-9]{1,12}', key) or not isinstance(name, str) or not name.strip():
            raise SyncContractError('invalid_theme_identity')
        if key in output:
            raise SyncContractError('duplicate_theme_id')
        output[key] = dict(r)
    return output

def choose_targets(themes: dict, known: set[str], cursor: int, top_n: int, rotate_n: int):
    ids = sorted(themes, key=lambda k: int(k))
    if not ids:
        raise SyncContractError('empty_theme_universe')
    new_ids = [i for i in ids if i not in known]
    ordered = list(themes)
    prioritized = ordered[:max(0, top_n)]
    start = cursor % len(ids)
    rotated = [ids[(start+i) % len(ids)] for i in range(max(0, min(rotate_n, len(ids))))]
    targets = list(dict.fromkeys(new_ids + prioritized + rotated))
    return {'new':new_ids, 'targets':targets, 'next_cursor':(start + max(0, rotate_n)) % len(ids),
            'universe':len(ids), 'prioritized':prioritized, 'rotated':rotated}

def validate_quote(theme_id: str, theme_name: str, trade_date: str, rows: list,
                   api_code: int, api_total: int, visible_codes: list[str]):
    if api_code != 200 or not isinstance(api_total,int):
        raise SyncContractError('quote_api_failed')
    if api_total <= 0 or not isinstance(rows,list) or len(rows) != api_total:
        raise SyncContractError('quote_pagination_incomplete')
    pairs=[]
    for raw in rows:
        if not isinstance(raw,list) or len(raw)<11:
            raise SyncContractError('invalid_quote_row')
        stock_id=str(raw[2]);name=str(raw[3])
        if not re.fullmatch(r'[0-9]{6}',stock_id) or not name.strip() or name=='****':
            raise SyncContractError('masked_or_invalid_stock')
        if not str(raw[0]).startswith(trade_date):
            raise SyncContractError('quote_trade_date_stale')
        pairs.append({'stock_id':stock_id,'stock_name':name})
    ids=[x['stock_id'] for x in pairs]
    if len(ids)!=len(set(ids)):
        raise SyncContractError('duplicate_stock_in_quote')
    if len(visible_codes)!=len(ids) or set(visible_codes)!=set(ids):
        raise SyncContractError('visible_quote_mismatch')
    return {'subject_key':theme_id, 'subject_name':theme_name,
            'trade_date':trade_date,'expected_total':api_total,
            'pairs':pairs,'roster_sha256':digest(sorted(pairs,key=lambda x:x['stock_id']))}

def validate_first_level_branches(root_name: str, visible_root: str, branches: list):
    if root_name!=visible_root or not isinstance(branches,list):
        raise SyncContractError('unverified_first_level_tree')
    seen=set();out=[]
    for name in branches:
        if not isinstance(name,str) or not name.strip() or name=='****' or len(name)>150:
            raise SyncContractError('invalid_branch_label')
        name=name.strip()
        if name!=root_name and name not in seen:
            seen.add(name);out.append(name)
    return out

def effective_date(raw: str) -> date:
    try: return date.fromisoformat(raw)
    except (ValueError,TypeError): raise SyncContractError('invalid_trade_date') from None
