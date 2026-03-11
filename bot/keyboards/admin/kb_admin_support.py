from bot.utils.telegram import create_inline


def support_kb(support_id: int):
    return create_inline(
        [
            ['✅ Решено', 'call', f'admin_support_decided:{support_id}'],
            ['❌ Закрыть', 'call', f'admin_support_closed:{support_id}'],
            ['🛠 Передать разработчику', 'call', f'admin_support_call_dev:{support_id}'],
        ],
        2
    )
