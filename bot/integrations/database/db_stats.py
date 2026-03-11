"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from dataclasses import dataclass

from .models.statistics_base import Events


@dataclass()
class DBStats:
    Events = Events
