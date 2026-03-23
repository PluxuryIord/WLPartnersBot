"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from bot.integrations import DB


class AdminFilter(BaseFilter):
    def __init__(self, system_admins: list[int]):
        self._system_admins = system_admins
        self.db_admins = [admin.admin_id for admin in DB.Admin.select(all_scalars=True)]

    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        return self.is_admin(event.from_user.id)

    def is_admin(self, user_id: int):
        return True if user_id in self.db_admins else False

    def is_system(self, user_id: int):
        return True if user_id in self._system_admins else False

    def get_admins_id(self):
        return self.db_admins

    def add_admin(self, user_id: int, adder: int, access: dict):
        DB.Admin.add(user_id, adder, access)
        self.db_admins.append(user_id)

    def remove_admin(self, initiator: int, admin_id: int):
        if admin_id in self._system_admins and not self.is_system(initiator):
            return False
        else:
            DB.AdminNotification.remove(mark=admin_id)
            DB.Alert.remove(mark=admin_id)
            DB.Admin.remove(mark=admin_id)
            self.db_admins.remove(admin_id)
            return True
