"""
Локальная генерация QR-карточки прямо на сервере бота.

Зачем: раньше при каждом показе QR бот делал HTTP-запрос в админ-панель
(`/api/events/codes/{code}/qr-card`) — это ~1.5 сек на cold cache + ~100 мс
сетевого round-trip Копенгаген ↔ Москва. Перенос работы в локальный Python
с pillow сокращает время до ~150-300 мс и убирает зависимость от админки
(если она лежит — QR всё равно генерируется).

Ассеты (фон + шрифт) подтягиваются один раз при первом запросе с публичных
эндпоинтов админ-панели и кэшируются в памяти модуля навсегда. Template
~50KB, шрифт ~150KB — копейки.

API: единственная асинхронная функция `generate_qr_card_bytes(code, caption)`,
возвращает bytes PNG (lossless — острые края QR остаются чёткими как у
sharp на админ-панели). Тяжёлая работа pillow вынесена в thread pool.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from typing import Optional

import aiohttp
import qrcode
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger('wl_bot')

# ── Card layout — те же пропорции, что у админской карточки ───────────────
CARD_W = 530
CARD_H = 800
QR_SIZE = 320
QR_TOP = 200
QR_COLOR = (255, 106, 19)  # #FF6A13 — Winline orange
FONT_SIZE = 72
LINE_GAP = 16

# Source: same admin server that used to render the whole card.
ADMIN_BASE = (os.getenv('ADMIN_PANEL_BASE') or 'https://winlinepartners.ru').rstrip('/')
TEMPLATE_URL = f'{ADMIN_BASE}/api/events/assets/qr-template'
FONT_URL = f'{ADMIN_BASE}/api/events/assets/qr-font'

# ── Module-level cache. Loaded once, kept forever. ──────────────────────────
_template_bg: Optional[Image.Image] = None
_font: Optional[ImageFont.FreeTypeFont] = None
_init_lock = asyncio.Lock()


async def _http_get(url: str) -> bytes:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


async def _ensure_assets() -> None:
    """Lazy load template + font from admin once per bot process."""
    global _template_bg, _font
    if _template_bg is not None and _font is not None:
        return
    async with _init_lock:
        if _template_bg is None:
            try:
                buf = await _http_get(TEMPLATE_URL)
                img = Image.open(io.BytesIO(buf)).convert('RGBA')
                _template_bg = img.resize((CARD_W, CARD_H), Image.LANCZOS)
            except Exception as e:
                logger.warning(f'[qr-card] template fetch failed, using solid black: {e}')
                _template_bg = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 255))
        if _font is None:
            try:
                buf = await _http_get(FONT_URL)
                _font = ImageFont.truetype(io.BytesIO(buf), FONT_SIZE)
            except Exception as e:
                logger.warning(f'[qr-card] font fetch failed, using default: {e}')
                _font = ImageFont.load_default()


def _draw_centered_text(draw: ImageDraw.ImageDraw, text: str, y_top: int, font, fill='white') -> None:
    """Draw text centered horizontally, possibly multi-line."""
    if not text:
        return
    lines = text.split('\n')
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (CARD_W - w) // 2
        y = y_top + i * (FONT_SIZE + LINE_GAP)
        draw.text((x, y), line, font=font, fill=fill)


def _generate_sync(code: str, caption: str) -> bytes:
    """Heavy lifting — runs in a thread pool. Don't call directly from async code."""
    assert _template_bg is not None and _font is not None  # _ensure_assets ran

    # Copy bg to avoid mutating the cached image.
    bg = _template_bg.copy()

    # Generate QR (orange on transparent), resize, paste.
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=QR_COLOR, back_color=(0, 0, 0, 0)).convert('RGBA')
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.LANCZOS)
    bg.paste(qr_img, ((CARD_W - QR_SIZE) // 2, QR_TOP), qr_img)

    # Caption under the QR, centered vertically in the remaining space.
    if caption:
        draw = ImageDraw.Draw(bg)
        lines = caption.split('\n')
        line_h = FONT_SIZE + LINE_GAP
        text_block_h = len(lines) * line_h
        space_top = QR_TOP + QR_SIZE
        space_h = CARD_H - space_top
        text_top = space_top + max(0, (space_h - text_block_h) // 2)
        _draw_centered_text(draw, caption, text_top, _font)

    # PNG, lossless. Compression level 1 — самое быстрое сжатие, file ~2-3x
    # больше (~400-600 KB) но encode в 3-5x быстрее.
    out = io.BytesIO()
    bg.save(out, 'PNG', compress_level=1)
    return out.getvalue()


async def generate_qr_card_bytes(code: str, caption: str = '') -> bytes:
    """Public entry point. Returns PNG bytes ready for Telegram send_photo."""
    await _ensure_assets()
    return await asyncio.to_thread(_generate_sync, code, caption)


async def preload_assets() -> None:
    """Optional: call once at bot startup to avoid first-user latency."""
    try:
        await _ensure_assets()
    except Exception as e:
        logger.warning(f'[qr-card] preload failed (non-fatal): {e}')


# ── Pre-generated cards cache ───────────────────────────────────────────────
# Идея: когда юзер только-только заходит по deep-link
# (t.me/winline_partners_bot?start=event), мы в фоне выпускаем event_code и
# рендерим карточку. Пока юзер 30 секунд проходит интро и анкету, карточка
# уже готова и лежит в этом dict'е. В _send_event_qr делаем pop — отдаём
# мгновенно, без рендера. Если pre-gen не успел/упал — fallback на on-demand
# рендер сохранён.
_pregenerated_cards: dict = {}
_PREGEN_TTL_SEC = 3600  # 1 час, чтобы протухшие записи не копились


def cache_qr_card(code: str, data: bytes) -> None:
    """Положить уже отрендеренные байты в кэш под ключом event_code."""
    import time as _t
    _pregenerated_cards[code] = (_t.monotonic(), data)


def pop_qr_card(code: str) -> Optional[bytes]:
    """Достать байты из кэша, если есть и не протухли. Удаляет запись."""
    import time as _t
    entry = _pregenerated_cards.pop(code, None)
    if not entry:
        return None
    ts, data = entry
    if _t.monotonic() - ts > _PREGEN_TTL_SEC:
        return None
    return data


async def pregenerate_qr_card(code: str, caption: str = '') -> None:
    """Отрендерить карточку фоном.

    Двухуровневая стратегия:
      1) рендерим PNG локально (pillow)
      2) если включён pre-upload в служебные чаты (QR_STORAGE_CHATS) —
         загружаем туда, получаем file_id, сохраняем в MySQL.
         Дальше _send_event_qr отправит юзеру по file_id (мгновенно).
      3) ВНЕ зависимости от успеха upload'а, оставляем PNG в memory cache —
         если file_id не получили, на показе сработает on-demand fallback.

    Безопасна к ошибкам — любые сбои логируем, ничего не блокируем.
    """
    if not code:
        return
    if code in _pregenerated_cards:
        return  # уже отрендерено для этого кода — не дублируем работу
    try:
        data = await generate_qr_card_bytes(code, caption)
        cache_qr_card(code, data)
        logger.info(f'[qr-card] pregenerate ok: code={code} size={len(data)//1024}KB')
    except Exception as e:
        logger.warning(f'[qr-card] pregenerate failed for {code}: {e}')
        return

    # Параллельно: pre-upload в storage chat для получения file_id.
    # Делаем ПОСЛЕ рендера, в фоне, чтобы upload-задержка не блокировала
    # последующие _send_event_qr'ы которые могут попасть в memory cache.
    try:
        from bot.utils import qr_storage  # type: ignore
        from bot.utils.announce_bot import bot  # type: ignore
        await qr_storage.upload_for_file_id(bot, data, code)
    except Exception as e:
        logger.warning(f'[qr-card] storage upload failed for {code}: {e}')
