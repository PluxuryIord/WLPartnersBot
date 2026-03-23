"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Session

from bot.integrations.database.connection import stats_sqlite_engine


class Base(DeclarativeBase):
    @staticmethod
    def _db_add(data, autoincrement_id: bool = False) -> bool | int:
        with Session(stats_sqlite_engine) as session:
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
    def _db_select(table, all_scalars: bool = False):
        with Session(stats_sqlite_engine) as session:
            if all_scalars:
                return session.scalars(select(table)).all()
            else:
                return session.scalars(select(table)).one_or_none()

    @staticmethod
    def _db_remove(table, line_id: int) -> None:
        with Session(stats_sqlite_engine) as session:
            session.execute(delete(table).where(table.id == line_id))
            session.commit()

    @staticmethod
    def create_tables() -> None:
        Base.metadata.create_all(bind=stats_sqlite_engine)
