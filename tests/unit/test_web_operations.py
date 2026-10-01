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
    body = cls.model_validate_json(json.dumps({'report_date': '2026-09-25', 'report_revision': 'a'*64, 'channels': ['lark','email']}))
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
    data = {'report_date': '2026-09-25', 'report_revision': 'a'*64, 'channels': ['email']}
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
