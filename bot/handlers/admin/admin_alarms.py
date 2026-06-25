"""Admin command to run the trigger-alarm engine on demand.

  /run_alarms          → one pass using the configured dry-run mode (env)
  /run_alarms dry      → force dry-run (log only, send nothing)
  /run_alarms live     → force real send (ignores ALARMS_DRY_RUN)

Useful for testing without waiting for the scheduler. Respects ALARM_TEST_CHAT_ID
and ALARM_THRESHOLD_SCALE just like the scheduled pass.
"""
from aiogram import Dispatcher
from aiogram.filters.command import Command
from aiogram.types import Message

from bot.initialization import config
from bot.utils import alarms


async def run_alarms_cmd(message: Message):
    arg = ''
    parts = (message.text or '').split(maxsplit=1)
    if len(parts) > 1:
        arg = parts[1].strip().lower()

    if not alarms.ALARMS_ENABLED:
        await message.answer('⚠️ Алармы выключены: ALARMS_ENABLED=false в .env бота.')
        return

    # Report/preview: evaluate everyone, but send NOTHING to real users — only a
    # detailed report + 1 sample of each message to the test recipients
    # (ALARM_TEST_CHAT_ID list, or the admin who ran it).
    if arg in ('report', 'preview', 'отчет', 'отчёт'):
        recipients = alarms._TEST_CHAT_IDS or [message.from_user.id]
        await message.answer('⏳ Готовлю отчёт-превью (реальным юзерам ничего не отправляю)…')
        res = await alarms.run_preview(message.bot, recipients)
        if res.get('note'):
            await message.answer(f'ℹ️ {res["note"]}')
        elif res.get('preview'):
            await message.answer('✅ Отчёт отправлен получателям: '
                                 + ', '.join(map(str, res.get('recipients', []))))
        return

    dry_run = None
    if arg in ('dry', 'dryrun', 'dry-run'):
        dry_run = True
    elif arg in ('live', 'real', 'send'):
        dry_run = False

    await message.answer('⏳ Запускаю прогон алармов…')
    summary = await alarms.run_pass(message.bot, dry_run=dry_run)

    if not summary.get('enabled', True):
        await message.answer(f'Алармы выключены: {summary.get("note")}')
        return
    if summary.get('note'):
        await message.answer(f'ℹ️ {summary["note"]}')
        return

    fired = summary.get('fired', {})
    fired_lines = '\n'.join(f'  • {k}: {v}' for k, v in fired.items() if v) or '  —'
    mode = 'DRY-RUN (ничего не отправлено)' if summary.get('dry_run') else 'БОЕВОЙ'
    test_chat = summary.get('test_chat')
    cap_line = ''
    if summary.get('capped'):
        cap_line = (f'\n⚠️ Достигнут лимит отправок за проход '
                    f'(ALARM_MAX_SENDS_PER_PASS={alarms.ALARM_MAX_SENDS_PER_PASS}) — '
                    f'проход остановлен. Для боевого залпа подними лимит или 0.')
    text = (
        f'✅ Прогон завершён\n'
        f'Режим: <b>{mode}</b>\n'
        + (f'Тест-чат: <code>{test_chat}</code>\n' if test_chat else '')
        + f'Юзеров проверено: {summary.get("users", 0)}\n'
        f'Отправлено: {summary.get("sent", 0)} | dry: {summary.get("dryrun", 0)} | '
        f'пропущено (дедуп): {summary.get("skipped_dedup", 0)} | ошибок: {summary.get("failed", 0)}\n'
        f'Сработало по триггерам:\n{fired_lines}'
        + cap_line
    )
    await message.answer(text)


def register_handlers_admin_alarms(dp: Dispatcher):
    dp.message.register(run_alarms_cmd, Command(commands='run_alarms'), config.admin_filter)
