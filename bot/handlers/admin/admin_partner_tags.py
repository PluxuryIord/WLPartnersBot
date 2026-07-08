"""Admin command to sync partner status tags on demand.

  /retag_partners → one full pass: recompute the status tag for every
                    logged-in user from the wl_admon mirror and sync the
                    panel's wl_admin_user_tags (drops the legacy «Партнёр»).

The scheduled job does the same every PARTNER_TAGS_INTERVAL_SEC — this is for
the initial one-off migration and for checking without waiting.
"""
from aiogram import Dispatcher
from aiogram.filters.command import Command
from aiogram.types import Message

from bot.initialization import config
from bot.utils import partner_tags


async def retag_partners_cmd(message: Message):
    await message.answer('⏳ Пересчитываю статусные теги партнёров по зеркалу…')
    res = await partner_tags.run_retag_pass()

    by_tag_lines = '\n'.join(
        f'  • {tag}: {n}' for tag, n in res.get('by_tag', {}).items() if n
    ) or '  —'
    text = (
        f'✅ Теги синхронизированы\n'
        f'Аудитория (user_auth): {res.get("users", 0)}\n'
        f'Протегировано: {res.get("tagged", 0)} | изменилось: {res.get("changed", 0)}\n'
        f'Нет в зеркале (пропущены): {res.get("skipped_no_mirror", 0)} | ошибок: {res.get("errors", 0)}\n'
        f'По тегам:\n{by_tag_lines}'
    )
    await message.answer(text)


def register_handlers_admin_partner_tags(dp: Dispatcher):
    dp.message.register(retag_partners_cmd, Command(commands='retag_partners'), config.admin_filter)
