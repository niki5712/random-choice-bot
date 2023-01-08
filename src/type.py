from collections import namedtuple
from typing import Optional, Union

from telethon.sync import events, types, utils

from error import OrderLimitIsReachedException


class NoChange:
    pass


NO_CHANGE = NoChange()


MessageKey = namedtuple('MessageKey', 'chat_id message_id')
SenderKey = namedtuple('SenderKey', 'chat_id sender_id')
OrderSenderKey = namedtuple('OrderSenderKey', 'post_id comment_id sender_id')


class Order:
    __slots__ = ('comment_key', 'post_key', 'sender', 'subscribed', 'text', 'count')

    def __init__(
            self,
            event: Union[events.NewMessage, events.MessageEdited],
            post_key: MessageKey,
            active_post: dict,
            sender: Union[types.User, types.Channel],
            subscribed: Optional[bool]):
        self.comment_key = MessageKey(chat_id=event.chat_id, message_id=event.id)
        self.post_key = post_key
        self.sender = sender
        self.subscribed = subscribed
        self.text = event.raw_text

        sender_key = self.sender_key

        if active_post['user_order_counter'][sender_key] >= active_post['user_order_limit']:
            raise OrderLimitIsReachedException(
                f"The number of orders for {self.sender_name!r} (chat_id {event.chat_id})"
                    f" has reached the limit: {active_post['user_order_limit']}",
                sender_key
            )

        self.count = next(active_post['count_order'])

    def __repr__(self):
        return str(dict(
            comment_key=self.comment_key,
            post_key=self.post_key,
            sender_key=self.sender_key,
            subscription=self.subscription,
            text=self.text,
            count=self.count,
        ))

    def __str__(self):
        # TODO: как экранировать символы для такого формата markdown?
        # TODO: как применить bold к ссылке, чтобы bold вовремя заканчивался?
        return '''\
{subscription} [{sender_name}]({sender_url}){sender_mention}

`{count:0>3}.` {text}'''.format(
            subscription=self.subscription,
            sender_name=self.sender_name,
            sender_url=self.sender_url,
            sender_mention=self.sender_mention,
            count=self.count,
            text=self.text,
        )

    @property
    def sender_key(self):
        return OrderSenderKey(
            post_id=self.post_key.chat_id,
            comment_id=self.post_key.message_id,
            sender_id=utils.get_peer_id(self.sender),
        )

    @property
    def sender_name(self):
        return utils.get_display_name(self.sender)

    @property
    def sender_url(self):
        # Можно запретить упоминать себя через URL: Settings > Privacy and Security > Forwarded Messages
        if isinstance(self.sender, types.User):
            return f'tg://user?id={self.sender.id}'

        # TODO: Как сослаться на профиль чата?
        return f't.me/c/{self.sender.id}'

    @property
    def sender_mention(self):
        return f' ([@{self.sender.username}](@{self.sender.username}))' if self.sender.username else ''

    @property
    def subscription(self):
        if self.subscribed is None:
            return '❔'

        return '👥' if self.subscribed else '👤'

    def update(
            self,
            *,
            subscribed: Union[Optional[bool], NoChange] = NO_CHANGE,
            text: Union[Optional[str], NoChange] = NO_CHANGE,
    ) -> None:
        if not isinstance(subscribed, NoChange):
            self.subscribed = subscribed
        if not isinstance(text, NoChange):
            self.text = text
