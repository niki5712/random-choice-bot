import os
from datetime import datetime
from time import sleep

from telethon import errors
from telethon.sync import TelegramClient

from log import LOG_BOT


def clear_chat(client):
    logging = LOG_BOT.getChild('clear_chat')

    chat_entity = input('Enter the chat entity where the script should remove Deleted Accounts from: ')
    logging.info('Enter the chat entity from where the script should remove Deleted Accounts from: ')

    my_chat = client.get_entity(chat_entity)
    print(f'Chat entity: {my_chat.to_dict()!r}')
    logging.info(f'Chat entity: {my_chat.to_dict()!r}')

    num = client.get_participants(my_chat, limit=0).total
    print(f'Total participants: {num}')
    logging.info(f'Total participants: {num}')
    sleep(0.5)
    deleted_account_list = []

    for num, user in enumerate(client.iter_participants(my_chat), start=1):
        sleep(0.1)

        if not user.deleted:
            continue

        try:
            print(f'Deleted Account: {user.to_dict()}')
            logging.debug(f'Deleted Account: {user.to_dict()}')
            _service_message = client.kick_participant(my_chat, user)
            sleep(0.5)
            print(f'service_message: {_service_message and _service_message.to_dict()}')
            logging.debug(f'service_message: {_service_message and _service_message.to_dict()}')

            deleted_account_list.append(user)
        except Exception as error:
            print(f'Failed to kick one Deleted Account because: {str(error)}')
            logging.error(f'Failed to kick one Deleted Account because: {str(error)}')

    print(f'Total participants: {num}')
    logging.info(f'Total participants: {num}')

    if deleted_account_list:
        print(f'Kicked {len(deleted_account_list)} Deleted Accounts')
        logging.info(f'Kicked {len(deleted_account_list)} Deleted Accounts')
    else:
        print(f'No Deleted Accounts found in {my_chat}')
        logging.info(f'No Deleted Accounts found in {my_chat}')

    num = client.get_participants(my_chat, limit=0).total
    print(f'Total participants: {num}')
    logging.info(f'Total participants: {num}')
    sleep(0.5)


def main():
    logging = LOG_BOT.getChild('main')

    session_file = f'../session/{datetime.now():%Y-%m-%d-%H%M%S}'
    api_id, _, api_hash = os.environ['JUKEBOX_BOT_APP_API_TOKEN'].partition(':')
    bot_token = os.environ['JUKEBOX_BOT_AUTH_TOKEN']

    try:
        with TelegramClient(session_file, int(api_id), api_hash).start(bot_token=bot_token) as client:
            sleep(0.5)
            clear_chat(client)
            client.log_out()  # TODO: помогает избавиться от ImportBotAuthorizationRequest? нет!
    except errors.FloodWaitError as error:
        print(f'Failed to authorize because: {str(error)}')
        logging.info(f'Failed to authorize because: {str(error)}')
        sleep(error.seconds)


if __name__ == '__main__':
    main()
