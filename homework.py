import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
import telegram
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler('my_logger.log',
                              encoding='UTF-8',
                              maxBytes=50000000,
                              backupCount=5
                              )
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(message)s, %(funcName)s, %(lineno)s'
)
handler.setFormatter(formatter)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = os.getenv('RETRY_TIME', 600)
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def init_logger():
    """Loggining в отдельной функции."""
    logging.basicConfig(
        level=logging.INFO,
        format=(
            '%(asctime)s [%(levelname)s] - '
            '(%(filename)s).%(funcName)s:%(lineno)d - %(message)s'
        ),
        handlers=[
            logging.FileHandler('output.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def send_message(bot, message):
    """Начали отправку сообщения в Telegram."""
    try:
        logger.info(
            f'Начали отправку сообщения в чат '
            f'{TELEGRAM_CHAT_ID}: '
            f'{message}'
        )
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(
            f'Успешная отправка сообщения в чат'
            f' {TELEGRAM_CHAT_ID}: '
            f'{message}'
        )
    except Exception:
        raise ValueError('Ошибка отправки сообщения')


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В случае успешного запроса должна вернуть ответ API,
    преобразовав его из формата JSON к типам данных Python.
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        logger.info(
            'Начинается соединение с апи для проверки {status} {homework}'
        )
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params=params
                                         )
    except Exception as error:
        raise Exception(f'Ошибка при запросе к основному API: {error}')
    if homework_statuses.status_code != HTTPStatus.OK:
        status_code = homework_statuses.status_code
        raise Exception(f'Ошибка  успешного запроса {status_code}')
    try:
        return homework_statuses.json()
    except ValueError:
        logger.error('Ошибка ответа из формата json')
        raise ValueError('Ошибка  ответа из формата json')


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError('В функцию поступил не словарь.')
    if 'homeworks' and 'current_date' not in response:
        raise KeyError('Некорректный ответ API')
    if not isinstance(response.get('homeworks'), list):
        raise TypeError('В функцию поступил не список.')
    if not response.get('homeworks'):
        raise Exception('Новых статусов нет')
    try:
        return response.get('homeworks')[0]
    except Exception:
        raise Exception('Нет домашних работ')


def parse_status(homework):
    """Извлекает из информации статус этой работы."""
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ "homework_name" в ответе API.')
    if 'status' not in homework:
        raise Exception('Отсутствует ключ "status" в ответе API.')
    homework_name = homework.get('homework_name')
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        raise Exception(f'Неизвестный статус работы: {homework_status}')
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствуют несколько переменных окружения ['
                        'PRACTICUM_TOKEN, '
                        'TELEGRAM_TOKEN, '
                        'TELEGRAM_CHAT_ID]'
                        )
        sys.exit('message')
        try:
            bot = telegram.Bot(token=TELEGRAM_TOKEN)
        except Exception:
            logger.info('Ошибка создания бота')
    current_timestamp = int(time.time())
    homework_statuses = ''
    error_message = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get('current_date')
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
            else:
                logger.error('Нет домашней работы')
            if message != homework_statuses:
                send_message(bot, message)
                homework_statuses = message
        except Exception:
            logger.error('Ожидание ответа')
            telegram_message = str('Началась проверка домашнего задания')
            if telegram_message != error_message:
                send_message(bot, telegram_message)
                error_message = telegram_message
                logger.error('Отправка сообщения не возможна, '
                             'не работает приложение телеграмм;'
                             )
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    init_logger()
    main()
