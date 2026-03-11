import asyncio

from aiogram.utils.markdown import hlink

from bot.utils.announce_bot import bot


async def main():
    url_link = f'tg://user?id={1127810972}'
    link_user = hlink('Пользователь', url_link)
    await bot.send_message(
        928877223,
        f'{link_user} найден!'
    )

    # data = await bot.get_forum_topic_icon_stickers()
    # data = dict(enumerate(map(str, data)))
    # for string in data:
    #     print(data[string ])

asyncio.run(main())