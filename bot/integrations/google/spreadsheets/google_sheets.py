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
# Fixed columns: all possible answer keys across all branches
ANKETA_HEADER = ['Дата', 'User ID', 'ФИО', 'Username', 'Роль', 'Компания', 'Категория трафика', 'Должность', 'Род деятельности']
# answerKey → column index (0-based)
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


async def new_answers(user_id: str, full_name: str, username: str, answers: dict):
    """
    Save anketa answers to Google Sheets.
    answers: dict of {answerKey: value}, e.g. {'role': 'Трафик', 'company': 'Acme', 'traffic_type': 'Gambling'}
    Writes to the active sheet (set via admin panel). If no sheet — skips.
    """
    try:
        sheet_name = _get_active_sheet_name()
        if not sheet_name:
            print('[google_sheets] Нет активного листа анкеты — пропускаю запись')
            return

        ws = sh.worksheet(sheet_name)

        # Read header row to build dynamic column map
        header = ws.row_values(1)
        col_map = {}
        for i, h in enumerate(header):
            if i >= ANKETA_BASE_COLS and h:
                col_map[h] = i  # answerKey name → column index

        # Find next empty row
        col_b = ws.col_values(2)  # User ID column
        empty_line = len(col_b) + 1

        # Build row
        row = [''] * len(header)
        row[0] = dt.now()
        row[1] = str(user_id)
        row[2] = full_name or 'Нет'
        row[3] = username if username else 'Нет'

        for key, value in answers.items():
            col_idx = col_map.get(key)
            if col_idx is not None:
                row[col_idx] = value

        end_col = chr(ord('A') + len(row) - 1) if len(row) <= 26 else 'Z'
        ws.update(f'A{empty_line}:{end_col}{empty_line}', [row])
    except Exception as e:
        print(f'[google_sheets] Ошибка записи ответов анкеты: {e}')