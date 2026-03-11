"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from bot.integrations import DB
from bot.initialization import config

admin_accesses = {
    'alert': ['📩|Меню рассылок', 'admin_alert'],
    'notifications': ['🔔|Настройка уведомлений', 'admin_notifications'],
    'admins': ['👥|Администраторы', 'admin_admins'],
    'bot_info': ['🔐|Данные и статистика', 'admin_bot_info'],
    'qr_generator': ['📷|QR генератор', 'admin_qr_generator']
}

null_admin_access = {access: False for access in admin_accesses}
full_admin_access = {access: True for access in admin_accesses}

for admin in DB.Admin.select(all_scalars=True):
    admin_access = admin.access.copy()
    for access in admin_accesses:
        if access not in admin_access:
            if config.admin_filter.is_system(admin.admin_id):
                admin_access[access] = True
            else:
                admin_access[access] = False
    if admin_access != admin.access:
        DB.Admin.update(mark=admin.admin_id, access=admin_access)
