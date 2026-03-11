"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

# Пользователя(ей)
users_counter_ending = {0: 'ей', 1: 'ь', 2: 'я', 3: 'я', 4: 'я', 5: 'ей', 6: 'ей', 7: 'ей', 8: 'ей', 9: 'ей'}
# Вложения(ий)
files_counter_ending = {0: 'й', 1: 'е', 2: 'я', 3: 'я', 4: 'я', 5: 'й', 6: 'й', 7: 'й', 8: 'й', 9: 'й'}
# Раз(а)
once_ending = {0: '', 1: '', 2: 'а', 3: 'а', 4: 'а', 5: '', 6: '', 7: '', 8: '', 9: ''}


def last_number(number: int):
    return int(str(number)[-1])
