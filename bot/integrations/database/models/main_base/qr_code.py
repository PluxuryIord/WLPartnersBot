"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, BigInteger, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base

if TYPE_CHECKING:
    from typing import Union, Optional

from .admin_notification import AdminNotification


class QRCode(Base):
    __tablename__ = 'qr_code'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[bool] = mapped_column(nullable=False, default=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    valid_qr: Mapped[str] = mapped_column(Text, nullable=False, default="QR успешно отсканирован")
    invalid_qr: Mapped[str] = mapped_column(Text, nullable=False, default="QR не работает")

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return QRCode._base_check_mark(QRCode.id, mark, 0)

    @staticmethod
    def add(user_id: int, payload: str) -> bool:
        new_qr = QRCode(user_id=user_id, payload=payload)
        return QRCode._db_add(new_qr, True)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['QRCode'], 'QRCode']:
        return QRCode._db_select(QRCode, QRCode._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return QRCode._db_update(QRCode, QRCode._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return QRCode._db_remove(QRCode, QRCode._check_mark(mark), where)
