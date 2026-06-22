"""Dedup log of alarm sends — also the audit trail the panel reads back.

Owned by the bot (created via Base.create_tables). One row per delivered (or
dry-run) alarm. Dedup key is (trigger_type, telegram_id, entity_key, dry_run):
  - `entity_key`  '' for user-level triggers, website_id for site-level ones.
  - `dry_run`     tests dedup against tests, production against production — so a
                  dry-run pass never suppresses the eventual real send.

Going live after testing: clear the dry-run rows (panel «Сбросить журнал» or
DELETE FROM wl_alarm_log WHERE dry_run=1) so the test history isn't kept around.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Integer, String, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Union, Optional


class AlarmLog(Base):
    __tablename__ = 'wl_alarm_log'
    __table_args__ = (
        UniqueConstraint('trigger_type', 'telegram_id', 'entity_key', 'dry_run',
                         name='uniq_alarm_dedup'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trigger_type: Mapped[str] = mapped_column(String(40), nullable=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # '' (not NULL) for user-level triggers, so the UNIQUE dedup key actually matches.
    entity_key: Mapped[str] = mapped_column(String(64), nullable=False, default='')
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ok: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    message_preview: Mapped[str] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return AlarmLog._base_check_mark(AlarmLog.id, mark, 0)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['AlarmLog'], 'AlarmLog']:
        return AlarmLog._db_select(AlarmLog, AlarmLog._check_mark(mark), where, all_scalars)
