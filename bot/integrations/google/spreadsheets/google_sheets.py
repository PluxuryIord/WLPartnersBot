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
ANKETA_COL_MAP = {
    'role': 4,
    'company': 5,
    'traffic_type': 6,
    'position': 7,
    'occupation': 8,
}


def _get_or_create_answers_worksheet():
    """Get or create the 'Ответы анкеты' worksheet."""
    try:
        ws = sh.worksheet('Ответы анкеты')
        # Ensure header is up to date
        ws.update('A1:I1', [ANKETA_HEADER])
        return ws
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title='Ответы анкеты', rows=10000, cols=15)
        ws.update('A1:I1', [ANKETA_HEADER])
        ws.format('A1:I1', {'textFormat': {'bold': True}})
        return ws


async def new_answers(user_id: str, full_name: str, username: str, answers: dict):
    """
    Save anketa answers to Google Sheets.
    answers: dict of {answerKey: value}, e.g. {'role': 'Трафик', 'company': 'Acme', 'traffic_type': 'Gambling'}
    Columns are fixed — empty cells for keys not in this branch.
    """
    try:
        ws = _get_or_create_answers_worksheet()

        # Find next empty row
        col_b = ws.col_values(2)  # User ID column
        empty_line = len(col_b) + 1

        # Build row with fixed 9 columns
        row = [''] * len(ANKETA_HEADER)
        row[0] = dt.now()
        row[1] = str(user_id)
        row[2] = full_name or 'Нет'
        row[3] = username if username else 'Нет'

        for key, value in answers.items():
            col_idx = ANKETA_COL_MAP.get(key)
            if col_idx is not None:
                row[col_idx] = value

        ws.update(f'A{empty_line}:I{empty_line}', [row])
    except Exception as e:
        print(f'[google_sheets] Ошибка записи ответов анкеты: {e}')