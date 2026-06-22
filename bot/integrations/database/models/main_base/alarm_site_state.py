"""Snapshot of partner website statuses, kept so the alarm engine can detect
*transitions* (the data source has no status-change timestamps).

Owned by the bot (created via Base.create_tables). One row per website_id:
  - `status`            last status we observed (1 active / 2 moderation / 3 rejected)
  - `moderation_since`  when we first saw it enter status=2 (for «модерация > Nч»)

The engine reads the prior row, compares with the freshly fetched status, and
fires the matching alarm on a change (2→1 approved, →3 rejected, → entering 2
starts the moderation clock). See bot/utils/alarms.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Union, Optional


class AlarmSiteState(Base):
    __tablename__ = 'wl_alarm_site_state'

    website_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    status: Mapped[int] = mapped_column(Integer, nullable=True)
    moderation_since: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return AlarmSiteState._base_check_mark(AlarmSiteState.website_id, mark, 0)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['AlarmSiteState'], 'AlarmSiteState']:
        return AlarmSiteState._db_select(AlarmSiteState, AlarmSiteState._check_mark(mark), where, all_scalars)
