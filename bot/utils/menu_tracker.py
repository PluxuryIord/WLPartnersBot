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


async def track(action: str) -> None:
    """Increment the counter for a main-menu action. No-op for any other callback."""
    label = MENU_ACTIONS.get(action)
    if not label:
        return
    try:
        await asyncio.to_thread(_increment, action, label)
    except Exception as e:
        logger.warning(f'[menu_tracker] increment failed for {action}: {e}')
