import time
from bot.integrations import DB

_cache = {'settings': None, 'ts': 0}
TTL = 30  # секунд

def get_settings_cached():
    now = time.time()
    if _cache['settings'] and (now - _cache['ts']) < TTL:
        return _cache['settings']
    s = DB.Settings.select()
    _cache['settings'] = s
    _cache['ts'] = now
    return s
