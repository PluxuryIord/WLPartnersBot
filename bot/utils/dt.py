"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from datetime import datetime, timedelta
from typing import Optional, Union, Literal

import pandas as pd

date_formats = {
    0: '%d.%m.%Y %H:%M',
    1: '%d.%m.%Y',
    2: '%d.%m.%Y %H:%M:%S',
    3: '%H:%M',
    'path': '%d.%m.%Y %H-%M-%S'
}


def change_date(date: Union[datetime, str],
                change_arg: Literal['+', '-'] = '+',
                change_days: Optional[int] = 0,
                change_hours: Optional[int] = 0,
                change_minutes: Optional[int] = 0,
                change_seconds: Optional[int] = 0,
                date_format: Optional[str] = None,
                return_str_format: Optional[str] = None) -> datetime | str:
    if isinstance(date, str):
        date = datetime.strptime(date, date_format)
    change_time = timedelta(days=change_days, hours=change_hours, minutes=change_minutes, seconds=change_seconds)
    if change_arg == '+':
        date = date + change_time
    else:
        date = date - change_time
    if return_str_format:
        return date.strftime(return_str_format)
    else:
        return date


def now(date_format: Literal[0, 1, 2, 3, 'path', 'datetime'] = 0,
        change_arg: Literal['+', '-'] = '+',
        change_days: Optional[int] = 0,
        change_hours: Optional[int] = 0,
        change_minutes: Optional[int] = 0,
        change_seconds: Optional[int] = 0) -> datetime | str:
    date_now = change_date(datetime.now(), change_arg, change_days, change_hours, change_minutes, change_seconds)
    if date_format == 'datetime':
        return date_now
    else:
        return date_now.strftime(date_formats[date_format])


def convert_period_to_dates(start_date: str,
                            end_date: str,
                            date_format: str,
                            result_date_format: str = '%Y-%m-%d') -> list:
    start_date = datetime.strptime(start_date, date_format).strftime('%Y-%m-%d')
    end_date = datetime.strptime(end_date, date_format).strftime('%Y-%m-%d')
    period_for_dates_days = pd.date_range(start=start_date, end=end_date).strftime(result_date_format).tolist()
    return period_for_dates_days


def reformat_str_date(date: str,
                      old_date_format: str,
                      new_date_format: str) -> str:
    return datetime.strptime(date, old_date_format).strftime(new_date_format)


def to_str(date: datetime, date_format: Literal[0, 1, 2, 3, 'path'] = 0):
    return date.strftime(date_formats[date_format])
