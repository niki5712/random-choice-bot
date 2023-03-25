import os
from pathlib import Path


LOGGING_LEVEL = 'DEBUG'

AUTH_TOKEN = os.environ['JUKEBOX_BOT_AUTH_TOKEN']
API_SERVER = os.environ.get('JUKEBOX_BOT_API_SERVER', 'https://api.telegram.org')
REQUEST_TIMEOUT = 300
# TODO: возможно лимит в 20 запросов в минуту обусловлен тем, что бот не логинется?
API_CALL_TIMEOUT = 1.5
API_CALL_RETRIES = 20
API_CALL_RETRY_TIMEOUT = 1.5

USERNAME = Path('../info/username.txt').read_text(encoding='utf-8').strip()  # TODO: можно получить из метода getMe

EVENT_TIMEOUT = 0.3

PRIVACY = Path('../settings/privacy.txt').read_text(encoding='utf-8').strip().upper() == 'ENABLE'

USER_ORDER_LIMIT = int(Path('../settings/user_order_limit.txt').read_text(encoding='utf-8').strip())

ORDERTABLE_MARKDOWN_V_2 = Path('../settings/inline_query_result_ordertable.txt').read_text(encoding='utf-8').strip()
FANSIGN_MARKDOWN_V_2 = Path('../settings/inline_query_result_fansign.txt').read_text(encoding='utf-8').strip()

COMMENT_PREFIX = '.'
