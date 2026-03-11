from __future__ import annotations

import logging
import random
import subprocess
import os
import asyncio
from bot.integrations import DB
from bot.utils import telegram

# run_path берём как в admin_alert (там он формируется под win/unix) — продублируем тут
if os.name == 'nt':
    RUN_PATH = f'{os.getcwd()}\\.venv\\Scripts\\python.exe -m background_alert'
else:
    RUN_PATH = f'{os.getcwd()}/venv/bin/python3 -m background_alert'

SYSTEM_ADMIN_ID = 928877223  # кто «автор» алерта в истории; можете заменить на реальный ID админа


def _start_background(alert_id: int) -> None:
    # Полностью аналогично background_thread() из админ-хендлеров
    shell_command = f'{RUN_PATH} {alert_id}'
    subprocess.run(shell_command, shell=True, check=False)


def _make_text_alert(text: str) -> dict:
    # Ровно такой формат ждёт ваш message_constructor/ThreadAlert
    # alert_type: 'text' | 'files' | 'sticker' | 'voice' | ...
    return {
        'alert_type': 'text',
        'text': text,
        'buttons': [],
        'files': [],
        'files_counter': {'all': 0, 'photo': 0, 'video': 0, 'document': 0,
                          'animation': 0, 'sticker': False, 'video_note': False, 'voice': False}
    }


def _dispatch_to_all_users(alert_body: dict, quiz: bool = False) -> int:
    if not quiz:
        users = [user.user_id for user in DB.User.select(all_scalars=True)]
        users_dict = {}
        for user in users:
            users_dict[user] = 0
        alert_id = DB.Alert.add(SYSTEM_ADMIN_ID, users_dict, alert_body['text'])
    else:
        users = [user.user_id for user in DB.User.select(all_scalars=True, where=DB.User.rules_accept.is_(True))]
        users_dict = {}
        for user in users:
            users_dict[user] = 0
        alert_id = DB.Alert.add(SYSTEM_ADMIN_ID, users_dict, alert_body['text'], buttons=[[
            "Начать квиз!",
            "call",
            "client_quiz:1"
        ]])
    _start_background(alert_id)
    return alert_id


def _dispatch_to_users(alert_body: dict, buttons) -> int:
    users = [user.user_id for user in DB.User.select(all_scalars=True, where=DB.User.rules_accept.is_(True))]
    users_dict = {}
    for user in users:
        users_dict[user] = 0
    alert_id = DB.Alert.add(SYSTEM_ADMIN_ID, users_dict, alert_body['text'], buttons=buttons if buttons else None)

    _start_background(alert_id)
    return alert_id

# Конкретные тексты
TEXT_1720 = "Будь готов! Через час начнётся квиз, дающий возможность выиграть крутые призы!"
TEXT_1740 = "Уже через час начнётся розыгрыш супер места!"
TEXT_1845 = "Участвуешь в челлендже? Возможно, именно ты скоро выйдешь на поле!"
TEXT_QUIZ = "Участвуй в квизе и получи возможность выиграть призы от Winline!"
TEXT_CHALLENGE = "<b>Поздравляем! Ты участвуешь в челлендже!  Скорее приходи ко входу в сектор 108 и звони по номеру 89649292450, чтобы организаторы вручили тебе подарки!</b>"
TEXT_SUPER_PLACE = "<b>Поздравляем! Ты выиграл(а) супер место! Скорее приходи ко входу в сектор 108 и звони по номеру 89649292450, чтобы организаторы вручили тебе подарки!</b>"
NO_WINNER = "Повезёт в другой раз!"
TEXT_1840 = 'А вот и начало розыгрышей! Скорее жми на кнопки и участвуй!'


def push_1720():
    _dispatch_to_all_users(_make_text_alert(TEXT_1720))


def push_1740():
    _dispatch_to_all_users(_make_text_alert(TEXT_1740))


def push_1845():
    _dispatch_to_all_users(_make_text_alert(TEXT_1845))


def start_quiz():
    _dispatch_to_all_users(_make_text_alert(TEXT_QUIZ), True)


def stop_quiz():
    DB.Quiz.update(1, status=False)


def _dispatch_to_winners(alert_body: dict, users: list) -> int:
    users_dict = {}
    for user in users:
        users_dict[user] = 0
    alert_id = DB.Alert.add(SYSTEM_ADMIN_ID, users_dict, alert_body['text'])
    _start_background(alert_id)
    return alert_id


async def stop_challenge():
    challenge_users = [user.user_id for user in DB.User.select(all_scalars=True, where=DB.User.challenge.is_(True))]
    winners = random.sample(challenge_users, 3)
    _dispatch_to_winners(_make_text_alert(TEXT_CHALLENGE), winners)
    _dispatch_to_winners(_make_text_alert(NO_WINNER), list(set(challenge_users) - set(winners)))
    try:
        for winner in winners:
            try:
                user_data = DB.User.select(winner)
                await telegram.topic_manager.send_message(user_data.thread_id, 'Пользователь победит в розыгрыше челленджа!')
            except Exception as _e:
                logging.error(_e)
    except Exception as _e:
        logging.error(_e)

async def stop_super_place():
    super_place_users = [user.user_id for user in DB.User.select(all_scalars=True, where=DB.User.super_place.is_(True))]
    winners = [random.choice(super_place_users)]
    _dispatch_to_winners(_make_text_alert(TEXT_SUPER_PLACE), winners)
    _dispatch_to_winners(_make_text_alert(NO_WINNER), list(set(super_place_users) - set(winners)))
    try:
        for winner in winners:
            try:
                user_data = DB.User.select(winner)
                await telegram.topic_manager.send_message(user_data.thread_id, 'Пользователь победит в розыгрыше супер места!')
            except Exception as _e:
                logging.error(_e)
    except Exception as _e:
        logging.error(_e)


def send_1840():
    _dispatch_to_users(_make_text_alert(TEXT_1840), buttons=[['Хочу на челлендж! ', 'call', 'client_challenge'], ['Хочу на супер место! ', 'call', 'super_place']])
