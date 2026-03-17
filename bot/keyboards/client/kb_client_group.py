from bot.utils.telegram import create_inline

# ── Group main menu ──────────────────────────────────────────────────────────

group_main_menu = create_inline([
    ['📢 Промо материалы', 'call', 'group_promo'],
    ['📅 Календарь спорт. событий', 'call', 'group_calendar'],
    ['🌐 Актуальные лендинги', 'call', 'group_landings'],
    ['📚 База знаний', 'call', 'group_knowledge_base'],
], 1)

promo_menu = create_inline([
    ['Открыть промо материалы', 'url', 'https://winline.tv/m/banner'],
    ['🔙 Меню', 'call', 'group_main_menu'],
], 1)

calendar_menu = create_inline([
    ['Открыть календарь', 'url', 'https://docs.google.com/spreadsheets/d/1zMg4sJlUUD2I-SPEUc7MRC6rRkbZHWpBju0vGlzNeIo/edit?gid=0#gid=0'],
    ['🔙 Меню', 'call', 'group_main_menu'],
], 1)

landings_menu = create_inline([
    ['🔙 Меню', 'call', 'group_main_menu'],
], 1)

knowledge_base_menu = create_inline([
    ['Обзор личного кабинета', 'call', 'group_kb_lk_overview'],
    ['Информация по офферу', 'call', 'group_kb_offer_info'],
    ['Генерация реф.ссылки', 'call', 'group_kb_ref_link'],
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


# ── PM (private message) keyboards ──────────────────────────────────────────

pm_knowledge_base_menu = create_inline([
    ['Обзор личного кабинета', 'call', 'pm_kb_lk_overview'],
    ['Информация по офферу', 'call', 'pm_kb_offer_info'],
    ['Генерация реф.ссылки', 'call', 'pm_kb_ref_link'],
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
    ['Открыть промо материалы', 'url', 'https://winline.tv/m/banner'],
    ['🔙 Меню', 'call', 'client_back_menu'],
], 1)
