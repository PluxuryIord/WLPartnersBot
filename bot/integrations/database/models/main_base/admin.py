"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base

if TYPE_CHECKING:
    from .user import User
    from typing import Union, Optional

from .admin_notification import AdminNotification


class Admin(Base):
    __tablename__ = 'admins'

    admin_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'), primary_key=True)
    appointment_date: Mapped[datetime]
    appointment: Mapped[int]
    access: Mapped[dict] = mapped_column(JSON)

    user: Mapped['User'] = relationship(back_populates='admin')
    notification: Mapped['AdminNotification'] = relationship(back_populates='admin', cascade='all, delete-orphan')

    @staticmethod
    def _check_mark(mark: int) -> Optional['Base']:
        return Admin._base_check_mark(Admin.admin_id, mark, 0)

    @staticmethod
    def add(admin_id: int, appointment: int, access: dict) -> bool:
        new_admin = Admin(admin_id=admin_id, appointment_date=datetime.now(),
                          appointment=appointment, access=access)
        if Admin._db_add(new_admin):
            return AdminNotification.add(admin_id)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['Admin'], 'Admin']:
        return Admin._db_select(Admin, Admin._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return Admin._db_update(Admin, Admin._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return Admin._db_remove(Admin, Admin._check_mark(mark), where)
