class BotException(Exception):
    pass


class SecretStr(str):
    def __new__(cls, value: [str, 'SecretStr']):
        if isinstance(value, SecretStr):
            return value

        return super().__new__(cls, value)

    def __str__(self) -> str:
        return self and '*****'

    def __repr__(self) -> str:
        return repr(str(self))
