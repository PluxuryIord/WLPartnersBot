from aiogram import F, types, Dispatcher
from aiogram.types import ReactionTypeEmoji

from bot.integrations import DB
from bot.utils import telegram


async def appeal_decided(call: types.CallbackQuery):
    await call.message.react(reaction=[ReactionTypeEmoji(emoji="👍")], is_big=True)
    await call.message.edit_text(call.message.html_text.replace('Открыто', 'Решено'), reply_markup=None)
    await telegram.topic_manager.edit_topic(
        name=None,
        thread_id=call.message.message_thread_id,
        emoji_id='5237699328843200968'
    )
    DB.Support.update(mark=int(call.data.split(':')[1]), status='Решено', status_open=0)

async def appeal_closed(call: types.CallbackQuery):
    await call.message.react(reaction=[ReactionTypeEmoji(emoji="👎")], is_big=True)
    await call.message.edit_text(call.message.html_text.replace('Открыто', 'Закрыто'), reply_markup=None)
    await telegram.topic_manager.edit_topic(
        name=None,
        thread_id=call.message.message_thread_id,
        emoji_id='5377498341074542641'
    )
    DB.Support.update(mark=int(call.data.split(':')[1]), status='Закрыто', status_open=0)


async def appeal_bug(call: types.CallbackQuery):
    await call.message.react(reaction=[ReactionTypeEmoji(emoji="👨‍💻")], is_big=True)
    await call.message.edit_text(call.message.html_text.replace('Открыто', 'Передано разработчику'),
                                 reply_markup=None)
    await telegram.topic_manager.edit_topic(
        name=None,
        thread_id=call.message.message_thread_id,
        emoji_id='5309832892262654231'
    )
    DB.Support.update(mark=int(call.data.split(':')[1]), status='Передано разработчику', status_open=1)
    thread_url = telegram.topic_manager.topic_url(call.message.message_thread_id)
    await call.message.bot.send_message(
        928877223,
        f'<b>В обращении №<code>{int(call.data.split(":")[1])}</code> нужна помощь разработчика!</b>',
        reply_markup=telegram.create_inline([['⤴️Открыть диалог', 'url', thread_url]], 1)
    )

def register_admin_handlers_support(dp: Dispatcher):
    dp.callback_query.register(appeal_decided, F.data.startswith('admin_support_decided'))
    dp.callback_query.register(appeal_closed, F.data.startswith('admin_support_closed'))
    dp.callback_query.register(appeal_bug, F.data.startswith('admin_support_call_dev'))