"""
Mailer для OTP-писем при авторизации по email.

Поддерживает два провайдера:
  - SMTP (по умолчанию, если задан SMTP_HOST) — обычный SMTP-сервер,
    в т.ч. без авторизации (внутренний релей с whitelist по IP).
    Env: MAIL_PROVIDER=smtp (опционально),
         SMTP_HOST, SMTP_PORT (по умолчанию 587),
         SMTP_USER, SMTP_PASS (опционально, для релеев по IP можно не задавать),
         SMTP_FROM, SMTP_FROM_NAME, SMTP_USE_TLS (true/false, для 465).
  - Resend HTTPS API (fallback, если SMTP_HOST не задан или MAIL_PROVIDER=resend).
    Env: RESEND_API_KEY, RESEND_FROM, RESEND_FROM_NAME.

Имя файла оставлено историческим для совместимости импортов.
"""
import os
import ssl
import smtplib
import asyncio
import logging
from email.message import EmailMessage

import aiohttp

logger = logging.getLogger('wl_bot')

# ── SMTP ──
SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587') or 587)
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASS = os.getenv('SMTP_PASS', '')
SMTP_FROM = os.getenv('SMTP_FROM', '')
SMTP_FROM_NAME = os.getenv('SMTP_FROM_NAME', 'Winline Partners')
SMTP_USE_TLS = (os.getenv('SMTP_USE_TLS', 'false') or 'false').lower() == 'true'  # SSL on connect (порт 465)

# ── Resend ──
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
RESEND_FROM = os.getenv('RESEND_FROM', '')
RESEND_FROM_NAME = os.getenv('RESEND_FROM_NAME', 'Winline Partners')

MAIL_PROVIDER = (os.getenv('MAIL_PROVIDER', '') or '').lower()


def _provider() -> str:
    if MAIL_PROVIDER in ('smtp', 'resend'):
        return MAIL_PROVIDER
    if SMTP_HOST:
        return 'smtp'
    if RESEND_API_KEY and RESEND_FROM:
        return 'resend'
    return ''


def is_configured() -> bool:
    p = _provider()
    if p == 'smtp':
        return bool(SMTP_HOST and SMTP_FROM)
    if p == 'resend':
        return bool(RESEND_API_KEY and RESEND_FROM)
    return False


def _otp_html(code: str) -> str:
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;'
        'max-width:480px;margin:0 auto;padding:24px;color:#222">'
        '<h2 style="margin:0 0 12px">Код подтверждения</h2>'
        '<p style="margin:0 0 16px;color:#555">Вы авторизуетесь в боте Winline Partners.</p>'
        f'<div style="font-size:32px;letter-spacing:8px;font-weight:700;padding:16px 20px;'
        f'background:#f3f4f6;border-radius:8px;text-align:center">{code}</div>'
        '<p style="margin:16px 0 0;color:#888;font-size:13px">'
        'Код действителен 10 минут. Если это были не вы — проигнорируйте это письмо.</p>'
        '</div>'
    )


def _otp_text(code: str) -> str:
    return (
        f'Ваш одноразовый код для авторизации в Winline Partners: {code}\n\n'
        f'Код действителен 10 минут. Если это были не вы — проигнорируйте письмо.'
    )


def _build_message(to: str, code: str) -> EmailMessage:
    msg = EmailMessage()
    from_addr = SMTP_FROM
    msg['From'] = f'{SMTP_FROM_NAME} <{from_addr}>' if SMTP_FROM_NAME else from_addr
    msg['To'] = to
    msg['Subject'] = f'Код подтверждения: {code}'
    msg.set_content(_otp_text(code))
    msg.add_alternative(_otp_html(code), subtype='html')
    return msg


def _send_smtp_sync(to: str, code: str) -> bool:
    msg = _build_message(to, code)
    try:
        if SMTP_USE_TLS:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            client = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ctx)
        else:
            client = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        with client as server:
            server.ehlo()
            # Оппортунистический STARTTLS, если сервер его умеет
            if not SMTP_USE_TLS:
                try:
                    if server.has_extn('starttls'):
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        server.starttls(context=ctx)
                        server.ehlo()
                except smtplib.SMTPException as e:
                    logger.info(f'[smtp] STARTTLS skipped: {e}')
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logger.info(f'[smtp] sent OTP to {to} via {SMTP_HOST}:{SMTP_PORT}')
        return True
    except Exception as e:
        logger.warning(f'[smtp] send failed: {e}')
        return False


async def _send_smtp(to: str, code: str) -> bool:
    return await asyncio.to_thread(_send_smtp_sync, to, code)


async def _send_resend(to: str, code: str) -> bool:
    from_addr = f'{RESEND_FROM_NAME} <{RESEND_FROM}>' if RESEND_FROM_NAME else RESEND_FROM
    payload = {
        'from': from_addr, 'to': to,
        'subject': f'Код подтверждения: {code}',
        'text': _otp_text(code), 'html': _otp_html(code),
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(
                'https://api.resend.com/emails',
                headers={
                    'Authorization': f'Bearer {RESEND_API_KEY}',
                    'Content-Type': 'application/json',
                },
                json=payload,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    logger.warning(f'[resend] send failed HTTP {resp.status}: {data}')
                    return False
                logger.info(f'[resend] sent to {to}, id={data.get("id")}')
                return True
    except Exception as e:
        logger.warning(f'[resend] exception: {e}')
        return False


async def send_otp_email(to: str, code: str) -> bool:
    """Send OTP via configured provider. Returns True on success."""
    if not is_configured():
        logger.warning('[mailer] не сконфигурирован (нет SMTP_HOST/SMTP_FROM и RESEND_API_KEY/RESEND_FROM)')
        return False
    p = _provider()
    if p == 'smtp':
        return await _send_smtp(to, code)
    return await _send_resend(to, code)
