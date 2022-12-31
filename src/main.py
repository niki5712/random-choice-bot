from collections import Counter, defaultdict
from datetime import datetime
from itertools import count

import config
from common import search_bot_mention, toggle_chat_id
from constant.chat import id as chat_id, type as chat_type
from exceptions import BotException, OrderException, OrderLimitIsReachedException
from log import LOG_BOT
from order import Order
from telegram_api import TelegramAPI


CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP = dict(
    creator=True,
    administrator=True,
    member=True,
    restricted=True,
    left=False,
    kicked=False,
)

# TODO: уметь обновить parameters_of_get_updates['offset'] налету
parameters_of_get_updates = dict(
    allowed_updates=['message', 'edited_message', 'chat_member', 'my_chat_member', 'inline_query'])

# TODO: уметь обновлять active_post_map налету (можно отредактировать соответствующий пост)
active_post_map = defaultdict(dict)
sender_to_order_maps = defaultdict(dict)

channel_user_map = dict()

last_group_message_map = defaultdict(dict)
last_welcome_message_map = defaultdict(dict)

start_time = datetime.now()


# TODO: разобраться с тем, как с минимальными правами получать только нужные сообщения, а не все из группы.
#  администратор получается не нужен, но без администратора нельзя удалять сообщения...
# https://core.telegram.org/bots/faq#what-messages-will-my-bot-get


def process_updates(updates, telegram):
    logging = LOG_BOT.getChild('process_updates')

    for update in sorted(updates, key=lambda x: x['update_id']):
        parameters_of_get_updates['offset'] = update['update_id'] + 1

        # - обновить статус участника в канале
        # - поприветствовать новичка в группе
        chat_member = update.get('chat_member') or update.get('my_chat_member')
        if chat_member:
            if (
                    chat_member['chat']['type'] == chat_type.CHANNEL
                    and chat_member['chat']['id'] in chat_id.CHANNEL_IDS
            ):
                channel_user_key = chat_member['chat']['id'], chat_member['new_chat_member']['user']['id']
                channel_user_map[channel_user_key] = chat_member['new_chat_member']

                for channel_id, active_post_id in reversed(active_post_map):
                    if channel_id != chat_member['chat']['id']:
                        continue

                    sender_key = channel_id, active_post_id, chat_member['new_chat_member']['user']['id']
                    for order in reversed(sender_to_order_maps[sender_key].values()):
                        old_order = str(order)

                        order.update(
                            from_=chat_member['new_chat_member']['user'],
                            sender_chat={},
                            subscribed=CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP.get(
                                chat_member['new_chat_member']['status']),
                            text=order.text,
                        )

                        if str(order) == old_order:
                            logging.warning(f'No changes in the order "{order}"')
                        else:
                            try:
                                edited_message = telegram.api_call(
                                    'editMessageText',
                                    dict(
                                        chat_id=order.group_id,
                                        message_id=order.message_id,
                                        text=str(order),
                                        parse_mode='MarkdownV2',
                                        disable_web_page_preview=True,
                                    )
                                )
                            except BotException:
                                logging.error(f'Cannot edit the order "{order}" of the chat with id {order.group_id!r}')
                                edited_message = {}

                            if not edited_message:
                                continue

                            logging.info(f'Edited order is "{order}"')
            elif (
                    chat_member['chat']['type'] == chat_type.SUPERGROUP
                    and chat_member['chat']['id'] in chat_id.GROUP_IDS
            ):
                if start_time > datetime.fromtimestamp(chat_member['date']):
                    logging.warning(
                        f"start_time {start_time} > chat_member.date "
                            f"{datetime.fromtimestamp(chat_member['date'])}, Update {update['update_id']} skipped"
                    )
                    continue

                if chat_member['old_chat_member']['status'] not in CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP:
                    logging.error(
                        f"chat_member.old_chat_member {chat_member['old_chat_member']!r}: "
                            f"status not in CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP "
                            f"{CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP!r}, Update {update['update_id']} skipped"
                    )
                    continue

                if CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP[chat_member['old_chat_member']['status']]:
                    logging.warning(
                        f"chat_member.old_chat_member.status: {chat_member['old_chat_member']['status']!r}, "
                            f"Update {update['update_id']} skipped"
                    )
                    continue

                if chat_member['new_chat_member']['status'] not in CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP:
                    logging.error(
                        f"chat_member.new_chat_member {chat_member['new_chat_member']!r}: "
                            f"status not in CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP "
                            f"{CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP!r}, Update {update['update_id']} skipped"
                    )
                    continue

                if not CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP[chat_member['new_chat_member']['status']]:
                    logging.warning(
                        f"chat_member.new_chat_member.status: {chat_member['new_chat_member']['status']!r}, "
                            f"Update {update['update_id']} skipped"
                    )
                    continue

                group_id = chat_member['chat']['id']
                last_welcome_message = last_welcome_message_map[group_id]

                if last_welcome_message and (
                        last_group_message_map[group_id]['message_id'] -
                        last_welcome_message['message_id'] < config.WELCOME_MESSAGE_DISTANCE_LIMIT
                ):
                    logging.warning(
                        f"last_group_message.message_id {last_group_message_map[group_id]['message_id']!r} - "
                            f"last_welcome_message.message_id {last_welcome_message['message_id']!r} < "
                            f"WELCOME_MESSAGE_DISTANCE_LIMIT {config.WELCOME_MESSAGE_DISTANCE_LIMIT!r}, "
                            f"Update {update['update_id']} skipped"
                    )
                    continue

                try:
                    sent_message = telegram.api_call(
                        'sendMessage',
                        dict(
                            chat_id=group_id,
                            text=config.WELCOME_MESSAGE_MARKDOWN_V2,
                            parse_mode='MarkdownV2',
                            disable_web_page_preview=True,
                            reply_markup=dict(
                                inline_keyboard=[[dict(
                                    text=config.WELCOME_MESSAGE_BUTTON_TEXT,
                                    url=config.WELCOME_MESSAGE_BUTTON_URL,
                                )]]
                            ),
                        )
                    )
                except BotException:
                    logging.error(
                        f'Cannot send the text message "{config.WELCOME_MESSAGE_MARKDOWN_V2}" '
                            f'of the chat with id {group_id!r}'
                    )
                    continue

                if last_welcome_message:
                    try:
                        telegram.api_call(
                            'deleteMessage',
                            dict(
                                chat_id=last_welcome_message['chat']['id'],
                                message_id=last_welcome_message['message_id'],
                            )
                        )
                    except BotException:
                        logging.error(f"Cannot delete the message {last_welcome_message!r}")

                last_welcome_message_map[group_id] = sent_message
                logging.info(
                    f"last_welcome_message is {last_welcome_message_map[group_id]!r} "
                         f"for chat {chat_member['chat']!r}"
                )
            else:
                logging.warning(
                    f"chat_member.chat {chat_member['chat']!r}: "
                        f"id not in CHAT_IDS {chat_id.CHAT_IDS!r}, Update {update['update_id']} skipped"
                )
            continue

        # предложить создать пост для розыгрыша
        inline_query = update.get('inline_query')
        if inline_query:
            inline_query_chat_type = inline_query.get('chat_type')
            if not inline_query_chat_type:
                logging.warning(f"inline_query {inline_query!r}: no chat_type, Update {update['update_id']} skipped")
                try:
                    telegram.api_call('answerInlineQuery', dict(inline_query_id=inline_query['id'], results=[]))
                except BotException:
                    logging.error(f"Cannot send answer to the inline query {inline_query!r}")
                continue
            elif inline_query_chat_type != chat_type.CHANNEL:
                logging.warning(
                    f"inline_query {inline_query!r}: "
                        f"chat_type != {chat_type.CHANNEL!r}, Update {update['update_id']} skipped"
                )
                try:
                    telegram.api_call('answerInlineQuery', dict(inline_query_id=inline_query['id'], results=[]))
                except BotException:
                    logging.error(f"Cannot send answer to the inline query {inline_query!r}")
                continue

            # TODO: может приходится перезаходить в канал, чтобы увидеть InlineQueryResult из-за пустого запроса?
            # TODO: осуществлять поиск по inline_query['query']
            # TODO: обеспечить обратную совместимость, разрешить отправлять произвольный текст после упоминания бота
            # TODO: можно ли сделать, чтобы слайдер был горизонтальным? через картинки?
            try:
                telegram.api_call(
                    'answerInlineQuery',
                    dict(
                        inline_query_id=inline_query['id'],
                        results=[
                            dict(
                                type='article',
                                id='ordertable',
                                title='ordertable 🎵',
                                input_message_content=dict(
                                    message_text=config.ORDERTABLE_MARKDOWN_V2,
                                    parse_mode='MarkdownV2',
                                    disable_web_page_preview=True,
                                ),
                                description='пост для розыгрыша песен',
                                thumbnail_url='https://e7.pngegg.com/pngimages/862/929/png-clipart-musical-instruments-bass-guitar-acoustic-guitar-string-instruments-musical-instruments-guitar-accessory-cuatro.png',
                            ),
                            dict(
                                type='article',
                                id='fansign',
                                title='fansign 📷',
                                input_message_content=dict(
                                    message_text=config.FANSIGN_MARKDOWN_V2,
                                    parse_mode='MarkdownV2',
                                    disable_web_page_preview=True,
                                ),
                                description='пост для розыгрыша сигн',
                                thumbnail_url='https://e7.pngegg.com/pngimages/279/99/png-clipart-digital-cameras-graphy-video-cameras-drawing-camera-rectangle-photography.png',
                            ),
                        ],
                    )
                )
            except BotException:
                logging.error(f"Cannot send answer to the inline query {inline_query!r}")
            continue

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

        last_group_message_map[message['chat']['id']] = message

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
            elif sender_chat['type'] != chat_type.CHANNEL:
                logging.warning(
                    f"message.sender_chat {sender_chat!r}: "
                        f"type != {chat_type.CHANNEL!r}, Update {update['update_id']} skipped"
                )
                continue
            elif sender_chat['id'] not in chat_id.CHANNEL_IDS:
                logging.warning(
                    f"message.sender_chat {sender_chat!r}: "
                        f"id not in CHANNEL_IDS {chat_id.CHANNEL_IDS!r}, Update {update['update_id']} skipped"
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

            if forward_from_chat['type'] != chat_type.CHANNEL:
                logging.warning(
                    f"message.forward_from_chat {forward_from_chat!r}: "
                        f"type != {chat_type.CHANNEL!r}, Update {update['update_id']} skipped"
                )
                continue
            elif forward_from_chat['id'] not in chat_id.CHANNEL_IDS:
                logging.warning(
                    f"message.forward_from_chat {forward_from_chat!r}: "
                        f"id not in CHANNEL_IDS {chat_id.CHANNEL_IDS!r}, Update {update['update_id']} skipped"
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
            # TODO: избавиться от необходимости упоминать бота явно, но оставить совместимость
            # via_bot = message.get('via_bot')
            # if not via_bot:
            #     logging.warning(f"message {message!r}: no via_bot, Update {update['update_id']} skipped")
            #     continue
            # elif via_bot.get('username') != config.USERNAME:
            #     logging.warning(
            #         f"message.via_bot {via_bot!r}: username != {config.USERNAME!r}, "
            #             f"Update {update['update_id']} skipped"
            #     )
            #     continue

            forward_from_message_id = message.get('forward_from_message_id')
            if not forward_from_message_id:
                logging.warning(
                    f"message {message!r}: no forward_from_message_id, Update {update['update_id']} skipped")
                continue

            logging.info(f"Active channel post at {datetime.fromtimestamp(post_date)} is \"{text}\"")
            logging.debug(f'Active channel post ID is {forward_from_message_id!r}')

            post_key = forward_from_chat['id'], forward_from_message_id
            if 'edited_message' in update and post_key in active_post_map:
                active_post_map[post_key]['user_order_limit'] = int(
                    bot_mention.group('limit') or config.USER_ORDER_LIMIT)
            else:
                active_post_map[post_key] = dict(
                    channel_id=forward_from_chat['id'],
                    id=forward_from_message_id,
                    message_id=message['message_id'],
                    user_order_counter=Counter(),
                    user_order_limit=int(bot_mention.group('limit') or config.USER_ORDER_LIMIT),
                    count_order=count(start=1)
                )

            logging.info(f"User order limit is {active_post_map[post_key]['user_order_limit']!r}")
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

        # TODO: проверить корректность работы бота в условиях нестабильного интернета
        # TODO: можно ли отправлять системные сообщения ботом в канал, которые видят только админы, чтобы использовать
        #  более удобные средства взаимодействия с ботом, например Inline Keyboard?
        # TODO: что использовать для оставление заказов пользователем?
        #  Inline Queries: https://core.telegram.org/bots/inline#spreading-virally
        #  Inline Keyboard
        # TODO: использовать Inline Keyboard для редактирования заказа пользователем
        # TODO: использовать Inline Keyboard для удаления заказа администратором
        # TODO: выводить число заказанных песен и сигн на OBS
        # TODO: использовать custom_emoji?
        #  https://core.telegram.org/api/links#custom-emoji-stickerset-links
        #  https://core.telegram.org/api/custom-emoji
        # TODO: уметь делать рассылку от имени бота участникам розыгрыша
        # TODO: ??? добавить возможность писать под постом от бота в случае ЧП
        # TODO: вывести правила в ответ на новый активный пост
        # TODO: обрабатывать команды /start, /stop, а также `Stop and block bot` и `Restart bot` в профиле бота
        # TODO: информировать пользователя об ошибках через временные сообщения
        # TODO: в логе не хватает информации для какого поста характерна та или иная проблема
        #  и контекст лучше писать после описания проблемы, а не до
        # TODO: показать кнопку я тут, если Лёля нажала кнопку покажи себя на записи выигравшего
        # TODO: добавить анимацию печати если требуется подождать
        # TODO: по сути нету необходимости в зависимости от requests, можно обойтись встроенным функционалом

        # найти заказы
        reply_to_message_forward_from_message_id = reply_to_message.get('forward_from_message_id')
        if reply_to_message_forward_from_message_id:
            channel_id = reply_to_message['forward_from_chat']['id']
            post_key = channel_id, reply_to_message_forward_from_message_id
            if post_key not in active_post_map:
                logging.warning(
                    f"message.reply_to_message {reply_to_message!r}: "
                        f"forward_from_message_id {post_key!r} not in "
                        f"active_post_map {active_post_map!r}, Update {update['update_id']} skipped"
                )
                continue

            try:
                if sender_chat:
                    sender_member = dict(status='creator', user=from_)
                else:
                    channel_user_key = channel_id, from_['id']
                    sender_member = channel_user_map.get(channel_user_key) or channel_user_map.setdefault(
                        channel_user_key,
                        telegram.api_call('getChatMember', dict(chat_id=channel_id, user_id=from_['id']))
                    )
            except BotException:
                logging.error(
                    f"Cannot get information about the member {from_!r} of "
                        f"the chat {reply_to_message['forward_from_chat']!r}"
                )
                sender_member = {}

            try:
                order = Order(
                    chat=message['chat'],
                    active_post=active_post_map[post_key],
                    message_thread_id=message.get('message_thread_id'),
                    message_id=message['message_id'],  # TODO: sent_message['message_id']
                    reply_to_message=reply_to_message,
                    from_=from_,
                    sender_chat=sender_chat,
                    subscribed=CHAT_MEMBER_STATUS_TO_SUBSCRIBED_MAP.get(sender_member.get('status')),
                    text=text,
                )
            except OrderLimitIsReachedException as error:
                orders_formatted = ' '.join(
                    '[*{number:0>3}*](t.me/c/{chat_id}/{message_id})'.format(
                        number=order.count,
                        chat_id=toggle_chat_id(message['chat']['id']),
                        message_id=order_message_id,
                    )
                    for order_message_id, order in sender_to_order_maps[error.sender_key].items()
                )

                try:
                    # TODO: автоматически удалять информационное сообщение через определённое время
                    text = '''\
🕯️ достигнут лимит сообщений 🕯️
*но можно _изменить_ существующие*
✨ просто _*ответь*_ на одно из них ✨:
{orders}'''.format(orders=orders_formatted)

                    telegram.api_call(
                        'sendMessage',
                        dict(
                            chat_id=message['chat']['id'],
                            text=text,
                            parse_mode='MarkdownV2',
                            disable_web_page_preview=True,
                            disable_notification=True,
                            protect_content=True,
                            reply_to_message_id=message['message_id'],
                        )
                    )
                except BotException:
                    logging.error(
                        f'Cannot send the text message "{text}" of the chat with id {message["chat"]["id"]!r}')
                logging.warning(f"{error}, Update {update['update_id']} skipped")
                continue
            except OrderException as error:
                logging.warning(f"{error}, Update {update['update_id']} skipped")
                continue

            try:
                # TODO: попробовать copyMessage + caption, вместо sendMessage
                # TODO: разобраться как работает ForceReply и для чего нужен
                sent_message = telegram.api_call(
                    'sendMessage',
                    dict(
                        chat_id=order.group_id,
                        text=str(order),
                        parse_mode='MarkdownV2',
                        disable_web_page_preview=True,
                        disable_notification=True,
                        protect_content=True,
                        reply_to_message_id=reply_to_message['message_id'],
                    )
                )
            except BotException:
                logging.error(f'Cannot send the text message "{order}" of the chat with id {order.group_id!r}')
                continue

            try:
                telegram.api_call(
                    'deleteMessage', dict(chat_id=message['chat']['id'], message_id=message['message_id']))
            except BotException:
                logging.error(f"Cannot delete the message {text!r} from {order.sender_name!r}")

            order.message_id = sent_message['message_id']
            sender_to_order_maps[order.sender_key][order.message_id] = order

            user_order_counter = active_post_map[post_key]['user_order_counter']
            user_order_counter[order.sender_key] += 1
            logging.info(f"User order count: {user_order_counter[order.sender_key]!r}, order.text is \"{order.text}\"")
            continue

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
        for channel_id, active_post_id in reversed(active_post_map):
            sender_key = channel_id, active_post_id, sender_id

            order = sender_to_order_maps[sender_key].get(reply_to_message['message_id'])
            if order:
                break
        else:
            logging.warning(
                f"message.reply_to_message.message_id {reply_to_message['message_id']!r} "
                    f"is not found in order maps {sender_to_order_maps!r}, Update {update['update_id']} skipped"
            )
            continue

        old_order = str(order)

        # TODO: пытаться получить статус if order.subscribed is None
        order.update(
            from_=from_,
            sender_chat=sender_chat,
            subscribed=order.subscribed,
            text=text,
        )

        if str(order) == old_order:
            logging.warning(f'No changes in the order "{order}"')
        else:
            try:
                edited_message = telegram.api_call(
                    'editMessageText',
                    dict(
                        chat_id=order.group_id,
                        message_id=order.message_id,
                        text=str(order),
                        parse_mode='MarkdownV2',
                        disable_web_page_preview=True,
                    )
                )
            except BotException:
                logging.error(
                    f'Cannot edit the text message {reply_to_message!r} of the chat with id {order.group_id!r}')
                edited_message = {}

            if not edited_message:
                continue

            logging.info(f'Edited order is "{order}"')

        try:
            telegram.api_call(
                'deleteMessage', dict(chat_id=message['chat']['id'], message_id=message['message_id']))
        except BotException:
            logging.error(f"Cannot delete the message {text!r} from {order.sender_name!r}")


def main():
    logging = LOG_BOT.getChild('main')
    telegram = TelegramAPI()
    logging.debug(repr(telegram))

    # Минимальные права:
    # - администратор связанной с каналом группы;
    # - удаление сообщений в группе;
    # - администратор канала;

    # TODO: убедиться что обычный пользователь ничего не получает в результатах и ничего не может сделать
    # TODO: похоже из-за inline_mode создаются также команды, доступные в связанной группе, вопрос для какого scope:
    #  - /ordertable@jkbxbot
    #  - /fansign@jkbxbot

    try:
        while True:
            try:
                updates = telegram.api_call('getUpdates', parameters_of_get_updates, timeout=config.EVENT_TIMEOUT)
            except BotException:
                logging.error(f"Cannot get updates")
                updates = []
            else:
                logging.debug(f"Got {len(updates)} updates")

            if not updates:
                continue

            process_updates(updates, telegram)
    finally:
        for last_welcome_message in last_welcome_message_map.values():
            try:
                telegram.api_call(
                    'deleteMessage',
                    dict(
                        chat_id=last_welcome_message['chat']['id'],
                        message_id=last_welcome_message['message_id'],
                    )
                )
            except BotException:
                logging.error(f"Cannot delete the message {last_welcome_message!r}")


if __name__ == '__main__':
    # TODO: переписать на python-telegram? https://github.com/alexander-akhmetov/python-telegram
    # TODO: переписать на Telethon? https://github.com/LonamiWebs/Telethon
    # TODO: переписать на pyrogram? https://github.com/pyrogram/pyrogram
    main()
