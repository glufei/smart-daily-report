import importlib
import importlib.util
import sqlite3
from uuid import uuid4

import pytest


def new_store(path):
    assert importlib.util.find_spec('smart_daily_report.shared.operation_storage') is not None, 'Persistent operation acceptance is missing'
    module = importlib.import_module('smart_daily_report.shared.operation_storage')
    cls = getattr(module, 'OperationStore', None)
    assert cls is not None
    store = cls(path)
    assert hasattr(store, 'initialize') and hasattr(store, 'accept'), 'Operation acceptance contract is missing'
    store.initialize()
    return store


def accept(store, key, fingerprint='generation:2026-09-25'):
    return store.accept(key, 'generation', '2026-09-25', fingerprint, None,
                        {'github_commits':{'status':'pending','error_code':None},
                         'lark_tasks':{'status':'disabled','error_code':None},
                         'lark_messages':{'status':'disabled','error_code':None}},
                        {channel:{'status':'not_requested','attempts':0,'error_code':None} for channel in ('email','lark')})


def test_same_key_replays_same_operation_across_instances(tmp_path):
    path = tmp_path / 'operations.sqlite3'
    key = str(uuid4())
    first_store = new_store(path)
    first, first_new = accept(first_store, key)
    second, second_new = accept(new_store(path), key)
    assert first_new is True and second_new is False
    assert first == second
    assert first['request_id'] == key and first['status'] == 'running'
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM operations').fetchone()[0] == 1


def test_changed_fingerprint_is_conflict_and_record_unchanged(tmp_path):
    path = tmp_path / 'operations.sqlite3'
    store = new_store(path)
    key = str(uuid4())
    original, _ = accept(store, key)
    before = path.read_bytes()
    caught = None
    try:
        accept(store, key, 'generation:2026-09-26')
    except Exception as error:
        caught = error
    assert getattr(caught, 'code', None) == 'idempotency_conflict', 'A reused key must not silently target different work'
    assert path.read_bytes() == before


def test_competing_accepts_reserve_only_one_activity_slot(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    path = tmp_path / 'operations.sqlite3'
    stores = [new_store(path), new_store(path)]
    barrier = Barrier(2)
    def compete(store):
        barrier.wait(timeout=5)
        try:
            return ('accepted', accept(store, str(uuid4()))[0]['operation_id'])
        except Exception as error:
            return ('rejected', getattr(error, 'code', type(error).__name__))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, stores))
    assert sum(result[0]=='accepted' for result in results) == 1, 'Concurrent requests must not execute two operations'
    assert [result[1] for result in results if result[0]=='rejected'] == ['operation_busy']
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM operations').fetchone()[0] == 1


def test_finish_releases_slot_and_preserves_original_key(tmp_path):
    store = new_store(tmp_path / 'operations.sqlite3')
    key = str(uuid4())
    first, _ = accept(store, key)
    finish = getattr(store, 'finish', None)
    assert finish is not None, 'A completed operation must release the activity slot'
    finish(first['operation_id'], status='succeeded', report_revision='a'*64,
           sources={**first['sources'],'github_commits':{'status':'success','error_code':None}},
           deliveries=first['deliveries'], error_code=None)
    second, new = accept(store, str(uuid4()))
    replay, replay_new = accept(store, key)
    assert new is True and second['operation_id'] != first['operation_id']
    assert replay_new is False and replay['status']=='succeeded'
    assert replay['operation_id']==first['operation_id'] and replay['report_revision']=='a'*64


def test_current_selects_active_then_latest_and_reads_are_readonly(tmp_path):
    path = tmp_path / 'operations.sqlite3'
    store = new_store(path)
    assert all(hasattr(store, name) for name in ('get','by_key','current')), 'Status queries are missing'
    assert store.current() is None
    first, _ = accept(store, str(uuid4()))
    assert store.current() == first
    store.finish(first['operation_id'], status='succeeded', report_revision='a'*64,
                 sources=first['sources'], deliveries=first['deliveries'], error_code=None)
    second, _ = accept(store, str(uuid4()))
    before = path.read_bytes()
    assert store.current()==second
    assert store.by_key(first['request_id'])['status']=='succeeded'
    assert store.get(second['operation_id'])==second
    assert store.get(str(uuid4())) is None
    assert store.by_key(str(uuid4())) is None
    assert path.read_bytes()==before
    store.finish(second['operation_id'], status='failed', report_revision=None,
                 sources=second['sources'], deliveries=second['deliveries'], error_code='all_sources_failed')
    assert store.current()['operation_id']==second['operation_id']


def test_status_reads_never_create_missing_database(tmp_path):
    module = importlib.import_module('smart_daily_report.shared.operation_storage')
    path = tmp_path/'missing.sqlite3'
    store = module.OperationStore(path)
    assert hasattr(store, 'current')
    with pytest.raises(sqlite3.Error):
        store.current()
    assert not path.exists()


def test_restart_marks_pending_delivery_unknown_without_replaying(tmp_path):
    path = tmp_path / 'operations.sqlite3'
    store = new_store(path)
    record, _ = store.accept(str(uuid4()), 'delivery', '2026-09-25', 'send:a', 'a'*64,
        {name:None for name in ('github_commits','lark_tasks','lark_messages')},
        {'email':{'status':'accepted','attempts':1,'error_code':None},
         'lark':{'status':'pending','attempts':0,'error_code':None}})
    restarted = new_store(path)
    recover = getattr(restarted, 'recover_interrupted', None)
    assert recover is not None, 'Restart must not silently leave retryable pending deliveries'
    recover()
    recovered = restarted.get(record['operation_id'])
    assert recovered['status']=='interrupted' and recovered['error_code']=='operation_interrupted'
    assert recovered['deliveries']['lark']=={'status':'unknown','attempts':0,'error_code':'delivery_unknown'}
    assert recovered['deliveries']['email']==record['deliveries']['email']
    before = path.read_bytes()
    recover()
    assert path.read_bytes()==before
    next_record, fresh = accept(restarted, str(uuid4()))
    assert fresh and next_record['operation_id']!=record['operation_id']


def test_channel_result_is_persisted_before_another_channel(tmp_path):
    store = new_store(tmp_path / 'operations.sqlite3')
    record, _ = store.accept(str(uuid4()), 'delivery', '2026-09-25', 'send:a', 'a'*64,
        {name:None for name in ('github_commits','lark_tasks','lark_messages')},
        {name:{'status':'pending','attempts':0,'error_code':None} for name in ('email','lark')})
    write_channel = getattr(store, 'record_delivery', None)
    assert write_channel is not None, 'Channel evidence must survive before the next send'
    write_channel(record['operation_id'], 'email', {'status':'accepted','attempts':1,'error_code':None})
    saved = store.get(record['operation_id'])
    assert saved['status']=='running'
    assert saved['deliveries']['email']=={'status':'accepted','attempts':1,'error_code':None}
    assert saved['deliveries']['lark']=={'status':'pending','attempts':0,'error_code':None}


def test_preview_metadata_is_for_exact_revision_and_reads_are_readonly(tmp_path):
    path=tmp_path/'operations.sqlite3'
    store=new_store(path)
    metadata=getattr(store,'preview_metadata',None)
    assert metadata is not None, 'Preview must show evidence for its own saved revision'
    assert metadata('2026-09-25','a'*64)==(None, {'email':None,'lark':None})
    generation,_=accept(store,str(uuid4()))
    sources={**generation['sources'],'github_commits':{'status':'success','error_code':None}}
    store.finish(generation['operation_id'],status='succeeded',report_revision='a'*64,
                 sources=sources,deliveries=generation['deliveries'],error_code=None)
    deliveries={'email':{'status':'accepted','attempts':1,'error_code':None},
                'lark':{'status':'not_requested','attempts':0,'error_code':None}}
    delivery,_=store.accept(str(uuid4()),'delivery','2026-09-25','send:a','a'*64,
                           {name:None for name in generation['sources']},deliveries)
    store.finish(delivery['operation_id'],status='succeeded',report_revision='a'*64,
                 sources=delivery['sources'],deliveries=deliveries,error_code=None)
    before=path.read_bytes()
    assert metadata('2026-09-25','a'*64)==(sources,{'email':deliveries['email'],'lark':None})
    assert metadata('2026-09-25','b'*64)==(None,{'email':None,'lark':None})
    assert metadata('2026-09-24','a'*64)==(None,{'email':None,'lark':None})
    assert path.read_bytes()==before


def test_store_failure_prevents_acceptance_before_business(tmp_path):
    path=tmp_path/'operations.sqlite3'
    store=new_store(path)
    path.write_bytes(b'not a sqlite database')
    before=path.read_bytes()
    with pytest.raises(sqlite3.Error):
        accept(store,str(uuid4()))
    assert path.read_bytes()==before


def test_delivery_preparation_runs_only_after_replay_and_busy_checks(tmp_path):
    import inspect
    from smart_daily_report.shared.operation_storage import OperationConflict
    store=new_store(tmp_path/'operations.sqlite3')
    assert 'before_insert' in inspect.signature(store.accept).parameters, 'Transactional preparation is missing'
    calls=[]
    kwargs=dict(request_id=str(uuid4()),kind='delivery',report_date='2026-09-25',request_fingerprint='delivery-a',report_revision='a'*64,
      sources={key:None for key in ('github_commits','lark_tasks','lark_messages')},
      deliveries={'email':{'status':'pending','attempts':0,'error_code':None},'lark':{'status':'not_requested','attempts':0,'error_code':None}},
      before_insert=lambda:calls.append('prepared'))
    first,new=store.accept(**kwargs); assert new and calls==['prepared']
    replay,new=store.accept(**kwargs); assert not new and replay==first and calls==['prepared']
    with pytest.raises(OperationConflict): store.accept(**{**kwargs,'request_id':str(uuid4())})
    assert calls==['prepared']


@pytest.mark.parametrize('status',['accepted','partial_failure','unknown'])
def test_delivery_guard_is_inside_acceptance_transaction(tmp_path,status):
    from smart_daily_report.shared.operation_storage import OperationConflict
    store=new_store(tmp_path/'operations.sqlite3')
    sources={key:None for key in ('github_commits','lark_tasks','lark_messages')}
    deliveries={'email':{'status':'pending','attempts':0,'error_code':None},'lark':{'status':'not_requested','attempts':0,'error_code':None}}
    first,_=store.accept(str(uuid4()),'delivery','2026-09-25','first','a'*64,sources,deliveries)
    terminal={**deliveries,'email':{'status':status,'attempts':1,'error_code':None}}
    store.finish(first['operation_id'],status='succeeded',report_revision='a'*64,sources=sources,deliveries=terminal,error_code=None)
    before=store.path.read_bytes()
    with pytest.raises(OperationConflict,match='delivery_not_repeatable'):
        store.accept(str(uuid4()),'delivery','2026-09-25','second','a'*64,sources,deliveries)
    assert store.path.read_bytes()==before


def test_failed_delivery_preparation_rolls_back_without_acceptance(tmp_path):
    store=new_store(tmp_path/'operations.sqlite3')
    before=store.path.read_bytes()
    def fail(): raise ValueError('revision changed')
    with pytest.raises(ValueError): store.accept(str(uuid4()),'delivery','2026-09-25','body','a'*64,{}, {},before_insert=fail)
    assert store.path.read_bytes()==before and store.current() is None
