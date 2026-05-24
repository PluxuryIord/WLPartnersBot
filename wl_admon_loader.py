"""WL Admon S3 → MySQL loader.

Periodically pulls parquet exports from s3://wldp-admon-export/ and
upserts them into wl_admon_* tables in FDM_WinlinePartners.

  Run as systemd:  systemctl start wl_admon_loader
  Run manually:    venv/bin/python3 wl_admon_loader.py
  One-shot:        venv/bin/python3 wl_admon_loader.py --once

Why a separate process: parquet → DataFrame → executemany is heavy
and shouldn't share the bot's event loop. Loader does this in a
plain blocking loop with a configurable sleep between ticks.

Env (reads from .env via environs, same as the bot):
  WL_DUMPS_S3_ENDPOINT / WL_DUMPS_S3_BUCKET / WL_DUMPS_S3_KEY /
  WL_DUMPS_S3_SECRET / WL_DUMPS_S3_REGION / WL_DUMPS_S3_PREFIX
  WL_ADMON_LOADER_INTERVAL_SEC  (default 600)
  MYSQL_*  (used by bot.integrations.database)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import logging
import os
import re
import signal
import sys
import time
from collections import defaultdict
from datetime import date as _date
from typing import Iterable, Optional

import boto3
import pyarrow.parquet as pq
from botocore.config import Config as BotoConfig

# Reuse the bot's SQLAlchemy engine — pool_pre_ping + pool_recycle already
# configured there. Loader gets the same robust connection management.
from bot.integrations.database.connection.engine import mysql_engine

logger = logging.getLogger('wl_admon_loader')

# ─── Config ────────────────────────────────────────────────────────────────

S3_ENDPOINT = os.getenv('WL_DUMPS_S3_ENDPOINT', '')
S3_BUCKET = os.getenv('WL_DUMPS_S3_BUCKET', '')
S3_KEY = os.getenv('WL_DUMPS_S3_KEY', '')
S3_SECRET = os.getenv('WL_DUMPS_S3_SECRET', '')
S3_REGION = os.getenv('WL_DUMPS_S3_REGION', 'ru-central1')
_raw_prefix = os.getenv('WL_DUMPS_S3_PREFIX', '')
S3_PREFIX = (_raw_prefix.rstrip('/') + '/') if _raw_prefix else ''

INTERVAL_SEC = int(os.getenv('WL_ADMON_LOADER_INTERVAL_SEC', '600') or 600)
BATCH_SIZE = 1000

SNAPSHOT_TABLES = ('users', 'websites', 'offers')
INCREMENTAL_TABLES = ('conversions', 'stats_group_by')


def is_configured() -> bool:
    return bool(S3_BUCKET and S3_KEY and S3_SECRET)


def _s3_client():
    return boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT or None,
        region_name=S3_REGION or None,
        aws_access_key_id=S3_KEY,
        aws_secret_access_key=S3_SECRET,
        config=BotoConfig(signature_version='s3v4',
                          s3={'addressing_style': 'path'},
                          retries={'max_attempts': 5, 'mode': 'adaptive'}),
    )


# ─── S3 helpers ────────────────────────────────────────────────────────────

_PARTITION_RE = re.compile(r'dt=(\d{4}-\d{2}-\d{2})/hh=(\d{2})')


def _list_table_keys(s3, table: str) -> list[str]:
    paginator = s3.get_paginator('list_objects_v2')
    out = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=f'{S3_PREFIX}{table}/'):
        for o in page.get('Contents') or []:
            k = o['Key']
            if k.endswith('.parquet'):
                out.append(k)
    out.sort()  # lexicographic == chronological thanks to zero-padded dt/hh
    return out


def _latest_partition_keys(keys: list[str]) -> list[str]:
    """For snapshot tables: pick all keys that belong to MAX(dt,hh) partition."""
    by_part = defaultdict(list)
    for k in keys:
        m = _PARTITION_RE.search(k)
        if m:
            by_part[(m.group(1), m.group(2))].append(k)
    if not by_part:
        return []
    return by_part[max(by_part.keys())]


def _read_parquet(s3, key: str):
    body = s3.get_object(Bucket=S3_BUCKET, Key=key)['Body'].read()
    return pq.read_table(io.BytesIO(body))


# ─── MySQL helpers ─────────────────────────────────────────────────────────

def _raw_conn():
    """pymysql connection via SQLAlchemy's engine pool. Use as context manager."""
    return mysql_engine.raw_connection()


def _ingested_keys(table: str) -> set[str]:
    with _raw_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT s3_key FROM wl_admon_ingested WHERE table_name=%s", (table,))
        return {row[0] for row in cur.fetchall()}


def _mark_ingested(table: str, s3_key: str, rows: int) -> None:
    with _raw_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO wl_admon_ingested (table_name, s3_key, rows_count) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE rows_count=VALUES(rows_count), loaded_at=CURRENT_TIMESTAMP",
            (table, s3_key, rows),
        )
        conn.commit()


def _clear_ingested(table: str) -> None:
    with _raw_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM wl_admon_ingested WHERE table_name=%s", (table,))
        conn.commit()


def _truncate(table: str) -> None:
    with _raw_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"TRUNCATE TABLE wl_admon_{table}")
        conn.commit()


def _executemany_batched(sql: str, rows: list[tuple]) -> int:
    """Run executemany in chunks of BATCH_SIZE to bound packet size."""
    if not rows:
        return 0
    total = 0
    with _raw_conn() as conn:
        cur = conn.cursor()
        for i in range(0, len(rows), BATCH_SIZE):
            cur.executemany(sql, rows[i:i + BATCH_SIZE])
            total += cur.rowcount
        conn.commit()
    return total


# ─── Row builders (parquet → tuple matching column order) ──────────────────

def _to_str(v) -> Optional[str]:
    if v is None:
        return None
    return str(v) if not isinstance(v, str) else v


def _to_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_date(v) -> Optional[_date]:
    if v is None:
        return None
    if isinstance(v, _date):
        return v
    s = str(v)[:10]
    try:
        y, m, d = s.split('-')
        return _date(int(y), int(m), int(d))
    except Exception:
        return None


def _to_bool(v) -> Optional[int]:
    if v is None:
        return None
    return 1 if v else 0


def _extract_partner_email(users_json: Optional[str]) -> Optional[str]:
    """Conversions.users is a JSON string '[{"email": "x"}]'. Extract first email."""
    if not users_json:
        return None
    m = re.search(r'"email"\s*:\s*"([^"]+)"', users_json)
    return m.group(1).lower() if m else None


def _row_users(d: dict) -> tuple:
    return (
        _to_int(d.get('id')),
        _to_str(d.get('email')),
        _to_str(d.get('role')),
        _to_int(d.get('status')),
        _to_bool(d.get('emailConfirmed')),
        _to_str(d.get('firstName')),
        _to_str(d.get('lastName')),
        _to_str(d.get('middleName')),
        _to_str(d.get('phone')),
        _to_str(d.get('telegram')),
        _to_str(d.get('created')),
        _to_str(d.get('lastLogin')),
        _to_str(d.get('credit')),
        _to_str(d.get('debit')),
        _to_str(d.get('manager__email')),
        _to_str(d.get('referrer__email')),
    )


_SQL_USERS = (
    "INSERT INTO wl_admon_users (id, email, role, status, email_confirmed, "
    "first_name, last_name, middle_name, phone, telegram, created_ms, "
    "last_login_ms, credit, debit, manager_email, referrer_email) "
    "VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s)"
)


def _row_websites(d: dict) -> tuple:
    return (
        _to_int(d.get('id')),
        _to_str(d.get('alias')),
        _to_str(d.get('name')),
        _to_int(d.get('type')),
        _to_int(d.get('status')),
        _to_int(d.get('user__id')),
        _to_str(d.get('user__email')),
        _to_str(d.get('personalManager__email')),
        _to_str(d.get('url')),
        _to_str(d.get('created')),
    )


_SQL_WEBSITES = (
    "INSERT INTO wl_admon_websites (id, alias, name, type, status, user_id, "
    "user_email, manager_email, url, created_ms) "
    "VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s)"
)


def _row_offers(d: dict) -> tuple:
    return (
        _to_str(d.get('id')),
        _to_str(d.get('alias')),
        _to_str(d.get('name')),
        _to_int(d.get('status')),
    )


_SQL_OFFERS = (
    "INSERT INTO wl_admon_offers (id, alias, name, status) "
    "VALUES (%s,%s,%s,%s)"
)


def _row_conversions(d: dict) -> tuple:
    return (
        _to_str(d.get('id')),
        _to_date(d.get('date')),
        _to_str(d.get('goal')),
        _to_int(d.get('status')),
        _to_int(d.get('reward')),
        _extract_partner_email(d.get('users')),
        _to_str(d.get('created')),
        _to_str(d.get('updated')),
    )


_SQL_CONVERSIONS = (
    "INSERT INTO wl_admon_conversions (id, date, goal, status, reward, "
    "partner_email, created_ms, updated_ms) "
    "VALUES (%s,%s,%s,%s,%s, %s,%s,%s) "
    "ON DUPLICATE KEY UPDATE "
    "date=VALUES(date), goal=VALUES(goal), status=VALUES(status), "
    "reward=VALUES(reward), partner_email=VALUES(partner_email), "
    "updated_ms=VALUES(updated_ms)"
)


def _dedupe_hash_sgb(d: dict) -> str:
    parts = '|'.join(str(d.get(k) or '') for k in
                     ('datetz', 'userId', 'websiteId', 'offerId', 'offerTag', 'link'))
    return hashlib.sha1(parts.encode('utf-8')).hexdigest()


def _row_stats_group_by(d: dict) -> tuple:
    return (
        _dedupe_hash_sgb(d),
        _to_date(d.get('datetz')),
        _to_int(d.get('userId')),
        _to_int(d.get('websiteId')),
        _to_str(d.get('offerId')),
        _to_str(d.get('offerTag')),
        _to_str(d.get('link')),
        _to_int(d.get('clicks')),
        _to_int(d.get('goal11Quantity')),
        _to_int(d.get('goal12Quantity')),
        _to_int(d.get('goal13Quantity')),
        _to_int(d.get('rewardConfirmed')),
        d.get('rewardCreated'),  # double, keep as-is
        _to_int(d.get('rewardCanceled')),
        d.get('rewardProcessing'),
    )


_SQL_STATS_GROUP_BY = (
    "INSERT INTO wl_admon_stats_group_by (dedupe_hash, datetz, user_id, "
    "website_id, offer_id, offer_tag, link, clicks, goal11_quantity, "
    "goal12_quantity, goal13_quantity, reward_confirmed, reward_created, "
    "reward_canceled, reward_processing) "
    "VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE "
    "clicks=VALUES(clicks), goal11_quantity=VALUES(goal11_quantity), "
    "goal12_quantity=VALUES(goal12_quantity), goal13_quantity=VALUES(goal13_quantity), "
    "reward_confirmed=VALUES(reward_confirmed), reward_created=VALUES(reward_created), "
    "reward_canceled=VALUES(reward_canceled), reward_processing=VALUES(reward_processing)"
)


_BUILDERS = {
    'users':          (_row_users,           _SQL_USERS),
    'websites':       (_row_websites,        _SQL_WEBSITES),
    'offers':         (_row_offers,          _SQL_OFFERS),
    'conversions':    (_row_conversions,     _SQL_CONVERSIONS),
    'stats_group_by': (_row_stats_group_by,  _SQL_STATS_GROUP_BY),
}


# ─── Per-table processors ──────────────────────────────────────────────────

def _process_snapshot_table(s3, table: str) -> None:
    """For snapshot tables (users/websites/offers): if a newer partition exists
    in S3 than what's in wl_admon_ingested → TRUNCATE + reload that partition."""
    keys = _list_table_keys(s3, table)
    if not keys:
        logger.info(f'[{table}] no parquet files in S3, skipping')
        return
    latest_keys = _latest_partition_keys(keys)
    already = _ingested_keys(table)
    if set(latest_keys) <= already:
        logger.info(f'[{table}] up-to-date ({len(latest_keys)} files in latest partition)')
        return

    logger.info(f'[{table}] refreshing snapshot from {len(latest_keys)} latest file(s)')
    builder, sql = _BUILDERS[table]

    rows_total: list[tuple] = []
    for key in latest_keys:
        tbl = _read_parquet(s3, key)
        for d in tbl.to_pylist():
            rows_total.append(builder(d))

    # Snapshot semantics: wipe and reload atomically-ish (truncate isn't
    # transactional in MySQL, but it's fast enough that the gap is tiny;
    # bot reads handle empty results gracefully).
    _truncate(table)
    _clear_ingested(table)
    inserted = _executemany_batched(sql, rows_total)
    for key in latest_keys:
        _mark_ingested(table, key, inserted // max(len(latest_keys), 1))
    logger.info(f'[{table}] snapshot reloaded: {inserted} rows from {len(latest_keys)} files')


def _process_incremental_table(s3, table: str) -> None:
    """For conversions/stats_group_by: UPSERT only new s3 keys; old ones merged in place."""
    keys = _list_table_keys(s3, table)
    if not keys:
        logger.info(f'[{table}] no parquet files in S3, skipping')
        return
    already = _ingested_keys(table)
    new_keys = [k for k in keys if k not in already]
    if not new_keys:
        logger.info(f'[{table}] no new files (have {len(already)} ingested)')
        return

    logger.info(f'[{table}] {len(new_keys)} new file(s) to ingest')
    builder, sql = _BUILDERS[table]

    for key in new_keys:
        try:
            tbl = _read_parquet(s3, key)
            rows = [builder(d) for d in tbl.to_pylist()]
            inserted = _executemany_batched(sql, rows)
            _mark_ingested(table, key, len(rows))
            logger.info(f'[{table}] {key}: {len(rows)} rows ({inserted} affected)')
        except Exception:
            logger.exception(f'[{table}] failed on {key}, skipping (will retry next tick)')


def tick() -> None:
    if not is_configured():
        logger.warning('S3 credentials not configured (WL_DUMPS_S3_*), skipping tick')
        return
    s3 = _s3_client()
    for t in SNAPSHOT_TABLES:
        try:
            _process_snapshot_table(s3, t)
        except Exception:
            logger.exception(f'[{t}] snapshot tick failed')
    for t in INCREMENTAL_TABLES:
        try:
            _process_incremental_table(s3, t)
        except Exception:
            logger.exception(f'[{t}] incremental tick failed')


# ─── Entrypoint ────────────────────────────────────────────────────────────

_stop = False


def _on_signal(signum, _frame):
    global _stop
    logger.info(f'caught signal {signum}, will exit after current tick')
    _stop = True


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true',
                        help='Run a single tick and exit (for cron/testing).')
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    logger.info(f'wl_admon_loader starting (interval={INTERVAL_SEC}s, '
                f'bucket={S3_BUCKET}, prefix={S3_PREFIX!r})')
    if args.once:
        tick()
        return

    while not _stop:
        start = time.time()
        tick()
        elapsed = time.time() - start
        sleep_for = max(1.0, INTERVAL_SEC - elapsed)
        logger.info(f'tick done in {elapsed:.1f}s, sleeping {sleep_for:.0f}s')
        # Sleep in 1-second chunks so SIGTERM is honored quickly.
        for _ in range(int(sleep_for)):
            if _stop:
                break
            time.sleep(1)
    logger.info('exiting cleanly')


if __name__ == '__main__':
    sys.exit(main())
