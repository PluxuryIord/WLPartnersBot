"""Counts clicks on the authorised main-menu buttons, by stable callback action.

The visible button text is dynamic (admin renames it in scenarios), but the
callback action stays constant — so we count by action and keep a default label.

Storage: sidecar table `wl_menu_clicks` (the bot DB user has CREATE but not
ALTER, so a new table is the safe pattern). URL buttons (e.g. «Чат с менеджером»)
are NOT trackable — Telegram never sends a callback for them.
"""
import asyncio
import logging

from bot.integrations.database.connection import mysql_engine

logger = logging.getLogger('wl_bot')

# Stable callback action → default readable label (authorised main menu).
MENU_ACTIONS = {
    'client_my_stats': '📊 Моя статистика',
    'client_knowledge_base': 'База знаний',
    'client_ask_ai': '❓ Спросить ИИ',
    'client_offers': 'Информация по офферу',
    'client_promo': 'Актуальные крео и лендинги',
    'client_socials': 'Наши соц. сети',
    'client_calendar': '📅 Календарь мероприятий',
    'client_show_my_qr': 'Показать мой QR код',
    'client_logout': '🚪 Выйти из аккаунта',
    'admin_menu': '⚙️ Меню администратора',
}


def _ensure_table():
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS wl_menu_clicks ("
            "  action VARCHAR(64) NOT NULL PRIMARY KEY,"
            "  label VARCHAR(128),"
            "  clicks INT NOT NULL DEFAULT 0,"
            "  updated_at DATETIME"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
        conn.commit()
    finally:
        conn.close()


try:
    _ensure_table()
except Exception as e:
    logger.warning(f'[menu_tracker] ensure table failed: {e}')


def _increment(action: str, label: str):
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO wl_menu_clicks (action, label, clicks, updated_at) "
            "VALUES (%s, %s, 1, NOW()) "
            "ON DUPLICATE KEY UPDATE clicks = clicks + 1, label = VALUES(label), updated_at = NOW()",
            (action, label),
        )
        conn.commit()
    finally:
        conn.close()


def _live_menu_map() -> dict:
    """{action: label} for the buttons CURRENTLY in the main_menu scenario.

    The menu is admin-editable, so we read the live (cached) scenario instead of
    trusting a hardcoded list — that way new/renamed buttons are tracked too.
    Reads only the warm cache (no DB on the hot path); empty → caller falls back
    to MENU_ACTIONS. url: buttons are skipped (Telegram sends no callback)."""
    try:
        from bot.utils import dynamic_kb
        data = dynamic_kb._cache.get('data')
        if not data:
            return {}
        screen = (data.get('screens') or {}).get('main_menu')
        if not screen or not screen.get('buttons'):
            return {}
        out = {}
        for key, btn in screen['buttons'].items():
            if key == '_order' or not isinstance(btn, dict):
                continue
            action = (btn.get('action') or '').strip()
            if not action or action.startswith('url:'):
                continue
            if action.startswith('callback:'):
                action = action[9:]
            out[action] = (btn.get('label') or action).strip()
        return out
    except Exception:
        return {}


async def track(action: str) -> None:
    """Increment the counter for a main-menu button. No-op for any other callback.
    Uses the LIVE main_menu scenario (so all current buttons count), falling back
    to the hardcoded MENU_ACTIONS when the scenario isn't loaded."""
    actions = _live_menu_map() or MENU_ACTIONS
    label = actions.get(action)
    if not label:
        return
    try:
        await asyncio.to_thread(_increment, action, label)
    except Exception as e:
        logger.warning(f'[menu_tracker] increment failed for {action}: {e}')
