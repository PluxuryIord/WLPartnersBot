"""Build inline keyboards dynamically from bot_scenarios in DB."""
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
