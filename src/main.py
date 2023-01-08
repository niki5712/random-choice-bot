import asyncio
import mimetypes
import os
from collections import Counter, defaultdict
from datetime import datetime
from itertools import count

from telethon.sync import TelegramClient, errors, events, types

import config
from common import match_order, search_bot_mention
from constant.chat import id as chat_id
from error import OrderException, OrderLimitIsReachedException
from log import LOG_BOT
from type import MessageKey, Order, OrderSenderKey, SenderKey


# TODO: уметь обновлять active_post_map налету (можно отредактировать соответствующий пост)
active_post_map = defaultdict(dict)
sender_to_order_maps = defaultdict(dict)

channel_user_map = dict()

last_group_message_map = defaultdict(dict)
last_welcome_message_map = defaultdict(dict)

start_time = datetime.now()

lock = asyncio.Lock()


# TODO: разобраться с тем, как с минимальными правами получать только нужные сообщения, а не все из группы.
#  администратор получается не нужен, но без администратора нельзя удалять сообщения...
# https://core.telegram.org/bots/faq#what-messages-will-my-bot-get


def add_handlers_for_draw(client):
    # TODO: в логе не хватает информации для какого поста характерна та или иная проблема
    #  и контекст лучше писать после описания проблемы, а не до
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
    # TODO: показать кнопку я тут, если Лёля нажала кнопку покажи себя на записи выигравшего
    # TODO: добавить анимацию печати если требуется подождать

    # обновить статус участника в канале
    @client.on(events.ChatAction(
        chats=chat_id.CHANNEL_IDS,
        func=lambda event: any([event.user_joined, event.user_left, event.user_added, event.user_kicked]),
    ))
    async def channel_participant_handler(event):
        async with lock:
            logging = LOG_BOT.getChild('channel_participant_handler')

            subscribed = event.user_joined or event.user_added or not (event.user_left or event.user_kicked)

            for post_key in reversed(active_post_map):
                if post_key.chat_id != event.chat_id:
                    continue

                for user_id in event.user_ids:
                    channel_user_map[SenderKey(chat_id=post_key.chat_id, sender_id=user_id)] = subscribed

                    sender_key = OrderSenderKey(
                        post_id=post_key.chat_id, comment_id=post_key.message_id, sender_id=user_id)
                    for order in reversed(sender_to_order_maps[sender_key].values()):
                        order.update(subscribed=subscribed)

                        try:
                            # TODO: хранить в order объект message?
                            await event.client.edit_message(
                                entity=order.comment_key.chat_id,
                                message=order.comment_key.message_id,
                                text=str(order),
                                link_preview=False,
                            )
                        except errors.MessageNotModifiedError as error:
                            logging.warning(f'{error}. No changes in order "{order}"')
                        except errors.RPCError as error:
                            logging.error(f'{error}. Cannot edit order "{order}": order {order!r}')
                            continue
                        else:
                            logging.info(f'Edited order is "{order}"')

    # предложить создать пост для розыгрыша
    @client.on(events.InlineQuery)
    async def inline_query_handler(event):
        async with lock:
            logging = LOG_BOT.getChild('inline_query_handler')

            if not isinstance(event.query.peer_type, types.InlineQueryPeerTypeBroadcast):
                logging.warning(
                    f"not isinstance(peer_type, InlineQueryPeerTypeBroadcast): "
                        f"inline_query.query {event.query}, Update {event} skipped"
                )
                try:
                    await event.answer()
                except errors.RPCError as error:
                    logging.error(f"{error}. Cannot answer to inline query {event.query}")
                return

            # TODO: может приходится перезаходить в канал, чтобы увидеть InlineQueryResult из-за пустого запроса?
            # TODO: осуществлять поиск по inline_query['query']
            # TODO: обеспечить обратную совместимость, разрешить отправлять произвольный текст после упоминания бота
            # TODO: можно ли сделать, чтобы слайдер был горизонтальным? через картинки?

            # TODO: создать функцию make_thumb
            ordertable_thumb_url = (
                'https://e7.pngegg.com/pngimages/862/929/'
                    'png-clipart-musical-instruments-bass-guitar-acoustic-guitar-string-instruments-'
                    'musical-instruments-guitar-accessory-cuatro.png'
            )
            ordertable_thumb_mime_type, _ = mimetypes.guess_type(ordertable_thumb_url)

            fansign_thumb_url = (
                'https://e7.pngegg.com/pngimages/279/99/'
                    'png-clipart-digital-cameras-graphy-video-cameras-drawing-camera-rectangle-photography.png'
            )
            fansign_thumb_mime_type, _ = mimetypes.guess_type(ordertable_thumb_url)

            builder = event.builder

            try:
                await event.answer([
                    builder.article(
                        title='ordertable 🎵',
                        description='пост для розыгрыша песен',
                        thumb=types.InputWebDocument(
                            url=ordertable_thumb_url,
                            size=0,
                            mime_type=ordertable_thumb_mime_type,
                            attributes=[],
                        ),
                        # TODO: придумать как добавить поддержку spoiler
                        text=config.ORDERTABLE_MARKDOWN,
                        link_preview=False,
                    ),
                    builder.article(
                        title='fansign 📷',
                        description='пост для розыгрыша сигн',
                        thumb=types.InputWebDocument(
                            url=fansign_thumb_url,
                            size=0,
                            mime_type=fansign_thumb_mime_type,
                            attributes=[],
                        ),
                        # TODO: придумать как добавить поддержку spoiler
                        text=config.FANSIGN_MARKDOWN,
                        link_preview=False,
                    ),
                ])
            except errors.RPCError as error:
                logging.error(f"{error}. Cannot answer to inline query {event.query}")

    async def post_handler(event):
        async with lock:
            logging = LOG_BOT.getChild('post_handler')

            # # TODO: понять как работать с entities: [{'length': 8, 'offset': 38, 'type': 'mention'}],
            # #  text: 'пост для выбора вашей песни на стриме @eljsbot'
            # # TODO: Обработать ситуацию когда из активного поста убрали упоминание бота
            # bot_mention = search_bot_mention(event.raw_text)
            # if not bot_mention:
            #     logging.warning(
            #         f"message.text {event.raw_text!r} doesn't mention bot {config.USERNAME!r}, "
            #             f"Update {event} skipped"
            #     )
            #     return
            # # # TODO: избавиться от необходимости упоминать бота явно, но оставить совместимость
            # # via_bot = event.via_bot
            # # if not via_bot:
            # #     logging.warning(f"message {event.message}: no via_bot, Update {event} skipped")
            # #     return
            # # elif via_bot.username != config.USERNAME:
            # #     logging.warning(
            # #         f"message.via_bot {via_bot}: username != {config.USERNAME!r}, "
            # #             f"Update {event} skipped"
            # #     )
            # #     return

            if not event.forward.saved_from_msg_id:
                logging.warning(
                    f"message.forward {event.forward}: "
                        f"no saved_from_msg_id, message was forwarded manually, Update {event} skipped"
                )
                return

            if not event.forward.channel_post:
                logging.warning(f"message.forward {event.forward}: no channel_post, Update {event} skipped")
                return

            # TODO: post_date теперь в UTC+0, устанавливать tzinfo или перевести лог в UTC+0?
            post_date = event.edit_date or event.forward.date
            if not post_date:
                logging.warning(f"message {event.message}: no post_date, Update {event} skipped")
                return

            logging.info(f"Active channel post at {post_date} is \"{event.raw_text}\"")
            logging.debug(f'Active channel post ID is {event.forward.channel_post}')

            post_key = MessageKey(chat_id=event.forward.chat_id, message_id=event.forward.channel_post)
            if isinstance(event, events.MessageEdited.Event) and post_key in active_post_map:
                active_post_map[post_key]['user_order_limit'] = int(
                    event.pattern_match.group('limit') or config.USER_ORDER_LIMIT)
            else:
                active_post_map[post_key] = dict(
                    channel_id=event.forward.chat_id,
                    id=event.forward.channel_post,
                    message_id=event.id,
                    user_order_counter=Counter(),  # TODO: defaultdict(lambda: count(start=1))
                    user_order_limit=int(event.pattern_match.group('limit') or config.USER_ORDER_LIMIT),
                    count_order=count(start=1)
                )

            logging.info(f"User order limit is {active_post_map[post_key]['user_order_limit']}")

    # найти активный пост
    post_event_kwargs = dict(
        chats=chat_id.GROUP_IDS,
        incoming=True,
        from_users=chat_id.CHANNEL_IDS,
        forwards=True,
        pattern=search_bot_mention,
    )
    client.add_event_handler(post_handler, events.NewMessage(**post_event_kwargs))
    client.add_event_handler(post_handler, events.MessageEdited(**post_event_kwargs))

    async def order_handler(event):
        async with lock:
            logging = LOG_BOT.getChild('order_handler')

            # TODO: одним reply_to не обойтись, но возможно получится избавиться от дополнительного запроса,
            #  если в active_post_map иначе хранить записи
            try:
                reply_to_message = await event.get_reply_message()
            except errors.RPCError as error:
                logging.error(f"{error}. Cannot get reply message, Update {event} skipped")
                return

            if not reply_to_message.forward:
                logging.warning(f"no forward: message.reply_to_message {reply_to_message}, Update {event} skipped")
                return

            post_key = MessageKey(
                chat_id=reply_to_message.forward.chat_id, message_id=reply_to_message.forward.channel_post)

            if post_key not in active_post_map:
                logging.warning(
                    f"message.reply_to_message.forward {reply_to_message.forward}: "
                        f"post_key {post_key} not in active_post_map {active_post_map}, Update {event} skipped"
                )
                return

            try:
                if event.sender_id:
                    sender_id = event.sender_id
                    sender = await event.get_sender()
                else:
                    # TODO: нужен баг на telethon? у сообщений отправленных от имени группы, а не канала
                    #  from_id=None и sender_id=None
                    logging.warning(f"no sender_id: message {event.message}")
                    sender_id = event.chat_id
                    sender = await event.get_chat()
                    logging.warning(f"new sender is {sender}")
            except errors.RPCError as error:
                logging.error(f"{error}. Cannot get sender, Update {event} skipped")
                return

            channel_user_key = SenderKey(chat_id=post_key.chat_id, sender_id=sender_id)

            try:
                if sender_id in [post_key.chat_id, event.chat_id]:
                    sender_subscribed = channel_user_map.setdefault(channel_user_key, True)
                elif channel_user_key in channel_user_map:
                    sender_subscribed = channel_user_map[channel_user_key]
                else:
                    sender_participant = (
                        await client.get_permissions(entity=post_key.chat_id, user=sender_id)).participant
                    sender_subscribed = not (sender_participant.has_left or sender_participant.is_banned)
                    channel_user_map[channel_user_key] = sender_subscribed
            except errors.UserNotParticipantError as error:
                logging.warning(f"{error}. Cannot get permissions for user {sender} of channel {post_key.chat_id}")
                sender_subscribed = channel_user_map[channel_user_key] = False
            except (ValueError, errors.RPCError) as error:
                logging.error(f"{error}. Cannot get permissions for user {sender} of channel {post_key.chat_id}")
                sender_subscribed = None

            # TODO: как обойтись без asyncio.Lock()?
            # если одновременно отправить сразу пачку сообщений от одного отправителя,
            #  то они отправятся в хаотичном порядке и active_post_map[post_key]['user_order_limit'] игнорируется
            #  orders_formatted тоже в хаотичном порядке будет
            try:
                order = Order(
                    event=event,
                    post_key=post_key,
                    active_post=active_post_map[post_key],
                    sender=sender,
                    subscribed=sender_subscribed,
                )

                try:
                    # TODO: попробовать copyMessage + caption, вместо sendMessage
                    # TODO: разобраться как работает ForceReply и для чего нужен
                    # TODO: можно ли добавлять reply_markup к пользовательским сообщениям?
                    sent_message = await event.respond(
                        message=str(order),
                        link_preview=False,
                        silent=True,
                        # TODO: protect_content=True, похоже надо прокидывать noforwards=True
                        reply_to=reply_to_message,
                    )
                except errors.RPCError as error:
                    logging.error(f'{error}. Cannot send message "{order}": order {order!r}')
                    return

                order.comment_key = MessageKey(chat_id=event.chat_id, message_id=sent_message.id)

                user_order_counter = active_post_map[post_key]['user_order_counter']
                user_order_counter[order.sender_key] += 1
                logging.info(
                    f"User order count: {user_order_counter[order.sender_key]}, order.text is \"{order.text}\"")
            except OrderLimitIsReachedException as error:
                orders_formatted = ' '.join(
                    '[{number:0>3}](t.me/c/{chat_id}/{message_id})'.format(
                        number=order.count,
                        chat_id=event.peer_id.channel_id,
                        message_id=order_message_id,
                    )
                    for order_message_id, order in sender_to_order_maps[error.sender_key].items()
                )

                text = f'''\
достигнут лимит сообщений, но
**можно __изменить__ существующие**,
просто ответь на одно из них:
**{orders_formatted}**
__**автоматическое сообщение**__'''

                try:
                    # TODO: автоматически удалять информационное сообщение через определённое время
                    await event.reply(
                        message=text,
                        link_preview=False,
                        # TODO: protect_content=True, похоже надо прокидывать noforwards=True
                    )
                except errors.RPCError as reply_error:
                    logging.error(f'{reply_error}. Cannot send message "{text}" of chat {event.chat_id}')
                logging.warning(f"{error}. Update {event} skipped")
                return
            except OrderException as error:
                logging.warning(f"{error}. Update {event} skipped")
                return

            sender_to_order_maps[order.sender_key][order.comment_key.message_id] = order

            try:
                await event.delete()
            except errors.RPCError as error:
                logging.error(f"{error}. Cannot delete message {event.message}")

    # найти заказы
    # TODO: добавить в func простое условие, чтобы отбрасывать события для reply_to_order_handler и не нужно было
    #  запрашивать get_reply_message()
    order_event_kwargs = dict(
        chats=chat_id.GROUP_IDS,
        func=lambda event: active_post_map and event.is_reply and not event.fwd_from,
        incoming=True,
        forwards=False,  # TODO: завести баг на telethon? not event.fwd_from
        pattern=match_order,
    )
    client.add_event_handler(order_handler, events.NewMessage(**order_event_kwargs))
    client.add_event_handler(order_handler, events.MessageEdited(**order_event_kwargs))

    # найти правки заказов
    # TODO: добавить в func простое условие, чтобы отбрасывать события для order_handler и не нужно было
    #  запрашивать get_reply_message()
    @client.on(events.NewMessage(
        chats=chat_id.GROUP_IDS,
        func=lambda event: active_post_map and event.is_reply and not event.fwd_from,
        incoming=True,
        forwards=False,  # TODO: завести баг на telethon? not event.fwd_from
        pattern=match_order,
    ))
    async def reply_to_order_handler(event):
        async with lock:
            logging = LOG_BOT.getChild('reply_to_order_handler')

            # TODO: одним reply_to не обойтись, но возможно получится избавиться от дополнительного запроса,
            #  если в active_post_map иначе хранить записи
            try:
                reply_to_message = await event.get_reply_message()
            except errors.RPCError as error:
                logging.error(f"{error}. Cannot get reply message, Update {event} skipped")
                return

            if not reply_to_message.out:
                logging.warning(f"is not outgoing: message.reply_to_message {reply_to_message}, Update {event} skipped")
                return

            if event.sender_id:
                sender_id = event.sender_id
            else:
                # TODO: нужен баг на telethon? у сообщений отправленных от имени группы, а не канала
                #  from_id=None и sender_id=None
                logging.warning(f"no sender_id: message {event.message}")
                sender_id = event.chat_id
                logging.warning(f"new sender_id is {sender_id}")

            # TODO: упростить, можем ли взять в качестве id что-то кроме active_post_id?
            for post_key in reversed(active_post_map):
                sender_key = OrderSenderKey(
                    post_id=post_key.chat_id, comment_id=post_key.message_id, sender_id=sender_id)

                order = sender_to_order_maps[sender_key].get(reply_to_message.id)
                if order:
                    break
            else:
                logging.warning(
                    f"id is not found in order maps {sender_to_order_maps[sender_key]}: "
                        f"message.reply_to_message {reply_to_message}, Update {event} skipped"
                )
                return

            # TODO: пытаться получить статус if order.subscribed is None
            order.update(text=event.raw_text)

            try:
                await reply_to_message.edit(text=str(order))
            except errors.MessageNotModifiedError as error:
                logging.warning(f'{error}. No changes in order "{order}"')
            except errors.RPCError as error:
                logging.error(f"{error}. Cannot edit message {reply_to_message}")
                return
            else:
                logging.info(f'Edited order is "{order}"')

            try:
                await event.delete()
            except errors.RPCError as error:
                logging.error(f"{error}. Cannot delete message {event.message}")


def add_handlers_for_discussion(client):
    async def group_message_handler(event):
        async with lock:
            last_group_message_map[event.chat_id] = event.message

    # обновить last_group_message_map
    group_message_event_kwargs = dict(chats=chat_id.GROUP_IDS)
    client.add_event_handler(group_message_handler, events.NewMessage(**group_message_event_kwargs))
    client.add_event_handler(group_message_handler, events.MessageEdited(**group_message_event_kwargs))


def main():
    logging = LOG_BOT.getChild('main')

    api_id, _, api_hash = os.environ['JUKEBOX_BOT_APP_API_TOKEN'].partition(':')
    bot_token = os.environ['JUKEBOX_BOT_AUTH_TOKEN']

    with TelegramClient(
            session=str(config.SESSION_DIR / 'bot'), api_id=int(api_id), api_hash=api_hash,
            request_retries=config.REQUEST_RETRIES,
            connection_retries=config.CONNECTION_RETRIES,
            retry_delay=config.RETRY_DELAY,
    ).start(bot_token=bot_token) as client:
        logging.debug(client)

        # Минимальные права:
        # - администратор связанной с каналом группы;
        # - удаление сообщений в группе;
        # - администратор канала;

        # TODO: убедиться что обычный пользователь ничего не получает в результатах и ничего не может сделать
        # TODO: похоже из-за inline_mode создаются также команды, доступные в связанной группе, вопрос для какого scope:
        #  - /ordertable@jkbxbot
        #  - /fansign@jkbxbot

        add_handlers_for_draw(client)
        add_handlers_for_discussion(client)

        client.run_until_disconnected()


if __name__ == '__main__':
    # TODO: переписать на python-telegram? https://github.com/alexander-akhmetov/python-telegram
    # TODO: переписать на pyrogram? https://github.com/pyrogram/pyrogram
    main()
