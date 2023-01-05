import re

from config import USERNAME


class SecretStr(str):
    def __new__(cls, value: [str, 'SecretStr']):
        if isinstance(value, SecretStr):
            return value

        return super().__new__(cls, value)

    def __str__(self) -> str:
        return self and '*****'

    def __repr__(self) -> str:
        return repr(str(self))


search_bot_mention = re.compile(rf'\B@{USERNAME}(?:\s+l(?P<limit>\d+))?\b').search


def get_short_id(id_: int) -> int:
    return -1_000_000_000_000 - id_


def get_name(obj):
    return ' '.join(filter(None, [obj.get('first_name'), obj.get('last_name')]))
