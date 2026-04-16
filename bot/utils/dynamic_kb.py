"""Build inline keyboards dynamically from bot_scenarios in DB."""
import logging

logger = logging.getLogger('wl_bot')

from bot.integrations import DB
from bot.utils.telegram import create_inline

_cache = {'data': None}


def _load():
    """Load bot_scenarios from DB into cache."""
    try:
        row = DB.Text.select(where=DB.Text.category == 'bot_scenarios')
        if row and row.data:
            d = row.data if isinstance(row.data, dict) else {}
            _cache['data'] = d
            return d
    except Exception:
        pass
    return _cache.get('data') or {}


def reload():
    """Force reload from DB."""
    _cache['data'] = None
    return _load()


def get_screen_kb(screen_id, extra_buttons=None, cols=1):
    """Build inline keyboard for a screen from scenarios data.

    extra_buttons: list of [label, type, data] to append (e.g. admin button)
    Returns InlineKeyboardMarkup or None if screen not found.
    """
    data = _cache.get('data') or _load()
    screens = data.get('screens', {})
    screen = screens.get(screen_id)
    if not screen or not screen.get('buttons'):
        return None

    buttons_def = screen['buttons']
    order = buttons_def.get('_order', [])

    buttons = []
    for key in order:
        btn = buttons_def.get(key)
        if not btn:
            continue
        action = btn.get('action', '')
        label = btn.get('label', '???')
        if action.startswith('url:'):
            url = action[4:]
            buttons.append([label, 'url', url])
        elif action.startswith('callback:'):
            cb = action[9:]
            buttons.append([label, 'call', cb])
        else:
            buttons.append([label, 'call', action])

    if extra_buttons:
        buttons.extend(extra_buttons)

    if not buttons:
        return None
    return create_inline(buttons, cols)


def get_screen_kb_filtered(screen_id, extra_buttons=None, skip_actions=None, cols=1):
    """Like get_screen_kb but can skip buttons by action substring."""
    data = _cache.get('data') or _load()
    screens = data.get('screens', {})
    screen = screens.get(screen_id)
    if not screen or not screen.get('buttons'):
        return None

    buttons_def = screen['buttons']
    order = buttons_def.get('_order', [])
    skip = skip_actions or []

    buttons = []
    for key in order:
        btn = buttons_def.get(key)
        if not btn:
            continue
        action = btn.get('action', '')
        label = btn.get('label', '???')

        # Skip if action matches any skip pattern
        if any(s in action for s in skip):
            continue

        if action.startswith('url:'):
            buttons.append([label, 'url', action[4:]])
        elif action.startswith('callback:'):
            buttons.append([label, 'call', action[9:]])
        else:
            buttons.append([label, 'call', action])

    if extra_buttons:
        buttons.extend(extra_buttons)

    if not buttons:
        return None
    return create_inline(buttons, cols)


# ─── Anketa flow helpers ─────────────────────────────────────────────────────

def get_screen(screen_id):
    """Get raw screen data dict."""
    data = _cache.get('data') or _load()
    return data.get('screens', {}).get(screen_id)


def get_anketa_screens():
    """Get all screens with scenario=5 (anketa flow screens)."""
    data = _cache.get('data') or _load()
    screens = data.get('screens', {})
    return {sid: s for sid, s in screens.items() if s.get('scenario') == 5}


def find_first_anketa_screen():
    """
    Find the entry point of the anketa flow.
    Prefers `anketa_role` (fixed entry point), falls back to first scenario:5 screen.
    """
    data = _cache.get('data') or _load()
    screens = data.get('screens', {})
    if 'anketa_role' in screens and screens['anketa_role'].get('scenario') == 5:
        return 'anketa_role'
    # Fallback: return first scenario:5 screen found
    for sid, s in screens.items():
        if s.get('scenario') == 5:
            return sid
    return None


def get_screen_text(screen_id):
    """Get the first message text from a screen."""
    data = _cache.get('data') or _load()
    screen = data.get('screens', {}).get(screen_id)
    if not screen:
        return ''
    messages = screen.get('messages', {})
    for key in messages:
        text = messages[key].get('text', '')
        if text:
            return text
    return screen.get('title', '')
