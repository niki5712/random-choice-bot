class OrderException(Exception):
    pass


class OrderLimitIsReachedException(OrderException):
    def __init__(self, message: str, sender_key):
        self.message = message
        self.sender_key = sender_key

        OrderException.__init__(self, self.message)
