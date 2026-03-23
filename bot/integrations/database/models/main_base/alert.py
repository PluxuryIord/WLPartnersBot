"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base

if TYPE_CHECKING:
    from .user import User
    from typing import Optional, Union


class Alert(Base):
    __tablename__ = 'alerts'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    data: Mapped[dict] = mapped_column(JSON)
    date_sent: Mapped[datetime] = mapped_column(nullable=True)
    successfully_sent: Mapped[int] = mapped_column(default=0)
    error_sent: Mapped[int] = mapped_column(default=0)
    dispatch_log: Mapped[str] = mapped_column(LONGTEXT, default='⏳Рассылка запускается...\n\n')
    status_code: Mapped[int] = mapped_column(default=0)
    admin_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'))
    recipients: Mapped[dict] = mapped_column(JSON, nullable=True)

    user: Mapped['User'] = relationship(back_populates='alert')

    @staticmethod
    def _check_mark(mark: int) -> Optional['Base']:
        return Alert._base_check_mark(Alert.id, mark, 0)

    @staticmethod
    def add(admin_id: int, recipients: dict = None, text: str = None, buttons: list = None) -> Union[bool | int]:
        default_data = {'alert_type': None, 'text': '',
                        'files_counter': {
                            'all': 0,
                            'photo': 0,
                            'video': 0,
                            'document': 0,
                            'animation': 0,
                            'sticker': False,
                            'video_note': False,
                            'voice': False},
                        'files': [], 'buttons': []}
        if text:
            default_data['alert_type'] = 'text'
            default_data['text'] = text
        if buttons:
            default_data['buttons'] = buttons
        new_alert = Alert(data=default_data, admin_id=admin_id, recipients=recipients)
        return Alert._db_add(new_alert, autoincrement_id=True)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['Alert'], 'Alert']:
        return Alert._db_select(Alert, Alert._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return Alert._db_update(Alert, Alert._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return Alert._db_remove(Alert, Alert._check_mark(mark), where)
