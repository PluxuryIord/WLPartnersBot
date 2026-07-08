"""Partner status tags — auto-segmentation of the panel's user tags.

Replaces the single «Партнёр» tag with five mutually-exclusive status tags,
computed from the wl_admon mirror (user status + website statuses):

  Партнёр действующий      ≥1 active website (status=1)
  Партнёр на модерации     ≥1 website on moderation (status=2) and none active
  Партнёр не активный      has websites, but none active/on-moderation
                           (all rejected/blocked), user himself active
  Партнёр заблокированный  admon user status != 1 (platform-blocked)
  Партнёр без площадки     registered in admon, zero websites

Audience = everyone with a user_auth row (logged into the bot / mini app).
Tags live in the panel's wl_admin_user_tags; the legacy «Партнёр» tag is
removed on retag. Runs: on login (client_main / event_v2 / admin_api /auth),
on a schedule (PARTNER_TAGS_INTERVAL_SEC, mirror refreshes every ~10 min),
and manually via /retag_partners.

Reads ONLY the wl_admon mirror (never the live API) — same rule as alarms.
"""
from __future__ import annotations

import os
import asyncio
import logging

from bot.integrations.database.connection import mysql_engine
from bot.integrations.winline import db_admon

logger = logging.getLogger('wl_bot')

PARTNER_TAGS_ENABLED = (os.getenv('PARTNER_TAGS_ENABLED', 'True').strip().lower()
                        in ('1', 'true', 'yes', 'on'))
PARTNER_TAGS_INTERVAL_SEC = int(os.getenv('PARTNER_TAGS_INTERVAL_SEC', '1800') or 1800)

TAG_ACTIVE = 'Партнёр действующий'
TAG_MODERATION = 'Партнёр на модерации'
TAG_INACTIVE = 'Партнёр не активный'
TAG_BLOCKED = 'Партнёр заблокированный'
TAG_NO_SITE = 'Партнёр без площадки'

STATUS_TAGS = [TAG_ACTIVE, TAG_MODERATION, TAG_INACTIVE, TAG_BLOCKED, TAG_NO_SITE]
LEGACY_TAG = 'Партнёр'
_MANAGED = STATUS_TAGS + [LEGACY_TAG]


def compute_tag(profile: dict | None, sites: list[dict] | None) -> str | None:
    """Status tag for a partner. None → couldn't classify (e.g. not in mirror)."""
    if not profile:
        return None
    status = profile.get('status')
    if status is not None and int(status or 0) != 1:
        return TAG_BLOCKED
    sites = sites or []
    if not sites:
        return TAG_NO_SITE
    st = {int(s.get('status') or 0) for s in sites}
    if 1 in st:
        return TAG_ACTIVE
    if 2 in st:
        return TAG_MODERATION
    return TAG_INACTIVE


# ─── blocking SQL (short-lived connections via asyncio.to_thread) ─────────────

def _q_audience() -> list[tuple[int, str]]:
    """(telegram_id, email) for everyone logged in — incl. users who blocked
    the bot (their partner status still matters for panel segments)."""
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, email FROM user_auth "
                    "WHERE email IS NOT NULL AND email <> ''")
        return [(int(r[0]), str(r[1]).strip().lower()) for r in cur.fetchall() if r[0] and r[1]]
    finally:
        conn.close()


def _q_current_tag(user_id: int) -> str | None:
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        placeholders = ','.join(['%s'] * len(STATUS_TAGS))
        cur.execute(
            f"SELECT tag FROM wl_admin_user_tags WHERE user_id=%s AND tag IN ({placeholders}) LIMIT 1",
            (user_id, *STATUS_TAGS),
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _q_apply_tag(user_id: int, tag: str) -> None:
    """Set the status tag exclusively: drop other managed tags (incl. legacy
    «Партнёр»), insert the new one."""
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        placeholders = ','.join(['%s'] * len(_MANAGED))
        cur.execute(
            f"DELETE FROM wl_admin_user_tags WHERE user_id=%s AND tag IN ({placeholders}) AND tag<>%s",
            (user_id, *_MANAGED, tag),
        )
        cur.execute(
            "INSERT IGNORE INTO wl_admin_user_tags (user_id, tag) VALUES (%s, %s)",
            (user_id, tag),
        )
        conn.commit()
    finally:
        conn.close()


# ─── per-user retag ───────────────────────────────────────────────────────────

async def retag_user(telegram_id: int, email: str) -> tuple[str | None, bool]:
    """Compute + apply the status tag for one user. Returns (tag, changed).
    Mirror-only; a user missing from the mirror keeps whatever tags they have
    (no destructive cleanup on data gaps)."""
    profile = await db_admon.get_user_by_email(email)
    if not profile:
        return None, False
    sites = []
    if profile.get('id'):
        sites = (await db_admon.get_user_websites(int(profile['id']))) or []
    tag = compute_tag(profile, sites)
    if not tag:
        return None, False
    current = await asyncio.to_thread(_q_current_tag, telegram_id)
    # Apply in both cases — even when unchanged it sweeps a lingering legacy
    # «Партнёр» tag; the write is idempotent (DELETE others + INSERT IGNORE).
    await asyncio.to_thread(_q_apply_tag, telegram_id, tag)
    return tag, current != tag


async def retag_after_login(telegram_id: int, email: str) -> None:
    """Best-effort hook for auth flows — never raises."""
    try:
        tag, _ = await retag_user(telegram_id, email)
        if tag:
            logger.info(f'[partner_tags] login retag tg={telegram_id} → {tag}')
    except Exception as e:
        logger.warning(f'[partner_tags] login retag failed tg={telegram_id}: {e}')


# ─── full pass ────────────────────────────────────────────────────────────────

async def run_retag_pass(concurrency: int = 8) -> dict:
    """Walk the whole logged-in audience and sync status tags.
    Returns counters for the admin command / logs."""
    audience = await asyncio.to_thread(_q_audience)
    counters = {'users': len(audience), 'tagged': 0, 'changed': 0, 'skipped_no_mirror': 0,
                'by_tag': {t: 0 for t in STATUS_TAGS}, 'errors': 0}
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(tg_id: int, email: str):
        async with sem:
            try:
                tag, changed = await retag_user(tg_id, email)
                if tag is None:
                    counters['skipped_no_mirror'] += 1
                    return
                counters['tagged'] += 1
                counters['by_tag'][tag] += 1
                if changed:
                    counters['changed'] += 1
            except Exception as e:
                counters['errors'] += 1
                logger.warning(f'[partner_tags] retag failed tg={tg_id}: {e}')

    await asyncio.gather(*(one(tg, em) for tg, em in audience))
    logger.warning(f'[partner_tags] pass done: {counters}')
    return counters


async def scheduled_retag() -> None:
    """apscheduler entrypoint. No-op unless enabled."""
    if not PARTNER_TAGS_ENABLED:
        return
    try:
        await run_retag_pass()
    except Exception as e:
        logger.warning(f'[partner_tags] scheduled pass crashed: {e}')
