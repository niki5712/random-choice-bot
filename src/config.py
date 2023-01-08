import os
from pathlib import Path


REPO_DIR = Path(__file__).parents[1]

SESSION_DIR = REPO_DIR / 'session'
SESSION_DIR.mkdir(exist_ok=True)

LOG_DIR = REPO_DIR / 'log'
LOG_DIR.mkdir(exist_ok=True)

LOGGING_LEVEL = 'DEBUG'

AUTH_TOKEN = os.environ['JUKEBOX_BOT_AUTH_TOKEN']
API_SERVER = os.environ.get('JUKEBOX_BOT_API_SERVER', 'https://api.telegram.org')
# TODO: возможно лимит в 20 запросов в минуту обусловлен тем, что бот не логинется?
REQUEST_RETRIES = 20
REQUEST_TIMEOUT = 1.5
CONNECTION_RETRIES = 24
RETRY_DELAY = 1.5

USERNAME = Path('../info/username.txt').read_text(encoding='utf-8').strip()  # TODO: можно получить из метода getMe

EVENT_TIMEOUT = 0.3

PRIVACY = Path('../settings/privacy.txt').read_text(encoding='utf-8').strip().upper() == 'ENABLE'

# TODO: установить значение по умолчанию в 1, т.к. розыгрыш песен больше не актуален
USER_ORDER_LIMIT = int(Path('../settings/user_order_limit.txt').read_text(encoding='utf-8').strip())

ORDERTABLE_MARKDOWN = Path('../settings/inline_query_result_ordertable.txt').read_text(encoding='utf-8').strip()
FANSIGN_MARKDOWN = Path('../settings/inline_query_result_fansign.txt').read_text(encoding='utf-8').strip()

WELCOME_MESSAGE_MARKDOWN_V2 = Path('../settings/welcome_message.txt').read_text(encoding='utf-8').strip()
WELCOME_MESSAGE_BUTTON_TEXT = Path('../settings/welcome_message_button_text.txt').read_text(encoding='utf-8').strip()
WELCOME_MESSAGE_BUTTON_URL = Path('../settings/welcome_message_button_url.txt').read_text(encoding='utf-8').strip()
WELCOME_MESSAGE_DISTANCE_LIMIT = 15

COMMENT_PREFIX = '.'
