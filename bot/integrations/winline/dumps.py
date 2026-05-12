"""Reader for the daily Winline data dumps in S3.

Bucket layout:
  <prefix>/<object>/dt=YYYY-MM-DD/hh=HH/<file>.parquet

Objects:
  - users        (full refresh)
  - websites     (full refresh)
  - offers       (full refresh)
  - stats_group_by (incremental — merge all partitions, last-write-wins)

Used as an alternative data source to the live IAP GraphQL API. Switching
is controlled by env var WL_DATA_SOURCE (api|s3, default api).

Caching: each object is read in full into memory, with a TTL refresh
(WL_DUMPS_CACHE_TTL seconds, default 1h). Boto3 / pyarrow are imported
lazily so absence of the libs doesn't crash the bot when running in
api-only mode.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger('wl_bot')

ENDPOINT = os.getenv('WL_DUMPS_S3_ENDPOINT', 'https://s3.twcstorage.ru')
BUCKET = os.getenv('WL_DUMPS_S3_BUCKET', '')
ACCESS_KEY = os.getenv('WL_DUMPS_S3_KEY', '')
SECRET_KEY = os.getenv('WL_DUMPS_S3_SECRET', '')
PREFIX = (os.getenv('WL_DUMPS_S3_PREFIX', 'test1/') or 'test1/').rstrip('/') + '/'
CACHE_TTL_SEC = int(os.getenv('WL_DUMPS_CACHE_TTL', '3600') or 3600)


def is_configured() -> bool:
    return bool(BUCKET and ACCESS_KEY and SECRET_KEY)


# ── Cache ───────────────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, object]] = {}
_lock = asyncio.Lock()


def _client():
    import boto3  # lazy
    return boto3.client(
        's3', endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
    )


def _list_keys(name: str) -> list[str]:
    """Return all parquet keys under <prefix><name>/, sorted lexicographically
    (which equals chronological order thanks to zero-padded dt/hh)."""
    s3 = _client()
    paginator = s3.get_paginator('list_objects_v2')
    keys = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f'{PREFIX}{name}/'):
        for obj in page.get('Contents', []) or []:
            k = obj['Key']
            if k.endswith('.parquet'):
                keys.append(k)
    keys.sort()
    return keys


def _read_blocking(name: str, full_refresh: bool):
    """Synchronous: list keys, fetch parquet bytes, return concatenated DataFrame.

    full_refresh=True  → only the latest dt=…/hh=… partition is read.
    full_refresh=False → all partitions read in chronological order, then
                         duplicates dropped keeping the latest occurrence.
    """
    import pyarrow.parquet as pq
    import pandas as pd

    s3 = _client()
    keys = _list_keys(name)
    if not keys:
        return None

    if full_refresh:
        partitions: dict[tuple[str, str], list[str]] = defaultdict(list)
        for k in keys:
            # k = <prefix><name>/dt=YYYY-MM-DD/hh=HH/<file>.parquet
            parts = k.split('/')
            dt_p = next((p for p in parts if p.startswith('dt=')), None)
            hh_p = next((p for p in parts if p.startswith('hh=')), None)
            if dt_p and hh_p:
                partitions[(dt_p, hh_p)].append(k)
        if not partitions:
            return None
        latest_key = max(partitions.keys())
        keys = partitions[latest_key]

    # Limit columns for big event tables to keep memory + parse time sane.
    # `items` (per-conversion JSON) and other heavy fields are not used by the
    # bot anywhere — skipping them shrinks the DataFrame ~10x.
    column_subset = _COLUMN_SUBSETS.get(name)

    frames = []
    for k in keys:
        body = s3.get_object(Bucket=BUCKET, Key=k)['Body'].read()
        buf = io.BytesIO(body)
        if column_subset:
            try:
                table = pq.read_table(buf, columns=column_subset)
            except Exception:
                # Schema changed / column missing — fall back to full read once.
                buf.seek(0)
                table = pq.read_table(buf)
        else:
            table = pq.read_table(buf)
        frames.append(table.to_pandas())
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)

    # Post-process conversions: extract partner email into a flat column so
    # filtering by partner becomes a vectorized string compare. In wldp-admon
    # the `users` column is serialized as a JSON STRING like
    # '[{"email": "x@y.z"}]' (not a list of structs), so regex extract is both
    # correct and fast for millions of rows.
    if name == 'conversions' and 'users' in df.columns:
        df['_partner_email'] = (
            df['users'].astype('string')
            .str.extract(r'"email"\s*:\s*"([^"]+)"', expand=False)
            .str.lower()
        )
    return df


# Columns to materialize per object. Conversions is the big one — we only need
# enough for per-partner stat aggregation. Everything else stays "all columns".
_COLUMN_SUBSETS = {
    'conversions': ['id', 'date', 'goal', 'status', 'reward', 'users'],
}


# Composite keys for incremental merge — last-write-wins per object.
_MERGE_KEYS = {
    'stats_group_by': ['linkId', 'websiteId', 'userId', 'offerId', 'datetz', 'category', 'offerTag'],
    'conversions': ['id'],
}

# Mapping of conversions.status -> reward bucket. ASSUMPTION pending supplier
# confirmation: 1=created/in-processing, 2=confirmed, 3=canceled.
# If the supplier replies otherwise, flip the mapping here.
_STATUS_TO_BUCKET = {
    1: 'rewardCreated',
    2: 'rewardConfirmed',
    3: 'rewardCanceled',
}


async def _get(name: str):
    """Cached async getter. Returns a pandas DataFrame or None."""
    now = time.time()
    cached = _cache.get(name)
    if cached and now - cached[0] < CACHE_TTL_SEC:
        return cached[1]

    async with _lock:
        cached = _cache.get(name)
        if cached and time.time() - cached[0] < CACHE_TTL_SEC:
            return cached[1]
        full = name not in _MERGE_KEYS  # full refresh = small tables
        df = await asyncio.to_thread(_read_blocking, name, full)
        if df is not None and name in _MERGE_KEYS:
            keys = [k for k in _MERGE_KEYS[name] if k in df.columns]
            if keys:
                df = df.drop_duplicates(subset=keys, keep='last').reset_index(drop=True)
        _cache[name] = (time.time(), df)
        return df


# ── Public API (mirrors winline.api shape so callers don't care) ────────────

async def get_user_by_email(email: str) -> Optional[dict]:
    if not is_configured():
        return None
    df = await _get('users')
    if df is None or df.empty:
        return None
    em = (email or '').strip().lower()
    matched = df[df['email'].str.lower() == em]
    if matched.empty:
        return None
    import pandas as pd
    row = matched.iloc[0].to_dict()
    return {k: (None if pd.isna(v) else v) for k, v in row.items()}


async def get_user_websites(user_id: int) -> list[dict]:
    if not is_configured():
        return []
    df = await _get('websites')
    if df is None or df.empty:
        return []
    matched = df[df['user__id'] == int(user_id)]
    if matched.empty:
        return []
    import pandas as pd
    out = []
    for _, row in matched.iterrows():
        d = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        # Restore nested shape similar to GraphQL response
        d['user'] = {'id': d.pop('user__id', None), 'email': d.pop('user__email', None)}
        pm_email = d.pop('personalManager__email', None)
        d['personalManager'] = {'email': pm_email} if pm_email else None
        out.append(d)
    return out


async def _user_id_to_email(user_id: int) -> Optional[str]:
    """Resolve partner email by user_id via the users dump (small full table)."""
    df = await _get('users')
    if df is None or df.empty:
        return None
    row = df[df['id'] == int(user_id)]
    if row.empty:
        return None
    em = row.iloc[0].get('email')
    return (em or '').strip().lower() or None


async def _stats_from_conversions(email: str, start_d, end_d) -> tuple[dict, set]:
    """Aggregate goals + rewards (bucketed by status) from conversions for a
    partner's email between two dates (inclusive).

    Returns (totals_dict, set_of_dates_covered). totals_dict has keys
    matching the stats_group_by output: goal11/12/13 quantities and three
    reward buckets. covered_dates is the set of YYYY-MM-DD strings for which
    conversions had ANY row for this partner — used by the caller to avoid
    double-counting against stats_group_by.
    """
    out = {'goal11Quantity': 0, 'goal12Quantity': 0, 'goal13Quantity': 0,
           'rewardConfirmed': 0, 'rewardCreated': 0, 'rewardCanceled': 0}
    covered: set[str] = set()
    df = await _get('conversions')
    if df is None or df.empty:
        return out, covered

    # Date filter (date column is 'YYYY-MM-DD' string in the dump).
    start_s, end_s = start_d.isoformat(), end_d.isoformat()
    sub = df[(df['date'] >= start_s) & (df['date'] <= end_s)]
    if sub.empty:
        return out, covered

    # Vectorized email filter via the precomputed `_partner_email` column
    # (set up in _read_blocking at conversions load time).
    em = email.strip().lower()
    if '_partner_email' in sub.columns:
        sub = sub[sub['_partner_email'] == em]
    else:
        # Defensive fallback if the load-time post-processing was skipped.
        def _matches(lst):
            try:
                for u in (lst or []):
                    if isinstance(u, dict):
                        e = u.get('email')
                        if e and str(e).strip().lower() == em:
                            return True
            except Exception:
                return False
            return False
        sub = sub[sub['users'].apply(_matches)]
    if sub.empty:
        return out, covered

    # Quantities by goal.
    goal_counts = sub.groupby('goal').size().to_dict()
    out['goal11Quantity'] = int(goal_counts.get('goal11', 0))
    out['goal12Quantity'] = int(goal_counts.get('goal12', 0))
    out['goal13Quantity'] = int(goal_counts.get('goal13', 0))

    # Rewards bucketed by status.
    for status_val, bucket in _STATUS_TO_BUCKET.items():
        rows = sub[sub['status'] == status_val]
        if rows.empty:
            continue
        try:
            out[bucket] = int(rows['reward'].fillna(0).sum())
        except (TypeError, ValueError):
            out[bucket] = 0

    covered = set(sub['date'].astype(str).unique())
    return out, covered


async def get_user_stats(user_id: int, start_iso: str, end_iso: str) -> Optional[dict]:
    """Return totals for the 6 metrics available in the dump.

    Strategy:
      1. Aggregate REG/DEP/DEP2 + reward buckets from `conversions/` for the
         partner (matched by email). Conversions is fresh (hourly) and is the
         only place where deposits live after the 2026-05-05 stats_group_by
         format change.
      2. For dates NOT covered by conversions, fall back to `stats_group_by`
         (which still has reg-only data for older periods, including the
         pre-2026-05-05 fat snapshot with full history).
      3. Clicks are not in either dump — caller backfills from live API.
    """
    if not is_configured():
        return None

    try:
        start_d = datetime.fromisoformat(start_iso.replace('Z', '+00:00')[:10]).date()
        end_d = datetime.fromisoformat(end_iso.replace('Z', '+00:00')[:10]).date()
    except Exception:
        return None

    totals = {'goal11Quantity': 0, 'goal12Quantity': 0, 'goal13Quantity': 0,
              'rewardConfirmed': 0, 'rewardCreated': 0, 'rewardCanceled': 0}

    # 1) conversions (preferred)
    covered: set[str] = set()
    email = await _user_id_to_email(user_id)
    if email:
        try:
            conv_totals, covered = await _stats_from_conversions(email, start_d, end_d)
            for k, v in conv_totals.items():
                totals[k] = totals.get(k, 0) + v
        except Exception as e:
            logger.warning(f'[WL] conversions aggregation failed: {e}')

    # 2) stats_group_by fallback for dates not covered by conversions
    df = await _get('stats_group_by')
    if df is not None and not df.empty:
        sub = df[
            (df['userId'] == int(user_id))
            & (df['datetz'].astype(str) >= start_d.isoformat())
            & (df['datetz'].astype(str) <= end_d.isoformat())
        ]
        if covered:
            sub = sub[~sub['datetz'].astype(str).isin(covered)]
        if not sub.empty:
            for m in ('goal11Quantity', 'goal12Quantity', 'goal13Quantity',
                      'rewardConfirmed', 'rewardCreated', 'rewardCanceled'):
                if m in sub.columns:
                    try:
                        totals[m] += int(sub[m].fillna(0).sum())
                    except (TypeError, ValueError):
                        pass

    # clicks intentionally absent — caller fills it from API
    totals['clicks'] = 0
    return totals
