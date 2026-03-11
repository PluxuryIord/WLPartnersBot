"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

# Bot Default Commands
default_commands = [
    ['start', '💻 Главное меню']
]


# Startup set bot-menu commands
async def set_menu_commands(bot_command: Bot) -> None:
    commands = []
    for command in default_commands:
        commands.append(BotCommand(command=command[0], description=command[1]))
    await bot_command.set_my_commands(commands=commands, scope=BotCommandScopeAllPrivateChats())
