"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from typing import Union, Optional

from sqlalchemy import Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class Texts(Base):
    __tablename__ = 'texts'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, nullable=True)

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return Texts._base_check_mark(Texts.id, mark, 0)

    @staticmethod
    def add(category: str, description: str, texts_data: dict) -> Union[bool | int]:
        new_category = Texts(category=category, description=description, data=texts_data)
        return Texts._db_add(new_category)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['Text'], 'Text']:
        return Texts._db_select(Texts, Texts._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return Texts._db_update(Texts, Texts._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return Texts._db_remove(Texts, Texts._check_mark(mark), where)
