"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

import json
import os
import random
import string
from os import path
from typing import Literal

from aiogram.types.input_file import FSInputFile

from bot.utils.dt import now


def get_random_path(file_type: Literal['txt', 'json', 'xlsx'], k: int = 5):
    temp_path = 'temp/' + now('path') + ' ' + ''.join(random.choices(string.hexdigits, k=k)) + f'.{file_type}'
    if path.exists(temp_path):
        return get_random_path(file_type, k + 1)
    return temp_path


def create_txt(text: str, aiogram: bool = False, output_file_name: str = 'result') -> str | tuple:
    random_path = get_random_path('txt')
    with open(random_path, 'w', encoding='utf-8') as file:
        file.write(text)
    if aiogram:
        input_file = FSInputFile(random_path, filename=f'{output_file_name}.txt')
        return input_file, random_path
    else:
        return random_path


def read_txt(file_path: str) -> str | bool:
    try:
        with open(file_path, encoding="utf8") as file:
            return file.read()
    except FileNotFoundError:
        return False


def open_json_file(file_path: str) -> dict | bool:
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return False


def save_json(data: dict, file_path: str = None) -> str:
    if not file_path:
        file_path = get_random_path('json')
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    return file_path


def rename_file(old_path: str, new_path: str) -> bool:
    try:
        os.rename(old_path, new_path)
        return True
    except (FileNotFoundError, PermissionError):
        return False


def remove_file(path_path: str) -> bool:
    try:
        os.remove(path_path)
        return True
    except (FileNotFoundError, PermissionError):
        return False
