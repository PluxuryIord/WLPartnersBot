"""
Knowledge-base AI assistant.

- Reads `knowledge_base` JSON from MySQL (cached for 5 min).
- Strips HTML tags into plain text and feeds the whole base to Claude Haiku.
- Logs every Q/A in `wl_ai_dialogs` for audit + per-user rate limiting.
- Uses Anthropic prompt caching for the system prompt + base, so repeat
  questions cost ~10% of first-time input.

Env: ANTHROPIC_API_KEY, MYSQL_*.
"""
import json
import os
import re
import time
import asyncio
from typing import Optional, Tuple

import mysql.connector
from anthropic import Anthropic

MODEL = 'claude-haiku-4-5-20251001'
MAX_DAILY_QUESTIONS = 20
KB_CACHE_TTL = 300  # 5 minutes

_client: Optional[Anthropic] = None
_kb_cache: dict = {'fetched_at': 0.0, 'text': '', 'titles': []}
_table_ready = False


# ─── infra ──────────────────────────────────────────────────────────────────
def _get_client() -> Optional[Anthropic]:
    global _client
    if _client is not None:
        return _client
    key = os.getenv('ANTHROPIC_API_KEY', '').strip()
    if not key:
        return None
    _client = Anthropic(api_key=key)
    return _client


def _connect():
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', ''),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        user=os.getenv('MYSQL_USER', ''),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DATABASE', ''),
    )


def _ensure_table():
    """Create wl_ai_dialogs table if not exists. Lazy, runs once per process."""
    global _table_ready
    if _table_ready:
        return
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS wl_ai_dialogs (
              id BIGINT AUTO_INCREMENT PRIMARY KEY,
              user_id BIGINT NOT NULL,
              question TEXT NOT NULL,
              answer MEDIUMTEXT,
              tokens_input INT DEFAULT 0,
              tokens_output INT DEFAULT 0,
              tokens_cache_read INT DEFAULT 0,
              tokens_cache_write INT DEFAULT 0,
              error VARCHAR(500) DEFAULT NULL,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              INDEX idx_user_created (user_id, created_at),
              INDEX idx_created (created_at)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """)
        conn.commit()
        cur.close()
        conn.close()
        _table_ready = True
    except Exception as e:
        print(f'[ai] ensure_table failed: {e}')


# ─── KB loading ─────────────────────────────────────────────────────────────
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_WHITESPACE_RE = re.compile(r'[ \t]+')
_NEWLINES_RE = re.compile(r'\n{3,}')


def _strip_html(html: str) -> str:
    if not html:
        return ''
    text = html.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
    text = text.replace('</p>', '\n').replace('</div>', '\n').replace('</li>', '\n')
    text = _HTML_TAG_RE.sub('', text)
    # Decode common HTML entities
    text = (text.replace('&nbsp;', ' ')
                .replace('&amp;', '&')
                .replace('&lt;', '<')
                .replace('&gt;', '>')
                .replace('&quot;', '"')
                .replace('&#39;', "'"))
    text = _WHITESPACE_RE.sub(' ', text)
    text = _NEWLINES_RE.sub('\n\n', text)
    return text.strip()


def _load_kb_text() -> Tuple[str, list]:
    """Read knowledge_base JSON, return (formatted_plain_text, [titles])."""
    now = time.time()
    if now - _kb_cache['fetched_at'] < KB_CACHE_TTL and _kb_cache['text']:
        return _kb_cache['text'], _kb_cache['titles']

    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT data FROM texts WHERE category = 'knowledge_base' LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return '', []
        data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except Exception as e:
        print(f'[ai] load KB failed: {e}')
        return _kb_cache['text'], _kb_cache['titles']

    meta = data.get('_meta') or {}
    order = meta.get('order') or [k for k in data.keys() if not k.startswith('_') and not k.endswith('_photo') and not k.endswith('_s3')]
    titles = meta.get('titles') or {}

    parts = []
    title_list = []
    for key in order:
        content = data.get(key)
        if not content:
            continue
        title = titles.get(key, key)
        plain = _strip_html(str(content))
        if not plain:
            continue
        parts.append(f'## {title}\n{plain}')
        title_list.append(title)

    text = '\n\n'.join(parts)
    _kb_cache['fetched_at'] = now
    _kb_cache['text'] = text
    _kb_cache['titles'] = title_list
    return text, title_list


# ─── rate limiting ──────────────────────────────────────────────────────────
def get_remaining_questions(user_id: int) -> int:
    """How many questions user can still ask in next 24h. Negative on error → allow."""
    _ensure_table()
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM wl_ai_dialogs "
            "WHERE user_id = %s AND created_at >= NOW() - INTERVAL 1 DAY AND error IS NULL",
            (user_id,),
        )
        used = cur.fetchone()[0]
        cur.close()
        conn.close()
        return max(0, MAX_DAILY_QUESTIONS - int(used or 0))
    except Exception as e:
        print(f'[ai] rate-limit check failed: {e}')
        return MAX_DAILY_QUESTIONS  # fail-open


def _log_dialog(user_id: int, question: str, answer: Optional[str],
                in_tok: int, out_tok: int, cache_r: int, cache_w: int,
                error: Optional[str] = None):
    _ensure_table()
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO wl_ai_dialogs "
            "(user_id, question, answer, tokens_input, tokens_output, "
            "tokens_cache_read, tokens_cache_write, error) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (user_id, question[:4000], (answer or '')[:8000],
             in_tok, out_tok, cache_r, cache_w, error[:500] if error else None),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f'[ai] log_dialog failed: {e}')


# ─── main entry ─────────────────────────────────────────────────────────────
SYSTEM_TEMPLATE = (
    'Ты — ассистент партнёрской программы Winline. '
    'Отвечай на вопросы пользователя СТРОГО на основе предоставленной базы знаний. '
    'Если в базе нет нужной информации — честно скажи: '
    '"К сожалению, в базе знаний нет ответа на этот вопрос. Обратитесь к менеджеру: @winline_affiliate". '
    'Не выдумывай факты. Не отвечай на вопросы вне темы партнёрки. '
    'Отвечай на русском, кратко и по делу. Можешь использовать форматирование Telegram HTML: '
    '<b>жирный</b>, <i>курсив</i>, <code>код</code>, переносы строк.\n\n'
    'БАЗА ЗНАНИЙ:\n'
)


async def ask(user_id: int, question: str) -> Tuple[bool, str]:
    """
    Returns (ok, text).
    ok=False → text is a user-facing error message.
    """
    client = _get_client()
    if not client:
        return False, '⚠️ ИИ-ассистент временно недоступен (нет ключа API).'

    question = (question or '').strip()
    if not question:
        return False, 'Пустой вопрос.'
    if len(question) > 1000:
        return False, 'Вопрос слишком длинный (максимум 1000 символов).'

    kb_text, _titles = _load_kb_text()
    if not kb_text:
        return False, '⚠️ База знаний пуста. Обратитесь к менеджеру: @winline_affiliate'

    system_blocks = [
        {
            'type': 'text',
            'text': SYSTEM_TEMPLATE + kb_text,
            'cache_control': {'type': 'ephemeral'},
        }
    ]

    def _call():
        return client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=system_blocks,
            messages=[{'role': 'user', 'content': question}],
        )

    try:
        resp = await asyncio.to_thread(_call)
    except Exception as e:
        msg = str(e)[:300]
        print(f'[ai] API error: {msg}')
        _log_dialog(user_id, question, None, 0, 0, 0, 0, error=msg)
        return False, '⚠️ Не удалось получить ответ от ИИ. Попробуйте позже.'

    answer = ''
    for block in resp.content:
        if getattr(block, 'type', '') == 'text':
            answer += block.text

    usage = resp.usage
    in_tok = getattr(usage, 'input_tokens', 0) or 0
    out_tok = getattr(usage, 'output_tokens', 0) or 0
    cache_r = getattr(usage, 'cache_read_input_tokens', 0) or 0
    cache_w = getattr(usage, 'cache_creation_input_tokens', 0) or 0

    _log_dialog(user_id, question, answer, in_tok, out_tok, cache_r, cache_w)
    return True, answer.strip() or 'Не удалось сформировать ответ.'
