import re
from collections import Counter, namedtuple
from datetime import datetime
from itertools import count
from time import sleep

import config
from common import BotException
from constant.chat import type as chat_type
from constant.user import first_name
from log import LOG_BOT
from telegram_api import TelegramAPI


GROUP_IDS = {-1001285375423, -1001686234152}
CHANNEL_IDS = {-1001496858363, -1001761942943}

# TODO: уметь обновить parameters_of_get_updates['offset'] налету
parameters_of_get_updates = dict()

# TODO: уметь обновить active_post_id налету (можно отредактировать соответствующий пост)
active_post_id = None
user_order_limit = None
count_order = count(start=1)

user_order_counter = Counter()

search_bot_mention = re.compile(rf'\B@{config.USERNAME}(?:\s+l(?P<limit>\d+))?\b').search
match_dot_whitespace = re.compile(r'\.\s+').match

# TODO: разобраться с тем, как с минимальными правами получать только нужные сообщения, а не все из группы
#  администратор получается не нужен, но без администратора нельзя удалять сообщения...
# https://core.telegram.org/bots/faq#what-messages-will-my-bot-get

# FIXME: сейчас бот по сути умеет работать только с одним каналом (chat_id) и одним постом (active_post_id) из него


def get_name(obj):
    return ' '.join(filter(None, [obj.get('first_name'), obj.get('last_name')]))


class Order(namedtuple(
        'Order',
        ['chat_id', 'active_post_id', 'sender_id', 'sender_name', 'sender_username', 'count', 'text'])):
    __slots__ = ()

    @property
    def key(self):
        return self.chat_id, self.active_post_id, self.sender_id

    def __str__(self):
        return f'От: {self.sender_name} ({self.sender_username})\n\n{self.count:0>3}. {self.text}'


def process_updates(updates, telegram):
    global active_post_id, user_order_limit, count_order

    logging = LOG_BOT.getChild('process_updates')

    for update in sorted(updates, key=lambda x: x['update_id']):
        parameters_of_get_updates['offset'] = update['update_id'] + 1

        message = update.get('message') or update.get('edited_message')
        if not message:
            logging.warn(f"no message, Update {update} skipped")
            continue

        if message['chat']['id'] not in GROUP_IDS:
            logging.warn(
                f"message.chat {message['chat']!r}: id not in GROUP_IDS {GROUP_IDS!r}, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        text = message.get('text')
        if not text:
            logging.warn(f"message {message!r}: no text, Update {update['update_id']} skipped")
            continue

        from_ = message.get('from')
        if not from_:
            logging.warn(f"message {message!r}: no from, Update {update['update_id']} skipped")
            continue

        sender_chat = message.get('sender_chat', {})

        # найти активный пост
        forward_from_chat = message.get('forward_from_chat')
        if forward_from_chat:
            if not sender_chat:
                logging.warn(f"message {message!r}: no sender_chat, Update {update['update_id']} skipped")
                continue
            elif sender_chat['id'] not in CHANNEL_IDS:
                logging.warn(
                    f"message.sender_chat {sender_chat!r}: "
                        f"id not in CHANNEL_IDS {CHANNEL_IDS!r}, Update {update['update_id']} skipped"
                )
                continue
            elif sender_chat['type'] != chat_type.CHANNEL:
                logging.warn(
                    f"message.sender_chat {sender_chat!r}: "
                        f"type != {chat_type.CHANNEL!r}, Update {update['update_id']} skipped"
                )
                continue

            # # TODO: надо проверять??? Кажется нету смысла, аккаунт фейковый всё равно
            # # 'from': {'id': 777000, 'is_bot': False, 'first_name': 'Telegram'}
            # # 'from' Optional. Sender of the message; empty for messages sent to channels. For backward compatibility,
            # # the field contains a fake sender user in non-channel chats, if the message was sent on behalf of a chat.
            # if from_['is_bot']:
            #     logging.warn(f"message.from {from_!r}: is bot, Update {update['update_id']} skipped")
            #     continue
            # elif from_['first_name'] != first_name.TELEGRAM:
            #     logging.warn(
            #         f"message.from {from_!r}: first_name != {first_name.TELEGRAM}, "
            #             f"Update {update['update_id']} skipped"
            #     )
            #     continue

            if forward_from_chat['id'] not in CHANNEL_IDS:
                logging.warn(
                    f"message.forward_from_chat {forward_from_chat!r}: "
                        f"id not in CHANNEL_IDS {CHANNEL_IDS!r}, Update {update['update_id']} skipped"
                )
                continue
            elif forward_from_chat['type'] != chat_type.CHANNEL:
                logging.warn(
                    f"message.forward_from_chat {forward_from_chat!r}: "
                        f"type != {chat_type.CHANNEL!r}, Update {update['update_id']} skipped"
                )
                continue

            forward_date = message.get('forward_date')
            if not forward_date:
                logging.warn(f"message {message!r}: no forward_date, Update {update['update_id']} skipped")
                continue

            # TODO: понять как работать с entities: [{'length': 8, 'offset': 38, 'type': 'mention'}],
            #  text: 'пост для выбора вашей песни на стриме @eljsbot'
            # TODO: Обработать ситуацию когда из активного поста убрали упоминание бота
            bot_mention = search_bot_mention(text)
            if not bot_mention:
                logging.warn(
                    f"message.text {text!r} doesn't mention bot {config.USERNAME!r}, "
                        f"Update {update['update_id']} skipped"
                )
                continue

            active_post_id = message.get('forward_from_message_id')
            if not active_post_id:
                logging.warn(f"message {message!r}: no forward_from_message_id, Update {update['update_id']} skipped")
                continue

            logging.info(f"Active channel post at {datetime.fromtimestamp(forward_date)} is \"{text}\"")
            logging.debug(f'Active channel post ID is {active_post_id!r}')

            user_order_limit = int(bot_mention.group('limit') or config.USER_ORDER_LIMIT)
            logging.info(f'User order limit is {user_order_limit!r}')

            # очищать count_order необходимо только для нового поста
            if 'edited_message' in update:
                continue

            count_order = count(start=1)
            logging.info('Order counter was reset')
            continue

        if not active_post_id:
            logging.warn(f"no active_post_id {active_post_id!r}, Update {update['update_id']} skipped")
            continue

        # TODO: вывести правила в ответ на новый активный пост
        # TODO: обрабатывать команды /start, /stop, а также `Stop and block bot` и `Restart bot` в профиле бота
        # Минимальные права: быть администратором связанной супергруппы и уметь удалять сообщения в ней
        # vvv TODO: настроить задержку
        # TODO: информировать пользователя об ошибках через временные сообщения
        # TODO: в логе не хватает информации для какого поста характерна та или иная проблема
        #  и контекст лучше писать после описания проблемы, а не до
        # TODO: проверить наличие подписки для добавления песни
        # TODO: проверить наличие подписки для изменения песни
        # TODO: проверить наличие подписки, если ваш билет счастливый
        # TODO: показать кнопку я тут, если Лёля нажала кнопку покажи себя на записи выигравшего
        # TODO: добавить анимацию печати для ожидания удаления сообщения
        # TODO: по сути нету необходимости в зависимости от requests, можно обойтись встроенным функционалом

        # найти заказы
        # TODO: Изменять заказ через ответ на свой же заказ
        # TODO: Обновить документацию

        reply_to_message = message.get('reply_to_message')
        if not reply_to_message:
            logging.warn(f"message {message!r}: no reply_to_message, Update {update['update_id']} skipped")
            continue
        elif reply_to_message['chat'] != message['chat']:
            logging.warn(
                f"message.reply_to_message.chat {reply_to_message['chat']!r} != message.chat {message['chat']!r}, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        reply_to_message_forward_from_message_id = reply_to_message.get('forward_from_message_id')
        if not reply_to_message_forward_from_message_id:
            logging.warn(
                f"message.reply_to_message {reply_to_message!r}: no forward_from_message_id, "
                    f"Update {update['update_id']} skipped"
            )
            continue
        elif reply_to_message_forward_from_message_id != active_post_id:
            logging.warn(
                f"message.reply_to_message {reply_to_message!r}: "
                    f"forward_from_message_id {reply_to_message_forward_from_message_id!r} != "
                    f"active_post_id {active_post_id!r}, Update {update['update_id']} skipped"
            )
            continue

        # TODO: надо проверять???
        # 'from' Optional. Sender of the message; empty for messages sent to channels. For backward compatibility,
        # the field contains a fake sender user in non-channel chats, if the message was sent on behalf of a chat.
        reply_to_message_from = reply_to_message.get('from')
        if not reply_to_message_from:
            logging.warn(
                f"message.reply_to_message.from {reply_to_message!r}: no from, "
                    f"Update {update['update_id']} skipped"
            )
            continue
        elif reply_to_message_from['is_bot']:
            logging.warn(
                f"message.reply_to_message.from {reply_to_message_from!r}: is bot, "
                    f"Update {update['update_id']} skipped"
            )
            continue
        elif reply_to_message_from['first_name'] != first_name.TELEGRAM:
            logging.warn(
                f"message.reply_to_message.from {reply_to_message_from!r}: first_name != {first_name.TELEGRAM}, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        reply_to_message_sender_chat = reply_to_message.get('sender_chat')
        if not reply_to_message_sender_chat:
            logging.warn(
                f"message.reply_to_message {reply_to_message!r}: no sender_chat, Update {update['update_id']} skipped")
            continue
        elif reply_to_message_sender_chat['id'] not in CHANNEL_IDS:
            logging.warn(
                f"message.reply_to_message.sender_chat {reply_to_message_sender_chat!r}: "
                    f"id not in CHANNEL_IDS {CHANNEL_IDS!r}, Update {update['update_id']} skipped"
            )
            continue
        elif reply_to_message_sender_chat['type'] != chat_type.CHANNEL:
            logging.warn(
                f"message.reply_to_message.sender_chat {reply_to_message_sender_chat!r}: "
                    f"type != {chat_type.CHANNEL!r}, Update {update['update_id']} skipped"
            )
            continue

        reply_to_message_forward_from_chat = reply_to_message.get('forward_from_chat')
        if not reply_to_message_forward_from_chat:
            logging.warn(
                f"message.reply_to_message {reply_to_message!r}: no forward_from_chat, "
                    f"Update {update['update_id']} skipped"
            )
            continue
        elif reply_to_message_sender_chat != reply_to_message_forward_from_chat:
            logging.warn(
                f"message.reply_to_message.sender_chat {reply_to_message_sender_chat!r} != "
                    f"message.reply_to_message.forward_from_chat {reply_to_message_forward_from_chat!r}, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        reply_to_message_text = reply_to_message.get('text')
        if not reply_to_message_text:
            logging.warn(
                f"message.reply_to_message {reply_to_message!r}: no text, Update {update['update_id']} skipped")
            continue
        elif not search_bot_mention(reply_to_message_text):
            logging.warn(
                f"message.reply_to_message.text {reply_to_message_text!r} doesn't mention bot {config.USERNAME!r}, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        # TODO: понять как работать с entities: [{'length': 8, 'offset': 38, 'type': 'mention'}],
        #  text: 'пост для выбора вашей песни на стриме @eljsbot'
        dot_whitespace = match_dot_whitespace(text)
        if not dot_whitespace:
            logging.warn(
                f"message.text {text!r} doesn't start with '. ', Update {update['update_id']} skipped")
            continue

        logging.debug(f"message.text is \"{text}\", Update is {update['update_id']}")

        order = Order(
            chat_id=None,
            active_post_id=None,
            sender_id=None,
            sender_name=None,
            sender_username=None,
            count=None,
            text=(text[:dot_whitespace.start()] + text[dot_whitespace.end():]).strip(),
        )

        if not order.text:
            logging.warn(f"order.text is empty, Update {update['update_id']} skipped")
            continue

        order = order._replace(
            chat_id=message['chat']['id'],
            active_post_id=active_post_id,
            # FIXME: sender_id: Chat.id (sender_chat.id) может случайно совпасть с User.id (from.id)?
            sender_id=sender_chat.get('id', from_['id']),
            sender_name=sender_chat.get('title', get_name(from_)),
            sender_username=sender_chat.get('username', from_.get('username', '')),
        )

        if user_order_counter[order.key] >= user_order_limit:
            chat = (
                message['chat'].get('title')
                or get_name(message['chat'])
                or message['chat'].get('username')
                or message['chat']['id']
            )
            logging.warn(
                f"The number of orders for {order.sender_name!r} ({chat!r}) has reached the limit: "
                    f"{user_order_limit!r}, Update {update['update_id']} skipped"
            )
            continue

        order = order._replace(count=next(count_order))

        sent_message = telegram.api_call(
            'sendMessage',
            dict(
                chat_id=message['chat']['id'],
                text=str(order),
                disable_notification=True,
                disable_web_page_preview=True,  # TODO: Что это?
                reply_to_message_id=reply_to_message['message_id'],
                # allow_sending_without_reply=True,
            )
        )

        if not sent_message:
            continue

        user_order_counter.update([order.key])
        logging.info(f'User order count: {user_order_counter[order.key]!r}, order.text is "{order.text}"')

        try:
            telegram.api_call('deleteMessage', dict(chat_id=message['chat']['id'], message_id=message['message_id']))
        except BotException:
            logging.error(f"Cannot delete message {text!r} from {order.sender_name!r}")
            pass


def main():
    logging = LOG_BOT.getChild('main')
    telegram = TelegramAPI()
    logging.debug(repr(telegram))

    while True:
        updates = telegram.api_call('getUpdates', parameters_of_get_updates)
        logging.debug(f"Got {len(updates)} updates")

        if not updates:
            sleep(config.EVENT_TIMEOUT)
            continue

        process_updates(updates, telegram)


if __name__ == '__main__':
    # TODO: переписать на python-telegram? https://github.com/alexander-akhmetov/python-telegram
    # TODO: переписать на Telethon? https://github.com/LonamiWebs/Telethon
    # TODO: переписать на pyrogram? https://github.com/pyrogram/pyrogram
    main()
