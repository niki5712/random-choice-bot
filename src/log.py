from datetime import datetime
from logging import *

import config


FORMAT = '{asctime} {process:5} {levelname:8} {name}: {message}'

basicConfig(
    format=FORMAT,
    style='{',  # TODO: Разобраться почему не работает
    level=config.LOGGING_LEVEL,
    # TODO: определять working directory
    stream=open(f'../log/{datetime.now():%Y-%m-%d-%H%M%S}.log', 'w', encoding='utf-8'),
)

# root = getLogger()
# handler = StreamHandler()
# handler.setFormatter(Formatter(FORMAT, style='{'))
# root.addHandler(handler)

getLogger('urllib3').setLevel(INFO)

LOG_BOT = getLogger('Bot')
