"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from typing import Any, Union, Literal

from sqlalchemy import select, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Session

from bot.integrations.database.connection import mysql_engine


class Base(DeclarativeBase):

    @staticmethod
    def _check_filter(exc_type: Literal['select', 'update', 'remove'], table, default_mark, where=False):
        stmt = None
        if default_mark is not False:
            where = default_mark
        if where is not False:
            if not isinstance(where, list):
                where = [where]
            if exc_type == 'select':
                stmt = select(table).where(*where)
            elif exc_type == 'update':
                stmt = update(table).where(*where)
            elif exc_type == 'remove':
                stmt = delete(table).where(*where)
            return stmt
        else:
            if exc_type == 'select':
                return select(table)
            else:
                return False

    @staticmethod
    def _db_add(data, autoincrement_id: bool = False) -> bool | int:
        with Session(mysql_engine) as session:
            session.add(data)
            try:
                if autoincrement_id:
                    session.flush()
                    return data.id
                return True
            except IntegrityError:
                return False
            finally:
                session.commit()

    @staticmethod
    def _db_select(table, default_mark=False,
                   where=False, all_scalars: bool = False):
        filter_stmt = Base._check_filter('select', table, default_mark, where)
        if filter_stmt is not False:
            stmt = filter_stmt
        else:
            return False
        with Session(mysql_engine) as session:
            if all_scalars:
                return session.scalars(stmt).all()
            else:
                return session.scalars(stmt).one_or_none()

    @staticmethod
    def _db_update(
            table, default_mark=False,
            where=False, **kwargs
    ) -> bool:
        filter_stmt = Base._check_filter('update', table, default_mark, where)
        if filter_stmt is not False:
            stmt = filter_stmt
        else:
            stmt = update(table)
        with Session(mysql_engine) as session:
            session.execute(stmt.values(**kwargs))
            session.commit()
            return True

    @staticmethod
    def _db_remove(
            table, default_mark, where=False
    ) -> bool:
        if default_mark is not False or where is not False:
            filter_stmt = Base._check_filter('remove', table, default_mark, where)
            if filter_stmt is not False:
                stmt = filter_stmt
            else:
                return False
        else:
            stmt = delete(table)
        with Session(mysql_engine) as session:
            session.execute(stmt)
            session.commit()
            return True

    @staticmethod
    def _base_check_mark(db_object: 'Base', mark: Any, example_type: Union[int, float, str, bool, dict]
                         ) -> Union['Base', bool]:
        if mark:
            if isinstance(mark, type(example_type)):
                return db_object == mark
            else:
                raise AttributeError(f'Mark error: Input({db_object}) is not of type {type(example_type)})')
        else:
            return False

    @staticmethod
    def create_tables() -> None:
        Base.metadata.create_all(bind=mysql_engine)
