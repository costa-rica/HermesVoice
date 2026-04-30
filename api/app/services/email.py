from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ..config import settings


async def send_verification_code(email: str, code: str) -> None:
    host = settings.HERMES_VOICE_SMTP_HOST
    from_email = settings.HERMES_VOICE_SMTP_FROM_EMAIL
    if not host or not from_email:
        raise RuntimeError("SMTP host and from email must be configured")

    message = EmailMessage()
    message["Subject"] = "Your HermesVoice verification code"
    message["From"] = from_email
    message["To"] = email
    message.set_content(
        "Your HermesVoice verification code is "
        f"{code}. It expires in {settings.LOGIN_CODE_TTL_SECONDS // 60} minutes."
    )

    with smtplib.SMTP(host, settings.HERMES_VOICE_SMTP_PORT, timeout=15) as smtp:
        if settings.HERMES_VOICE_SMTP_USE_TLS:
            smtp.starttls()
        if settings.HERMES_VOICE_SMTP_USERNAME or settings.HERMES_VOICE_SMTP_PASSWORD:
            smtp.login(
                settings.HERMES_VOICE_SMTP_USERNAME,
                settings.HERMES_VOICE_SMTP_PASSWORD,
            )
        smtp.send_message(message)
