"""
Resend HTTPS API — отправка OTP-писем для авторизации по email.
Env: RESEND_API_KEY, RESEND_FROM (например noreply@winlinepartners.ru),
     RESEND_FROM_NAME (по умолчанию 'Winline Partners').
"""
import os
import logging
import aiohttp

logger = logging.getLogger('wl_bot')

RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
RESEND_FROM = os.getenv('RESEND_FROM', '')
RESEND_FROM_NAME = os.getenv('RESEND_FROM_NAME', 'Winline Partners')


def is_configured() -> bool:
    return bool(RESEND_API_KEY and RESEND_FROM)


async def send_otp_email(to: str, code: str) -> bool:
    """Send OTP code via Resend. Returns True on success, False otherwise."""
    if not is_configured():
        logger.warning('[resend] RESEND_API_KEY/RESEND_FROM не заданы — письмо не отправлено')
        return False

    from_addr = f'{RESEND_FROM_NAME} <{RESEND_FROM}>' if RESEND_FROM_NAME else RESEND_FROM
    subject = f'Код подтверждения: {code}'
    text = (
        f'Ваш одноразовый код для авторизации в Winline Partners: {code}\n\n'
        f'Код действителен 10 минут. Если это были не вы — проигнорируйте письмо.'
    )
    html = f'''
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#222">
      <h2 style="margin:0 0 12px">Код подтверждения</h2>
      <p style="margin:0 0 16px;color:#555">Вы авторизуетесь в боте Winline Partners.</p>
      <div style="font-size:32px;letter-spacing:8px;font-weight:700;padding:16px 20px;background:#f3f4f6;border-radius:8px;text-align:center">{code}</div>
      <p style="margin:16px 0 0;color:#888;font-size:13px">Код действителен 10 минут. Если это были не вы — проигнорируйте это письмо.</p>
    </div>'''

    payload = {'from': from_addr, 'to': to, 'subject': subject, 'text': text, 'html': html}
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
