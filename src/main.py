import re
from collections import Counter, defaultdict
from datetime import datetime
from itertools import count
from time import sleep

import config
from constant.chat import id as chat_id, type as chat_type
from exceptions import BotException, OrderException
from log import LOG_BOT
from order import Order
from telegram_api import TelegramAPI


# TODO: уметь обновить parameters_of_get_updates['offset'] налету
parameters_of_get_updates = dict(allowed_updates=[])

# TODO: уметь обновлять active_post_map налету (можно отредактировать соответствующий пост)
# TODO: придумать тип вроде структуры для активного поста
# ActivePost = namedtuple('ActivePost', ['id', 'user_order_counter', 'user_order_limit', 'count_order'])
active_post_map = defaultdict(dict)
sender_to_order_maps = defaultdict(dict)

# TODO: Обновить документацию
search_bot_mention = re.compile(rf'\B@{config.USERNAME}(?:\s+l(?P<limit>\d+))?\b').search

# TODO: разобраться с тем, как с минимальными правами получать только нужные сообщения, а не все из группы
#  администратор получается не нужен, но без администратора нельзя удалять сообщения...
# https://core.telegram.org/bots/faq#what-messages-will-my-bot-get

# TODO: проверить выдёргивание lan кабеля при работающем боте


def get_name(obj):
    return ' '.join(filter(None, [obj.get('first_name'), obj.get('last_name')]))


def process_updates(updates, telegram):
    logging = LOG_BOT.getChild('process_updates')

    for update in sorted(updates, key=lambda x: x['update_id']):
        parameters_of_get_updates['offset'] = update['update_id'] + 1

        message = update.get('message') or update.get('edited_message')
        if not message:
            logging.warning(f"no message, Update {update} skipped")
            continue

        if message['chat']['id'] not in chat_id.GROUP_IDS:
            logging.warning(
                f"message.chat {message['chat']!r}: id not in GROUP_IDS {chat_id.GROUP_IDS!r}, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        text = message.get('text')
        if not text:
            logging.warning(f"message {message!r}: no text, Update {update['update_id']} skipped")
            continue

        from_ = message.get('from')
        if not from_:
            logging.warning(f"message {message!r}: no from, Update {update['update_id']} skipped")
            continue

        sender_chat = message.get('sender_chat', {})

        # найти активный пост
        forward_from_chat = message.get('forward_from_chat')
        if forward_from_chat:
            if not sender_chat:
                logging.warning(f"message {message!r}: no sender_chat, Update {update['update_id']} skipped")
                continue
            elif sender_chat['id'] not in chat_id.CHANNEL_IDS:
                logging.warning(
                    f"message.sender_chat {sender_chat!r}: "
                        f"id not in CHANNEL_IDS {chat_id.CHANNEL_IDS!r}, Update {update['update_id']} skipped"
                )
                continue
            elif sender_chat['type'] != chat_type.CHANNEL:
                logging.warning(
                    f"message.sender_chat {sender_chat!r}: "
                        f"type != {chat_type.CHANNEL!r}, Update {update['update_id']} skipped"
                )
                continue

            # # TODO: надо проверять??? Кажется нету смысла, аккаунт фейковый всё равно
            # # 'from': {'id': 777000, 'is_bot': False, 'first_name': 'Telegram'}
            # # 'from' Optional. Sender of the message; empty for messages sent to channels. For backward compatibility,
            # # the field contains a fake sender user in non-channel chats, if the message was sent on behalf of a chat.
            # if from_['is_bot']:
            #     logging.warning(f"message.from {from_!r}: is bot, Update {update['update_id']} skipped")
            #     continue
            # elif from_['first_name'] != first_name.TELEGRAM:
            #     logging.warning(
            #         f"message.from {from_!r}: first_name != {first_name.TELEGRAM}, "
            #             f"Update {update['update_id']} skipped"
            #     )
            #     continue

            if forward_from_chat['id'] not in chat_id.CHANNEL_IDS:
                logging.warning(
                    f"message.forward_from_chat {forward_from_chat!r}: "
                        f"id not in CHANNEL_IDS {chat_id.CHANNEL_IDS!r}, Update {update['update_id']} skipped"
                )
                continue
            elif forward_from_chat['type'] != chat_type.CHANNEL:
                logging.warning(
                    f"message.forward_from_chat {forward_from_chat!r}: "
                        f"type != {chat_type.CHANNEL!r}, Update {update['update_id']} skipped"
                )
                continue

            post_date = message.get('edit_date') or message.get('forward_date')
            if not post_date:
                logging.warning(f"message {message!r}: no forward_date, Update {update['update_id']} skipped")
                continue

            # TODO: понять как работать с entities: [{'length': 8, 'offset': 38, 'type': 'mention'}],
            #  text: 'пост для выбора вашей песни на стриме @eljsbot'
            # TODO: Обработать ситуацию когда из активного поста убрали упоминание бота
            bot_mention = search_bot_mention(text)
            if not bot_mention:
                logging.warning(
                    f"message.text {text!r} doesn't mention bot {config.USERNAME!r}, "
                        f"Update {update['update_id']} skipped"
                )
                continue

            forward_from_message_id = message.get('forward_from_message_id')
            if not forward_from_message_id:
                logging.warning(
                    f"message {message!r}: no forward_from_message_id, Update {update['update_id']} skipped")
                continue

            logging.info(f"Active channel post at {datetime.fromtimestamp(post_date)} is \"{text}\"")
            logging.debug(f'Active channel post ID is {forward_from_message_id!r}')

            if 'edited_message' in update and forward_from_message_id in active_post_map:
                active_post_map[forward_from_message_id]['user_order_limit'] = int(
                    bot_mention.group('limit') or config.USER_ORDER_LIMIT)
            else:
                active_post_map[forward_from_message_id] = dict(
                    id=forward_from_message_id,
                    user_order_counter=Counter(),
                    user_order_limit=int(bot_mention.group('limit') or config.USER_ORDER_LIMIT),
                    count_order=count(start=1)
                )

            logging.info(f"User order limit is {active_post_map[forward_from_message_id]['user_order_limit']!r}")
            continue

        if not active_post_map:
            logging.warning(f"no active_post_map {active_post_map!r}, Update {update['update_id']} skipped")
            continue

        reply_to_message = message.get('reply_to_message')
        if not reply_to_message:
            logging.warning(f"message {message!r}: no reply_to_message, Update {update['update_id']} skipped")
            continue
        elif reply_to_message['chat'] != message['chat']:
            logging.warning(
                f"message.reply_to_message.chat {reply_to_message['chat']!r} != message.chat {message['chat']!r}, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        # TODO: надо проверять???
        # 'from' Optional. Sender of the message; empty for messages sent to channels. For backward compatibility,
        # the field contains a fake sender user in non-channel chats, if the message was sent on behalf of a chat.
        reply_to_message_from = reply_to_message.get('from')
        if not reply_to_message_from:
            logging.warning(
                f"message.reply_to_message.from {reply_to_message!r}: no from, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        reply_to_message_text = reply_to_message.get('text')
        if not reply_to_message_text:
            logging.warning(
                f"message.reply_to_message {reply_to_message!r}: no text, Update {update['update_id']} skipped")
            continue

        # TODO: понять как работать с entities: [{'length': 8, 'offset': 38, 'type': 'mention'}],
        #  text: 'пост для выбора вашей песни на стриме @eljsbot'
        if text.startswith(config.COMMENT_PREFIX):
            logging.warning(
                f"message.text {text!r} starts with {config.COMMENT_PREFIX!r}, Update {update['update_id']} skipped")
            continue

        # TODO: уметь делать рассылку от имени бота участникам розыгрыша
        # TODO: создавать пост с заказами с помощью inline keyboard button
        # TODO: ??? добавить возможность писать под постом от бота в случае ЧП
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
        reply_to_message_forward_from_message_id = reply_to_message.get('forward_from_message_id')
        if reply_to_message_forward_from_message_id:
            if reply_to_message_forward_from_message_id not in active_post_map:
                logging.warning(
                    f"message.reply_to_message {reply_to_message!r}: "
                        f"forward_from_message_id {reply_to_message_forward_from_message_id!r} not in "
                        f"active_post_map {active_post_map!r}, Update {update['update_id']} skipped"
                )
                continue

            try:
                order = Order(
                    chat=message['chat'],
                    active_post=active_post_map[reply_to_message_forward_from_message_id],
                    message_id=message['message_id'],  # TODO: sent_message['message_id']
                    reply_to_message=reply_to_message,
                    from_=from_,
                    sender_chat=sender_chat,
                    text=text,
                )
            except OrderException as error:
                logging.warning(f"{error}, Update {update['update_id']} skipped")
                continue

            # TODO: попробовать copyMessage + caption, вместо sendMessage
            # TODO: разобраться как работает ForceReply и для чего нужен
            sent_message = telegram.api_call(
                'sendMessage',
                dict(
                    chat_id=order.chat_id,
                    text=str(order),
                    parse_mode='MarkdownV2',
                    disable_web_page_preview=True,
                    disable_notification=True,
                    protect_content=True,
                    reply_to_message_id=reply_to_message['message_id'],
                    # TODO: разобраться, что такое reply_markup
                )
            )

            if not sent_message:
                continue

            order.message_id = sent_message['message_id']
            sender_to_order_maps[order.sender_key][order.message_id] = order

            user_order_counter = active_post_map[reply_to_message_forward_from_message_id]['user_order_counter']
            user_order_counter[order.sender_key] += 1
            logging.info(f"User order count: {user_order_counter[order.sender_key]!r}, order.text is \"{order.text}\"")

            try:
                telegram.api_call(
                    'deleteMessage', dict(chat_id=message['chat']['id'], message_id=message['message_id']))
            except BotException:
                logging.error(f"Cannot delete message {text!r} from {order.sender_name!r}")
                pass
            continue

        # TODO: Обновить документацию
        # найти правки заказов
        if not reply_to_message_from['is_bot']:
            logging.warning(
                f"message.reply_to_message.from {reply_to_message_from!r}: is not bot, "
                    f"Update {update['update_id']} skipped"
            )
            continue
        elif reply_to_message_from.get('username') != config.USERNAME:
            logging.warning(
                f"message.reply_to_message.from {reply_to_message_from!r}: username != {config.USERNAME}, "
                    f"Update {update['update_id']} skipped"
            )
            continue

        sender_id = sender_chat.get('id', from_['id'])

        # TODO: упростить, можем ли взять в качестве id что-то кроме active_post_id?
        # FIXME: id у активного поста может быть одинаковым в разным каналах?
        for active_post_id in active_post_map:
            sender_key = message['chat']['id'], active_post_id, sender_id

            order = sender_to_order_maps[sender_key].get(reply_to_message['message_id'])
            if order:
                break
        else:
            logging.warning(
                f"message.reply_to_message.message_id {reply_to_message['message_id']!r} "
                    f"is not found in order maps {sender_to_order_maps!r}, Update {update['update_id']} skipped"
            )
            continue

        # TODO: обновлять все поля, а не только text, т.к. пользователь может изменить sender_name, sender_username
        order.text = text

        edited_message = telegram.api_call(
            'editMessageText',
            dict(
                chat_id=order.chat_id,
                message_id=order.message_id,
                text=str(order),
                parse_mode='MarkdownV2',
                disable_web_page_preview=True,
                # TODO: разобраться, что такое reply_markup
            )
        )

        if not edited_message:
            continue

        logging.info(f'Edited order.text is "{order.text}"')

        try:
            telegram.api_call(
                'deleteMessage', dict(chat_id=message['chat']['id'], message_id=message['message_id']))
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
