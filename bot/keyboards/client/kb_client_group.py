from bot.utils.telegram import create_inline

promo_menu = create_inline([
    ['Открыть промо материалы', 'url', 'https://winline.tv/m/banner'],
], 1)

calendar_menu = create_inline([
    ['Открыть календарь', 'url', 'https://docs.google.com/spreadsheets/d/PLACEHOLDER'],
], 1)

knowledge_base_menu = create_inline([
    ['Обзор личного кабинета', 'call', 'group_kb_lk_overview'],
    ['Информация по офферу', 'call', 'group_kb_offer_info'],
    ['Генерация реф.ссылки', 'call', 'group_kb_ref_link'],
    ['Настройка постбэка', 'call', 'group_kb_postback'],
    ['Скачивание отчета', 'call', 'group_kb_download_report'],
], 1)

back_to_knowledge_base = create_inline([
    ['🔙 К базе знаний', 'call', 'group_knowledge_base'],
], 1)
