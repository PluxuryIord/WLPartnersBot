"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram.client.default import DefaultBotProperties
from pydantic import ValidationError

if TYPE_CHECKING:
    from typing import List, Optional, Union, Literal

    from aiogram.types import InlineQuery, User, MessageEntity
    from aiogram.fsm.context import FSMContext
    from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply, InputFile
    from aiogram.utils.keyboard import InlineKeyboardMarkup

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types.base import UNSET_DISABLE_WEB_PAGE_PREVIEW, UNSET_PROTECT_CONTENT, UNSET_PARSE_MODE
from aiogram.types import InputMediaPhoto, InputMediaDocument, InputMediaAnimation, InputMediaVideo
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.utils.markdown import hlink
from aiogram.exceptions import TelegramAPIError

import asyncio

import itertools

from bot.initialization import config
from bot.integrations import DB
from bot.utils import files
from bot.utils.announce_bot import bot, dp


def generate_user_hlink(update: Union[Message, CallbackQuery] = None,
                        user_id: int = None,
                        user_name: str = None,
                        text_link: str = None) -> Optional[str]:
    if update:
        text_link = update.from_user.full_name
        url_link = f'tg://user?id={update.from_user.id}'
        user_name = update.from_user.username
    else:
        if not user_id or not text_link:
            raise AttributeError('User id and text link is not None')
        url_link = f'tg://user?id={user_id}'
    more_info = f'(@{user_name})' if user_name else ''
    url_user = hlink(text_link, url_link)
    hlink_user = f'{url_user} {more_info}'
    return hlink_user


def generate_hlink(text_link: str, url_link: str) -> hlink:
    link = hlink(text_link, url_link)
    return link


def repack_keyboard(buttons: list):
    repack_buttons = []
    for button in buttons:
        if button[1] == 'call':
            repack_buttons.append([InlineKeyboardButton(text=button[0], callback_data=button[2])])
        elif button[1] == 'url':
            repack_buttons.append([InlineKeyboardButton(text=button[0], url=button[2])])
        elif button[1] == 'inline':
            repack_buttons.append([InlineKeyboardButton(text=button[0], switch_inline_query_current_chat=button[2])])
    return repack_buttons


def create_inline(buttons: list, adjust: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardBuilder(markup=repack_keyboard(buttons))
    return markup.adjust(adjust).as_markup(resize_keyboard=True)


def generate_rows_markup(buttons: list, rows: list) -> List[List[InlineKeyboardButton]] | str:
    markup = []
    counter_button = 0
    for i in range(0, len(rows)):
        buttons_row = []
        for i2 in range(rows[i]):
            try:
                buttons_row.append(buttons[counter_button][0])
                counter_button += 1
            except IndexError:
                raise AttributeError('ERROR: Wrong rows specified')
        markup.append(buttons_row)
    return markup


def create_inline_rows(buttons: list, rows: list) -> str | InlineKeyboardMarkup:
    markup = generate_rows_markup(repack_keyboard(buttons), rows)
    markup = InlineKeyboardBuilder(markup=markup)
    return markup.as_markup(resize_keyboard=True)


def generate_url_buttons(buttons_info: List[List[str]]) -> InlineKeyboardMarkup:
    buttons = []
    for button in buttons_info:
        buttons.append([button[0], 'url', button[1]])
    markup = create_inline(buttons, 1)
    return markup


async def get_bot_data(bot_object: Bot) -> User:
    return await bot_object.me()


async def delete_message(event: Union[CallbackQuery, Message] = False,
                         chat_id: Optional[int] = 0,
                         message_id: Optional[int] = 0,
                         try_redact: bool = True):
    if event:
        if isinstance(event, CallbackQuery):
            message_id = event.message.message_id
            chat_id = event.message.chat.id
        else:
            message_id = event.message_id
            chat_id = event.chat.id
    else:
        if not message_id:
            raise AttributeError('Message ID is None!')
    try:
        await bot.delete_message(chat_id, message_id)
        return True
    except TelegramAPIError:
        if try_redact:
            try:
                await bot.edit_message_text('🗑', chat_id, message_id)
                return True
            except (TelegramAPIError, ValidationError):
                return False
        else:
            return False


async def inline_helper(query: InlineQuery, results: list[list[str]], no_result: int = 0):
    """
    :param no_result: minimum number of results
    :param query: event InlineQuery
    :param results: list[title, description, url, message_text]
    :return:
    """
    offset = int(query.offset) if query.offset else 0
    offset_results = results[offset:offset + 50]
    articles = []
    article_index = 0
    for result in offset_results:
        if article_index == 50:
            break
        articles.append(InlineQueryResultArticle(
            id=str(article_index),
            title=result[0],
            description=result[1],
            thumb_url=result[2],
            input_message_content=InputTextMessageContent(message_text=result[3])
        ))
        article_index += 1
    if len(results) > offset + 50:
        await query.answer(articles, cache_time=1, is_personal=True, next_offset=str(offset + 50))
    else:
        if len(results) == no_result:
            articles.append(InlineQueryResultArticle(
                id='0', title='😔Нет результатов', description='По данному запросу ничего не найдено',
                thumb_url='https://cdn-icons-png.flaticon.com/512/7214/7214241.png',
                input_message_content=InputTextMessageContent(message_text='/start')))
        await query.answer(articles, cache_time=1, is_personal=True)


async def is_sub(chat_id: int, user_id: int):
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if 'left' in member.status:
            return False
        else:
            return member
    except TelegramAPIError:
        return False


async def edit_text_from_id(
        message_id: int,
        chat_id: int,
        text: str,
        inline_message_id: Optional[str] = None,
        parse_mode: Optional[str] = UNSET_PARSE_MODE,
        entities: Optional[List[MessageEntity]] = None,
        disable_web_page_preview: Optional[bool] = UNSET_DISABLE_WEB_PAGE_PREVIEW,
        reply_markup: Optional[InlineKeyboardMarkup] = None):
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, inline_message_id=inline_message_id,
            parse_mode=parse_mode, entities=entities,
            disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        return False


async def edit_text(
        message: Message,
        text: str,
        inline_message_id: Optional[str] = None,
        parse_mode: Optional[str] = UNSET_PARSE_MODE,
        entities: Optional[List[MessageEntity]] = None,
        disable_web_page_preview: Optional[bool] = UNSET_DISABLE_WEB_PAGE_PREVIEW,
        reply_markup: Optional[InlineKeyboardMarkup] = None):
    try:
        await message.edit_text(
            text=text, inline_message_id=inline_message_id, parse_mode=parse_mode, entities=entities,
            disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        return False


async def send_message(
        chat_id: Union[int, str],
        text: str,
        message_thread_id: Optional[int] = None,
        parse_mode: Optional[str] = UNSET_PARSE_MODE,
        entities: Optional[List[MessageEntity]] = None,
        disable_web_page_preview: Optional[bool] = UNSET_DISABLE_WEB_PAGE_PREVIEW,
        disable_notification: Optional[bool] = None,
        protect_content: Optional[bool] = UNSET_PROTECT_CONTENT,
        reply_to_message_id: Optional[int] = None,
        allow_sending_without_reply: Optional[bool] = None,
        reply_markup: Optional[
            Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply]
        ] = None,
        request_timeout: Optional[int] = None) -> Message | bool:
    try:
        message = await bot.send_message(
            chat_id=chat_id, text=text, message_thread_id=message_thread_id, parse_mode=parse_mode, entities=entities,
            disable_web_page_preview=disable_web_page_preview, disable_notification=disable_notification,
            protect_content=protect_content, reply_to_message_id=reply_to_message_id,
            allow_sending_without_reply=allow_sending_without_reply, reply_markup=reply_markup,
            request_timeout=request_timeout)
        return message
    except TelegramAPIError as err:
        logging.debug(str(err))
        return False


async def send_document(
        chat_id: Union[int, str],
        document: InputFile | str,
        message_thread_id: Optional[int] = None,
        thumbnail: InputFile | str = None,
        caption: str = None,
        parse_mode: Optional[str] = UNSET_PARSE_MODE,
        caption_entities: Optional[List[MessageEntity]] = None,
        disable_content_type_detection: bool | None = None,
        disable_notification: Optional[bool] = None,
        protect_content: Optional[bool] = UNSET_PROTECT_CONTENT,
        reply_to_message_id: Optional[int] = None,
        allow_sending_without_reply: Optional[bool] = None,
        reply_markup: Optional[
            Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply]
        ] = None,
        request_timeout: Optional[int] = None) -> Message | bool:
    try:
        message = await bot.send_document(
            chat_id=chat_id, document=document, message_thread_id=message_thread_id, caption=caption,
            thumbnail=thumbnail, parse_mode=parse_mode, caption_entities=caption_entities,
            disable_content_type_detection=disable_content_type_detection, disable_notification=disable_notification,
            protect_content=protect_content, reply_to_message_id=reply_to_message_id,
            allow_sending_without_reply=allow_sending_without_reply, reply_markup=reply_markup,
            request_timeout=request_timeout)
        return message
    except TelegramAPIError as err:
        logging.debug(str(err))
        return False


def input_media(media_type: str, media: str, caption: str):
    match media_type:
        case 'photo':
            return InputMediaPhoto(media=media, caption=caption)
        case 'document':
            return InputMediaDocument(media=media, caption=caption)
        case 'animation':
            return InputMediaAnimation(media=media, caption=caption)
        case 'video':
            return InputMediaVideo(media=media, caption=caption)


async def message_constructor(chat_id: int, data: dict) -> list[Message] | bool:
    text, message_files, buttons = data['text'], data['files'], data['buttons']
    buttons = create_inline(buttons, 1)
    try:
        if len(message_files) > 1:
            media_group = []
            for i in range(len(message_files)):
                file_type, file_id = message_files[i][0], message_files[i][1]
                caption = text if (i == 0 and text) else None
                media_group.append(input_media(media_type=file_type, media=file_id, caption=caption))
            messages: list[Message] = await bot.send_media_group(chat_id=chat_id, media=media_group)
            return messages
        else:
            if not message_files:
                message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=buttons)
            else:
                match message_files[0][0]:
                    case 'photo':
                        message = await bot.send_photo(chat_id=chat_id, photo=message_files[0][1],
                                                       caption=text, reply_markup=buttons)
                    case 'video':
                        message = await bot.send_video(chat_id=chat_id, video=message_files[0][1],
                                                       caption=text, reply_markup=buttons)
                    case 'document':
                        message = await bot.send_document(chat_id=chat_id, document=message_files[0][1],
                                                          caption=text, reply_markup=buttons)
                    case 'animation':
                        message = await bot.send_animation(chat_id=chat_id, animation=message_files[0][1],
                                                           caption=text, reply_markup=buttons)
                    case 'sticker':
                        message = await bot.send_sticker(chat_id=chat_id, sticker=message_files[0][1],
                                                         reply_markup=buttons)
                    case 'video_note':
                        message = await bot.send_video_note(chat_id=chat_id, video_note=message_files[0][1],
                                                            reply_markup=buttons)
                    case 'voice':
                        message = await bot.send_voice(chat_id=chat_id, voice=message_files[0][1],
                                                       reply_markup=buttons)
                    case _:
                        return False
            return [message]
    except TelegramRetryAfter as body:
        await asyncio.sleep(body.retry_after)
        return await message_constructor(chat_id, data)
    except TelegramAPIError:
        return False


async def get_input_file(message: Message, state: FSMContext) -> bool | tuple[list, Message]:
    await message.delete()
    storage = await state.get_data()
    menu: Message = storage.get('menu')
    try:
        await menu.edit_text('⏳')
        if not message.document or '.txt' not in message.document.file_name:
            await menu.edit_text(f'<b>❌Пожалуйста, отправьте txt файл или нажмите "Отменить"!</b>',
                                 reply_markup=kb_delete_message)
        else:
            file = await bot.get_file(message.document.file_id)
            temp_path = files.get_random_path('txt')
            await bot.download_file(file.file_path, temp_path)
            lines = files.read_txt(temp_path).split('\n')
            files.remove_file(temp_path)
            return lines, menu
    except TelegramAPIError:
        ...
    return False


async def get_state(chat_id: int, user_id: int) -> FSMContext:
    return dp.fsm.resolve_context(bot, chat_id=chat_id, user_id=user_id)


def unpack_media_group(messages: List[Message], special_format: Literal['no_caption', 'input_media'] = False):
    media_files = []
    for message in messages:
        if message.document:
            media_files.append(['document', message.document.file_id, message.html_text])
        elif message.photo:
            media_files.append(['photo', message.photo[-1].file_id, message.html_text])
        elif message.audio:
            media_files.append(['audio', message.audio.file_id, message.html_text])
        elif message.animation:
            media_files.append(['animation', message.animation.file_id, message.html_text])
        elif message.video:
            media_files.append(['video', message.video.file_id, message.html_text])
    if special_format:
        if special_format == 'no_caption':
            media_files = [[message[0], message[1]] for message in media_files]
        elif special_format == 'input_media':
            media_files = [input_media(media[0], media[1], media[2]) for media in media_files]
    return media_files


class TopicManager:
    def __init__(self):
        self.bots = itertools.cycle([Bot(token=alert_bot, default=DefaultBotProperties(parse_mode='HTML', link_preview_is_disabled=True)) for alert_bot in config.alert_bots])
        self.bot_group = DB.Settings.select().bot_group
        self.alert = DB.Settings.select().alert_thread

    async def create_topic(self, name: str, emoji_id: int):
        topic = await next(self.bots).create_forum_topic(
            chat_id=self.bot_group,
            name=name,
            icon_custom_emoji_id=str(emoji_id))
        return topic.message_thread_id

    async def create_user_topic(self, first_name: str):
        return await self.create_topic(f'{first_name} [Пользователь]', 5417915203100613993)

    async def send_message(self, thread_id: int, text: str,
                           reply_markup: InlineKeyboardMarkup = None, main_bot: bool = False,
                           reply_to_message_id: int = None):
        bot_obj = bot if main_bot else next(self.bots)
        message = await bot_obj.send_message(chat_id=self.bot_group,
                                             message_thread_id=thread_id,
                                             text=text,
                                             reply_to_message_id=reply_to_message_id,
                                             reply_markup=reply_markup)
        return message

    async def edit_topic(self, name: str | bool = None, general: bool = False, thread_id: int = None, emoji_id: str = None):
        if general:
            await next(self.bots).edit_general_forum_topic(self.bot_group, name)
        else:
            if not thread_id:
                raise Exception('thread_id not specified')
            await next(self.bots).edit_forum_topic(self.bot_group, thread_id, name, emoji_id)

    def topic_url(self, thread_id: int):
        str_bot_group = str(self.bot_group)
        str_bot_group = str_bot_group.replace('-100', '')
        return f'https://t.me/c/{str_bot_group}/{thread_id}'


topic_manager = TopicManager()
kb_delete_message = create_inline([['✅Прочитано', 'call', 'client_delete_message']], 1)
kb_back_menu = create_inline([['🔙 Меню', 'call', 'client_back_menu']], 1)
