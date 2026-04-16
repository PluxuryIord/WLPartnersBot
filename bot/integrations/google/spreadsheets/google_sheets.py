import gspread

from bot.utils import dt

gc = gspread.service_account(filename='bot/integrations/google/spreadsheets/creds/excel-365615-03e4325f8c64.json')
sh = gc.open_by_key('1wfqrdL30DicmCikX_PBaYHTxbEoJwA8wQgF2jQowA4A')
worksheet_users = sh.get_worksheet_by_id(0)
worksheet_prizes = sh.get_worksheet_by_id(1782648089)

async def new_user(user_id: str, full_name: str, username, role: str, traffic_type: str, rl_full_name: str, number: str):
    subs = worksheet_users.get('B2:B10000')
    empty_line = len(subs) + 2
    values = [[
        user_id,
        full_name,
        username if username else 'Нет',
        dt.now(),
        role,
        traffic_type,
        rl_full_name,
        number
    ]]
    worksheet_users.update(range_name=f'B{empty_line}:I{empty_line}', values=values)


async def new_prize(user_id: str, prize: str, qr_id: str):
    subs = worksheet_prizes.get('B2:B10000')
    empty_line = len(subs) + 2
    values = [[
        user_id,
        prize,
        dt.now(),
        qr_id
    ]]
    worksheet_prizes.update(range_name=f'B{empty_line}:E{empty_line}', values=values)


# ─── Лист для ответов анкеты ─────────────────────────────────────────────────
# Panel writes Russian screen titles as headers; bot maps answerKey → column
# by ORDER (reads bot_scenarios from the same MySQL as panel, filters scenario:5
# screens with answerKey, preserves iteration order — identical algorithm).
ANKETA_BASE_COLS = 4  # Дата, User ID, ФИО, Username


def _get_active_sheet_name():
    """Read active anketa sheet name from event_settings in DB."""
    import json, os, mysql.connector
    try:
        conn = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', ''), port=int(os.getenv('MYSQL_PORT', 3306)),
            user=os.getenv('MYSQL_USER', ''), password=os.getenv('MYSQL_PASSWORD', ''),
            database=os.getenv('MYSQL_DATABASE', ''),
        )
        cur = conn.cursor()
        cur.execute("SELECT data FROM texts WHERE category = 'event_settings' LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return data.get('anketa_active_sheet')
    except Exception as e:
        print(f'[google_sheets] Ошибка чтения active sheet: {e}')
    return None


def _get_anketa_answer_keys():
    """
    Read ordered list of answerKeys from bot_scenarios — same algorithm as panel's
    new-anketa-sheet endpoint. Bot uses this order to map answerKey → column index.
    """
    import json, os, mysql.connector
    try:
        conn = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', ''), port=int(os.getenv('MYSQL_PORT', 3306)),
            user=os.getenv('MYSQL_USER', ''), password=os.getenv('MYSQL_PASSWORD', ''),
            database=os.getenv('MYSQL_DATABASE', ''),
        )
        cur = conn.cursor()
        cur.execute("SELECT data FROM texts WHERE category = 'bot_scenarios' LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return []
        data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        screens = (data or {}).get('screens', {}) or {}
        keys = []
        seen = set()
        for s in screens.values():
            if s.get('scenario') == 5 and s.get('answerKey') and s['answerKey'] not in seen:
                seen.add(s['answerKey'])
                keys.append(s['answerKey'])
        return keys
    except Exception as e:
        print(f'[google_sheets] Ошибка чтения answerKeys: {e}')
        return []


def _col_letter(n: int) -> str:
    """1-based column number → A1 letter (A, B, ..., Z, AA, AB, ...)."""
    s = ''
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord('A') + r) + s
    return s


async def new_answers(user_id: str, full_name: str, username: str, answers: dict):
    """
    Save anketa answers to Google Sheets.
    answers: dict of {answerKey: value}, e.g. {'role': 'Трафик', 'company': 'Acme', 'traffic_type': 'Gambling'}
    Writes to the active sheet (set via admin panel). If no sheet — skips.
    Column mapping is by ORDER of answerKeys from bot_scenarios (not by header name),
    so Google Sheet can have human-readable Russian titles in header row.
    """
    try:
        sheet_name = _get_active_sheet_name()
        if not sheet_name:
            print('[google_sheets] Нет активного листа анкеты — пропускаю запись')
            return

        answer_keys = _get_anketa_answer_keys()
        if not answer_keys:
            print('[google_sheets] Нет answerKeys в bot_scenarios — пропускаю запись')
            return

        ws = sh.worksheet(sheet_name)

        # Find next empty row based on column B (User ID)
        col_b = ws.col_values(2)
        empty_line = len(col_b) + 1

        # Build row: base cols + answer cols in deterministic order
        total_cols = ANKETA_BASE_COLS + len(answer_keys)
        row = [''] * total_cols
        row[0] = dt.now()
        row[1] = str(user_id)
        row[2] = full_name or 'Нет'
        row[3] = username if username else 'Нет'

        for i, key in enumerate(answer_keys):
            val = answers.get(key, '')
            row[ANKETA_BASE_COLS + i] = val if val is not None else ''

        end_col = _col_letter(total_cols)
        ws.update(range_name=f'A{empty_line}:{end_col}{empty_line}', values=[row])
    except Exception as e:
        print(f'[google_sheets] Ошибка записи ответов анкеты: {e}')