"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
# Site Company: buy-bot.ru

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message
    from aiogram import Dispatcher
    from aiogram.fsm.context import FSMContext

import hashlib
import hmac
import json
import logging

import aiohttp
from aiogram.exceptions import TelegramAPIError

from bot.handlers.client import client_main
from bot.integrations import DB
from bot.keyboards.admin import kb_admin_topic
from bot.utils import telegram as telegram
from bot.utils.announce_bot import bot
from bot.handlers.client.client_main import back_menu
from bot.initialization import config


def _extract_media(msg):
    """Extract media info from a single aiogram Message."""
    if msg.photo:
        return {'file_id': msg.photo[-1].file_id, 'mime_type': 'image/jpeg'}
    elif msg.document:
        return {'file_id': msg.document.file_id, 'file_name': msg.document.file_name or 'file',
                'mime_type': msg.document.mime_type or 'application/octet-stream'}
    elif msg.video:
        return {'file_id': msg.video.file_id, 'mime_type': msg.video.mime_type or 'video/mp4'}
    elif msg.voice:
        return {'file_id': msg.voice.file_id, 'mime_type': msg.voice.mime_type or 'audio/ogg'}
    elif msg.audio:
        return {'file_id': msg.audio.file_id, 'mime_type': msg.audio.mime_type or 'audio/mpeg'}
    elif msg.sticker:
        s = msg.sticker
        info = {
            'file_id': s.file_id,
            'file_unique_id': s.file_unique_id,
            'mime_type': 'image/webp',
            'is_animated': bool(s.is_animated),
            'is_video': bool(s.is_video),
        }
        if s.is_video:
            info['mime_type'] = 'video/webm'
        if s.thumbnail:
            info['thumbnail'] = {
                'file_id': s.thumbnail.file_id,
                'file_unique_id': s.thumbnail.file_unique_id,
            }
        return info
    return None


async def _notify_admin_panel(message, album=None):
    """POST message to admin panel webhook so it appears in web chat."""
    url = config.admin_panel_webhook
    secret = config.admin_panel_webhook_secret
    if not url:
        return

    user = message.from_user
    caption = message.text or message.caption or ''
    if album:
        for msg in album:
            cap = msg.text or msg.caption or ''
            if cap:
                caption = cap
                break

    payload = {
        'user_id': user.id,
        'text': caption,
        'username': user.username or '',
        'full_name': user.full_name or '',
    }

    if album:
        media_items = []
        for msg in album:
            m = _extract_media(msg)
            if m:
                media_items.append(m)
        if media_items:
            payload['media'] = media_items
    else:
        m = _extract_media(message)
        if m:
            if message.photo:
                payload['photo'] = m
            elif message.document:
                payload['document'] = m
            elif message.video:
                payload['video'] = m
            elif message.voice:
                payload['voice'] = m
            elif message.audio:
                payload['audio'] = m
            elif message.sticker:
                payload['sticker'] = m
        elif getattr(message, 'poll', None):
            p = message.poll
            payload['poll'] = {
                'question': p.question or '',
                'options': [o.text for o in (p.options or [])],
                'is_anonymous': bool(getattr(p, 'is_anonymous', True)),
                'allows_multiple_answers': bool(getattr(p, 'allows_multiple_answers', False)),
                'type': getattr(p, 'type', 'regular'),

            }

    body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if secret:
        signature = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
        headers['x-webhook-signature'] = signature

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=body, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logging.warning(f'[admin_panel_webhook] {resp.status}: {body[:200]}')
    except Exception as e:
        logging.warning(f'[admin_panel_webhook] Failed: {e}')


async def not_handled_callback(call: CallbackQuery, state: FSMContext):
    logging.error(f'Not handled | DATA: {call.data} | State: {await state.get_state()}')
    await call.answer('🚫Произошла ошибка при нажатии кнопки, повторите попытку',
                      show_alert=True)
    await back_menu(call, state)


async def not_handled_message(message: Message, state: FSMContext,
                              user_data: DB.User | None = None, album: list[Message] = False):
    forward_message = None

    if message.chat.type == 'private':
        if message.text and message.text.lower() in ['старт', 'перезапустить', 'перезапуск', 'начать',
                                                     'запустить', 'запуск', 'start']:
            return await client_main.main_menu(message, message.from_user, user_data, state)
        elif user_data:
            if message.reply_to_message:
                if message.reply_to_message.from_user.id == message.from_user.id:
                    message_data = DB.ForwardTopicMessages.select(
                        where=[
                            DB.ForwardTopicMessages.chat_id == message.from_user.id,
                            DB.ForwardTopicMessages.message_id == message.reply_to_message.message_id,
                            DB.ForwardTopicMessages.from_entity == 'user'
                        ])
                    if message_data:
                        forward_message = message_data.forward_message_id
                else:
                    message_data = DB.ForwardTopicMessages.select(
                        where=[
                            DB.ForwardTopicMessages.chat_id == message.from_user.id,
                            DB.ForwardTopicMessages.forward_message_id == message.reply_to_message.message_id,
                            DB.ForwardTopicMessages.from_entity == 'bot'
                        ]
                    )
                    if message_data:
                        forward_message = message_data.message_id
            if not album:
                if forward_message:
                    await telegram.topic_manager.send_message(
                        thread_id=user_data.thread_id,
                        text='Ответ на сообщение:',
                        reply_to_message_id=forward_message
                    )
                mess = await bot.forward_message(chat_id=telegram.topic_manager.bot_group,
                                                 from_chat_id=message.chat.id,
                                                 message_id=message.message_id,
                                                 message_thread_id=user_data.thread_id)
            else:
                mess = await bot.send_media_group(chat_id=telegram.topic_manager.bot_group,
                                                  media=telegram.unpack_media_group(album, 'input_media'),
                                                  message_thread_id=user_data.thread_id,
                                                  reply_to_message_id=forward_message)
                mess = mess[0]
            DB.ForwardTopicMessages.add(message.from_user.id, message.message_id, mess.message_id, 'user')

            # Notify admin panel web chat
            await _notify_admin_panel(message, album=album if album else None)
    elif message.message_thread_id and message.chat.id == telegram.topic_manager.bot_group:
        thread_user = DB.User.select(where=DB.User.thread_id == message.message_thread_id)
        if thread_user:
            if message.text and message.text[0] == '!':
                return await message.reply('<b>✅Заметка сохранена</b>')
            elif message.text and message.text[0] == '/':
                return await message.reply('<b>❌Команда не найдена!</b>')
            try:
                if message.reply_to_message:
                    if message.reply_to_message.from_user.is_bot:
                        message_data = DB.ForwardTopicMessages.select(
                            where=[
                                DB.ForwardTopicMessages.chat_id == thread_user.user_id,
                                DB.ForwardTopicMessages.forward_message_id == message.reply_to_message.message_id,
                                DB.ForwardTopicMessages.from_entity == 'user'
                            ])
                        if message_data:
                            forward_message = message_data.message_id
                    else:
                        message_data = DB.ForwardTopicMessages.select(
                            where=[
                                DB.ForwardTopicMessages.chat_id == thread_user.user_id,
                                DB.ForwardTopicMessages.message_id == message.reply_to_message.message_id,
                                DB.ForwardTopicMessages.from_entity == 'bot'
                            ])
                        if message_data:
                            forward_message = message_data.forward_message_id

                if not album:
                    message_new = await bot.copy_message(chat_id=thread_user.user_id,
                                                         from_chat_id=message.chat.id,
                                                         message_id=message.message_id,
                                                         reply_to_message_id=forward_message,
                                                         allow_sending_without_reply=True)
                    db_id = DB.TopicMessages.add(thread_user.user_id, False if message.text else True,
                                                 [message_new.message_id], message.from_user.id)
                    DB.ForwardTopicMessages.add(thread_user.user_id, message.message_id, message_new.message_id, 'bot')
                    await message.reply(
                        '✅Сообщение отправлено', reply_markup=kb_admin_topic.topic_message(message, db_id))
                else:
                    messages = await bot.send_media_group(chat_id=thread_user.user_id,
                                                          media=telegram.unpack_media_group(album, 'input_media'),
                                                          reply_to_message_id=forward_message,
                                                          allow_sending_without_reply=True)
                    db_id = DB.TopicMessages.add(thread_user.user_id, True, [mess.message_id for mess in messages],
                                                 message.from_user.id)
                    for msg in messages:
                        DB.ForwardTopicMessages.add(thread_user.user_id, msg.message_id, msg.message_id, 'bot')
                    await message.reply('✅Группа вложений отправлена',
                                        reply_markup=kb_admin_topic.topic_message(album[0], db_id))
            except TelegramAPIError as exc:
                str_exc = str(exc)
                if 'user was deleted' in str_exc:
                    await message.reply(f'❌Сообщение не доставлено: пользователь удален')
                elif 'message is too long' in str_exc:
                    await message.reply(f'❌Сообщение не доставлено: сообщение слишком длинное')
                elif 'bot was blocked by the user' in str_exc:
                    await message.reply(f'❌Сообщение не доставлено: пользователь заблокировал бота')
                else:
                    await message.reply(f'❌Сообщение не доставлено: {exc.message}')


def register_not_handled(dp: Dispatcher):
    dp.callback_query.register(not_handled_callback)
    dp.message.register(not_handled_message)
