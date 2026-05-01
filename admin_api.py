"""
Admin Panel API Bridge
Connects winline-admin-panel (Node.js) to the Telegram bot (Python/aiogram).

Runs on port 5050 (localhost only).
Start: cd ~/VScodeProjects/WLPartnersBot && venv/bin/python3 admin_api.py
"""

import asyncio
import os
import subprocess
import sys

import aiohttp
from aiohttp import web

from environs import Env

env = Env()
env.read_env()
BOT_TOKEN = env.str('TG_TOKEN')
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'
IAP_ADMIN_TOKEN = env.str('IAP_ADMIN_TOKEN', '')

# Add bot root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.integrations import DB  # noqa: E402
from bot.initialization.bot_texts.load_texts import bot_texts
from bot.utils.settings_cache import invalidate as invalidate_settings  # noqa: E402

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.name == 'nt':
    PYTHON_BIN = os.path.join(BOT_DIR, 'venv', 'Scripts', 'python.exe')
else:
    PYTHON_BIN = os.path.join(BOT_DIR, 'venv', 'bin', 'python3')

STATUS_MAP = {0: 'draft', 1: 'sending', 201: 'published'}


def cors_headers(response: web.Response) -> web.Response:
    response.headers['Access-Control-Allow-Origin'] = 'https://panel.wl-fdms.tw1.ru'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


async def preflight(request):
    return cors_headers(web.Response(status=204))


# ── GET /users/count?audience=all|registered|me&admin_tg_id=... ──────────────

async def get_users_count(request):
    audience = request.rel_url.query.get('audience', 'all')
    admin_tg_id = request.rel_url.query.get('admin_tg_id')

    def _query():
        users = DB.User.select(all_scalars=True)
        if audience == 'registered':
            return [u for u in users if u.registered and not u.banned]
        elif audience == 'me' and admin_tg_id:
            return [u for u in users if str(u.user_id) == str(admin_tg_id)]
        return [u for u in users if not u.banned]

    try:
        users = await asyncio.to_thread(_query)
        return cors_headers(web.json_response({'count': len(users), 'audience': audience}))
    except Exception as e:
        return cors_headers(web.json_response({'error': str(e)}, status=500))


# ── GET /broadcasts ──────────────────────────────────────────────────────────

async def get_broadcasts(request):
    def _query():
        return DB.Alert.select(all_scalars=True)

    try:
        alerts = await asyncio.to_thread(_query)
        result = []
        for a in reversed(alerts):
            if a.status_code == 0:
                continue
            text = (a.data.get('text', '') or '') if a.data else ''
            result.append({
                'id': a.id,
                'text': text[:120],
                'alert_type': a.data.get('alert_type') if a.data else None,
                'status': STATUS_MAP.get(a.status_code, 'unknown'),
                'date_sent': a.date_sent.isoformat() if a.date_sent else None,
                'successfully_sent': a.successfully_sent,
                'error_sent': a.error_sent,
            })
        return cors_headers(web.json_response(result))
    except Exception as e:
        return cors_headers(web.json_response({'error': str(e)}, status=500))


# ── POST /broadcasts ──────────────────────────────────────────────────────────

async def send_broadcast(request):
    try:
        body = await request.json()
    except Exception:
        return cors_headers(web.json_response({'error': 'Invalid JSON'}, status=400))

    text = body.get('text', '').strip()
    audience = body.get('audience', 'all')
    admin_tg_id = body.get('admin_tg_id')
    buttons = body.get('buttons', [])

    if not text:
        return cors_headers(web.json_response({'error': 'text is required'}, status=400))

    def _get_admin():
        admins = DB.Admin.select(all_scalars=True)
        return admins[0].admin_id if admins else None

    def _get_users():
        all_users = DB.User.select(all_scalars=True)
        if audience == 'registered':
            return [u for u in all_users if u.registered and not u.banned]
        elif audience == 'me' and admin_tg_id:
            return [u for u in all_users if str(u.user_id) == str(admin_tg_id)]
        return [u for u in all_users if not u.banned]

    def _create_alert(admin_id, users):
        alert_id = DB.Alert.add(admin_id=admin_id, text=text, buttons=buttons)
        if not alert_id:
            return None
        recipients = {str(u.user_id): 0 for u in users}
        DB.Alert.update(mark=alert_id, recipients=recipients)
        return alert_id

    try:
        admin_id = await asyncio.to_thread(_get_admin)
        if not admin_id:
            return cors_headers(web.json_response({'error': 'No admins in bot DB'}, status=500))

        users = await asyncio.to_thread(_get_users)
        if not users:
            return cors_headers(web.json_response({'error': 'No users for selected audience'}, status=400))

        alert_id = await asyncio.to_thread(_create_alert, admin_id, users)
        if not alert_id:
            return cors_headers(web.json_response({'error': 'Failed to create alert record'}, status=500))

        # Run background_alert subprocess
        cmd = [PYTHON_BIN, '-m', 'background_alert', str(alert_id)]
        subprocess.Popen(cmd, cwd=BOT_DIR)

        return cors_headers(web.json_response({
            'alert_id': alert_id,
            'recipients_count': len(users),
            'status': 'sending',
        }))
    except Exception as e:
        return cors_headers(web.json_response({'error': str(e)}, status=500))


# ── Telegram helpers ──────────────────────────────────────────────────────────

AUTHORIZED_KEYBOARD = {
    'inline_keyboard': [
        [{'text': 'База знаний', 'callback_data': 'client_knowledge_base'}],
        [{'text': 'Офферы', 'callback_data': 'client_offers'}],
        [{'text': 'Социальные сети', 'callback_data': 'client_socials'}],
        [{'text': 'Актуальные промо и ссылки', 'callback_data': 'client_promo'}],
        [{'text': 'Чат с менеджером', 'callback_data': 'client_chat_manager'}],
        [{'text': 'Я на мероприятии!', 'callback_data': 'client_at_event'}],
        [{'text': '🚪 Выйти из аккаунта', 'callback_data': 'client_logout'}],
    ]
}

AUTHORIZED_KEYBOARD_ADMIN = {
    'inline_keyboard': [
        [{'text': 'База знаний', 'callback_data': 'client_knowledge_base'}],
        [{'text': 'Офферы', 'callback_data': 'client_offers'}],
        [{'text': 'Социальные сети', 'callback_data': 'client_socials'}],
        [{'text': 'Актуальные промо и ссылки', 'callback_data': 'client_promo'}],
        [{'text': 'Чат с менеджером', 'callback_data': 'client_chat_manager'}],
        [{'text': 'Я на мероприятии!', 'callback_data': 'client_at_event'}],
        [{'text': '⚙️ Меню администратора', 'callback_data': 'admin_menu'}],
        [{'text': '🚪 Выйти из аккаунта', 'callback_data': 'client_logout'}],
    ]
}


def _is_admin(user_id: int) -> bool:
    """Check if user is admin via DB."""
    admin = DB.Admin.select(mark=user_id)
    return admin is not None

PHOTO_ID = 'AgACAgIAAxkBAAJ1zWhdevQQMSnK7IPyyuQVbD13znboAAJI9jEbyLfpSung7LZvwELaAQADAgADeAADNgQ'


async def tg_delete_message(session, chat_id, message_id):
    try:
        await session.post(f'{TELEGRAM_API}/deleteMessage', json={
            'chat_id': chat_id, 'message_id': message_id})
    except Exception:
        pass


async def tg_send_authorized_menu(session, user_id, email, is_admin=False):
    import html as _html
    email_text = f'\n\n📧 <b>Email:</b> {_html.escape(email)}' if email else ''
    caption = f'<b>✅ Вы авторизованы</b>{email_text}'
    kb = AUTHORIZED_KEYBOARD_ADMIN if is_admin else AUTHORIZED_KEYBOARD
    resp = await session.post(f'{TELEGRAM_API}/sendPhoto', json={
        'chat_id': user_id,
        'photo': PHOTO_ID,
        'caption': caption,
        'parse_mode': 'HTML',
        'reply_markup': kb,
    })
    data = await resp.json()
    if data.get('ok'):
        return data['result']['message_id']
    return None


async def tg_send_guest_menu(session, user_id):
    """Send start menu for non-partner (guest) user."""
    START_KEYBOARD = {
        'inline_keyboard': [
            [{'text': 'Я уже являюсь партнёром', 'callback_data': 'client_existing_partner'}],
            [{'text': 'Регистрация партнёров', 'callback_data': 'client_new_partner'}],
        ]
    }
    caption = ('<b>Такой email не найден среди партнёров Winline.\n\n'
               'Если вы хотите стать партнёром — пройдите регистрацию на платформе.</b>')
    resp = await session.post(f'{TELEGRAM_API}/sendPhoto', json={
        'chat_id': user_id,
        'photo': PHOTO_ID,
        'caption': caption,
        'parse_mode': 'HTML',
        'reply_markup': START_KEYBOARD,
    })
    data = await resp.json()
    if data.get('ok'):
        return data['result']['message_id']
    return None


# ── POST /auth ───────────────────────────────────────────────────────────────

async def auth_user(request):
    try:
        body = await request.json()
    except Exception:
        return cors_headers(web.json_response({'error': 'Invalid JSON'}, status=400))

    email = (body.get('email') or '').strip().lower()
    user_id = body.get('user_id')

    if not email or not user_id:
        return cors_headers(web.json_response({'error': 'email and user_id are required'}, status=400))

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return cors_headers(web.json_response({'error': 'Invalid user_id'}, status=400))

    # Check email in IAP API (if admin token is configured)
    is_partner = True  # default: accept all emails if no IAP token
    if IAP_ADMIN_TOKEN:
        try:
            is_partner = await _check_email_in_iap(email)
        except Exception:
            # If IAP check fails, accept the email anyway
            is_partner = True

    if not is_partner:
        # Not a partner → send guest menu
        try:
            async with aiohttp.ClientSession() as tg_session:
                user_data = await asyncio.to_thread(lambda: DB.User.select(user_id))
                if user_data and user_data.menu_id:
                    await tg_delete_message(tg_session, user_id, user_data.menu_id)
                new_msg_id = await tg_send_guest_menu(tg_session, user_id)
                if new_msg_id:
                    await asyncio.to_thread(lambda: DB.User.update(mark=user_id, menu_id=new_msg_id))
        except Exception:
            pass
        return cors_headers(web.json_response({
            'ok': False,
            'error': 'Email не найден среди партнёров Winline'
        }, status=404))

    # Partner found → save auth and send authorized menu
    def _save_auth():
        existing = DB.UserAuth.select(user_id)
        if existing:
            DB.UserAuth.update(user_id, email=email, token=None)
        else:
            DB.UserAuth.add(user_id, email, token=None)

    await asyncio.to_thread(_save_auth)

    try:
        async with aiohttp.ClientSession() as tg_session:
            user_data = await asyncio.to_thread(lambda: DB.User.select(user_id))
            if user_data and user_data.menu_id:
                await tg_delete_message(tg_session, user_id, user_data.menu_id)
            admin_flag = await asyncio.to_thread(lambda: _is_admin(user_id))
            new_msg_id = await tg_send_authorized_menu(tg_session, user_id, email, is_admin=admin_flag)
            if new_msg_id:
                await asyncio.to_thread(lambda: DB.User.update(mark=user_id, menu_id=new_msg_id))
    except Exception:
        pass

    return cors_headers(web.json_response({'ok': True, 'email': email}))


async def _check_email_in_iap(email: str) -> bool:
    """Check if email exists in IAP with partner status.
    Returns True if partner found, False otherwise.
    TODO: Update GraphQL query when IAP API structure is confirmed.
    """
    # Placeholder: will be updated with actual GraphQL query
    # For now, tries to search affiliates by email
    query = '''
query checkEmail($email: String!) {
    affiliates(filter: { email: $email }, limit: 1) {
        items { id email status }
    }
}
'''
    variables = {"email": email}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://iap-demo.admon.pro/api/graphql',
                headers={
                    'Authorization': f'Bearer {IAP_ADMIN_TOKEN}',
                    'Content-Type': 'application/json',
                },
                json={'query': query, 'variables': variables},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return True  # If API fails, accept email
                data = await resp.json()
                items = (data.get('data', {}).get('affiliates', {}).get('items') or [])
                return len(items) > 0
    except Exception:
        return True  # On error, accept email



# ── GET /reload-texts ────────────────────────────────────────────────────────

@web.middleware
async def check_api_key(request, handler):
    """Require X-API-Key header on every endpoint except /health and CORS preflight.

    If ADMIN_API_KEY env is empty, logs a warning once and allows all (legacy
    behavior, kept for backwards compatibility during rollout).
    """
    if request.method == 'OPTIONS' or request.path == '/health':
        return await handler(request)
    expected = os.environ.get('ADMIN_API_KEY', '')
    if not expected:
        if not getattr(check_api_key, '_warned', False):
            print('[admin_api] WARNING: ADMIN_API_KEY env is not set — endpoints are unauthenticated!')
            check_api_key._warned = True
        return await handler(request)
    api_key = request.headers.get('X-API-Key', '')
    # constant-time comparison to avoid timing oracle
    import hmac as _hmac
    if not _hmac.compare_digest(api_key, expected):
        return cors_headers(web.json_response({'error': 'Invalid API key'}, status=403))
    return await handler(request)


async def health(request):
    return web.json_response({'ok': True})

async def reload_texts(request):
    """Reload bot texts from DB (called by admin panel after scenarios save)."""
    try:
        await asyncio.to_thread(bot_texts.load_db_texts)
        return cors_headers(web.json_response({'ok': True, 'message': 'Texts reloaded'}))
    except Exception as e:
        return cors_headers(web.json_response({'error': str(e)}, status=500))


# ── POST /event/merch-given ──────────────────────────────────────────────────

async def event_merch_given(request):
    """Send registration promo to user after merch QR was scanned by hostess.

    Body: {"user_id": <telegram_id>}
    Pulls scenario text + buttons from bot_scenarios for screen
    `event_registration_promo` and sends via Telegram HTTP API.
    """
    try:
        body = await request.json()
        user_id = int(body.get('user_id') or 0)
        if not user_id:
            return cors_headers(web.json_response({'error': 'user_id is required'}, status=400))

        # Gate by raffle_hidden setting — when on, registration promo не отправляем
        try:
            import json as _json_mod, os as _os, mysql.connector as _mc
            _conn = _mc.connect(
                host=_os.getenv('MYSQL_HOST', ''), port=int(_os.getenv('MYSQL_PORT', 3306)),
                user=_os.getenv('MYSQL_USER', ''), password=_os.getenv('MYSQL_PASSWORD', ''),
                database=_os.getenv('MYSQL_DATABASE', ''),
            )
            try:
                _cur = _conn.cursor(dictionary=True)
                _cur.execute("SELECT data FROM texts WHERE category='event_settings' LIMIT 1")
                _row = _cur.fetchone()
                if _row and _row.get('data'):
                    _d = _row['data']
                    _s = _json_mod.loads(_d) if isinstance(_d, str) else _d
                    if _s and _s.get('raffle_hidden'):
                        return cors_headers(web.json_response({'ok': True, 'skipped': 'raffle_hidden'}))
            finally:
                _conn.close()
        except Exception:
            pass

        from bot.utils.scenario_texts import get_text
        from bot.utils.dynamic_kb import get_screen_kb

        text = get_text('event_registration_promo', 'promo') or (
            '<b>Хочешь выиграть 1 из 10 мячей, подписанным легендой '
            'футбола и амбассадором WINLINE, Роналдиньо?</b>\n\n'
            'Пройди регистрацию на сайте WINLINE PARTNERS'
        )
        kb_obj = get_screen_kb('event_registration_promo')
        # InlineKeyboardMarkup → dict for Telegram HTTP API
        reply_markup = None
        if kb_obj is not None:
            reply_markup = kb_obj.model_dump(exclude_none=True) if hasattr(kb_obj, 'model_dump') else kb_obj.dict(exclude_none=True)

        async with aiohttp.ClientSession() as session:
            payload = {
                'chat_id': user_id,
                'text': text,
                'parse_mode': 'HTML',
            }
            if reply_markup:
                import json as _json
                payload['reply_markup'] = _json.dumps(reply_markup)
            async with session.post(f'{TELEGRAM_API}/sendMessage', data=payload,
                                    timeout=aiohttp.ClientTimeout(total=10)) as r:
                resp_data = await r.json()
                if not resp_data.get('ok'):
                    return cors_headers(web.json_response(
                        {'error': resp_data.get('description', 'Telegram error')}, status=500))
                # Update user's menu_id so back-buttons clean up correctly
                msg_id = resp_data.get('result', {}).get('message_id')
                if msg_id:
                    try:
                        DB.User.update(mark=user_id, menu_id=msg_id)
                    except Exception:
                        pass

        return cors_headers(web.json_response({'ok': True}))
    except Exception as e:
        return cors_headers(web.json_response({'error': str(e)}, status=500))


# ── POST /telegram/relay ─────────────────────────────────────────────────────

async def telegram_relay(request):
    """Forward a Telegram Bot API call from the panel through this server.

    Body schema:
      { "method": "sendMessage", "params": { ...JSON params... } }
      { "method": "sendPhoto",  "params": { chat_id, caption?, parse_mode?, reply_markup?, ... },
        "file":   { "url": "...", "filename": "...", "mime": "...", "field": "photo" } }
      { "method": "sendMediaGroup", "params": { chat_id, ... },
        "files":  [ { "url", "filename", "mime", "attach": "file0" }, ... ] }

    The panel can't reach api.telegram.org (RKN-блок); we relay because the
    bot host has clean IPv4 outbound to Telegram.
    """
    try:
        body = await request.json()
    except Exception:
        return cors_headers(web.json_response({'ok': False, 'description': 'Invalid JSON'}, status=400))

    method = (body.get('method') or '').strip()
    if not method or '/' in method or '..' in method:
        return cors_headers(web.json_response({'ok': False, 'description': 'invalid method'}, status=400))
    params = body.get('params') or {}
    file = body.get('file')
    files = body.get('files')

    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if file or files:
                form = aiohttp.FormData()
                # Stringify non-string params (Telegram accepts strings in multipart)
                import json as _json
                for k, v in params.items():
                    if isinstance(v, (dict, list)):
                        form.add_field(k, _json.dumps(v))
                    elif isinstance(v, bool):
                        form.add_field(k, 'true' if v else 'false')
                    else:
                        form.add_field(k, str(v))

                async def _attach(file_spec):
                    url = file_spec.get('url')
                    if not url:
                        raise ValueError('file.url required')
                    async with session.get(url) as r:
                        if r.status != 200:
                            raise RuntimeError(f'media fetch {r.status} for {url}')
                        return await r.read()

                if file:
                    buf = await _attach(file)
                    form.add_field(file.get('field') or 'document', buf,
                                   filename=file.get('filename') or 'file',
                                   content_type=file.get('mime') or 'application/octet-stream')
                if files:
                    for f in files:
                        buf = await _attach(f)
                        form.add_field(f.get('attach') or f.get('field') or 'file', buf,
                                       filename=f.get('filename') or 'file',
                                       content_type=f.get('mime') or 'application/octet-stream')

                async with session.post(f'{TELEGRAM_API}/{method}', data=form) as r:
                    data = await r.json(content_type=None)
            else:
                async with session.post(f'{TELEGRAM_API}/{method}', json=params) as r:
                    data = await r.json(content_type=None)

        return cors_headers(web.json_response(data))
    except Exception as e:
        return cors_headers(web.json_response({'ok': False, 'description': f'relay: {e}'}, status=502))


# ── App setup ────────────────────────────────────────────────────────────────


def make_app():
    app = web.Application(middlewares=[check_api_key])
    app.router.add_route('OPTIONS', '/{path_info:.*}', preflight)
    app.router.add_get('/health', health)
    app.router.add_get('/users/count', get_users_count)
    app.router.add_get('/broadcasts', get_broadcasts)
    app.router.add_post('/broadcasts', send_broadcast)
    app.router.add_post('/auth', auth_user)
    app.router.add_get('/reload-texts', reload_texts)
    app.router.add_post('/event/merch-given', event_merch_given)
    app.router.add_post('/telegram/relay', telegram_relay)
    return app


if __name__ == '__main__':
    print('[admin_api] Starting on http://127.0.0.1:5050')
    web.run_app(make_app(), host='0.0.0.0', port=5050, print=None)
