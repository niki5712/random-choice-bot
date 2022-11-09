import requests

from common import SecretStr, BotException
import config
from log import LOG_BOT


class TelegramAPI:
    _token = SecretStr(config.AUTH_TOKEN)

    def __init__(self):
        self._base_url = f'{config.API_SERVER}/bot' + self._token + '/'
        self._request_timeout = config.REQUEST_TIMEOUT

        self._logger = LOG_BOT.getChild(self.__class__.__name__)
        self._logger.debug(f'Call {self}.__init__()')

    def perform_request(self, method, path, **kwargs):
        if method.lower() not in ['get', 'post']:
            raise BotException(f'{self}.perform_request: unknown method: {method}')

        try:
            response = getattr(requests, method.lower())(
                url=f'{self._base_url}{path}',
                timeout=self._request_timeout,
                **kwargs
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as error:
            raise BotException(str(error))

        return response

    def __str__(self):
        return f'<{self.__class__.__name__}>'

    def api_call(self, method, parameters=None):
        if parameters is None:
            parameters = {}

        self._logger.debug(
            f'Call {self}.api_call({method!r}, {parameters!r})')

        try:
            response = self.perform_request(method='post', path=method, json=parameters)
            # response.raise_for_status()  # TODO: проверить не лишаюсь ли я информации об обшибке из-за этой строки

            response_json = response.json()

            if not response_json['ok']:
                raise BotException(f'Unsuccessful request, got: {response_json!r}')

            result = response_json['result']

            self._logger.debug(f'Result of {self}.api_call is "{result}"')

            return result
        except BotException as error:
            error_message = str(error)
        except requests.exceptions.JSONDecodeError:
            # noinspection PyUnboundLocalVariable
            error_message = 'Unexpected response Content-Type: {!r}'.format(response.headers.get('Content-Type'))
        except KeyError:
            # noinspection PyUnboundLocalVariable
            error_message = f'Unexpected response scheme: {response_json!r}'

        error = BotException(error_message)

        self._logger.debug(
            f'Exception raised from {self}.api_call: {error.__class__.__name__} "{error}"')

        raise error
