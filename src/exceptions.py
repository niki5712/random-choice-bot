class BotException(Exception):
    pass


class OrderException(Exception):
    pass


class OrderLimitIsReachedException(OrderException):
    pass
