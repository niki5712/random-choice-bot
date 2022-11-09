import re
from itertools import count
from time import sleep
# from collections import namedtuple

import config
from log import LOG_BOT
from telegram_api import TelegramAPI
from constant.user import first_name
from constant.chat import type as chat_type
from datetime import datetime
from common import BotException
from collections import Counter


# TODO: уметь обновить active_channel_post_id налету (можно отредактировать соответствующий пост)
active_channel_post_id = None

# TODO: уметь обновить parameters_of_get_updates['offset'] налету
parameters_of_get_updates = dict()

search_bot_mention = re.compile(rf'\B@{config.USERNAME}\b').search
match_dot_whitespace = re.compile(r'\.\s').match

count_message = count(start=1)
order_counter = Counter()

GROUP_IDS = {-1001285375423, -1285375423, -1001686234152}

CHANNEL_USERNAMES = {'tt_elijess', 'niki_tmp'}
CHANNEL_IDS = {-1001496858363, -1496858363, -1001761942943}

# Chat = namedtuple('Chat', 'id type username')  # TODO: перечислить все поля


def process_updates(updates, telegram):
    global active_channel_post_id
    global count_message

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
            # TODO: понять как работать с entities: [{'length': 8, 'offset': 38, 'type': 'mention'}],
            #  text: 'пост для выбора вашей песни на стриме @eljsbot'
            # TODO: Обработать ситуацию когда из активного поста убрали упоминание бота
            if not search_bot_mention(text):
                logging.warn(
                    f"message.text {text!r} doesn't mention bot {config.USERNAME!r}, "
                        f"Update {update['update_id']} skipped"
                )
                continue

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
            elif sender_chat.get('username') not in CHANNEL_USERNAMES:
                logging.warn(
                    f"message.sender_chat {sender_chat!r}: "
                        f"username not in CHANNEL_USERNAMES {CHANNEL_USERNAMES!r}, Update {update['update_id']} skipped"
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
            elif forward_from_chat.get('username') not in CHANNEL_USERNAMES:
                logging.warn(
                    f"message.forward_from_chat {forward_from_chat!r}: "
                        f"username not in CHANNEL_USERNAMES {CHANNEL_USERNAMES!r}, Update {update['update_id']} skipped"
                )
                continue

            active_channel_post_id = message.get('forward_from_message_id')
            if not active_channel_post_id:
                logging.warn(f"message {message!r}: no forward_from_message_id, Update {update['update_id']} skipped")
                continue

            logging.debug(f'Active channel post ID is {active_channel_post_id!r}')

            forward_date = message.get('forward_date')
            if not forward_date:
                logging.warn(f"message {message!r}: no forward_date, Update {update['update_id']} skipped")
                continue

            logging.info(f"Active channel post at {datetime.fromtimestamp(forward_date)} is \"{text}\"")

            count_message = count(start=1)
            logging.info(f'Counter of messages was reset')
            continue

        if not active_channel_post_id:
            logging.warn(f"no active_channel_post_id {active_channel_post_id!r}, Update {update['update_id']} skipped")
            continue

        # TODO: понять как работать с entities: [{'length': 8, 'offset': 38, 'type': 'mention'}],
        #  text: 'пост для выбора вашей песни на стриме @eljsbot'
        dot_whitespace = match_dot_whitespace(text)
        if not dot_whitespace:
            logging.warn(
                f"message.text {text!r} doesn't start with '. ', Update {update['update_id']} skipped")
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
        elif reply_to_message_forward_from_message_id != active_channel_post_id:
            logging.warn(
                f"message.reply_to_message {reply_to_message!r}: "
                    f"forward_from_message_id {reply_to_message_forward_from_message_id!r} != "
                    f"active_channel_post_id {active_channel_post_id!r}, Update {update['update_id']} skipped"
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
        elif reply_to_message_sender_chat.get('username') not in CHANNEL_USERNAMES:
            logging.warn(
                f"message.reply_to_message.sender_chat {reply_to_message_sender_chat!r}: "
                    f"username not in CHANNEL_USERNAMES {CHANNEL_USERNAMES!r}, Update {update['update_id']} skipped"
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

        logging.debug(f"message.text is \"{text}\", Update is {update['update_id']}")

        order_text = (text[:dot_whitespace.start()] + text[dot_whitespace.end():]).strip()
        if not order_text:
            logging.warn(f"order is empty, Update {update['update_id']} skipped")
            continue

        order_id = message['chat']['id'], active_channel_post_id, message.get('sender_chat', {}).get('id', from_['id'])

        sender = sender_chat.get('title', ' '.join(filter(None, [from_['first_name'], from_.get('last_name')])))
        sender_username = sender_chat.get('username', from_.get('username', ''))

        if order_counter[order_id] >= config.ORDER_LIMIT:
            chat = (
                message['chat'].get('title')
                or ' '.join(filter(None, [message['chat'].get('first_name'), message['chat'].get('last_name')]))
                or message['chat'].get('username')
                or message['chat']['id']
            )
            logging.warn(
                f"The number of orders for {sender!r} ({chat!r}) has reached the limit: {config.ORDER_LIMIT!r}, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        order_text = f"By: {sender} ({sender_username})\n\n{next(count_message):0>3}. {order_text}"

        sent_message = telegram.api_call(
            'sendMessage',
            dict(
                chat_id=message['chat']['id'],
                text=order_text,
                disable_notification=True,
                disable_web_page_preview=True,  # TODO: Что это?
                reply_to_message_id=reply_to_message['message_id'],
                # allow_sending_without_reply=True,
            )
        )

        if not sent_message:
            continue

        order_counter.update([order_id])
        logging.info(f'Order count: {order_counter[order_id]!r}, order is "{order_text}"')

        try:
            telegram.api_call('deleteMessage', dict(chat_id=message['chat']['id'], message_id=message['message_id']))
        except BotException:
            logging.error(f"Cannot delete message {text!r} from {sender!r}")
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
