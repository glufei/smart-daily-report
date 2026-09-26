from datetime import date, datetime, timezone
from email.message import EmailMessage

import httpx

from smart_daily_report.notifier.email import send_email
from smart_daily_report.notifier.lark_bot import send_lark_message
from smart_daily_report.shared.models import DailyReport, SmtpConfig


def report():
    return DailyReport(date(2026, 9, 25), "team", [], {}, "# daily", "<h1>daily</h1>", datetime.now(timezone.utc))


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


def test_email_delivers_html():
    FakeSMTP.calls = 0
    result = send_email(report(), ["lead@test"], SmtpConfig("host", 587, None, None, "from@test", []), FakeSMTP)
    assert result.success and FakeSMTP.calls == 1


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


def test_email_retries_temporary_failure_then_succeeds():
    calls = []
    class Flaky(FakeSMTP):
        def send_message(self, message):
            calls.append(message)
            if len(calls) == 1:
                raise OSError("temporary")
    result = send_email(report(), ["lead@test"], SmtpConfig("host", 587, "u", "p", "from@test", [], False), Flaky, lambda _: None)
    assert result.success and result.attempts == 2


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


def test_lark_retries_transient_failure_and_sends_markdown():
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1: return httpx.Response(500)
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


def test_lark_webhook_reports_unavailable_after_retry_exhaustion():
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: (calls.append(request), httpx.Response(503))[1]))
    result = send_lark_message(report(), "https://webhook.invalid/secret", client, sleep=lambda _: None)
    assert not result.success and result.attempts == 3 and len(calls) == 3
