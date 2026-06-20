"""SQL-based reader for the wl_admon_* tables — drop-in replacement for
the in-memory pandas reader in `dumps.py`.

Public API mirrors `dumps.py` so callers in `api.py` don't care which
backend is active (controlled by WL_DATA_SOURCE env: api / s3 / db).

Why a separate module: the loader (wl_admon_loader.py) writes parquet
dumps into MySQL; this module reads them back via vanilla SQL. The bot
never hits S3 anymore — it just talks to MySQL like for any other
domain table.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date as _date, datetime
from typing import Optional
from urllib.parse import quote_plus

# The wl_admon_* mirror lives on its own DB host (separate box). Use a dedicated
# engine from WL_ADMON_DB_* env vars when configured; otherwise fall back to the
# bot's main engine so nothing breaks before the mirror is wired up.
_ADMON_HOST = os.getenv('WL_ADMON_DB_HOST', '')
if _ADMON_HOST:
    from sqlalchemy import create_engine as _create_engine
    mysql_engine = _create_engine(
        'mysql+pymysql://{u}:{p}@{h}:{port}/{db}?charset=utf8mb4'.format(
            u=os.getenv('WL_ADMON_DB_USER', ''),
            p=quote_plus(os.getenv('WL_ADMON_DB_PASSWORD', '')),
            h=_ADMON_HOST,
            port=int(os.getenv('WL_ADMON_DB_PORT', '3306') or 3306),
            db=os.getenv('WL_ADMON_DB_NAME', 'wl_admon'),
        ),
        pool_pre_ping=True,
        pool_recycle=3600,
    )
else:
    from bot.integrations.database.connection.engine import mysql_engine

logger = logging.getLogger('wl_bot')


def is_configured() -> bool:
    """The loader populates the tables; if they're empty, the bot should
    still treat the source as «not ready» and fall back to the live API.
    We trust the engine config but cheap-check the users table to make
    sure migrations were applied and the loader had at least one tick."""
    try:
        with mysql_engine.connect() as conn:
            from sqlalchemy import text
            r = conn.execute(text('SELECT COUNT(*) FROM wl_admon_users')).scalar()
            return bool(r and r > 0)
    except Exception as e:
        logger.warning(f'[db_admon] is_configured probe failed: {e}')
        return False


# ─── Blocking SQL helpers (called via asyncio.to_thread) ───────────────────

def _fetchone(sql: str, params: tuple) -> Optional[dict]:
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))
    finally:
        conn.close()


def _fetchall(sql: str, params: tuple) -> list[dict]:
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _scalar(sql: str, params: tuple):
    conn = mysql_engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# ─── Shape adapters: SQL row → dict that the bot's caller expects ──────────

def _adapt_user(row: dict) -> dict:
    """Return the same key shape that the GraphQL API and the old dumps
    reader emitted, so client_main.py doesn't need to know who fetched it."""
    if not row:
        return row
    return {
        'id': row.get('id'),
        'email': row.get('email'),
        'role': row.get('role'),
        'status': row.get('status'),
        'emailConfirmed': bool(row.get('email_confirmed')) if row.get('email_confirmed') is not None else None,
        'firstName': row.get('first_name'),
        'lastName': row.get('last_name'),
        'middleName': row.get('middle_name'),
        'phone': row.get('phone'),
        'telegram': row.get('telegram'),
        'created': row.get('created_ms'),
        'lastLogin': row.get('last_login_ms'),
        'credit': row.get('credit'),
        'debit': row.get('debit'),
        'manager': {'email': row.get('manager_email')} if row.get('manager_email') else None,
        'referrer': {'email': row.get('referrer_email')} if row.get('referrer_email') else None,
    }


def _adapt_website(row: dict) -> dict:
    """GraphQL-shaped website (with nested user / personalManager)."""
    return {
        'id': row.get('id'),
        'alias': row.get('alias'),
        'name': row.get('name'),
        'type': row.get('type'),
        'status': row.get('status'),
        'url': row.get('url'),
        'created': row.get('created_ms'),
        'user': {'id': row.get('user_id'), 'email': row.get('user_email')},
        'personalManager': {'email': row.get('manager_email')} if row.get('manager_email') else None,
    }


# ─── Public API (mirrors dumps.py / api.py shape) ──────────────────────────

async def get_user_by_email(email: str) -> Optional[dict]:
    em = (email or '').strip().lower()
    if not em:
        return None
    row = await asyncio.to_thread(
        _fetchone,
        "SELECT * FROM wl_admon_users WHERE LOWER(email)=%s LIMIT 1",
        (em,),
    )
    return _adapt_user(row) if row else None


async def get_user_websites(user_id: int) -> list[dict]:
    rows = await asyncio.to_thread(
        _fetchall,
        "SELECT * FROM wl_admon_websites WHERE user_id=%s",
        (int(user_id),),
    )
    return [_adapt_website(r) for r in rows]


async def _user_id_to_email(user_id: int) -> Optional[str]:
    em = await asyncio.to_thread(
        _scalar,
        "SELECT email FROM wl_admon_users WHERE id=%s LIMIT 1",
        (int(user_id),),
    )
    return (em or '').strip().lower() or None


# Status → reward bucket. Mirrors dumps._STATUS_TO_BUCKET.
_STATUS_TO_BUCKET = {1: 'rewardCreated', 2: 'rewardConfirmed', 3: 'rewardCanceled'}


async def _stats_from_conversions(email: str, start_d: _date, end_d: _date) -> tuple[dict, set]:
    """Aggregate goal counts + reward buckets from conversions for the
    partner's email between two dates. Mirrors dumps._stats_from_conversions."""
    out = {'goal11Quantity': 0, 'goal12Quantity': 0, 'goal13Quantity': 0,
           'rewardConfirmed': 0, 'rewardCreated': 0, 'rewardCanceled': 0}
    covered: set[str] = set()

    rows = await asyncio.to_thread(
        _fetchall,
        "SELECT date, goal, status, reward FROM wl_admon_conversions "
        "WHERE partner_email=%s AND date BETWEEN %s AND %s",
        (email, start_d, end_d),
    )
    if not rows:
        return out, covered

    for r in rows:
        goal = r.get('goal') or ''
        if goal == 'goal11': out['goal11Quantity'] += 1
        elif goal == 'goal12': out['goal12Quantity'] += 1
        elif goal == 'goal13': out['goal13Quantity'] += 1
        bucket = _STATUS_TO_BUCKET.get(r.get('status'))
        if bucket:
            out[bucket] += int(r.get('reward') or 0)
        d = r.get('date')
        if d:
            covered.add(d.isoformat() if isinstance(d, _date) else str(d)[:10])
    return out, covered


async def get_user_stats(user_id: int, start_iso: str, end_iso: str) -> Optional[dict]:
    """Aggregated metrics for the period. Same shape and rules as dumps:
      - goals & rewards from conversions (primary)
      - stats_group_by fills the gap for dates not in conversions
      - clicks are ALWAYS from stats_group_by (conversions has no clicks)
    """
    try:
        start_d = datetime.fromisoformat(start_iso.replace('Z', '+00:00')[:10]).date()
        end_d = datetime.fromisoformat(end_iso.replace('Z', '+00:00')[:10]).date()
    except Exception:
        return None

    totals = {'goal11Quantity': 0, 'goal12Quantity': 0, 'goal13Quantity': 0,
              'rewardConfirmed': 0, 'rewardCreated': 0, 'rewardCanceled': 0,
              'clicks': 0}

    # 1) conversions — primary source for goals/rewards
    covered: set[str] = set()
    email = await _user_id_to_email(user_id)
    if email:
        try:
            conv_totals, covered = await _stats_from_conversions(email, start_d, end_d)
            for k, v in conv_totals.items():
                totals[k] = totals.get(k, 0) + v
        except Exception as e:
            logger.warning(f'[db_admon] conversions aggregation failed: {e}')

    # 2) stats_group_by — clicks always; goals/rewards only for uncovered dates.
    #    Two queries: SUM(clicks) over whole period, plus the gap-fill aggregate.
    try:
        clicks_sum = await asyncio.to_thread(
            _scalar,
            "SELECT COALESCE(SUM(clicks), 0) FROM wl_admon_stats_group_by "
            "WHERE user_id=%s AND datetz BETWEEN %s AND %s",
            (int(user_id), start_d, end_d),
        )
        totals['clicks'] = int(clicks_sum or 0)
    except Exception as e:
        logger.warning(f'[db_admon] clicks aggregation failed: {e}')

    # Gap-fill: only dates not already counted by conversions.
    if covered:
        # MySQL doesn't love huge IN (…), but we typically have <=31 dates.
        placeholders = ','.join(['%s'] * len(covered))
        gap_sql = (
            "SELECT COALESCE(SUM(goal11_quantity), 0) AS g11, "
            "COALESCE(SUM(goal12_quantity), 0) AS g12, "
            "COALESCE(SUM(goal13_quantity), 0) AS g13, "
            "COALESCE(SUM(reward_confirmed), 0) AS rc, "
            "COALESCE(SUM(reward_created), 0)   AS rcr, "
            "COALESCE(SUM(reward_canceled), 0)  AS rcn "
            "FROM wl_admon_stats_group_by "
            "WHERE user_id=%s AND datetz BETWEEN %s AND %s "
            f"AND datetz NOT IN ({placeholders})"
        )
        params = (int(user_id), start_d, end_d, *sorted(covered))
    else:
        gap_sql = (
            "SELECT COALESCE(SUM(goal11_quantity), 0) AS g11, "
            "COALESCE(SUM(goal12_quantity), 0) AS g12, "
            "COALESCE(SUM(goal13_quantity), 0) AS g13, "
            "COALESCE(SUM(reward_confirmed), 0) AS rc, "
            "COALESCE(SUM(reward_created), 0)   AS rcr, "
            "COALESCE(SUM(reward_canceled), 0)  AS rcn "
            "FROM wl_admon_stats_group_by "
            "WHERE user_id=%s AND datetz BETWEEN %s AND %s"
        )
        params = (int(user_id), start_d, end_d)

    try:
        gap = await asyncio.to_thread(_fetchone, gap_sql, params)
        if gap:
            totals['goal11Quantity'] += int(gap['g11'] or 0)
            totals['goal12Quantity'] += int(gap['g12'] or 0)
            totals['goal13Quantity'] += int(gap['g13'] or 0)
            totals['rewardConfirmed'] += int(gap['rc'] or 0)
            totals['rewardCreated']   += int(gap['rcr'] or 0)
            totals['rewardCanceled']  += int(gap['rcn'] or 0)
    except Exception as e:
        logger.warning(f'[db_admon] gap-fill aggregation failed: {e}')

    return totals
