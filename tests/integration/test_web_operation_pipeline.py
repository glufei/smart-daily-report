import importlib
import importlib.util
from dataclasses import replace
from datetime import date
from uuid import uuid4

import httpx
import pytest

from smart_daily_report.shared.operation_storage import OperationStore
from smart_daily_report.web.operation_schemas import GenerationRequest


def make_service(config, tmp_path, handler=None):
    assert importlib.util.find_spec('smart_daily_report.web.operations') is not None, 'Real operation service is missing'
    module=importlib.import_module('smart_daily_report.web.operations')
    cls=getattr(module,'OperationService',None)
    assert cls is not None
    cfg=replace(config,github_repositories=['acme/repo'],database_path=str(tmp_path/'reports.sqlite3'))
    store=OperationStore(tmp_path/'reports.sqlite3.operations.sqlite3')
    factory=lambda: httpx.Client(transport=httpx.MockTransport(handler or (lambda request:httpx.Response(200,json=[]))))
    service=cls(cfg,store,client_factory=factory)
    return service,store,cfg


def test_generation_acceptance_is_durable_running_and_not_delivery(config,tmp_path):
    requests=[]
    service,store,cfg=make_service(config,tmp_path,lambda request:(requests.append(request),httpx.Response(200,json=[]))[1])
    accept=getattr(service,'accept_generation',None)
    assert accept is not None, 'Generation acceptance is missing'
    key=str(uuid4())
    body=GenerationRequest(report_date=date(2026,9,25))
    accepted=accept(body,key)
    assert accepted.is_new and accepted.snapshot is None
    assert accepted.view.status=='running' and accepted.view.request_id==key
    assert accepted.view.sources.github_commits.status=='pending'
    assert accepted.view.sources.lark_tasks.status=='disabled'
    assert accepted.view.deliveries.email.status=='not_requested'
    assert store.by_key(key)['operation_id']==accepted.view.operation_id
    assert requests==[] and not (tmp_path/'reports.sqlite3').exists()
    replay=accept(body,key)
    assert not replay.is_new and replay.view.operation_id==accepted.view.operation_id


def test_real_pipeline_commits_are_projected_into_saved_preview(config,tmp_path,monkeypatch):
    from pathlib import Path
    from smart_daily_report.shared.storage import get_report
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,json=[{'sha':'abc','commit':{'message':'Ship actual work','author':{'name':'Octo','date':'2026-09-25T02:00:00Z'}},
                         'author':{'login':'octo'},'html_url':'https://github.test/abc',
                         'stats':{'additions':3,'deletions':1},'files':[{'filename':'a.py'}]}])
    def forbidden(*args,**kwargs):
        raise AssertionError('Generation must not deliver')
    monkeypatch.setattr('smart_daily_report.main.send_email',forbidden)
    monkeypatch.setattr('smart_daily_report.main.send_lark_message',forbidden)
    service,store,cfg=make_service(config,tmp_path,handler)
    execute=getattr(service,'execute',None)
    assert execute is not None, 'Accepted generation does not execute the real pipeline'
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4()))
    execute(accepted.view.operation_id)
    result=store.get(accepted.view.operation_id)
    assert result['status']=='succeeded'
    assert result['sources']['github_commits']['status']=='success'
    assert result['sources']['lark_tasks']['status']=='disabled'
    assert all(item['status']=='not_requested' for item in result['deliveries'].values())
    assert len(result['report_revision'])==64
    report=get_report(Path(cfg.database_path),date(2026,9,25))
    record=report.members[0].commits[0]
    assert (record.record_id,record.member_id,record.additions,record.deletions,record.files_changed)==('abc','u1',3,1,1)
    assert len(requests)==1 and requests[0].method=='GET'


def test_version_hash_changes_for_content_and_preserves_list_order(records,statuses):
    from datetime import datetime,timezone
    from smart_daily_report.generator.formatter import generate_daily_report
    from smart_daily_report.shared.models import MemberReport
    module=importlib.import_module('smart_daily_report.web.operations')
    revision=getattr(module,'report_revision',None)
    assert revision is not None, 'Preview version digest is missing'
    report=generate_daily_report(date(2026,9,25),'team',[MemberReport('a','A',[records['commit']]),MemberReport('b','B')],statuses,datetime(2026,9,25,tzinfo=timezone.utc))
    assert revision(report)==revision(replace(report))
    assert len(revision(report))==64
    assert revision(report)!=revision(replace(report,generated_at=datetime(2026,9,25,1,tzinfo=timezone.utc)))
    assert revision(report)!=revision(replace(report,members=list(reversed(report.members))))
    assert revision(report)!=revision(replace(report,markdown='changed confirmed content'))


def test_failed_source_result_projects_safe_error_without_report(config,tmp_path):
    service,store,cfg=make_service(config,tmp_path,lambda request:httpx.Response(403))
    execute=getattr(service,'execute',None)
    assert execute is not None
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4()))
    execute(accepted.view.operation_id)
    result=store.get(accepted.view.operation_id)
    assert result['status']=='failed' and result['error_code']=='all_sources_failed'
    assert result['sources']['github_commits']=={'status':'failure','error_code':'source_auth_failed'}
    assert result['report_revision'] is None and not (tmp_path/'reports.sqlite3').exists()


def test_non_workday_generation_skips_without_upstream(config,tmp_path):
    requests=[]
    service,store,cfg=make_service(config,tmp_path,lambda request:(requests.append(request),httpx.Response(403))[1])
    execute=getattr(service,'execute',None)
    assert execute is not None
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,26)),str(uuid4()))
    execute(accepted.view.operation_id)
    result=store.get(accepted.view.operation_id)
    assert result['status']=='skipped' and result['error_code']=='non_workday'
    assert result['report_revision'] is None and requests==[]
    assert not (tmp_path/'reports.sqlite3').exists()


def test_one_source_failure_keeps_other_sources(config,tmp_path):
    config=replace(config,lark_project_ids=['list-1'])
    service,store,cfg=make_service(config,tmp_path)
    execute=getattr(service,'execute',None)
    assert execute is not None
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4()))
    execute(accepted.view.operation_id)
    result=store.get(accepted.view.operation_id)
    assert result['status']=='partial_failure' and result['report_revision'] is not None
    assert result['sources']['github_commits']['status']=='success'
    assert result['sources']['lark_tasks']=={'status':'failure','error_code':'source_auth_failed'}
    assert (tmp_path/'reports.sqlite3').exists()


def test_worker_exception_records_safe_terminal_result_and_releases_slot(config,tmp_path):
    import json
    service,store,cfg=make_service(config,tmp_path)
    def fail_client(): raise RuntimeError('private-marker token-body')
    service.client_factory=fail_client
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4()))
    try: service.execute(accepted.view.operation_id)
    except RuntimeError: pass
    result=store.get(accepted.view.operation_id)
    assert result['status']=='failed' and result['error_code']=='internal_error'
    assert 'private-marker' not in json.dumps(result)
    assert service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4())).is_new


def test_preview_does_not_attribute_current_config_to_old_history(config,tmp_path,statuses):
    import json
    from pathlib import Path
    from datetime import datetime,timezone
    from smart_daily_report.generator.formatter import generate_daily_report
    from smart_daily_report.shared.models import MemberReport
    from smart_daily_report.shared.storage import write_report
    config=replace(config,lark_webhook='https://hook.test/private-marker',smtp=replace(config.smtp,password='private-marker'))
    service,store,cfg=make_service(config,tmp_path)
    preview=getattr(service,'preview',None)
    assert preview is not None, 'Read-only confirmed preview is missing'
    report=generate_daily_report(date(2026,9,25),'team',[MemberReport('u1','M')],statuses,datetime(2026,9,25,tzinfo=timezone.utc))
    write_report(Path(cfg.database_path),report)
    before=Path(cfg.database_path).read_bytes()
    result=preview(date(2026,9,25))
    assert result.sources is None
    assert result.targets.email.previous is None and result.targets.lark.previous is None
    assert result.targets.email.enabled and result.targets.lark.enabled
    assert result.report.report_date==date(2026,9,25)
    assert 'private-marker' not in result.model_dump_json()
    assert Path(cfg.database_path).read_bytes()==before


def test_generated_preview_has_exact_report_and_source_evidence(config,tmp_path):
    service,store,cfg=make_service(config,tmp_path)
    preview=getattr(service,'preview',None)
    assert preview is not None
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4()))
    service.execute(accepted.view.operation_id)
    result=preview(date(2026,9,25))
    assert result.report_revision==store.get(accepted.view.operation_id)['report_revision']
    assert result.sources.github_commits.status=='success' and result.sources.lark_tasks.status=='disabled'
    assert not result.targets.lark.enabled


def test_preview_missing_or_broken_history_has_safe_distinct_error(config,tmp_path):
    from pathlib import Path
    service,store,cfg=make_service(config,tmp_path)
    preview=getattr(service,'preview',None)
    assert preview is not None
    caught=None
    try: preview(date(2026,9,25))
    except Exception as error: caught=error
    assert getattr(caught,'code',None)=='report_not_found'
    Path(cfg.database_path).write_bytes(b'private-marker not sqlite')
    caught=None
    try: preview(date(2026,9,25))
    except Exception as error: caught=error
    assert getattr(caught,'code',None)=='storage_read_failed'
    assert 'private-marker' not in str(caught)


def test_generation_http_202_status_and_preview_use_real_service(config,tmp_path):
    from fastapi.testclient import TestClient
    from smart_daily_report.web.app import create_app
    requests=[]
    service,store,cfg=make_service(config,tmp_path,lambda request:(requests.append(request),httpx.Response(200,json=[]))[1])
    key=str(uuid4())
    headers={'Authorization':'Bearer '+('t'*32),'Idempotency-Key':key,'Origin':'http://127.0.0.1:5173'}
    with TestClient(create_app(tmp_path/'reports.sqlite3',operations=service,operation_token='t'*32),base_url='http://127.0.0.1') as client:
        response=client.post('/api/v1/generations',json={'report_date':'2026-09-25'},headers=headers)
        assert response.status_code==202, 'Protected operation must accept real generation'
        assert response.json()['status']=='running'
        operation_id=response.json()['operation_id']
        result=client.get('/api/v1/operations/'+operation_id,headers=headers)
        assert result.status_code==200 and result.json()['status']=='succeeded'
        assert client.get('/api/v1/operations/current',headers=headers).json()==result.json()
        assert client.get('/api/v1/operations/by-key/'+key,headers=headers).json()==result.json()
        preview=client.get('/api/v1/reports/2026-09-25/preview',headers=headers)
        assert preview.status_code==200
        assert preview.json()['report_revision']==result.json()['report_revision']
        assert preview.json()['report']['report_date']=='2026-09-25'
        before=(tmp_path/'reports.sqlite3').read_bytes()
        replay=client.post('/api/v1/generations',json={'report_date':'2026-09-25'},headers=headers)
        assert replay.status_code==200 and replay.json()==result.json()
        assert len(requests)==1 and (tmp_path/'reports.sqlite3').read_bytes()==before
        assert response.headers['access-control-allow-origin']==headers['Origin']
        assert all(outcome['status']=='not_requested' for outcome in result.json()['deliveries'].values())


def test_invalid_http_control_input_is_400_without_side_effects(config,tmp_path):
    from fastapi.testclient import TestClient
    from smart_daily_report.web.app import create_app
    requests=[]
    service,store,cfg=make_service(config,tmp_path,lambda request:(requests.append(request),httpx.Response(200,json=[]))[1])
    before=store.path.read_bytes()
    authorization={'Authorization':'Bearer '+('t'*32),'Origin':'http://127.0.0.1:5173'}
    with TestClient(create_app(tmp_path/'reports.sqlite3',operations=service,operation_token='t'*32),base_url='http://127.0.0.1') as client:
        for key,body in [(None,{'report_date':'2026-09-25'}),('not-uuid',{'report_date':'2026-09-25'}),
                         (str(uuid4()),{'report_date':'20260925'}),(str(uuid4()),{'report_date':'2026-09-25','recipient':'private'}),
                         (str(uuid4()),[] )]:
            headers={**authorization,**({'Idempotency-Key':key} if key else {})}
            response=client.post('/api/v1/generations',json=body,headers=headers)
            assert response.status_code==400 and response.json()['error']['code']=='invalid_request'
            assert response.headers['access-control-allow-origin']==authorization['Origin']
    assert requests==[] and store.path.read_bytes()==before


def test_status_static_routes_and_bad_ids_are_safe(config,tmp_path):
    from fastapi.testclient import TestClient
    from smart_daily_report.web.app import create_app
    service,store,cfg=make_service(config,tmp_path)
    before=store.path.read_bytes()
    headers={'Authorization':'Bearer '+('t'*32)}
    with TestClient(create_app(tmp_path/'reports.sqlite3',operations=service,operation_token='t'*32),base_url='http://127.0.0.1') as client:
        assert client.get('/api/v1/operations/current',headers=headers).json() is None
        for url,status in [('/api/v1/operations/not-a-uuid',400),('/api/v1/operations/by-key/not-a-uuid',400),
                           ('/api/v1/operations/'+str(uuid4()),404),('/api/v1/operations/by-key/'+str(uuid4()),404),
                           ('/api/v1/reports/20260925/preview',400),('/api/v1/reports/2026-09-25/preview',404)]:
            response=client.get(url,headers=headers)
            assert response.status_code==status
            assert response.headers['cache-control']=='no-store'
    assert store.path.read_bytes()==before and not (tmp_path/'reports.sqlite3').exists()


def test_running_same_key_replays_without_scheduling_and_new_key_is_busy(config,tmp_path):
    from fastapi.testclient import TestClient
    from smart_daily_report.web.app import create_app
    requests=[]
    service,store,cfg=make_service(config,tmp_path,lambda request:(requests.append(request),httpx.Response(200,json=[]))[1])
    key=str(uuid4())
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),key)
    headers={'Authorization':'Bearer '+('t'*32),'Idempotency-Key':key}
    with TestClient(create_app(tmp_path/'reports.sqlite3',operations=service,operation_token='t'*32),base_url='http://127.0.0.1') as client:
        replay=client.post('/api/v1/generations',json={'report_date':'2026-09-25'},headers=headers)
        assert replay.status_code==202 and replay.json()['status']=='running'
        conflict=client.post('/api/v1/generations',json={'report_date':'2026-09-26'},headers=headers)
        assert conflict.status_code==409 and conflict.json()['error']['code']=='idempotency_conflict'
        busy=client.post('/api/v1/generations',json={'report_date':'2026-09-25'},headers={**headers,'Idempotency-Key':str(uuid4())})
        assert busy.status_code==409 and busy.json()['error']['code']=='operation_busy'
    assert requests==[] and store.get(accepted.view.operation_id)['status']=='running'


def test_operation_storage_failure_rejects_without_business(config,tmp_path):
    from fastapi.testclient import TestClient
    from smart_daily_report.web.app import create_app
    calls=[]
    service,store,cfg=make_service(config,tmp_path,lambda r:(calls.append(r),httpx.Response(200,json=[]))[1])
    store.path.write_bytes(b'corrupt-private-marker')
    with TestClient(create_app(tmp_path/'reports.sqlite3',operations=service,operation_token='t'*32),base_url='http://127.0.0.1') as client:
        response=client.post('/api/v1/generations',headers={'Authorization':'Bearer '+('t'*32),'Idempotency-Key':str(uuid4()),'Origin':'http://127.0.0.1:5173'},json={'report_date':'2026-09-25'})
    assert response.status_code==500
    assert response.json()['error']['code']=='operation_storage_failed'
    assert response.headers['access-control-allow-origin']=='http://127.0.0.1:5173'
    assert calls==[] and 'private-marker' not in response.text


def test_report_write_failure_keeps_real_source_outcomes(config,tmp_path,monkeypatch):
    service,store,cfg=make_service(config,tmp_path)
    def fail(*args,**kwargs): raise OSError('private-marker')
    monkeypatch.setattr('smart_daily_report.main.write_report',fail)
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4()))
    service.execute(accepted.view.operation_id)
    result=store.get(accepted.view.operation_id)
    assert result['status']=='failed' and result['error_code']=='report_write_failed'
    assert result['sources']['github_commits']['status']=='success'
    assert result['report_revision'] is None


def test_invalid_source_payload_is_not_unavailable_or_empty_success(config,tmp_path):
    service,store,cfg=make_service(config,tmp_path,lambda r:httpx.Response(200,json={'private-marker':'bad'}))
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4()))
    service.execute(accepted.view.operation_id)
    result=store.get(accepted.view.operation_id)
    assert result['sources']['github_commits']['error_code']=='source_payload_invalid'
    assert result['status']=='failed' and result['report_revision'] is None


def test_operation_startup_supports_new_database_directory(config,tmp_path):
    module=importlib.import_module('smart_daily_report.web.operations')
    database=tmp_path/'new-data'/'reports.sqlite3'
    store=OperationStore(database.with_name(database.name+'.operations.sqlite3'))
    try: service=module.OperationService(replace(config,database_path=str(database)),store)
    except Exception: service=None
    assert service is not None, 'New operation directory cannot initialize'
    assert store.path.exists() and not database.exists()


def test_sensitive_message_never_reaches_saved_preview(config,tmp_path,caplog):
    from pathlib import Path
    marker='sensitive-private-marker'
    config=replace(config,lark_project_ids=['list-1'],lark_chat_ids=['chat'],lark_app_id='app',lark_app_secret='secret',
      sensitive_keywords=[marker])
    requests=[]
    def handler(request):
        requests.append(request)
        if 'tenant_access_token' in request.url.path: return httpx.Response(200,json={'code':0,'tenant_access_token':'tenant-token'})
        if '/tasklists/' in request.url.path: return httpx.Response(200,json={'code':0,'data':{'items':[{'guid':'task-1','summary':'Ship actual task',
          'completed_at':1790301600000,'members':[{'id':'ou_1','type':'user','role':'assignee'}]}],'has_more':False}})
        if request.url.path.endswith('/messages'): return httpx.Response(200,json={'code':0,'data':{'items':[
          {'message_id':'safe','body':{'content':'{"text":"日报 done"}'},'sender':{'id':'ou_1'},'create_time':'2026-09-25T02:00:00Z'},
          {'message_id':'secret','body':{'content':'{"text":"日报 '+marker+'"}'},'sender':{'id':'ou_1'},'create_time':'2026-09-25T02:00:00Z'}],'has_more':False}})
        return httpx.Response(200,json=[])
    service,store,cfg=make_service(config,tmp_path,handler)
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4())); service.execute(accepted.view.operation_id)
    view=service.preview(date(2026,9,25))
    assert store.get(accepted.view.operation_id)['status']=='succeeded'
    assert view.report.members[0].tasks[0].status=='completed'
    assert view.report.members[0].tasks[0].status_from is None
    assert [r.content for r in view.report.members[0].messages]==['日报 done']
    assert marker not in view.model_dump_json()+caplog.text
    assert marker.encode() not in Path(cfg.database_path).read_bytes()+store.path.read_bytes()
    assert sum('/tasklists/' in r.url.path for r in requests)==1


def test_repeated_business_auth_denial_projects_auth_failure(config,tmp_path):
    cfg=replace(config,lark_project_ids=['list-1'],lark_app_id='app',lark_app_secret='secret')
    def handler(request):
        if 'tenant_access_token' in request.url.path: return httpx.Response(200,json={'code':0,'tenant_access_token':'token'})
        if '/tasklists/' in request.url.path: return httpx.Response(200,json={'code':99991663,'msg':'private-marker'})
        return httpx.Response(200,json=[])
    service,store,cfg=make_service(cfg,tmp_path,handler)
    accepted=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4())); service.execute(accepted.view.operation_id)
    result=store.get(accepted.view.operation_id)
    assert result['status']=='partial_failure'
    assert result['sources']['lark_tasks']['error_code']=='source_auth_failed'


def delivery_service(config,tmp_path,email_result=None,lark_result=None):
    requests=[]; sends=[]
    cfg=replace(config,lark_webhook='https://hook.test/key')
    def handler(request):
        requests.append(request)
        if request.url.host=='hook.test': return httpx.Response(200,json=lark_result or {'code':0})
        return httpx.Response(200,json=[])
    service,store,cfg=make_service(cfg,tmp_path,handler)
    class SMTP:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def starttls(self): pass
        def send_message(self,message):
            sends.append(message)
            if isinstance(email_result,Exception): raise email_result
            return {} if email_result is None else email_result
    service.smtp_factory=SMTP
    generated=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4())); service.execute(generated.view.operation_id)
    preview=service.preview(date(2026,9,25)); requests.clear()
    return service,store,cfg,preview,requests,sends


def test_preview_revision_changed_rejects_before_notifier(config,tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from smart_daily_report.shared.storage import get_report,write_report
    from smart_daily_report.web.app import create_app
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    report=get_report(Path(cfg.database_path),date(2026,9,25)); write_report(Path(cfg.database_path),replace(report,html=report.html+'updated'))
    with TestClient(create_app(Path(cfg.database_path),operations=service,operation_token='t'*32),base_url='http://127.0.0.1') as client:
        response=client.post('/api/v1/deliveries',json={'report_date':'2026-09-25','report_revision':preview.report_revision,'channels':['email','lark']},
          headers={'Authorization':'Bearer '+('t'*32),'Idempotency-Key':str(uuid4())})
    assert response.status_code==409 and response.json()['error']['code']=='report_revision_changed'
    assert requests==[] and sends==[]


def test_delivery_acceptance_keeps_snapshot_and_never_recollects(config,tmp_path):
    from smart_daily_report.web.operation_schemas import DeliveryRequest
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    accept=getattr(service,'accept_delivery',None)
    assert accept is not None, 'Confirmed snapshot delivery acceptance is missing'
    accepted=accept(DeliveryRequest(report_date=date(2026,9,25),report_revision=preview.report_revision,channels=['lark','email']),str(uuid4()))
    assert accepted.is_new and accepted.snapshot is not None and accepted.view.kind=='delivery'
    assert accepted.view.sources.model_dump()=={'github_commits':None,'lark_tasks':None,'lark_messages':None}
    assert all(item['status']=='pending' for item in accepted.view.deliveries.model_dump().values())
    assert requests==[] and sends==[]
    service.execute(accepted.view.operation_id,accepted.snapshot)
    record=store.get(accepted.view.operation_id)
    assert record['status']=='succeeded'
    assert all(item['status']=='accepted' for item in record['deliveries'].values())
    assert len(sends)==1 and len(requests)==1 and requests[0].url.host=='hook.test'


def accept_delivery(service,preview,key=None,channels=None):
    from smart_daily_report.web.operation_schemas import DeliveryRequest
    accept=getattr(service,'accept_delivery',None)
    assert accept is not None, 'Confirmed delivery is missing'
    return accept(DeliveryRequest(report_date=date.fromisoformat(preview.report.report_date.isoformat()),report_revision=preview.report_revision,
      channels=channels or ['email','lark']),key or str(uuid4()))


def test_same_key_completed_delivery_replays_even_after_new_report(config,tmp_path):
    from pathlib import Path
    from smart_daily_report.shared.storage import get_report,write_report
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    key=str(uuid4()); accepted=accept_delivery(service,preview,key,['lark','email']); service.execute(accepted.view.operation_id,accepted.snapshot)
    report=get_report(Path(cfg.database_path),date(2026,9,25)); write_report(Path(cfg.database_path),replace(report,html=report.html+'updated'))
    replay=accept_delivery(service,preview,key,['email','lark'])
    assert not replay.is_new and replay.view.operation_id==accepted.view.operation_id and replay.view.status=='succeeded'
    assert len(sends)==1 and len(requests)==1


def test_two_channels_use_snapshot_even_if_cli_updates_between(config,tmp_path):
    from pathlib import Path
    from smart_daily_report.shared.storage import get_report,write_report
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    accepted=accept_delivery(service,preview)
    smtp=service.smtp_factory
    class Update(smtp):
        def send_message(self,message):
            result=super().send_message(message)
            write_report(Path(cfg.database_path),replace(accepted.snapshot,markdown='new CLI content',html='new CLI content'))
            return result
    service.smtp_factory=Update
    service.execute(accepted.view.operation_id,accepted.snapshot)
    import json
    assert sends[0].get_body(('html',)).get_content().strip()==accepted.snapshot.html
    assert json.loads(requests[0].content)['card']['elements'][0]['content']==accepted.snapshot.markdown
    assert get_report(Path(cfg.database_path),date(2026,9,25)).markdown=='new CLI content'


@pytest.mark.parametrize('email_result,expected',[({'rejected@test':(550,b'no')},'partial_failure'),(TimeoutError('private-marker'),'unknown')])
def test_channel_error_never_blocks_other_selected_channel(config,tmp_path,email_result,expected):
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path,email_result=email_result)
    accepted=accept_delivery(service,preview); service.execute(accepted.view.operation_id,accepted.snapshot)
    record=store.get(accepted.view.operation_id)
    assert record['status']==expected and record['deliveries']['lark']['status']=='accepted'
    assert len(sends)==1 and len(requests)==1
    from smart_daily_report.shared.operation_storage import OperationConflict
    with pytest.raises(OperationConflict,match='delivery_not_repeatable'): accept_delivery(service,preview)
    assert len(sends)==1 and len(requests)==1


def test_accepted_channel_cannot_repeat(config,tmp_path):
    from smart_daily_report.shared.operation_storage import OperationConflict
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    accepted=accept_delivery(service,preview); service.execute(accepted.view.operation_id,accepted.snapshot)
    with pytest.raises(OperationConflict,match='delivery_not_repeatable'): accept_delivery(service,preview,channels=['email'])
    assert len(sends)==1 and len(requests)==1


def test_failure_to_persist_pending_state_sends_nothing(config,tmp_path,monkeypatch):
    import sqlite3
    from pathlib import Path
    from fastapi.testclient import TestClient
    from smart_daily_report.web.app import create_app
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    def fail(*args,**kwargs): raise sqlite3.OperationalError('private-marker')
    monkeypatch.setattr(store,'accept',fail)
    with TestClient(create_app(Path(cfg.database_path),operations=service,operation_token='t'*32),base_url='http://127.0.0.1') as client:
        response=client.post('/api/v1/deliveries',headers={'Authorization':'Bearer '+('t'*32),'Idempotency-Key':str(uuid4())},
          json={'report_date':'2026-09-25','report_revision':preview.report_revision,'channels':['email']})
    assert response.status_code==500 and response.json()['error']['code']=='operation_storage_failed'
    assert requests==[] and sends==[] and 'private-marker' not in response.text


def test_failure_to_persist_post_send_result_never_allows_resend(config,tmp_path,monkeypatch):
    import sqlite3
    from smart_daily_report.shared.operation_storage import OperationConflict
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    accepted=accept_delivery(service,preview,channels=['email'])
    def fail(*args,**kwargs): raise sqlite3.OperationalError('private-marker')
    with monkeypatch.context() as patch:
        patch.setattr(store,'record_delivery',fail)
        service.execute(accepted.view.operation_id,accepted.snapshot)
    assert len(sends)==1 and requests==[]
    store.recover_interrupted(); record=store.get(accepted.view.operation_id)
    assert record['status']=='interrupted' and record['deliveries']['email']['status']=='unknown'
    with pytest.raises(OperationConflict,match='delivery_not_repeatable'): accept_delivery(service,preview,channels=['email'])
    assert len(sends)==1


def test_non_workday_and_disabled_channel_are_rejected_before_call(config,tmp_path):
    from smart_daily_report.web.operations import OperationError
    from smart_daily_report.web.operation_schemas import DeliveryRequest
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    accept=getattr(service,'accept_delivery',None); assert accept is not None
    with pytest.raises(OperationError,match='non_workday'):
        accept(DeliveryRequest(report_date=date(2026,9,26),report_revision=preview.report_revision,channels=['email']),str(uuid4()))
    service.config=replace(service.config,lark_webhook=None)
    with pytest.raises(OperationError,match='channel_not_configured'): accept_delivery(service,preview,channels=['lark'])
    assert requests==[] and sends==[]


def test_rejected_channel_can_be_retried_alone_without_resending_accepted_channel(config,tmp_path):
    import smtplib
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path,email_result=smtplib.SMTPRecipientsRefused({'lead@test':(550,b'no')}))
    first=accept_delivery(service,preview); service.execute(first.view.operation_id,first.snapshot)
    assert store.get(first.view.operation_id)['status']=='partial_failure'
    class Accept(service.smtp_factory):
        def send_message(self,message): sends.append(message); return {}
    service.smtp_factory=Accept
    second=accept_delivery(service,preview,channels=['email']); service.execute(second.view.operation_id,second.snapshot)
    assert store.get(second.view.operation_id)['status']=='succeeded'
    assert len(sends)==2 and len(requests)==1


def test_completed_or_interrupted_operation_cannot_execute_again(config,tmp_path):
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    first=accept_delivery(service,preview,channels=['email']); service.execute(first.view.operation_id,first.snapshot)
    before=store.path.read_bytes(); service.execute(first.view.operation_id,first.snapshot)
    assert store.path.read_bytes()==before and len(sends)==1


def test_client_creation_failure_releases_delivery_slot_without_sending(config,tmp_path):
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    accepted=accept_delivery(service,preview)
    def fail(): raise OSError('private-marker')
    service.client_factory=fail
    service.execute(accepted.view.operation_id,accepted.snapshot)
    result=store.get(accepted.view.operation_id)
    assert result['status']=='unknown' and all(v['status']=='unknown' for v in result['deliveries'].values())
    assert requests==[] and sends==[]
    another=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4()))
    assert another.is_new


def test_unexpected_operation_exception_has_safe_cors_error(tmp_path):
    from fastapi.testclient import TestClient
    from smart_daily_report.web.app import create_app
    class Broken:
        def accept_generation(self,*args): raise RuntimeError('private-marker')
    with TestClient(create_app(tmp_path/'reports.sqlite3',operations=Broken(),operation_token='t'*32),base_url='http://127.0.0.1') as client:
        response=client.post('/api/v1/generations',headers={'Origin':'http://127.0.0.1:5173','Authorization':'Bearer '+('t'*32),'Idempotency-Key':str(uuid4())},json={'report_date':'2026-09-25'})
    assert response.status_code==500
    assert response.headers.get('access-control-allow-origin')=='http://127.0.0.1:5173'
    assert response.json()['error']=={'code':'internal_error','message':'操作请求处理失败'}
    assert 'private-marker' not in response.text


def test_delivery_http_replay_channel_order_and_duplicate_rejection(config,tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from smart_daily_report.shared.storage import write_report,get_report
    from smart_daily_report.web.app import create_app
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    key=str(uuid4()); headers={'Authorization':'Bearer '+('t'*32),'Idempotency-Key':key,'Origin':'http://127.0.0.1:5173'}
    body={'report_date':'2026-09-25','report_revision':preview.report_revision,'channels':['lark','email']}
    with TestClient(create_app(Path(cfg.database_path),operations=service,operation_token='t'*32),base_url='http://127.0.0.1') as client:
        first=client.post('/api/v1/deliveries',headers=headers,json=body)
        assert first.status_code==202 and first.json()['status']=='running'
        completed=client.get('/api/v1/operations/'+first.json()['operation_id'],headers=headers)
        assert completed.json()['status']=='succeeded'
        evidence=client.get('/api/v1/reports/2026-09-25/preview',headers=headers).json()
        assert evidence['targets']['email']['previous']['status']=='accepted'
        assert evidence['targets']['lark']['previous']['status']=='accepted'
        report=get_report(Path(cfg.database_path),date(2026,9,25)); write_report(Path(cfg.database_path),replace(report,html='updated CLI content'))
        before=store.path.read_bytes()
        replay=client.post('/api/v1/deliveries',headers=headers,json={**body,'channels':['email','lark']})
        assert replay.status_code==200 and replay.json()==completed.json()
        conflict=client.post('/api/v1/deliveries',headers=headers,json={**body,'channels':['email']})
        assert conflict.status_code==409 and conflict.json()['error']['code']=='idempotency_conflict'
        for change in ({'channels':['email','email']},{'recipient':'unauthorized@test'},{'report_date':'20260925'}):
            rejected=client.post('/api/v1/deliveries',headers=headers,json={**body,**change})
            assert rejected.status_code==400 and rejected.json()['error']['code']=='invalid_request'
        assert store.path.read_bytes()==before
    assert len(sends)==1 and len(requests)==1


def test_notifier_without_explicit_outcome_is_unknown_and_cannot_repeat(config,tmp_path,monkeypatch):
    from smart_daily_report.shared.models import DeliveryResult
    from smart_daily_report.shared.operation_storage import OperationConflict
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    monkeypatch.setattr('smart_daily_report.web.operations.send_email',lambda *args,**kwargs:DeliveryResult(True,1))
    accepted=accept_delivery(service,preview,channels=['email']); service.execute(accepted.view.operation_id,accepted.snapshot)
    assert store.get(accepted.view.operation_id)['status']=='unknown'
    with pytest.raises(OperationConflict,match='delivery_not_repeatable'): accept_delivery(service,preview,channels=['email'])


def test_delivery_without_in_memory_snapshot_never_loads_new_report_or_sends(config,tmp_path):
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path)
    accepted=accept_delivery(service,preview)
    service.execute(accepted.view.operation_id)
    assert store.get(accepted.view.operation_id)['status']=='unknown' and requests==[] and sends==[]


def test_all_channels_explicitly_rejected_are_failed(config,tmp_path):
    import smtplib
    service,store,cfg,preview,requests,sends=delivery_service(config,tmp_path,email_result=smtplib.SMTPRecipientsRefused({'lead@test':(550,b'no')}),lark_result={'code':19024})
    accepted=accept_delivery(service,preview); service.execute(accepted.view.operation_id,accepted.snapshot)
    result=store.get(accepted.view.operation_id)
    assert result['status']=='failed' and result['error_code']=='delivery_rejected'
    assert all(v['status']=='rejected' for v in result['deliveries'].values()) and len(sends)==1 and len(requests)==1


def test_malformed_only_message_source_preserves_saved_report(config, tmp_path, statuses):
    from datetime import datetime, timezone
    from pathlib import Path
    from smart_daily_report.generator.formatter import generate_daily_report
    from smart_daily_report.shared.storage import get_report, write_report
    def handler(request):
        if request.url.path.endswith('/tenant_access_token/internal'):
            return httpx.Response(200, json={'code': 0, 'tenant_access_token': 'synthetic-token'})
        return httpx.Response(200, json={'code': 0, 'data': {'has_more': False}})
    service, store, cfg = make_service(config, tmp_path, handler)
    service.config = replace(cfg, github_repositories=[], lark_chat_ids=['chat'], lark_app_id='app', lark_app_secret='synthetic-secret')
    report_date = date(2026, 9, 25)
    original = generate_daily_report(report_date, 'original team', [], statuses, datetime(2026, 9, 25, tzinfo=timezone.utc))
    write_report(Path(cfg.database_path), original)
    before = Path(cfg.database_path).read_bytes()
    accepted = service.accept_generation(GenerationRequest(report_date=report_date), str(uuid4()))
    service.execute(accepted.view.operation_id)
    result = store.get(accepted.view.operation_id)
    assert result['status'] == 'failed' and result['error_code'] == 'all_sources_failed'
    assert result['sources']['lark_messages']['status'] == 'failure'
    assert result['report_revision'] is None
    assert Path(cfg.database_path).read_bytes() == before
    assert get_report(Path(cfg.database_path), report_date) == original
