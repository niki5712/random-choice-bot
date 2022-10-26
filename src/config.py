import os
from pathlib import Path


LOGGING_LEVEL = 'DEBUG'

AUTH_TOKEN = os.environ['JUKEBOX_BOT_AUTH_TOKEN']
API_SERVER = os.environ.get('JUKEBOX_BOT_API_SERVER', 'https://api.telegram.org')
REQUEST_TIMEOUT = 300

USERNAME = Path('../info/username.txt').read_text().strip()  # TODO: можно получить из метода getMe

EVENT_TIMEOUT = 0.5

PRIVACY = Path('../settings/privacy.txt').read_text().strip().upper() == 'ENABLE'

USER_ORDER_LIMIT = int(Path('../settings/user_order_limit.txt').read_text().strip())
