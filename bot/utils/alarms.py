"""Trigger-alarm engine.

Periodically walks the bot's logged-in audience (rows in `user_auth`), pulls
each partner's Winline profile + websites, and fires the no-code rules authored
in the admin panel (`wl_alarm_rules`). Six trigger types are supported — see
TRIGGER_TYPES below.

Data has no status-change timestamps, so website transitions (approved /
rejected / «moderation > N») are detected by diffing against our own snapshot
table `wl_alarm_site_state`. Sends are deduped via `wl_alarm_log` so each alarm
reaches a user at most once.

All DB access goes through asyncio.to_thread on short-lived raw connections
(same pattern as db_admon.py) so a long pass never blocks the bot's event loop.

Safety (env, all read at import):
  ALARMS_ENABLED        master kill-switch (default False — nothing runs).
  ALARMS_DRY_RUN        log who WOULD get what, send nothing (default True).
  ALARM_TEST_CHAT_ID    route every alarm to this chat instead of the partner.
  ALARM_THRESHOLD_SCALE multiply every time threshold (e.g. 0.0007 ≈ days→minutes
                        for testing; 1.0 = real).
  ALARM_INTERVAL_SEC    scheduler period (default 3600).
  ALARM_MAX_USERS       cap audience per pass (0 = no cap).
  ALARM_SEND_DELAY      seconds slept between users (default 0.05).

Dedup vs test: any test activity (dry-run OR a test-chat override) is logged
with dry_run=1, so it dedups against the test space only and never suppresses
the eventual production send (dry_run=0).
"""
from __future__ import annotations

import os
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from bot.integrations.database.connection import mysql_engine
from bot.integrations.winline.api import get_user_by_email, get_user_websites, get_user_stats
from bot.integrations.winline import api as _wl_api

logger = logging.getLogger('wl_bot')


# ─── env switches ───────────────────────────────────────────────────────────

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ('1', 'true', 'yes', 'on')


ALARMS_ENABLED = _env_bool('ALARMS_ENABLED', False)
ALARMS_DRY_RUN = _env_bool('ALARMS_DRY_RUN', True)
ALARM_TEST_CHAT_ID = int(os.getenv('ALARM_TEST_CHAT_ID', '0') or 0)
ALARM_THRESHOLD_SCALE = float(os.getenv('ALARM_THRESHOLD_SCALE', '1') or 1)
ALARM_INTERVAL_SEC = int(os.getenv('ALARM_INTERVAL_SEC', '3600') or 3600)
ALARM_MAX_USERS = int(os.getenv('ALARM_MAX_USERS', '0') or 0)
ALARM_SEND_DELAY = float(os.getenv('ALARM_SEND_DELAY', '0.05') or 0.05)


# ─── trigger catalog ──────────────────────────────────────────────────────────

TRIGGER_TYPES = [
    'email_unconfirmed',  # registered ≥ N days ago, email still not confirmed
    'no_site',            # registered ≥ N hours ago, no websites at all
    'site_moderation',    # a website stuck in status=2 longer than N hours
    'site_rejected',      # website just transitioned to status=3 (rejected)
    'site_approved',      # website just transitioned 2 → 1 (approved)
    'no_clicks',          # has an active website ≥ N hours, but 0 clicks
]

# Fallback texts used only if the panel rule has an empty message_text.
DEFAULT_TEXTS = {
    'email_unconfirmed': '⚠️ Подтвердите email, чтобы получать выплаты.',
    'no_site': '🚀 Создайте первую площадку, чтобы начать зарабатывать.',
    'site_moderation': '⏳ Ваша площадка на модерации. Менеджер скоро её рассмотрит.',
    'site_rejected': '❌ Площадка отклонена. Причина: {reason}. Поможем исправить — напишите в поддержку.',
    'site_approved': '🎉 Поздравляем! Площадка прошла модерацию и готова к работе.',
    'no_clicks': '📈 Запустите первый поток трафика на вашу площадку.',
}

_UNIT_SECONDS = {'days': 86400, 'hours': 3600, 'minutes': 60}


# ─── blocking SQL (own short-lived connection, run via asyncio.to_thread) ─────

def _q_load_rules() -> dict:
    """Read enabled rules from wl_alarm_rules (owned by the panel). Tolerates a
    missing table → {}. Returns {trigger_type: {threshold_seconds, message, buttons}}."""
    out: dict = {}
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT trigger_type, enabled, threshold_value, threshold_unit, "
            "message_text, buttons_json FROM wl_alarm_rules"
        )
        rows = cur.fetchall()
        cols = [c[0] for c in cur.description]
    except Exception as e:
        logger.warning(f'[alarms] load_rules failed (table missing?): {e}')
        return out
    finally:
        conn.close()

    for row in rows:
        r = dict(zip(cols, row))
        if not r.get('enabled'):
            continue
        tt = r.get('trigger_type')
        if tt not in TRIGGER_TYPES:
            continue
        unit = (r.get('threshold_unit') or 'hours')
        val = r.get('threshold_value')
        thr_seconds = None
        if val is not None:
            thr_seconds = float(val) * _UNIT_SECONDS.get(unit, 3600) * ALARM_THRESHOLD_SCALE
        buttons = []
        if r.get('buttons_json'):
            try:
                buttons = json.loads(r['buttons_json']) or []
            except Exception:
                buttons = []
        out[tt] = {
            'threshold_seconds': thr_seconds,
            'message': (r.get('message_text') or DEFAULT_TEXTS.get(tt, '')).strip(),
            'buttons': buttons,
        }
    return out


def _q_audience(limit: int = 0) -> list[tuple[int, str]]:
    """(telegram_id, winline_email) for everyone logged into the bot, skipping banned."""
    sql = (
        "SELECT a.user_id, a.email FROM user_auth a "
        "LEFT JOIN users u ON u.user_id = a.user_id "
        "WHERE a.email IS NOT NULL AND a.email <> '' "
        "AND (u.banned IS NULL OR u.banned = 0)"
    )
    if limit and limit > 0:
        sql += f" LIMIT {int(limit)}"
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        return [(int(r[0]), str(r[1]).strip().lower()) for r in cur.fetchall() if r[0] and r[1]]
    finally:
        conn.close()


def _q_already_sent(trigger_type: str, telegram_id: int, entity_key: str, log_flag: int) -> bool:
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM wl_alarm_log WHERE trigger_type=%s AND telegram_id=%s "
            "AND entity_key<=>%s AND dry_run=%s LIMIT 1",
            (trigger_type, telegram_id, entity_key, log_flag),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def _q_record(trigger_type: str, telegram_id: int, entity_key: str,
              log_flag: int, ok: int, preview: str) -> None:
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO wl_alarm_log (trigger_type, telegram_id, entity_key, dry_run, ok, message_preview) "
            "VALUES (%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE ok=VALUES(ok), message_preview=VALUES(message_preview), sent_at=NOW()",
            (trigger_type, telegram_id, entity_key, log_flag, ok, (preview or '')[:500]),
        )
        conn.commit()
    finally:
        conn.close()


def _q_get_states(website_ids: list[int]) -> dict:
    """{website_id: {'status', 'moderation_since'}} for the given ids."""
    if not website_ids:
        return {}
    placeholders = ','.join(['%s'] * len(website_ids))
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT website_id, status, moderation_since FROM wl_alarm_site_state "
            f"WHERE website_id IN ({placeholders})",
            tuple(website_ids),
        )
        return {int(r[0]): {'status': r[1], 'moderation_since': r[2]} for r in cur.fetchall()}
    finally:
        conn.close()


def _q_upsert_states(rows: list[tuple]) -> None:
    """rows: [(website_id, user_id, status, moderation_since), ...]"""
    if not rows:
        return
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO wl_alarm_site_state (website_id, user_id, status, moderation_since, updated_at) "
            "VALUES (%s,%s,%s,%s,NOW()) "
            "ON DUPLICATE KEY UPDATE user_id=VALUES(user_id), status=VALUES(status), "
            "moderation_since=VALUES(moderation_since), updated_at=NOW()",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


# ─── parsing helpers ──────────────────────────────────────────────────────────

def _parse_created(value) -> Optional[datetime]:
    """Winline `created` may be epoch ms, epoch seconds, or an ISO string.
    Return a tz-aware UTC datetime, or None if unparseable."""
    if value is None:
        return None
    try:
        s = str(value).strip()
        if not s:
            return None
        if s.replace('.', '', 1).isdigit():       # numeric → epoch
            v = float(s)
            if v > 1e12:                           # milliseconds
                v /= 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc)
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))  # ISO string
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _age_seconds(created) -> Optional[float]:
    dt = _parse_created(created)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _render(template: str, ctx: dict) -> str:
    out = template or ''
    for key in ('first_name', 'reason', 'site_name', 'site_url'):
        out = out.replace('{' + key + '}', str(ctx.get(key, '') or ''))
    return out


# ─── snapshot / transition detection ──────────────────────────────────────────

async def _process_site_snapshots(user_id, sites: list[dict]) -> dict:
    """Diff current website statuses against the snapshot. Returns:
       {'approved': [site...], 'rejected': [site...],
        'moderation_clock': {website_id: moderation_since_datetime}}
    Also updates the snapshot rows. First observation of a site is a baseline —
    no transition fires (prevents a flood on first deploy)."""
    res = {'approved': [], 'rejected': [], 'moderation_clock': {}}
    valid = []
    for site in sites:
        try:
            valid.append((int(site.get('id')), site))
        except (TypeError, ValueError):
            continue
    if not valid:
        return res

    prior = await asyncio.to_thread(_q_get_states, [wid for wid, _ in valid])
    now = datetime.now()
    upserts = []

    for wid, site in valid:
        status = site.get('status')
        p = prior.get(wid)

        if p is None:
            mod_since = now if status == 2 else None
        else:
            prev_status = p['status']
            prev_mod_since = p['moderation_since']
            mod_since = (prev_mod_since or now) if status == 2 else None
            if status != prev_status:
                if status == 1 and prev_status == 2:
                    res['approved'].append(site)
                if status == 3 and prev_status != 3:
                    res['rejected'].append(site)

        upserts.append((wid, user_id, status, mod_since))
        if status == 2:
            res['moderation_clock'][wid] = mod_since

    await asyncio.to_thread(_q_upsert_states, upserts)
    return res


# ─── sending ──────────────────────────────────────────────────────────────────

def _build_markup(buttons: list):
    if not buttons:
        return None
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        rows = []
        for b in buttons:
            txt = (b.get('text') or '').strip()
            url = (b.get('url') or '').strip()
            if txt and url:
                rows.append([InlineKeyboardButton(text=txt, url=url)])
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    except Exception as e:
        logger.warning(f'[alarms] markup build failed: {e}')
        return None


async def _maybe_send(bot, *, trigger_type: str, telegram_id: int, entity_key: str,
                      message: str, buttons: list, dry_run: bool, counters: dict) -> None:
    """Dedup-check, then send (unless dry-run) and log. entity_key/dedup are keyed
    on the real recipient even when routed to a test chat."""
    # Any test activity (dry-run OR test-chat routing) lives in the dry_run=1 space.
    is_test = dry_run or bool(ALARM_TEST_CHAT_ID)
    log_flag = 1 if is_test else 0

    if await asyncio.to_thread(_q_already_sent, trigger_type, telegram_id, entity_key, log_flag):
        counters['skipped_dedup'] += 1
        return

    chat_id = ALARM_TEST_CHAT_ID or telegram_id
    preview = (message or '')[:500]

    if dry_run:
        await asyncio.to_thread(_q_record, trigger_type, telegram_id, entity_key, log_flag, 1, preview)
        counters['dryrun'] += 1
        logger.info(f'[alarms] DRY {trigger_type} → tg={telegram_id} key={entity_key!r}')
        return

    try:
        await bot.send_message(chat_id, message, reply_markup=_build_markup(buttons))
        await asyncio.to_thread(_q_record, trigger_type, telegram_id, entity_key, log_flag, 1, preview)
        counters['sent'] += 1
    except Exception as e:
        # Failed sends are NOT recorded as done, so a transient error retries next pass.
        counters['failed'] += 1
        logger.warning(f'[alarms] send failed {trigger_type} → tg={telegram_id} chat={chat_id}: {e}')


async def _fetch_reject_reason(uid, email, website_id) -> str:
    """Rejection reason lives only in the live API (not in the db mirror)."""
    try:
        live = await _wl_api._get_user_websites_api(int(uid), email)
        for s in live or []:
            if str(s.get('id')) == str(website_id):
                return (s.get('rejectionReasonComment') or '').strip()
    except Exception as e:
        logger.warning(f'[alarms] reject-reason fetch failed wid={website_id}: {e}')
    return ''


async def _clicks_since(uid, created) -> int:
    """Total clicks from the site's creation date to today. Clicks data in the
    mirror is incomplete, so a 0 here can be a data gap — this trigger is the
    least reliable and is meant to be enabled deliberately. Returns -1 if unknown."""
    start = _parse_created(created) or (datetime.now(timezone.utc) - timedelta(days=90))
    start_iso = start.date().isoformat()
    end_iso = datetime.now(timezone.utc).date().isoformat()
    try:
        stats = await get_user_stats(int(uid), start_iso, end_iso)
        return int((stats or {}).get('clicks') or 0)
    except Exception as e:
        logger.warning(f'[alarms] clicks fetch failed uid={uid}: {e}')
        return -1


# ─── per-user evaluation ───────────────────────────────────────────────────────

async def _evaluate_user(bot, telegram_id: int, email: str, rules: dict,
                         dry_run: bool, counters: dict) -> None:
    profile = await get_user_by_email(email)
    if not profile:
        return
    uid = profile.get('id')
    first_name = profile.get('firstName') or ''
    created = profile.get('created')
    sites = (await get_user_websites(int(uid), email)) if uid else []
    sites = sites or []

    snaps = await _process_site_snapshots(uid, sites)

    async def fire(tt, entity_key, ctx):
        rule = rules[tt]
        msg = _render(rule['message'], ctx)
        await _maybe_send(bot, trigger_type=tt, telegram_id=telegram_id,
                          entity_key=entity_key, message=msg, buttons=rule['buttons'],
                          dry_run=dry_run, counters=counters)
        counters['fired'][tt] += 1

    # 1) email not confirmed (≥ threshold since registration)
    if 'email_unconfirmed' in rules:
        thr = rules['email_unconfirmed']['threshold_seconds']
        age = _age_seconds(created)
        if thr is not None and age is not None and age >= thr:
            # db mirror may store a null/0 confirmation flag → verify live before firing.
            confirmed = profile.get('emailConfirmed')
            if confirmed is not True:
                live = await _wl_api._get_user_by_email_api(email)
                confirmed = live.get('emailConfirmed') if live else None
            if confirmed is False:
                await fire('email_unconfirmed', '', {'first_name': first_name})

    # 2) no website at all (≥ threshold since registration)
    if 'no_site' in rules and not sites:
        thr = rules['no_site']['threshold_seconds']
        age = _age_seconds(created)
        if thr is not None and age is not None and age >= thr:
            await fire('no_site', '', {'first_name': first_name})

    # 3) website stuck in moderation (status=2) longer than threshold
    if 'site_moderation' in rules:
        thr = rules['site_moderation']['threshold_seconds']
        now = datetime.now()
        for wid, mod_since in snaps['moderation_clock'].items():
            if thr is not None and mod_since is not None and (now - mod_since).total_seconds() >= thr:
                site = next((s for s in sites if str(s.get('id')) == str(wid)), {})
                await fire('site_moderation', str(wid),
                           {'first_name': first_name, 'site_name': site.get('name'),
                            'site_url': site.get('url')})

    # 4) website just rejected (→ status=3)
    if 'site_rejected' in rules:
        for site in snaps['rejected']:
            wid = site.get('id')
            reason = (site.get('rejectionReasonComment') or '').strip()
            if not reason and '{reason}' in rules['site_rejected']['message']:
                reason = await _fetch_reject_reason(uid, email, wid)
            await fire('site_rejected', str(wid),
                       {'first_name': first_name, 'reason': reason or '—',
                        'site_name': site.get('name'), 'site_url': site.get('url')})

    # 5) website just approved (2 → 1)
    if 'site_approved' in rules:
        for site in snaps['approved']:
            await fire('site_approved', str(site.get('id')),
                       {'first_name': first_name, 'site_name': site.get('name'),
                        'site_url': site.get('url')})

    # 6) active website but no clicks (≥ threshold since the site went active)
    if 'no_clicks' in rules:
        thr = rules['no_clicks']['threshold_seconds']
        active = [s for s in sites if s.get('status') == 1]
        if thr is not None and active:
            ages = [(_age_seconds(s.get('created')), s) for s in active]
            ages = [(a, s) for a, s in ages if a is not None]
            if ages:
                oldest_age, oldest = max(ages, key=lambda t: t[0])
                if oldest_age >= thr:
                    clicks = await _clicks_since(uid, oldest.get('created'))
                    if clicks == 0:
                        await fire('no_clicks', '',
                                   {'first_name': first_name, 'site_name': oldest.get('name'),
                                    'site_url': oldest.get('url')})


# ─── one full pass ─────────────────────────────────────────────────────────────

async def run_pass(bot, *, dry_run: Optional[bool] = None, limit: int = 0) -> dict:
    """Evaluate all enabled rules against the whole audience once.
    Returns a summary dict (also used by the /run_alarms admin command)."""
    if not ALARMS_ENABLED:
        return {'enabled': False, 'note': 'ALARMS_ENABLED=false'}

    if dry_run is None:
        dry_run = ALARMS_DRY_RUN

    rules = await asyncio.to_thread(_q_load_rules)
    if not rules:
        return {'enabled': True, 'note': 'нет активных правил (или таблица wl_alarm_rules не создана)'}

    audience = await asyncio.to_thread(_q_audience, limit or ALARM_MAX_USERS)
    counters = {'users': 0, 'sent': 0, 'dryrun': 0, 'skipped_dedup': 0, 'failed': 0,
                'fired': {tt: 0 for tt in rules}}

    for telegram_id, email in audience:
        counters['users'] += 1
        try:
            await _evaluate_user(bot, telegram_id, email, rules, dry_run, counters)
        except Exception as e:
            logger.warning(f'[alarms] user eval failed tg={telegram_id} email={email}: {e}')
        if ALARM_SEND_DELAY:
            await asyncio.sleep(ALARM_SEND_DELAY)

    counters['dry_run'] = dry_run
    counters['test_chat'] = ALARM_TEST_CHAT_ID or None
    counters['rules'] = list(rules.keys())
    logger.warning(f'[alarms] pass done: {counters}')
    return counters


# ─── scheduler entrypoint ──────────────────────────────────────────────────────

async def scheduled_pass() -> None:
    """Called by apscheduler. No-op unless ALARMS_ENABLED."""
    if not ALARMS_ENABLED:
        return
    try:
        from bot.utils.announce_bot import bot
        await run_pass(bot)
    except Exception as e:
        logger.warning(f'[alarms] scheduled pass crashed: {e}')
