"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base

if TYPE_CHECKING:
    from .admin import Admin
    from typing import Union, Optional


class AdminNotification(Base):
    __tablename__ = 'admins_notification'

    admin_id: Mapped[int] = mapped_column(ForeignKey('admins.admin_id'), primary_key=True)
    upgrade: Mapped[bool] = mapped_column(Boolean, default=False)
    registration: Mapped[bool] = mapped_column(Boolean, default=False)
    support: Mapped[bool] = mapped_column(Boolean, default=True)

    admin: Mapped['Admin'] = relationship(back_populates='notification')

    @staticmethod
    def _check_mark(mark: int) -> Optional['Base']:
        return AdminNotification._base_check_mark(AdminNotification.admin_id, mark, 0)

    @staticmethod
    def add(admin_id: int) -> bool:
        new_data = AdminNotification(admin_id=admin_id)
        return AdminNotification._db_add(new_data)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False
               ) -> Union[list['AdminNotification'], 'AdminNotification']:
        return AdminNotification._db_select(AdminNotification, AdminNotification._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return AdminNotification._db_update(AdminNotification, AdminNotification._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return AdminNotification._db_remove(AdminNotification, AdminNotification._check_mark(mark), where)
