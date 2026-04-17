"""Winline partners platform GraphQL client.

Uses IAP_ADMIN_TOKEN (same as for email check) against p.winline.ru/api/graphql.
"""
from __future__ import annotations

import os
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger('wl_bot')

IAP_API_URL = os.getenv('IAP_API_URL', 'https://p.winline.ru/api/graphql')
IAP_TOKEN = os.getenv('IAP_ADMIN_TOKEN', '')

_USER_FIELDS = """
  id email role status emailConfirmed
  firstName lastName middleName
  phone telegram
  credit debit
  tags { name }
  created updated lastLogin
  referrer { id email }
"""

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


async def get_user_by_email(email: str) -> Optional[dict]:
    """Fetch user profile by email. Returns dict or None."""
    safe = email.replace('"', '')
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
