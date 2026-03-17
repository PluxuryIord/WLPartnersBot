# План изменений

## 1. KB: кнопка «Назад» на последнем сообщении
**Файл:** `bot/handlers/client/client_group.py`
- При отправке многочастных сообщений (фото+текст, фото+текст+текст2) собираем message_id каждого
- К ПОСЛЕДНЕМУ сообщению прикрепляем кнопку «🔙 К базе знаний» с callback_data `group_kb_back:{id1},{id2},...`
- Новый хендлер `group_kb_back` — парсит id из callback, удаляет все сообщения, отправляет меню базы знаний

**Файл:** `bot/keyboards/client/kb_client_group.py`
- Добавить функцию `back_to_kb_with_ids(message_ids)` для генерации inline-кнопки с id в callback_data

## 2. Авторизация: ввод email в боте вместо WebApp
**Файл:** `bot/keyboards/client/kb_client_menu.py`
- Заменить `auth_menu` — убрать WebApp кнопку, сделать обычную callback кнопку «Авторизоваться» → `client_auth_email`

**Файл:** `bot/handlers/client/client_main.py`
- Новый хендлер `start_auth_email` (callback `client_auth_email`): удаляет сообщение, отправляет «Введите email», ставит FSM state `FsmAuth.wait_email`
- Новый хендлер `process_auth_email` (FSM `FsmAuth.wait_email`):
  - Валидация формата email
  - Сохраняет в UserAuth (email, без токена)
  - Показывает authorized_menu
- Убрать WebApp-зависимый код

**Файл:** `bot/states/wait_question.py`
- FsmAuth уже есть с `wait_email` — используем

**Файл:** `admin_api.py`
- Убрать auth endpoint (POST /auth) — больше не нужен
- Убрать WebApp-related код (AUTHORIZED_KEYBOARD, tg_send_authorized_menu, etc.)

**Файл:** `webapp/auth.html`
- Больше не используется (можно оставить, но ссылки на него убираем)

## 3. Фото в базе знаний
- Нужны новые file_id от пользователя — спросить позже
