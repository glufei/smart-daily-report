from __future__ import annotations

import smtplib
import time
from email.message import EmailMessage
from typing import Callable, Sequence

from ..shared.models import DailyReport, DeliveryResult, SmtpConfig


def send_email(report: DailyReport, recipients: Sequence[str], smtp_config: SmtpConfig,
               smtp_factory=smtplib.SMTP, sleep: Callable[[float], None] = time.sleep) -> DeliveryResult:
    message = EmailMessage()
    message["Subject"] = f"高畅智能日报（{report.report_date.isoformat()}）"
    message["From"] = smtp_config.sender
    message["To"] = ", ".join(recipients)
    message.set_content("请使用支持 HTML 的邮件客户端查看日报。")
    message.add_alternative(report.html, subtype="html")
    for attempt in range(1, 4):
        submitted = False
        result = None
        try:
            connection_factory = smtplib.SMTP_SSL if smtp_config.use_ssl else smtp_factory
            with connection_factory(smtp_config.host, smtp_config.port, timeout=10) as server:
                if smtp_config.starttls:
                    server.starttls()
                if smtp_config.username:
                    server.login(smtp_config.username, smtp_config.password or "")
                submitted = True
                refused = server.send_message(message)
                if not isinstance(refused, dict):
                    result = DeliveryResult(False, attempt, "smtp_unknown", "unknown")
                elif refused:
                    result = DeliveryResult(False, attempt, "smtp_partial", "partial_failure")
                else:
                    result = DeliveryResult(True, attempt, outcome="accepted")
            return result
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused,
                smtplib.SMTPSenderRefused, smtplib.SMTPDataError, smtplib.SMTPNotSupportedError):
            return result or DeliveryResult(False, attempt, "smtp_rejected", "rejected")
        except (OSError, smtplib.SMTPException):
            if result is not None:
                return result
            if submitted:
                return DeliveryResult(False, attempt, "smtp_unknown", "unknown")
            if attempt == 3:
                return DeliveryResult(False, attempt, "smtp_unavailable", "rejected")
            sleep(min(2 ** (attempt - 1), 5))
    return DeliveryResult(False, 3, "smtp_unavailable", "rejected")
