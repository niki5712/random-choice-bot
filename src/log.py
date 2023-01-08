from datetime import datetime
from logging import *

import config


FORMAT = '{asctime} {process:5} {levelname:8} {name}: {message}'

basicConfig(
    format=FORMAT,
    style='{',  # TODO: Разобраться почему не работает
    level=config.LOGGING_LEVEL,
    # TODO: определять working directory
    stream=(config.LOG_DIR / f'{datetime.now():%Y-%m-%d-%H%M%S}.log').open('w', encoding='utf-8'),
)

# root = getLogger()
# handler = StreamHandler()
# handler.setFormatter(Formatter(FORMAT, style='{'))
# root.addHandler(handler)

LOG_BOT = getLogger('Bot')
