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

# В РФ-регионе api.telegram.org заблокирован — нужен прокси (тот же что
# использует основной бот для polling). aiohttp_socks даёт SOCKS5/HTTP-
# коннектор; если TG_PROXY_URL не задан, ходим напрямую как раньше.
TG_PROXY_URL = env.str('TG_PROXY_URL', '')


def _telegram_session(timeout_sec: int = 60):
    """Возвращает aiohttp.ClientSession, маршрутизирующий запросы к
    api.telegram.org через TG_PROXY_URL, если он задан. Используется в
    /telegram/relay — раньше там был «голый» ClientSession без прокси,
    из-за чего relay молча падал по таймауту, а в очередь рассылок
    сыпались `last_error_msg='relay: '`."""
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    if TG_PROXY_URL:
        try:
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url(TG_PROXY_URL)
            return aiohttp.ClientSession(connector=connector, timeout=timeout)
        except Exception as e:
            print(f'[admin_api] TG_PROXY_URL configured but ProxyConnector failed: {e} — going direct')
    return aiohttp.ClientSession(timeout=timeout)

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

# Mini App URL — the «Открыть приложение» web_app button. Empty env = button is
# NOT added (don't show a dead button before the subdomain is live). Keep in
# sync with the scenario main_menu btn_webapp (panel scenarios.js migration).
MINIAPP_URL = env.str('MINIAPP_URL', '').strip()
_MINIAPP_ROW = ([[{'text': '📱 Открыть приложение', 'web_app': {'url': MINIAPP_URL}}]]
                if MINIAPP_URL else [])

AUTHORIZED_KEYBOARD = {
    'inline_keyboard': [
        *_MINIAPP_ROW,
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
        *_MINIAPP_ROW,
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

    # Status tag by mirror data (best-effort, mini app logins included)
    try:
        from bot.utils import partner_tags
        await partner_tags.retag_after_login(user_id, email)
    except Exception:
        pass

    # Mini-App login finalize: do NOT push anything into the user's bot chat.
    # (Previously sent «✅ Вы авторизованы» here, but the user already logged in
    # inside the Web App, so the bot message read as a spammy notification.)

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
    """Hostess scanned the merch QR at the stand.

    Эндпоинт остаётся для backward-compat (админка вызывает его при скане),
    но больше НЕ шлёт раффл-промо пользователю. Раньше шёл:
        анкета → merch QR → ...ждём скан... → этот endpoint шлёт промо.
    Сейчас раффл-промо уже отправляется в _anketa_finish сразу после QR
    (для трафик-партнёров; для Рекламодатель/Другое его вообще нет).
    Вторичный пуш после скана дублировал бы сообщение трафик-партнёрам
    и неуместно появлялся бы у Рекламодатель/Другое.

    Поведение: принимаем запрос, ничего не шлём, отдаём ok.
    """
    try:
        body = await request.json()
        user_id = int(body.get('user_id') or 0)
        if not user_id:
            return cors_headers(web.json_response({'error': 'user_id is required'}, status=400))
        return cors_headers(web.json_response({'ok': True, 'skipped': 'promo_already_sent_in_anketa_flow'}))
    except Exception as e:
        return cors_headers(web.json_response({'error': str(e)}, status=500))


# ── POST /logout ──────────────────────────────────────────────────────────────

async def logout_user(request):
    """Log a user out (called by the Mini App). Mirrors the bot's client_logout:
    deletes the user_auth row, replaces the menu message with the guest menu."""
    try:
        body = await request.json()
    except Exception:
        return cors_headers(web.json_response({'error': 'Invalid JSON'}, status=400))

    try:
        user_id = int(body.get('user_id') or 0)
    except (TypeError, ValueError):
        user_id = 0
    if not user_id:
        return cors_headers(web.json_response({'error': 'user_id is required'}, status=400))

    def _delete_auth():
        existing = DB.UserAuth.select(user_id)
        if not existing:
            return False
        DB.UserAuth.remove(user_id)
        return True

    try:
        had_auth = await asyncio.to_thread(_delete_auth)

        # Refresh the user's chat: drop old menu message, send the start menu.
        try:
            async with _telegram_session(timeout_sec=30) as tg_session:
                user_data = await asyncio.to_thread(lambda: DB.User.select(user_id))
                if user_data and user_data.menu_id:
                    await tg_delete_message(tg_session, user_id, user_data.menu_id)
                new_msg_id = await tg_send_guest_menu(tg_session, user_id)
                if new_msg_id:
                    await asyncio.to_thread(lambda: DB.User.update(mark=user_id, menu_id=new_msg_id))
        except Exception:
            pass  # logout itself succeeded; menu refresh is best-effort

        return cors_headers(web.json_response({'ok': True, 'had_auth': had_auth}))
    except Exception as e:
        return cors_headers(web.json_response({'error': str(e)}, status=500))


# ── GET /alarms/counts ────────────────────────────────────────────────────────

async def get_alarm_counts(request):
    """How many logged-in users currently match each alarm rule (enabled or not).
    Read-only preview — sends nothing, never touches the snapshot. Cached in the
    engine for a few minutes; ?force=1 recomputes now. Used by the panel's
    «Алармы» tab to show the audience size of every trigger before it's armed."""
    force = request.rel_url.query.get('force', '').lower() in ('1', 'true', 'yes')
    try:
        from bot.utils import alarms
        data = await alarms.count_matches(force=force)
        return cors_headers(web.json_response(data))
    except Exception as e:
        return cors_headers(web.json_response({'error': str(e)}, status=500))


# ── Mini App: partner stats (reads ONLY the wl_admon mirror) ─────────────────

async def _resolve_partner(tg_user_id: int):
    """tg id → (email from user_auth) → wl_admon user id. Returns (uid, email)
    or (None, error_response)."""
    auth = await asyncio.to_thread(lambda: DB.UserAuth.select(tg_user_id))
    email = (getattr(auth, 'email', '') or '').strip().lower() if auth else ''
    if not email:
        return None, cors_headers(web.json_response({'error': 'not_authorized'}, status=404))
    from bot.integrations.winline import db_admon
    profile = await db_admon.get_user_by_email(email)
    if not profile or not profile.get('id'):
        return None, cors_headers(web.json_response({'error': 'not_in_mirror'}, status=404))
    return {'uid': int(profile['id']), 'email': email}, None


async def miniapp_stats_summary(request):
    """GET /miniapp/stats/summary?tg_user_id= — totals for yesterday / last
    calendar week / last calendar month (same period logic the bot shows)."""
    try:
        tg_user_id = int(request.rel_url.query.get('tg_user_id') or 0)
    except ValueError:
        tg_user_id = 0
    if not tg_user_id:
        return cors_headers(web.json_response({'error': 'tg_user_id required'}, status=400))

    who, err = await _resolve_partner(tg_user_id)
    if err:
        return err

    from bot.integrations.winline import db_admon
    from bot.integrations.winline.api import get_period_range

    periods = {}
    labels = {}
    names = ('yesterday', 'week', 'month')
    ranges = {}
    for p in names:
        start_iso, end_iso, label = get_period_range(p)
        ranges[p] = (start_iso, end_iso)
        labels[p] = label
    results = await asyncio.gather(
        *(db_admon.get_user_stats(who['uid'], *ranges[p]) for p in names),
        return_exceptions=True,
    )
    for p, r in zip(names, results):
        periods[p] = r if isinstance(r, dict) else None

    return cors_headers(web.json_response({
        'email': who['email'],
        'periods': periods,
        'labels': labels,
    }))


async def miniapp_stats_daily(request):
    """GET /miniapp/stats/daily?tg_user_id=&start=YYYY-MM-DD&end=YYYY-MM-DD —
    dense per-day series (≤92 days) + totals computed by the same rules."""
    q = request.rel_url.query
    try:
        tg_user_id = int(q.get('tg_user_id') or 0)
    except ValueError:
        tg_user_id = 0
    start = (q.get('start') or '')[:10]
    end = (q.get('end') or '')[:10]
    if not tg_user_id or not start or not end:
        return cors_headers(web.json_response({'error': 'tg_user_id, start, end required'}, status=400))

    from datetime import date as _d
    try:
        sd, ed = _d.fromisoformat(start), _d.fromisoformat(end)
    except ValueError:
        return cors_headers(web.json_response({'error': 'bad dates'}, status=400))
    if ed < sd:
        return cors_headers(web.json_response({'error': 'end before start'}, status=400))
    if (ed - sd).days > 92:
        return cors_headers(web.json_response({'error': 'range too long (max 92 days)'}, status=400))

    who, err = await _resolve_partner(tg_user_id)
    if err:
        return err

    from bot.integrations.winline import db_admon
    days, totals = await asyncio.gather(
        db_admon.get_user_stats_daily(who['uid'], start, end),
        db_admon.get_user_stats(who['uid'], start, end),
    )
    return cors_headers(web.json_response({
        'email': who['email'],
        'days': days or [],
        'totals': totals or {},
    }))


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

    try:
        async with _telegram_session(timeout_sec=60) as session:
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
    app.router.add_post('/logout', logout_user)
    app.router.add_get('/reload-texts', reload_texts)
    app.router.add_get('/alarms/counts', get_alarm_counts)
    app.router.add_get('/miniapp/stats/summary', miniapp_stats_summary)
    app.router.add_get('/miniapp/stats/daily', miniapp_stats_daily)
    app.router.add_post('/event/merch-given', event_merch_given)
    app.router.add_post('/telegram/relay', telegram_relay)
    return app


if __name__ == '__main__':
    print('[admin_api] Starting on http://127.0.0.1:5050')
    web.run_app(make_app(), host='0.0.0.0', port=5050, print=None)
