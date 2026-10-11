import importlib
import importlib.util
import json
from datetime import date

import pytest
from pydantic import ValidationError


def operation_schemas():
    assert importlib.util.find_spec('smart_daily_report.web.operation_schemas') is not None, 'Operation request contracts are missing'
    return importlib.import_module('smart_daily_report.web.operation_schemas')


def test_generation_request_accepts_calendar_date_and_forbids_unknown_fields():
    schemas = operation_schemas()
    cls = getattr(schemas, 'GenerationRequest', None)
    assert cls is not None, 'Generation input contract is missing'
    assert cls.model_validate_json('{"report_date":"2026-09-25"}').report_date == date(2026, 9, 25)
    with pytest.raises(ValidationError):
        cls.model_validate_json('{"report_date":"2026-09-25","token":"private"}')


@pytest.mark.parametrize('value', ['20260925', '2026-02-30', '2026-09-25T00:00:00Z', 20260925, None])
def test_generation_request_rejects_non_calendar_input(value):
    schemas = operation_schemas()
    cls = getattr(schemas, 'GenerationRequest', None)
    assert cls is not None
    with pytest.raises(ValidationError):
        cls.model_validate_json(json.dumps({'report_date': value}))


def test_delivery_request_accepts_confirmed_revision_and_canonical_channels():
    cls = getattr(operation_schemas(), 'DeliveryRequest', None)
    assert cls is not None, 'Confirmed delivery contract is missing'
    body = cls.model_validate_json(json.dumps({'report_date': '2026-09-25', 'report_revision': 'a'*64, 'channels': ['lark','email'], 'email_recipients': ['lead@test']}))
    assert body.channels == ['email','lark']
    assert body.report_revision == 'a'*64


@pytest.mark.parametrize('changes', [
    {'channels': []}, {'channels': ['email','email']}, {'channels': ['sms']},
    {'channels': 'email'}, {'report_revision': 'A'*64}, {'report_revision': 'a'*63},
    {'report_revision': 'not-a-version'}, {'recipient': 'unconfirmed@test'},
])
def test_strict_operation_request_rejects_invalid_input(changes):
    cls = getattr(operation_schemas(), 'DeliveryRequest', None)
    assert cls is not None
    data = {'report_date': '2026-09-25', 'report_revision': 'a'*64, 'channels': ['email'], 'email_recipients': ['lead@test']}
    with pytest.raises(ValidationError):
        cls.model_validate_json(json.dumps({**data, **changes}))


@pytest.mark.parametrize('name,bad', [
    ('SourceOutcome', {'status':'invented','error_code':None}),
    ('DeliveryOutcome', {'status':'delivered','attempts':1,'error_code':None}),
    ('DeliveryOutcome', {'status':'not_requested','attempts':1,'error_code':None}),
    ('DeliveryOutcome', {'status':'accepted','attempts':-1,'error_code':None}),
])
def test_source_and_delivery_states_reject_unknown_values(name, bad):
    cls = getattr(operation_schemas(), name, None)
    assert cls is not None, 'Operation outcome contract is missing'
    with pytest.raises(ValidationError):
        cls.model_validate_json(json.dumps(bad))


def test_actual_outcomes_can_be_serialized_without_private_text():
    schemas = operation_schemas()
    source = getattr(schemas, 'SourceOutcome', None)
    delivery = getattr(schemas, 'DeliveryOutcome', None)
    assert source is not None and delivery is not None
    assert source(status='disabled', error_code=None).model_dump() == {'status':'disabled','error_code':None}
    assert delivery(status='accepted', attempts=1, error_code=None).model_dump() == {'status':'accepted','attempts':1,'error_code':None}
    with pytest.raises(ValidationError):
        delivery.model_validate_json('{"status":"unknown","attempts":1,"error_code":null,"message":"private"}')


def test_outcome_rejects_unapproved_error_body():
    cls=operation_schemas().SourceOutcome
    with pytest.raises(ValidationError):
        cls(status='failure',error_code='private-marker from upstream')


def operation_record():
    return {'operation_id':'d13e0218-2e9f-424e-bef6-8e5d6de79814',
            'request_id':'96ff843b-f0c4-4c11-a23e-bd2d6e15c938','kind':'generation',
            'report_date':'2026-09-25','status':'running','created_at':'2026-09-25T02:00:00Z',
            'updated_at':'2026-09-25T02:00:00Z','report_revision':None,'error_code':None,
            'sources':{name:{'status':'pending','error_code':None} for name in ('github_commits','lark_tasks','lark_messages')},
            'deliveries':{name:{'status':'not_requested','attempts':0,'error_code':None} for name in ('email','lark')}}


def test_operation_view_enforces_complete_sources_and_channels():
    cls=getattr(operation_schemas(),'OperationView',None)
    assert cls is not None, 'Operation result DTO is missing'
    data=operation_record()
    assert cls.model_validate_json(json.dumps(data)).status=='running'
    bad=json.loads(json.dumps(data)); bad['sources'].pop('lark_tasks')
    with pytest.raises(ValidationError): cls.model_validate_json(json.dumps(bad))
    bad=json.loads(json.dumps(data)); bad['deliveries']['sms']={}
    with pytest.raises(ValidationError): cls.model_validate_json(json.dumps(bad))
    bad={**data,'operation_id':'not-a-uuid'}
    with pytest.raises(ValidationError): cls.model_validate_json(json.dumps(bad))
    bad={**data,'created_at':'2026-09-25T02:00:00'}
    with pytest.raises(ValidationError): cls.model_validate_json(json.dumps(bad))


def test_auth_and_cors_guard_every_control_route(tmp_path):
    import inspect
    from fastapi.testclient import TestClient
    from smart_daily_report.web.app import create_app
    assert 'operations' in inspect.signature(create_app).parameters, 'Protected operation adapter is missing'
    class ForbiddenService:
        def __getattr__(self, name):
            raise AssertionError('Unauthorized request reached business service')
    path=tmp_path/'reports.sqlite3'
    app=create_app(path,operations=ForbiddenService(),operation_token='t'*32)
    routes=[('POST','/api/v1/generations'),('POST','/api/v1/deliveries'),('GET','/api/v1/operations/current'),
            ('GET','/api/v1/operations/96ff843b-f0c4-4c11-a23e-bd2d6e15c938'),
            ('GET','/api/v1/operations/by-key/96ff843b-f0c4-4c11-a23e-bd2d6e15c938'),
            ('GET','/api/v1/reports/2026-09-25/preview')]
    with TestClient(app,base_url='http://127.0.0.1') as client:
        for method,url in routes:
            for headers in ({},{'Authorization':'Bearer wrong'}, {'Origin':'http://127.0.0.1:5173'}):
                response=client.request(method,url,headers=headers)
                assert response.status_code==401
                assert response.json()['error']['code']=='operation_unauthorized'
                assert response.headers['cache-control']=='no-store'
                if 'Origin' in headers:
                    assert response.headers['access-control-allow-origin']==headers['Origin']
            response=client.request(method,url,headers={'Origin':'https://evil.test','Authorization':'Bearer '+('t'*32)})
            assert response.status_code==403
    assert not path.exists()


def test_preflight_accepts_explicit_headers_without_bearer(tmp_path):
    import inspect
    from fastapi.testclient import TestClient
    from smart_daily_report.web.app import create_app
    assert 'operations' in inspect.signature(create_app).parameters
    with TestClient(create_app(tmp_path/'reports.sqlite3',operations=object(),operation_token='t'*32),base_url='http://127.0.0.1') as client:
        response=client.options('/api/v1/generations',headers={'Origin':'http://127.0.0.1:5173',
             'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Authorization,Content-Type,Idempotency-Key'})
    assert response.status_code==200
    assert 'POST' in response.headers['access-control-allow-methods']
    assert all(name in response.headers['access-control-allow-headers'].lower() for name in ('authorization','content-type','idempotency-key'))


def operation_config_file(tmp_path):
    path=tmp_path/'config.yaml'
    path.write_text("team:\n  name: team\n  timezone: Asia/Shanghai\n  github_repositories: [acme/repo]\n  database_path: "+str(tmp_path/'reports.sqlite3')+"\nmembers:\n  - member_id: u1\n    display_name: Member\n",encoding='utf-8')
    return path


def test_operation_cli_accepts_config_mode(tmp_path,monkeypatch):
    from smart_daily_report.web import main as entry
    calls=[]
    monkeypatch.setenv('DAILY_REPORT_WEB_TOKEN','t'*32)
    monkeypatch.setattr(entry.uvicorn,'run',lambda app,**kwargs:calls.append((app,kwargs)))
    try: result=entry.main(['--config',str(operation_config_file(tmp_path))])
    except SystemExit: result=None
    assert result==0, 'Operation configuration mode cannot start'
    assert calls[0][1]=={'host':'127.0.0.1','port':8000,'access_log':False}
    assert (tmp_path/'reports.sqlite3.operations.sqlite3').exists()
    assert not (tmp_path/'reports.sqlite3').exists()


@pytest.mark.parametrize('token',[None,'',' '*32,'t'*31])
def test_missing_or_short_operation_token_fails_before_server(tmp_path,monkeypatch,token):
    from smart_daily_report.web import main as entry
    from smart_daily_report.shared.errors import ConfigError
    calls=[]
    if token is None: monkeypatch.delenv('DAILY_REPORT_WEB_TOKEN',raising=False)
    else: monkeypatch.setenv('DAILY_REPORT_WEB_TOKEN',token)
    monkeypatch.setattr(entry.uvicorn,'run',lambda *args,**kwargs:calls.append(kwargs))
    with pytest.raises(ConfigError): entry.main(['--config',str(operation_config_file(tmp_path))])
    assert calls==[] and not (tmp_path/'reports.sqlite3.operations.sqlite3').exists()


def test_readonly_start_ignores_operation_environment(tmp_path,monkeypatch):
    from smart_daily_report.web import main as entry
    calls=[]
    monkeypatch.setenv('DAILY_REPORT_WEB_TOKEN','invalid')
    def forbidden(*args,**kwargs): pytest.fail('Readonly startup must not load operation configuration')
    monkeypatch.setattr(entry,'load_config',forbidden,raising=False)
    monkeypatch.setattr(entry.uvicorn,'run',lambda app,**kwargs:calls.append(kwargs))
    assert entry.main(['--database',str(tmp_path/'reports.sqlite3')])==0
    assert calls[0]['host']=='127.0.0.1'
    assert not (tmp_path/'reports.sqlite3.operations.sqlite3').exists()


@pytest.mark.parametrize('changes',[{'github_repositories':[]},{'lark_project_ids':['list']},{'lark_chat_ids':['chat']}])
def test_operation_configuration_rejects_unusable_sources(config,changes):
    from dataclasses import replace
    from smart_daily_report.shared.errors import ConfigError
    from smart_daily_report.web import operations
    validate=getattr(operations,'validate_operation_config',None)
    assert validate is not None, 'Operation configuration validation is missing'
    cfg=replace(config,github_repositories=['acme/repo'])
    cfg=replace(cfg,**changes)
    with pytest.raises(ConfigError): validate(cfg,'t'*32)


def test_generation_and_delivery_cannot_mix_source_evidence():
    cls=operation_schemas().OperationView
    data=operation_record(); data['sources']['github_commits']=None
    with pytest.raises(ValidationError): cls.model_validate_json(json.dumps(data))
    data=operation_record(); data['kind']='delivery'; data['report_revision']='a'*64
    with pytest.raises(ValidationError): cls.model_validate_json(json.dumps(data))



def test_legacy_operation_has_unknown_targets_without_database_rewrite(tmp_path):
    from smart_daily_report.shared.operation_storage import OperationStore
    from uuid import uuid4
    import sqlite3
    store=OperationStore(tmp_path/'operations.sqlite3'); store.initialize()
    record=operation_record(); record.update(kind='delivery',sources={name:None for name in record['sources']})
    with sqlite3.connect(store.path) as connection:
        connection.execute('INSERT INTO operations VALUES (?,?,?,?,?,?)',
            (record['operation_id'],record['request_id'],'legacy','running',record['created_at'],json.dumps(record)))
    before=store.path.read_bytes()
    result=operation_schemas().OperationView.model_validate_json(json.dumps(store.get(record['operation_id'])))
    assert result.email_recipients is None
    assert store.path.read_bytes()==before
