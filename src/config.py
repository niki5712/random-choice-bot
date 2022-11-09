import os
from pathlib import Path


LOGGING_LEVEL = 'DEBUG'

AUTH_TOKEN = os.environ['JUKEBOX_BOT_AUTH_TOKEN']
API_SERVER = os.environ.get('JUKEBOX_BOT_API_SERVER', 'https://api.telegram.org')
REQUEST_TIMEOUT = 300

USERNAME = Path('../info/username.txt').read_text().strip()  # TODO: можно получить из метода getMe

EVENT_TIMEOUT = 0.5

ORDER_LIMIT = int(Path('../settings/order_limit.txt').read_text().strip())  # TODO: нужно уметь настраивать командой
