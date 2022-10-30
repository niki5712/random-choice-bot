import re

import config
from constant.chat import id as chat_id, type as chat_type
from constant.user import first_name
from exceptions import OrderException


# TODO: Обновить документацию
search_bot_mention = re.compile(rf'\B@{config.USERNAME}(?:\s+l(?P<limit>\d+))?\b').search
match_dot_whitespace = re.compile(r'\.\s+').match


def get_name(obj):
    return ' '.join(filter(None, [obj.get('first_name'), obj.get('last_name')]))


# TODO: придумать тип вроде структуры для активного поста
# class ActivePost(NamedTuple):
#     id: int
#     user_order_counter: Counter
#     user_order_limit: int
#     count_order: Iterator[int]


class Order:
    __slots__ = (
        'chat_id', 'active_post_id', 'message_id', 'sender_id', 'sender_name', 'sender_username', 'count', 'text')

    def __init__(
            self, chat: dict, active_post: dict, message_id: int,
            from_: dict, sender_chat: dict, reply_to_message: dict, text: str):
        self.chat_id = chat['id']
        self.active_post_id = active_post['id']
        self.message_id = message_id

        # TODO: надо проверять???
        # 'from' Optional. Sender of the message; empty for messages sent to channels. For backward compatibility,
        # the field contains a fake sender user in non-channel chats, if the message was sent on behalf of a chat.
        reply_to_message_from = reply_to_message.get('from')
        if not reply_to_message_from:
            raise OrderException(f"message.reply_to_message.from {reply_to_message!r}: no from")

        reply_to_message_text = reply_to_message.get('text')
        if not reply_to_message_text:
            raise OrderException(f"message.reply_to_message {reply_to_message!r}: no text")

        # TODO: понять как работать с entities: [{'length': 8, 'offset': 38, 'type': 'mention'}],
        #  text: 'пост для выбора вашей песни на стриме @eljsbot'
        dot_whitespace = match_dot_whitespace(text)
        if not dot_whitespace:
            raise OrderException(f"message.text {text!r} doesn't start with '. '")

        if reply_to_message_from['is_bot']:
            raise OrderException(f"message.reply_to_message.from {reply_to_message_from!r}: is bot")
        elif reply_to_message_from['first_name'] != first_name.TELEGRAM:
            raise OrderException(
                f"message.reply_to_message.from {reply_to_message_from!r}: first_name != {first_name.TELEGRAM}")

        reply_to_message_sender_chat = reply_to_message.get('sender_chat')
        if not reply_to_message_sender_chat:
            raise OrderException(f"message.reply_to_message {reply_to_message!r}: no sender_chat")
        elif reply_to_message_sender_chat['id'] not in chat_id.CHANNEL_IDS:
            raise OrderException(
                f"message.reply_to_message.sender_chat {reply_to_message_sender_chat!r}: "
                    f"id not in CHANNEL_IDS {chat_id.CHANNEL_IDS!r}"
            )
        elif reply_to_message_sender_chat['type'] != chat_type.CHANNEL:
            raise OrderException(
                f"message.reply_to_message.sender_chat {reply_to_message_sender_chat!r}: "
                    f"type != {chat_type.CHANNEL!r}"
            )

        reply_to_message_forward_from_chat = reply_to_message.get('forward_from_chat')
        if not reply_to_message_forward_from_chat:
            raise OrderException(f"message.reply_to_message {reply_to_message!r}: no forward_from_chat")
        elif reply_to_message_sender_chat != reply_to_message_forward_from_chat:
            raise OrderException(
                f"message.reply_to_message.sender_chat {reply_to_message_sender_chat!r} != "
                    f"message.reply_to_message.forward_from_chat {reply_to_message_forward_from_chat!r}"
            )

        if not search_bot_mention(reply_to_message_text):
            raise OrderException(
                f"message.reply_to_message.text {reply_to_message_text!r} doesn't mention bot {config.USERNAME!r}")

        self.text = (text[:dot_whitespace.start()] + text[dot_whitespace.end():]).strip()
        if not self.text:
            raise OrderException(f"order.text is empty")

        # FIXME: sender_id: Chat.id (sender_chat.id) может случайно совпасть с User.id (from.id)?
        self.sender_id = sender_chat.get('id', from_['id'])
        self.sender_name = sender_chat.get('title', get_name(from_))
        self.sender_username = sender_chat.get('username', from_.get('username', ''))

        if active_post['user_order_counter'][self.key] >= active_post['user_order_limit']:
            chat_name = chat.get('title') or get_name(chat) or chat.get('username') or chat['id']
            raise OrderException(
                f"The number of orders for {self.sender_name!r} ({chat_name!r})"
                    f" has reached the limit: {active_post['user_order_limit']!r}"
            )

        self.count = next(active_post['count_order'])

    def __repr__(self):
        return str(dict(
            key=self.key,
            sender_name=self.sender_name,
            sender_username=self.sender_username,
            count=self.count,
            text=self.text,
        ))

    def __str__(self):
        if self.sender_username:
            username = f' (@{self.sender_username})'
        else:
            username = ''

        return f'От: {self.sender_name}{username}\n\n{self.count:0>3}. {self.text}'

    # TODO: key -> sender_key
    @property
    def key(self):
        return self.chat_id, self.active_post_id, self.sender_id