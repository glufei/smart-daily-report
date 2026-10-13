from datetime import date, datetime, timezone
from email.message import EmailMessage

import httpx
import pytest

from smart_daily_report.notifier.email import send_email
from smart_daily_report.notifier.lark_bot import send_lark_message
from smart_daily_report.shared.models import DailyReport, SmtpConfig


def report():
    return DailyReport(date(2026, 9, 25), "team", [], {}, "# daily", "<h1>daily</h1>",
                       datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc))


class FakeSMTP:
    calls = 0
    def __init__(self, *args, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def starttls(self): pass
    def login(self, *args): pass
    def send_message(self, message):
        assert isinstance(message, EmailMessage) and "<h1>daily</h1>" in message.as_string()
        FakeSMTP.calls += 1
        return {}


def test_email_delivers_html():
    FakeSMTP.calls = 0
    result = send_email(report(), ["lead@test"], SmtpConfig("host", 587, None, None, "from@test", []), FakeSMTP)
    assert result.success and FakeSMTP.calls == 1

def test_email_subject_identifies_author_and_report_date():
    subjects = []
    class CapturingSMTP(FakeSMTP):
        def send_message(self, message):
            subjects.append(str(message["Subject"]))
            return {}

    result = send_email(report(), ["lead@test"], SmtpConfig("host", 587, None, None, "from@test", []), CapturingSMTP)

    assert result.success
    assert subjects == ["研一高畅2026-09-25智能日报"]


def test_email_subject_distinguishes_two_generations_on_same_date():
    subjects = []
    class CapturingSMTP(FakeSMTP):
        def send_message(self, message):
            subjects.append(str(message["Subject"]))
            return {}

    smtp = SmtpConfig("host", 587, None, None, "from@test", [])
    from dataclasses import replace
    for hour in (12, 13):
        snapshot = replace(report(), generated_at=datetime(2026, 9, 25, hour, tzinfo=timezone.utc))
        result = send_email(snapshot, ["mentor@test", "senior@test"], smtp, CapturingSMTP)
        assert result.success
    assert subjects == ["研一高畅2026-09-25智能日报",
                        "研一高畅2026-09-25智能日报"]


def test_email_uses_implicit_ssl_when_configured(monkeypatch):
    calls = []
    class FakeSSL(FakeSMTP):
        def starttls(self):
            raise AssertionError("implicit SSL must not issue STARTTLS")
    def factory(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeSSL(*args, **kwargs)
    monkeypatch.setattr("smart_daily_report.notifier.email.smtplib.SMTP_SSL", factory)
    result = send_email(report(), ["lead@test"],
                        SmtpConfig("smtp.163.com", 465, None, None, "from@test", [], False, True),
                        FakeSMTP)
    assert result.success and calls[0][0][:2] == ("smtp.163.com", 465)


def test_email_send_failure_is_unknown_without_retry():
    calls = []
    class Flaky(FakeSMTP):
        def send_message(self, message):
            calls.append(message)
            if len(calls) == 1:
                raise OSError("temporary")
    result = send_email(report(), ["lead@test"], SmtpConfig("host", 587, "u", "p", "from@test", [], False), Flaky, lambda _: None)
    assert not result.success and result.outcome == "unknown" and result.attempts == 1 and len(calls) == 1


def test_email_does_not_retry_authentication_failure():
    import smtplib
    class Rejected(FakeSMTP):
        def login(self, *args): raise smtplib.SMTPAuthenticationError(535, b"no")
    result = send_email(report(), ["lead@test"], SmtpConfig("host", 587, "u", "p", "from@test", []), Rejected, lambda _: None)
    assert not result.success and result.attempts == 1 and result.error_code == "smtp_rejected"


def test_email_reports_unavailable_after_three_attempts():
    class Offline(FakeSMTP):
        def __enter__(self): raise OSError("offline")
    waits = []
    result = send_email(report(), ["lead@test"], SmtpConfig("host", 587, None, None, "from@test", []), Offline, waits.append)
    assert not result.success and result.attempts == 3 and result.error_code == "smtp_unavailable"
    assert waits == [1, 2]


def test_lark_retries_connection_failure_and_sends_markdown():
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1: raise httpx.ConnectError("temporary")
        assert request.read()
        return httpx.Response(200, json={"StatusCode": 0})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = send_lark_message(report(), "https://webhook.invalid/secret", client, sleep=lambda _: None)
    assert result.success and result.attempts == 2 and len(calls) == 2


def test_lark_webhook_rejects_payload_without_retry():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"StatusCode": 19000})))
    result = send_lark_message(report(), "https://webhook.invalid/secret", client)
    assert not result.success and result.error_code == "lark_rejected" and result.attempts == 1


def test_lark_webhook_does_not_retry_client_error():
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: (calls.append(request), httpx.Response(400))[1]))
    result = send_lark_message(report(), "https://webhook.invalid/secret", client)
    assert not result.success and result.error_code == "http_400" and len(calls) == 1


def test_lark_webhook_server_error_is_unknown_without_retry():
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: (calls.append(request), httpx.Response(503))[1]))
    result = send_lark_message(report(), "https://webhook.invalid/secret", client, sleep=lambda _: None)
    assert not result.success and result.outcome == "unknown" and result.attempts == 1 and len(calls) == 1


def test_partial_recipient_refusal_is_not_full_success():
    calls=[]
    class Partial(FakeSMTP):
        def send_message(self,message): calls.append(message); return {'rejected@test':(550,b'private-marker')}
    result=send_email(report(),['lead@test','rejected@test'],SmtpConfig('host',587,None,None,'from@test',[]),Partial,lambda _:None)
    assert result.success is False and result.outcome=='partial_failure'
    assert result.attempts==1 and len(calls)==1


def test_connect_failure_can_retry_before_sending():
    connections=[]; sends=[]
    class Accept(FakeSMTP):
        def send_message(self,message): sends.append(message); return {}
    def factory(*args,**kwargs):
        connections.append(args)
        if len(connections)<3: raise OSError('private-marker')
        return Accept()
    result=send_email(report(),['lead@test'],SmtpConfig('host',587,None,None,'from@test',[]),factory,lambda _:None)
    assert result.success and result.outcome=='accepted' and result.attempts==3 and len(sends)==1


def test_auth_failure_is_rejected_without_retry():
    import smtplib
    sends=[]
    class Reject(FakeSMTP):
        def login(self,*args): raise smtplib.SMTPAuthenticationError(535,b'private-marker')
        def send_message(self,message): sends.append(message); return {}
    result=send_email(report(),['lead@test'],SmtpConfig('host',587,'user','password','from@test',[]),Reject,lambda _:None)
    assert not result.success and result.outcome=='rejected' and result.attempts==1 and sends==[]


def test_send_response_timeout_is_unknown_without_retry():
    sends=[]
    class Timeout(FakeSMTP):
        def send_message(self,message): sends.append(message); raise TimeoutError('private-marker')
    result=send_email(report(),['lead@test'],SmtpConfig('host',587,None,None,'from@test',[]),Timeout,lambda _:None)
    assert not result.success and result.outcome=='unknown' and result.attempts==1 and len(sends)==1


def test_quit_failure_after_acceptance_does_not_resend():
    sends=[]
    class QuitFailure(FakeSMTP):
        def send_message(self,message): sends.append(message); return {}
        def __exit__(self,*args): raise OSError('private-marker')
    result=send_email(report(),['lead@test'],SmtpConfig('host',587,None,None,'from@test',[]),QuitFailure,lambda _:None)
    assert result.success and result.outcome=='accepted' and result.attempts==1 and len(sends)==1


def test_smtp_response_without_acceptance_evidence_is_unknown():
    sends=[]
    class MissingEvidence(FakeSMTP):
        def send_message(self,message): sends.append(message); return None
    result=send_email(report(),['lead@test'],SmtpConfig('host',587,None,None,'from@test',[]),MissingEvidence,lambda _:None)
    assert not result.success and result.outcome=='unknown' and len(sends)==1


@pytest.mark.parametrize('phase', ['sender','recipients','data','unsupported_tls'])
def test_explicit_smtp_rejection_cannot_be_uncertain_or_retried(phase):
    import smtplib
    calls=[]
    class Reject(FakeSMTP):
        def starttls(self):
            if phase=='unsupported_tls': raise smtplib.SMTPNotSupportedError('private-marker')
        def send_message(self,message):
            calls.append(message)
            if phase=='sender': raise smtplib.SMTPSenderRefused(550,b'private-marker','from@test')
            if phase=='recipients': raise smtplib.SMTPRecipientsRefused({'lead@test':(550,b'private-marker')})
            raise smtplib.SMTPDataError(550,b'private-marker')
    result=send_email(report(),['lead@test'],SmtpConfig('host',587,None,None,'from@test',[]),Reject,lambda _:None)
    assert result.outcome=='rejected' and not result.success and result.attempts==1
    assert len(calls)==(0 if phase=='unsupported_tls' else 1)


def test_tls_modes_and_payload_keep_confirmed_content():
    events=[]; snapshot=report()
    class Accept(FakeSMTP):
        def starttls(self): events.append('tls')
        def login(self,*args): events.append('login')
        def send_message(self,message):
            events.append('send')
            assert message.get_body(('html',)).get_content().strip()==snapshot.html
            assert 'private-password' not in message.as_string()
            return {}
    result=send_email(snapshot,['lead@test'],SmtpConfig('host',587,'user','private-password','from@test',[]),Accept,lambda _:None)
    assert result.outcome=='accepted' and events==['tls','login','send']


def test_modern_lark_error_code_cannot_default_to_success():
    calls=[]
    with httpx.Client(transport=httpx.MockTransport(lambda request:(calls.append(request),httpx.Response(200,json={'code':19024,'msg':'private-marker'}))[1])) as client:
        result=send_lark_message(report(),'https://hook.test/key',client,lambda _:None)
    assert not result.success and result.outcome=='rejected' and result.attempts==1 and len(calls)==1


@pytest.mark.parametrize('payload,outcome',[
 ({'code':0},'accepted'),({'StatusCode':0},'accepted'),({'code':0,'StatusCode':0},'accepted'),
 ({'StatusCode':19000},'rejected'),({},'unknown'),({'code':0,'StatusCode':19000},'unknown'),
 ({'code':False},'unknown'),({'code':'0'},'unknown'),(['bad'],'unknown')])
def test_lark_delivery_requires_explicit_consistent_business_evidence(payload,outcome):
    calls=[]
    with httpx.Client(transport=httpx.MockTransport(lambda request:(calls.append(request),httpx.Response(200,json=payload))[1])) as client:
        result=send_lark_message(report(),'https://hook.test/key',client,lambda _:None)
    assert result.outcome==outcome and result.success==(outcome=='accepted') and result.attempts==1 and len(calls)==1


@pytest.mark.parametrize('kind',['invalid_json','read_timeout','write_error','server_error'])
def test_lark_uncertainty_is_not_automatically_reposted(kind):
    calls=[]
    def handler(request):
        calls.append(request)
        if kind=='invalid_json': return httpx.Response(200,text='{private-marker')
        if kind=='read_timeout': raise httpx.ReadTimeout('private-marker')
        if kind=='write_error': raise httpx.WriteError('private-marker')
        return httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client: result=send_lark_message(report(),'https://hook.test/key',client,lambda _:None)
    assert not result.success and result.outcome=='unknown' and result.attempts==1 and len(calls)==1


@pytest.mark.parametrize('error_cls',[httpx.ConnectError,httpx.ConnectTimeout])
def test_lark_only_pre_submission_connection_failure_can_retry(error_cls):
    calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)<3: raise error_cls('private-marker')
        return httpx.Response(200,json={'code':0})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client: result=send_lark_message(report(),'https://hook.test/key',client,lambda _:None)
    assert result.success and result.outcome=='accepted' and result.attempts==3 and len(calls)==3


def test_lark_connection_exhaustion_is_rejected_before_acceptance():
    calls=[]
    def handler(request): calls.append(request); raise httpx.ConnectError('private-marker')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client: result=send_lark_message(report(),'https://hook.test/key',client,lambda _:None)
    assert not result.success and result.outcome=='rejected' and result.attempts==3 and len(calls)==3
