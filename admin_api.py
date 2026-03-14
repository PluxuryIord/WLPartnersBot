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

# Add bot root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.integrations import DB  # noqa: E402

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.name == 'nt':
    PYTHON_BIN = os.path.join(BOT_DIR, 'venv', 'Scripts', 'python.exe')
else:
    PYTHON_BIN = os.path.join(BOT_DIR, 'venv', 'bin', 'python3')

STATUS_MAP = {0: 'draft', 1: 'sending', 201: 'published'}


def cors_headers(response: web.Response) -> web.Response:
    response.headers['Access-Control-Allow-Origin'] = '*'
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


IAP_DOMAIN = 'https://iap-demo.admon.pro'


# ── POST /auth ───────────────────────────────────────────────────────────────

async def auth_user(request):
    try:
        body = await request.json()
    except Exception:
        return cors_headers(web.json_response({'error': 'Invalid JSON'}, status=400))

    email = (body.get('email') or '').strip().lower()
    password = body.get('password') or ''
    user_id = body.get('user_id')

    if not email or not password or not user_id:
        return cors_headers(web.json_response({'error': 'email, password and user_id are required'}, status=400))

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return cors_headers(web.json_response({'error': 'Invalid user_id'}, status=400))

    # Proxy auth request to IAP API (server-side, no CORS issues)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{IAP_DOMAIN}/api/auth',
                json={'email': email, 'password': password},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    token = result.get('token', '')

                    def _save_auth():
                        existing = DB.UserAuth.select(user_id)
                        if existing:
                            DB.UserAuth.update(user_id, email=email, token=token)
                        else:
                            DB.UserAuth.add(user_id, email, token)

                    await asyncio.to_thread(_save_auth)

                    return cors_headers(web.json_response({'ok': True}))
                else:
                    return cors_headers(web.json_response(
                        {'error': 'Неверный email или пароль'}, status=401))
    except aiohttp.ClientError:
        return cors_headers(web.json_response(
            {'error': 'Ошибка подключения к платформе'}, status=502))


# ── App setup ────────────────────────────────────────────────────────────────

def make_app():
    app = web.Application()
    app.router.add_route('OPTIONS', '/{path_info:.*}', preflight)
    app.router.add_get('/users/count', get_users_count)
    app.router.add_get('/broadcasts', get_broadcasts)
    app.router.add_post('/broadcasts', send_broadcast)
    app.router.add_post('/auth', auth_user)
    return app


if __name__ == '__main__':
    print('[admin_api] Starting on http://127.0.0.1:5050')
    web.run_app(make_app(), host='127.0.0.1', port=5050, print=None)
