"""The fixture must exercise production collectors/notifiers without real side effects."""
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from smart_daily_report.web.operation_schemas import GenerationRequest


def load_fixture():
    path = Path(__file__).resolve().parents[2] / 'frontend/e2e/serve_operations_fixture.py'
    assert path.exists(), 'Operation browser fixture is missing'
    spec = importlib.util.spec_from_file_location('operations_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_uses_real_pipeline_and_counts_only_external_delivery(tmp_path):
    module = load_fixture()
    app, service = module.create_fixture(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        headers = {'Authorization': f'Bearer {module.TOKEN}', 'Idempotency-Key': str(uuid4()), 'Origin': 'http://127.0.0.1:5174'}
        result = client.post('/api/v1/generations', headers=headers, json={'report_date':'2026-09-25'})
        assert result.status_code == 202
        current = client.get('/api/v1/operations/current', headers=headers).json()
        assert current['status'] == 'succeeded'
        preview = client.get('/api/v1/reports/2026-09-25/preview', headers=headers).json()
        assert all(value['status'] == 'success' for value in preview['sources'].values())
        assert len(preview['report']['members'][0]['commits']) == 1
        assert len(preview['report']['members'][0]['tasks']) == 1
        assert len(preview['report']['members'][0]['messages']) == 1
        assert 'sensitive-message-marker' not in json.dumps(preview)
        assert module.delivery_counts(tmp_path) == {'email':0,'lark':0}
        headers['Idempotency-Key'] = str(uuid4())
        result = client.post('/api/v1/deliveries', headers=headers, json={'report_date':'2026-09-25','report_revision':preview['report_revision'],'channels':['email','lark'],'email_recipients':['fixture@example.invalid']})
        assert result.status_code == 202
        assert module.delivery_counts(tmp_path) == {'email':1,'lark':1}
        assert client.get('/api/v1/operations/current', headers=headers).json()['status'] == 'succeeded'


def test_fixture_failure_scenarios_are_external_boundaries_not_fake_api_routes(tmp_path):
    module = load_fixture()
    app, service = module.create_fixture(tmp_path)
    assert not any('fixture' in route.path or 'scenario' in route.path for route in app.routes)
    (tmp_path/'scenario.json').write_text(json.dumps({'email':'rejected','lark':'unknown'}))
    with TestClient(app, base_url='http://127.0.0.1') as client:
        headers={'Authorization':f'Bearer {module.TOKEN}', 'Idempotency-Key':str(uuid4())}
        client.post('/api/v1/generations', headers=headers, json={'report_date':'2026-09-25'})
        preview=client.get('/api/v1/reports/2026-09-25/preview', headers=headers).json()
        headers['Idempotency-Key']=str(uuid4())
        client.post('/api/v1/deliveries', headers=headers,json={'report_date':'2026-09-25','report_revision':preview['report_revision'],'channels':['email','lark'],'email_recipients':['fixture@example.invalid']})
        current=client.get('/api/v1/operations/current',headers=headers).json()
        assert current['status']=='unknown'
        assert current['deliveries']['email']['status']=='rejected'
        assert current['deliveries']['lark']['status']=='unknown'
        assert module.delivery_counts(tmp_path)=={'email':1,'lark':1}


def test_fixture_records_only_synthetic_selected_email_targets(tmp_path):
    from smart_daily_report.web.operation_schemas import DeliveryRequest
    from datetime import date
    module=load_fixture(); app,service=module.create_fixture(tmp_path)
    generated=service.accept_generation(GenerationRequest(report_date=date(2026,9,25)),str(uuid4()))
    service.execute(generated.view.operation_id)
    preview=service.preview(date(2026,9,25))
    assert preview.targets.email.recipients==['fixture@example.invalid','mentor@example.invalid']
    accepted=service.accept_delivery(DeliveryRequest(report_date=date(2026,9,25),report_revision=preview.report_revision,
        channels=['email'],email_recipients=['mentor@example.invalid']),str(uuid4()))
    service.execute(accepted.view.operation_id,accepted.snapshot)
    events=[json.loads(line) for line in (tmp_path/'deliveries.jsonl').read_text(encoding='utf-8').splitlines()]
    assert events==[{'channel':'email','recipients':['mentor@example.invalid']}]
