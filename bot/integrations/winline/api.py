"""Winline partners platform GraphQL client.

Uses IAP_ADMIN_TOKEN (same as for email check) against p.winline.ru/api/graphql.
"""
from __future__ import annotations

import os
import sys
import logging
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger('wl_bot')

IAP_API_URL = os.getenv('IAP_API_URL', 'https://p.winline.ru/api/graphql')
IAP_TOKEN = os.getenv('IAP_ADMIN_TOKEN', '')

_USER_FIELDS_BASE = """
  id email role status emailConfirmed
  firstName lastName middleName
  phone telegram
  credit debit
  tags { name }
  created updated lastLogin
  referrer { id email }
"""

# Candidate field names for organization/company (different schemas use different names).
# We try them in order; first set that succeeds is cached.
_ORG_FIELD_CANDIDATES = [
    "organizationName companyName",
    "organizationName",
    "companyName",
    "organization { name }",
    "company { name }",
    "",  # finally fall back to no org fields
]

_USER_FIELDS = _USER_FIELDS_BASE  # will be upgraded lazily on first successful org query
_ORG_FIELDS_RESOLVED = False

_WEBSITE_FIELDS = """
  id alias
  user { id email }
  personalManager { email }
  tags { name }
  name type subject url status
  visitorsPerMonth
  created description
  rejectionReasonType rejectionReasonComment
"""


async def _gql(query: str, variables: dict | None = None, timeout: int = 10) -> dict | None:
    """POST GraphQL query, return `data` dict or None on error."""
    if not IAP_TOKEN:
        logger.warning('[WL] IAP_ADMIN_TOKEN not set')
        return None
    payload = {'query': query}
    if variables:
        payload['variables'] = variables
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(
                IAP_API_URL,
                headers={'Authorization': f'Bearer {IAP_TOKEN}', 'Content-Type': 'application/json'},
                json=payload,
            ) as resp:
                if resp.status != 200:
                    logger.warning(f'[WL] HTTP {resp.status}')
                    return None
                data = await resp.json()
                if 'errors' in data:
                    logger.warning(f'[WL] GraphQL errors: {data["errors"]}')
                    return None
                return data.get('data')
    except Exception as e:
        logger.warning(f'[WL] request failed: {e}')
        return None


async def _introspect_user_fields() -> list[str]:
    """Return list of scalar/object field names available on the User type."""
    query = '{ __type(name: "User") { fields { name type { name kind ofType { name kind } } } } }'
    data = await _gql(query)
    if not data:
        return []
    t = data.get('__type') or {}
    fields = t.get('fields') or []
    names = [f.get('name') for f in fields if f.get('name')]
    return names


async def _resolve_org_fields(safe_email: str) -> None:
    """On first call, probe schema to pick org-name field(s) supported by User type."""
    global _USER_FIELDS, _ORG_FIELDS_RESOLVED
    if _ORG_FIELDS_RESOLVED:
        return

    available = await _introspect_user_fields()
    msg = f'[WL] User type fields ({len(available)}): {sorted(available)}'
    logger.warning(msg)
    print(msg, file=sys.stderr, flush=True)

    picks: list[str] = []
    # scalar name fields
    for cand in ('organizationName', 'companyName', 'orgName', 'inn', 'ogrn', 'kpp', 'legalName', 'fullName', 'shortName'):
        if cand in available:
            picks.append(cand)
    # object-type fields with nested name
    for cand in ('organization', 'company', 'org', 'legal', 'juridical', 'entity'):
        if cand in available:
            picks.append(f'{cand} {{ name }}')

    extra = ('\n  ' + ' '.join(picks)) if picks else ''
    candidate = _USER_FIELDS_BASE + extra
    query = '{ users(limit:1, offset:0, where:{email:"%s"}) { count rows { %s } } }' % (safe_email, candidate)
    data = await _gql(query)
    if data is not None and data.get('users') is not None:
        _USER_FIELDS = candidate
        _ORG_FIELDS_RESOLVED = True
        if picks:
            msg = f'[WL] using org fields: {picks}'
            logger.warning(msg)
            print(msg, file=sys.stderr, flush=True)
        return

    # fallback — base only
    logger.warning('[WL] org-field probe failed, using base fields only')
    _ORG_FIELDS_RESOLVED = True


async def get_user_by_email(email: str) -> Optional[dict]:
    """Fetch user profile by email. Returns dict or None."""
    safe = email.replace('"', '')
    await _resolve_org_fields(safe)
    query = '{ users(limit:1, offset:0, where:{email:"%s"}) { count rows { %s } } }' % (safe, _USER_FIELDS)
    data = await _gql(query)
    if not data:
        return None
    rows = (data.get('users') or {}).get('rows') or []
    return rows[0] if rows else None


async def get_user_websites(user_id: int, user_email: str | None = None) -> list[dict]:
    """Fetch all websites belonging to a given user.

    Primary path: filter by userId. If the GraphQL schema doesn't accept that
    filter (returns None/error), fall back to filtering by user.email, and
    finally to full-scan by email match (shouldn't normally happen).
    """
    # Try #1: where:{userId: N}
    query1 = '{ websites(limit:100, offset:0, where:{userId:%d}) { count rows { %s } } }' % (user_id, _WEBSITE_FIELDS)
    data = await _gql(query1)
    if data and data.get('websites') is not None:
        return (data['websites'].get('rows') or [])

    # Try #2: where:{user:{id:N}}
    query2 = '{ websites(limit:100, offset:0, where:{user:{id:%d}}) { count rows { %s } } }' % (user_id, _WEBSITE_FIELDS)
    data = await _gql(query2)
    if data and data.get('websites') is not None:
        return (data['websites'].get('rows') or [])

    # Try #3: by email
    if user_email:
        safe = user_email.replace('"', '')
        query3 = '{ websites(limit:100, offset:0, where:{user:{email:"%s"}}) { count rows { %s } } }' % (safe, _WEBSITE_FIELDS)
        data = await _gql(query3)
        if data and data.get('websites') is not None:
            return (data['websites'].get('rows') or [])

    logger.warning(f'[WL] get_user_websites: all filter attempts failed for user_id={user_id}')
    return []


# ── Period stats (statsGroupBy) ────────────────────────────────────────────

MSK_TZ = timezone(timedelta(hours=3))

_RU_MONTHS = {
    1: 'январь', 2: 'февраль', 3: 'март', 4: 'апрель', 5: 'май', 6: 'июнь',
    7: 'июль', 8: 'август', 9: 'сентябрь', 10: 'октябрь', 11: 'ноябрь', 12: 'декабрь',
}

_STATS_QUERY = (
    "query getStatsGroupBy($dimensions: [String], $metrics: [String!], "
    "$filter: JSON, $start: String!, $end: String!, $order: [String], "
    "$limit: Int, $offset: Int) { "
    "statsGroupBy(dimensions: $dimensions, metrics: $metrics, filter: $filter, "
    "start: $start, end: $end, order: $order, limit: $limit, offset: $offset) "
    "{ count rows } }"
)

_STATS_METRICS = [
    "clicks",
    "goal11Quantity",   # REG
    "goal12Quantity",   # DEP
    "goal13Quantity",   # DEP2
    "rewardConfirmed",  # commission confirmed (₽)
    "rewardCreated",    # commission in processing (₽)
    "rewardCanceled",   # commission cancelled (₽)
]


def _iso_msk(dt: datetime) -> str:
    """ISO-8601 with millisecond precision and +03:00 offset, matching panel payloads."""
    # keep milliseconds, then normalize +0300 -> +03:00
    s = dt.astimezone(MSK_TZ).strftime('%Y-%m-%dT%H:%M:%S.') + f'{dt.microsecond // 1000:03d}'
    off = dt.astimezone(MSK_TZ).strftime('%z')  # +0300
    return s + (off[:3] + ':' + off[3:] if off else '+03:00')


def get_period_range(period: str) -> tuple[str, str, str]:
    """Return (start_iso, end_iso, human_label) for a named period.

    period: 'yesterday' | 'week' | 'month'
    Uses Moscow timezone to match the partner panel.
    """
    now = datetime.now(MSK_TZ)
    today = now.date()

    if period == 'yesterday':
        d = today - timedelta(days=1)
        start_d, end_d = d, d
        label = f'за {d.strftime("%d.%m.%Y")}'
    elif period == 'week':
        # previous calendar week Mon-Sun (Python: Mon=0)
        this_mon = today - timedelta(days=today.weekday())
        last_mon = this_mon - timedelta(days=7)
        last_sun = last_mon + timedelta(days=6)
        start_d, end_d = last_mon, last_sun
        label = f'за прошлую неделю ({last_mon.strftime("%d.%m")}—{last_sun.strftime("%d.%m.%Y")})'
    elif period == 'month':
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        start_d, end_d = first_prev, last_prev
        label = f'за {_RU_MONTHS[first_prev.month]} {first_prev.year}'
    else:
        raise ValueError(f'unknown period: {period}')

    start_dt = datetime(start_d.year, start_d.month, start_d.day, 0, 0, 0, 0, tzinfo=MSK_TZ)
    end_dt = datetime(end_d.year, end_d.month, end_d.day, 23, 59, 59, 999000, tzinfo=MSK_TZ)
    return _iso_msk(start_dt), _iso_msk(end_dt), label


async def get_user_stats(user_id: int, start: str, end: str) -> Optional[dict]:
    """Fetch aggregated stats for a user between start/end (ISO strings w/ tz).

    Returns a dict with summed metrics or None on error:
      { clicks, goal11Quantity, goal12Quantity, goal13Quantity,
        rewardConfirmed, rewardCreated, rewardCanceled }
    """
    variables = {
        "dimensions": ["datetz"],  # matches panel — we sum rows client-side
        "metrics": _STATS_METRICS,
        "filter": {
            "tags": [],
            "users": [int(user_id)],
            "usersTags": [],
            "websites": [],
            "offers": [],
            "offersTags": [],
            "sub": [],
            "uniqueClicks": False,
            "granularity": "day",
            "categories": [],
            "links": [],
            "couponGroup": [],
        },
        "start": start,
        "end": end,
        "order": ["datetz:DESC"],
        "limit": 1000,
        "offset": 0,
    }
    data = await _gql(_STATS_QUERY, variables)
    if not data:
        return None
    rows = ((data.get('statsGroupBy') or {}).get('rows')) or []
    totals = {k: 0 for k in _STATS_METRICS}
    for row in rows:
        for k in _STATS_METRICS:
            v = row.get(k)
            if v is None:
                continue
            try:
                totals[k] += float(v) if isinstance(v, (float, str)) and '.' in str(v) else int(v)
            except (TypeError, ValueError):
                pass
    return totals
