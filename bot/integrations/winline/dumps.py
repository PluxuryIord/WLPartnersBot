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

    frames = []
    for k in keys:
        body = s3.get_object(Bucket=BUCKET, Key=k)['Body'].read()
        buf = io.BytesIO(body)
        frames.append(pq.read_table(buf).to_pandas())
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    return df


# Composite keys for incremental merge — last-write-wins per object.
_MERGE_KEYS = {
    'stats_group_by': ['linkId', 'websiteId', 'userId', 'offerId', 'datetz', 'category', 'offerTag'],
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


async def get_user_stats(user_id: int, start_iso: str, end_iso: str) -> Optional[dict]:
    """Return totals for the 6 metrics available in the dump.

    NOTE: clicks are NOT in the dump — caller must obtain them from the live API
    and merge into the result if needed.
    """
    if not is_configured():
        return None
    df = await _get('stats_group_by')
    if df is None or df.empty:
        return None

    try:
        start_d = datetime.fromisoformat(start_iso.replace('Z', '+00:00')[:10]).date()
        end_d = datetime.fromisoformat(end_iso.replace('Z', '+00:00')[:10]).date()
    except Exception:
        return None

    sub = df[
        (df['userId'] == int(user_id))
        & (df['datetz'] >= start_d.isoformat())
        & (df['datetz'] <= end_d.isoformat())
    ]
    metrics = ['goal11Quantity', 'goal12Quantity', 'goal13Quantity',
               'rewardConfirmed', 'rewardCreated', 'rewardCanceled']
    totals: dict[str, int | float] = {}
    for m in metrics:
        if m in sub.columns:
            try:
                totals[m] = int(sub[m].sum())
            except (TypeError, ValueError):
                totals[m] = 0
        else:
            totals[m] = 0
    # clicks intentionally absent — caller fills it from API
    totals['clicks'] = 0
    return totals
