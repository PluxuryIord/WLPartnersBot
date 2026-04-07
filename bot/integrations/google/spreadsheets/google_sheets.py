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
def _get_or_create_answers_worksheet():
    """Get or create the 'Ответы анкеты' worksheet."""
    try:
        return sh.worksheet('Ответы анкеты')
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title='Ответы анкеты', rows=10000, cols=30)
        ws.update('A1:E1', [['Дата', 'User ID', 'ФИО', 'Username', 'Вопрос → Ответ']])
        ws.format('A1:Z1', {'textFormat': {'bold': True}})
        return ws


async def new_answers(user_id: str, full_name: str, username: str, questions_answers: list[dict]):
    """
    Save anketa answers to Google Sheets.
    questions_answers: [{'question': str, 'answer': str}, ...]
    Each Q&A pair gets its own column after the base columns.
    """
    try:
        ws = _get_or_create_answers_worksheet()

        # Build header row dynamically if questions changed
        # Columns: Дата | User ID | ФИО | Username | Q1 | Q2 | Q3 | ...
        header = ['Дата', 'User ID', 'ФИО', 'Username']
        for qa in questions_answers:
            header.append(qa['question'])

        # Update header row (in case new questions were added)
        end_col = chr(ord('A') + len(header) - 1) if len(header) <= 26 else 'Z'
        ws.update(f'A1:{end_col}1', [header])

        # Find next empty row
        col_b = ws.col_values(2)  # User ID column
        empty_line = len(col_b) + 1

        # Build data row
        row = [
            dt.now(),
            str(user_id),
            full_name or 'Нет',
            username if username else 'Нет',
        ]
        for qa in questions_answers:
            row.append(qa['answer'])

        end_col = chr(ord('A') + len(row) - 1) if len(row) <= 26 else 'Z'
        ws.update(f'A{empty_line}:{end_col}{empty_line}', [row])
    except Exception as e:
        print(f'[google_sheets] Ошибка записи ответов анкеты: {e}')