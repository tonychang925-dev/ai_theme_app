"""Pure contract tests. These do NOT substitute for real CDP + DB E2E."""
import pytest
from tools.jyhf_daily_sync_v1.model import (SyncContractError,validate_list,choose_targets,
                                              validate_quote,digest)
from tools.jyhf_daily_sync_v1.runner import verify_capture_document,market_date_guard,main_sha_guard

def example_list():
    return [{'subjectId':9072494,'subjectName':'AI智能体安全'},
            {'subjectId':9022926,'subjectName':'优必选'}]

def example_quote():
    return ['2026-10-09 00:00:00','x','300369','绿盟科技',8.69,9.15,8.6,9,8.2,0.8,9.3]

def test_valid_list_and_new_target_priority():
    a=validate_list(example_list())
    p=choose_targets(a,{'9022926'},0,1,1)
    assert p['new']==['9072494']
    assert p['targets'][0]=='9072494'
    assert len(p['targets'])==len(set(p['targets']))

def test_duplicate_theme_fails():
    with pytest.raises(SyncContractError,match='duplicate_theme_id'):
        validate_list(example_list()+[example_list()[0]])

def test_quote_success_from_valid_shape():
    q=validate_quote('9072494','AI智能体安全','2026-10-09',[example_quote()],200,1,['300369'])
    assert q['expected_total']==1

@pytest.mark.parametrize('code,total,date,visible,expect',[
    (401,1,'2026-10-09',['300369'],'quote_api_failed'),
    (200,2,'2026-10-09',['300369'],'quote_pagination_incomplete'),
    (200,1,'2026-10-10',['300369'],'quote_trade_date_stale'),
    (200,1,'2026-10-09',['600000'],'visible_quote_mismatch')])
def test_bad_quote_fails_closed(code,total,date,visible,expect):
    with pytest.raises(SyncContractError,match=expect):
        validate_quote('9072494','AI智能体安全',date,[example_quote()],code,total,visible)

def test_immutable_evidence_hash_rejects_tamper():
    q=validate_quote('9072494','AI智能体安全','2026-10-09',[example_quote()],200,1,['300369'])
    doc={'version':'jyhf-ui-daily-v1','trade_date':'2026-10-09','subject_list':example_list(),'captures':[q]}
    verify_capture_document(doc)
    doc['captures'][0]['pairs'][0]['stock_id']='999999'
    with pytest.raises(SyncContractError,match='capture_hash_mismatch'):
        verify_capture_document(doc)

def test_current_day_guard_rejects_weekend_apply_and_candidate_branch():
    with pytest.raises(SyncContractError):
        market_date_guard('2026-10-10','apply')
    with pytest.raises(SyncContractError,match='NOT_CANONICAL_MAIN_FOR_DATABASE_WRITE'):
        main_sha_guard()
