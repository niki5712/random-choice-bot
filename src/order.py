import re
from typing import Optional

import config
from common import get_name, get_short_id, search_bot_mention
from constant.chat import id as chat_id, type as chat_type
from constant.user import first_name, id as user_id, username
from exceptions import OrderException


# TODO: придумать тип вроде структуры для активного поста
# class ActivePost(NamedTuple):
#     channel_id: int
#     id: int
#     message_thread_id: int
#     message_id: int
#     user_order_counter: Counter
#     user_order_limit: int
#     count_order: Iterator[int]


class Order:
    __slots__ = (
        'channel_id', 'active_post_id', 'group_id', 'message_thread_id', 'message_id',
        'sender_user_id', 'sender_chat_id', 'sender_name', 'sender_username', 'subscribed',
        'count', 'text',
    )

    def __init__(
            self, chat: dict, active_post: dict, message_thread_id: Optional[int], message_id: int,
            reply_to_message: dict, from_: dict, sender_chat: dict, subscribed: Optional[bool], text: str):
        self.group_id = chat['id']
        self.active_post_id = active_post['id']
        self.sender_user_id = from_['id']
        self.sender_chat_id = sender_chat.get('id')
        self.sender_name = sender_chat.get('title', get_name(from_))
        self.message_thread_id = message_thread_id or reply_to_message['message_id']
        self.message_id = message_id
        self.subscribed = subscribed
        self.text = text

        if sender_chat.get('username'):
            self.sender_username = sender_chat['username']
        elif from_.get('username') and not (
                from_.get('is_bot', False) and from_['username'] in [username.CHANNEL_BOT, username.GROUP_ANONYMOUS_BOT]
                or from_['id'] == user_id.TELEGRAM
        ):
            self.sender_username = from_['username']
        else:
            self.sender_username = ''

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
        if text.startswith(config.COMMENT_PREFIX):
            raise OrderException(f"message.text {text!r} starts with {config.COMMENT_PREFIX!r}")

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

        self.channel_id = reply_to_message_sender_chat['id']

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

        if active_post['user_order_counter'][self.sender_key] >= active_post['user_order_limit']:
            chat_name = chat.get('title') or get_name(chat) or chat.get('username') or chat['id']
            raise OrderException(
                f"The number of orders for {self.sender_name!r} ({chat_name!r})"
                    f" has reached the limit: {active_post['user_order_limit']!r}"
            )

        self.count = next(active_post['count_order'])

    def __repr__(self):
        return str(dict(
            sender_key=self.sender_key,
            group_id=self.group_id,
            message_thread_id=self.message_thread_id,
            message_id=self.message_id,
            subscription=self.subscription,
            sender_name=self.sender_name,
            sender_username=self.sender_username,
            count=self.count,
            text=self.text,
        ))

    def __str__(self):
        if self.sender_username:
            sender_mention = f' (@{self.sender_username})'
        else:
            sender_mention = ''

        # TODO: send a callback query to the bot via an inline button, чтобы ссылка точно работала
        # Можно запретить упоминать себя через URL: Settings > Privacy and Security > Forwarded Messages
        if self.sender_chat_id:
            # TODO: Как сослаться на профиль чата?
            sender_url = f't.me/c/{get_short_id(self.sender_chat_id)}'
        else:
            sender_url = f'tg:user?id={self.sender_user_id}'

        def escape(text):
            return re.sub(
                pattern=r'[\\_*[\]()~`>#+\-=|{}.!]',
                repl=lambda match_object: rf'\{match_object.group()}',
                string=text
            )

        return '''\
{subscription} [*{sender_name}*]({sender_url}){sender_mention}

`{number}` {text}'''.format(
            subscription=escape(self.subscription),
            sender_name=escape(self.sender_name),
            sender_url=escape(sender_url),
            sender_mention=escape(sender_mention),
            number=escape(f'{self.count:0>3}.'),
            text=escape(self.text),
        )

    @property
    def subscription(self):
        if self.subscribed is None:
            return '❔'

        return '👥' if self.subscribed else '👤'

    @property
    def sender_key(self):
        # FIXME: sender (chat/user) id: Chat.id (sender_chat.id) может случайно совпасть с User.id (from.id)?
        return self.channel_id, self.active_post_id, (self.sender_chat_id or self.sender_user_id)

    def update(self, from_: dict, sender_chat: dict, subscribed: Optional[bool], text: str):
        self.sender_name = sender_chat.get('title', get_name(from_))
        self.sender_username = sender_chat.get('username', from_.get('username', ''))
        self.subscribed = subscribed
        self.text = text

    def make_reply_markup(self) -> dict:
        return dict(
            inline_keyboard=[
                [
                    dict(
                        text='чтобы изменить, ответь на сообщение 👆',
                        url=f't.me/c/{get_short_id(self.group_id)}/{self.message_id}?thread={self.message_thread_id}',
                    ),
                ],
            ]
        )
