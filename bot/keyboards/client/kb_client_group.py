from bot.utils.telegram import create_inline

# ── Group main menu ──────────────────────────────────────────────────────────
group_main_menu = create_inline([
    ['📢 Промо материалы', 'call', 'group_promo'],
    ['📅 Календарь спорт. событий', 'call', 'group_calendar'],
    ['🌐 Актуальные лендинги', 'call', 'group_landings'],
    ['📚 База знаний', 'call', 'group_knowledge_base'],
], 1)

promo_menu = create_inline([
    ['Открыть креативы', 'url', 'https://winline.tv/m/banner'],
    ['🔙 Меню', 'call', 'group_main_menu'],
], 1)

calendar_menu = create_inline([
    ['Открыть календарь', 'url', 'https://docs.google.com/spreadsheets/d/1zMg4sJlUUD2I-SPEUc7MRC6rRkbZHWpBju0vGlzNeIo/edit?gid=0#gid=0'],
    ['🔙 Меню', 'call', 'group_main_menu'],
], 1)

landings_menu = create_inline([
    ['🔙 Меню', 'call', 'group_main_menu'],
], 1)

# Legacy static keyboards (kept for backward compat, but handlers now use build_kb_menu)
knowledge_base_menu = create_inline([
    ['Обзор личного кабинета', 'call', 'group_kb_lk_overview'],
    ['Информация по офферу', 'call', 'group_kb_offer_info'],
    ['Генерация реф. ссылки', 'call', 'group_kb_ref_link'],
    ['Настройка постбэка', 'call', 'group_kb_postback'],
    ['Скачивание отчета', 'call', 'group_kb_download_report'],
    ['🔙 Меню', 'call', 'group_main_menu'],
], 1)

back_to_knowledge_base = create_inline([
    ['🔙 К базе знаний', 'call', 'group_knowledge_base'],
], 1)

def back_to_kb_with_ids(message_ids: list[int]):
    """Back button that stores all message IDs to delete when pressed."""
    ids_str = ','.join(str(mid) for mid in message_ids)
    return create_inline([
        ['🔙 К базе знаний', 'call', f'group_kb_back:{ids_str}'],
    ], 1)


def build_kb_menu(kb_data: dict, prefix: str, back_callback: str):
    """Build dynamic KB menu from _meta in kb_data.
    prefix: 'group_kb_' or 'pm_kb_'
    back_callback: 'group_main_menu' or 'client_back_menu'
    Falls back to legacy hardcoded order if _meta is missing.
    """
    meta = kb_data.get('_meta', {})
    order = meta.get('order', [])
    titles = meta.get('titles', {})

    # Fallback: if _meta not yet migrated, use legacy keys
    if not order:
        LEGACY_ORDER = ['lk_overview', 'offer_info', 'ref_link', 'postback', 'download_report', 'download_report_2']
        LEGACY_TITLES = {
            'lk_overview': 'Обзор личного кабинета',
            'offer_info': 'Информация по офферу',
            'ref_link': 'Генерация реф. ссылки',
            'postback': 'Настройка постбэка',
            'download_report': 'Скачивание отчета',
            'download_report_2': 'Отчет «Конверсии»',
        }
        order = [k for k in LEGACY_ORDER if k in kb_data]
        titles = LEGACY_TITLES

    buttons = []
    for key in order:
        title = titles.get(key, key)
        buttons.append([title, 'call', f'{prefix}{key}'])
    buttons.append(['🔙 Меню', 'call', back_callback])
    return create_inline(buttons, 1)


# ── PM (private message) keyboards ──────────────────────────────────────────

pm_knowledge_base_menu = create_inline([
    ['Обзор личного кабинета', 'call', 'pm_kb_lk_overview'],
    ['Информация по офферу', 'call', 'pm_kb_offer_info'],
    ['Генерация реф. ссылки', 'call', 'pm_kb_ref_link'],
    ['Настройка постбэка', 'call', 'pm_kb_postback'],
    ['Скачивание отчета', 'call', 'pm_kb_download_report'],
    ['🔙 Меню', 'call', 'client_back_menu'],
], 1)

pm_back_to_knowledge_base = create_inline([
    ['🔙 К базе знаний', 'call', 'pm_knowledge_base'],
], 1)

def pm_back_to_kb_with_ids(message_ids: list[int]):
    """PM back button that stores all message IDs to delete when pressed."""
    ids_str = ','.join(str(mid) for mid in message_ids)
    return create_inline([
        ['🔙 К базе знаний', 'call', f'pm_kb_back:{ids_str}'],
    ], 1)

pm_promo_menu = create_inline([
    ['Открыть креативы', 'url', 'https://winline.tv/m/banner'],
    ['🔙 Меню', 'call', 'client_back_menu'],
], 1)
