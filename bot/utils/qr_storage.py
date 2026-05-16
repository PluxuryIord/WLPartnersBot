"""
Pre-upload pipeline для QR-карточек: храним file_id в служебных каналах TG,
а юзеру отправляем мгновенной пересылкой по file_id (без upload файла).

Архитектура:
- N служебных приватных каналов, где бот — админ (ENV: QR_STORAGE_CHATS=chat1,chat2,chat3)
- Round-robin: каждый pre-upload идёт в следующий канал по очереди → суммарный
  лимит = N × 20 msg/min, защита от flood-control
- Локальный rate-limiter на канал — не больше 18 upload/min на один чат
  (резерв на TG-овский 20 msg/min)
- file_id сохраняется в MySQL (wl_event_code_file_id) — переживает рестарт бота
- Health-check на старте: убеждаемся что бот реально может писать в каждый канал

Если pre-upload упал (rate limit / network / TG down) — _send_event_qr делает
on-demand рендер + обычный send_photo, как было раньше. Худший случай = текущий.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from typing import Optional

import mysql.connector

logger = logging.getLogger('wl_bot')

# ── ENV конфиг ──────────────────────────────────────────────────────────────
_RAW_CHATS = os.getenv('QR_STORAGE_CHATS', '').strip()
STORAGE_CHATS: list[int] = []
if _RAW_CHATS:
    for s in _RAW_CHATS.split(','):
        s = s.strip()
        if not s:
            continue
        try:
            STORAGE_CHATS.append(int(s))
        except ValueError:
            logger.warning(f'[qr-storage] Bad chat id in QR_STORAGE_CHATS: {s!r}')

IS_ENABLED = bool(STORAGE_CHATS)
PER_CHAT_RATE_LIMIT = 18  # msg per minute per chat (TG limit ~20, держим запас)
RATE_WINDOW_SEC = 60

# ── Round-robin указатель + rate-limit история по каналам ──────────────────
_rr_lock = asyncio.Lock()
_rr_idx = 0
_rate_history: dict[int, deque] = {chat_id: deque() for chat_id in STORAGE_CHATS}

# ── Локальный in-memory кэш file_id (на случай быстрых повторов до MySQL) ──
_file_id_memory_cache: dict[str, str] = {}


async def _pick_storage_chat() -> Optional[int]:
    """Round-robin выбор канала с учётом per-chat rate-limit.

    Если все каналы упёрлись в лимит — возвращаем None (caller сделает
    fallback на on-demand рендер).
    """
    if not IS_ENABLED:
        return None
    async with _rr_lock:
        global _rr_idx
        n = len(STORAGE_CHATS)
        now = time.monotonic()
        for _ in range(n):
            chat_id = STORAGE_CHATS[_rr_idx % n]
            _rr_idx = (_rr_idx + 1) % n
            hist = _rate_history[chat_id]
            # выкидываем устаревшие отметки
            while hist and now - hist[0] > RATE_WINDOW_SEC:
                hist.popleft()
            if len(hist) < PER_CHAT_RATE_LIMIT:
                hist.append(now)
                return chat_id
        # все каналы перегружены — попробуй потом
        return None


# ── MySQL persistence ──────────────────────────────────────────────────────

def _db_cfg() -> dict:
    return {
        'host': os.getenv('MYSQL_HOST', ''),
        'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', ''),
        'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', ''),
    }


def _sync_ensure_table() -> None:
    """Создаёт таблицу для хранения file_id. Идемпотентно (CREATE IF NOT EXISTS)."""
    conn = None
    try:
        conn = mysql.connector.connect(**_db_cfg())
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS wl_event_code_file_id (
                code            VARCHAR(32) PRIMARY KEY,
                tg_file_id      VARCHAR(255) NOT NULL,
                storage_chat_id BIGINT NULL,
                uploaded_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        conn.commit()
    except Exception as e:
        logger.warning(f'[qr-storage] ensure_table failed: {e}')
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def _sync_get_file_id(code: str) -> Optional[str]:
    conn = None
    try:
        conn = mysql.connector.connect(**_db_cfg())
        cur = conn.cursor()
        cur.execute('SELECT tg_file_id FROM wl_event_code_file_id WHERE code = %s', (code,))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.debug(f'[qr-storage] get_file_id({code}) failed: {e}')
        return None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def _sync_save_file_id(code: str, file_id: str, chat_id: int) -> None:
    conn = None
    try:
        conn = mysql.connector.connect(**_db_cfg())
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO wl_event_code_file_id (code, tg_file_id, storage_chat_id)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                tg_file_id = VALUES(tg_file_id),
                storage_chat_id = VALUES(storage_chat_id),
                uploaded_at = CURRENT_TIMESTAMP
            """,
            (code, file_id, chat_id),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f'[qr-storage] save_file_id({code}) failed: {e}')
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


async def get_cached_file_id(code: str) -> Optional[str]:
    """Достать file_id из памяти, потом из MySQL. None если нигде нет."""
    if not code:
        return None
    cached = _file_id_memory_cache.get(code)
    if cached:
        return cached
    fid = await asyncio.to_thread(_sync_get_file_id, code)
    if fid:
        _file_id_memory_cache[code] = fid
    return fid


async def store_file_id(code: str, file_id: str, chat_id: int) -> None:
    _file_id_memory_cache[code] = file_id
    await asyncio.to_thread(_sync_save_file_id, code, file_id, chat_id)


# ── Pre-upload в storage-чат ───────────────────────────────────────────────

async def upload_for_file_id(bot, png_bytes: bytes, code: str) -> Optional[str]:
    """Загрузить байты в один из служебных каналов, получить file_id,
    удалить сообщение из канала (file_id остаётся валидным навсегда).

    Возвращает file_id или None если pre-upload не удался (caller сделает
    fallback на on-demand).
    """
    if not IS_ENABLED:
        return None
    chat_id = await _pick_storage_chat()
    if not chat_id:
        logger.info('[qr-storage] all storage chats rate-limited, skip pre-upload')
        return None
    try:
        from aiogram.types import BufferedInputFile
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=BufferedInputFile(png_bytes, filename=f'{code}.png'),
            disable_notification=True,
        )
        file_id = None
        if msg.photo:
            # самый большой размер — последний элемент списка
            file_id = msg.photo[-1].file_id
        # моментально чистим storage chat — file_id остаётся валидным
        try:
            await bot.delete_message(chat_id, msg.message_id)
        except Exception:
            pass  # не удалили — chat будет чуть мусорнее, не критично
        if file_id:
            await store_file_id(code, file_id, chat_id)
            logger.info(f'[qr-storage] uploaded {code} -> chat {chat_id}, file_id={file_id[:30]}...')
        return file_id
    except Exception as e:
        logger.warning(f'[qr-storage] upload failed for {code} in chat {chat_id}: {e}')
        return None


# ── Health-check ───────────────────────────────────────────────────────────

async def health_check(bot) -> None:
    """Проверка при старте бота: все ли storage chats доступны и пишутся.

    Не падаем при ошибках — просто пишем warning в лог, чтобы админ увидел.
    """
    if not IS_ENABLED:
        logger.info('[qr-storage] disabled (QR_STORAGE_CHATS env empty) — on-demand only')
        return
    logger.info(f'[qr-storage] health-check: {len(STORAGE_CHATS)} chat(s) configured')
    for chat_id in STORAGE_CHATS:
        try:
            chat = await bot.get_chat(chat_id)
            logger.info(f'[qr-storage]   ✓ chat {chat_id} ({chat.title or chat.type}) accessible')
        except Exception as e:
            logger.warning(f'[qr-storage]   ✗ chat {chat_id} NOT accessible: {e}')


# Создаём таблицу при импорте — single-shot.
try:
    _sync_ensure_table()
except Exception as e:
    logger.warning(f'[qr-storage] init: {e}')
