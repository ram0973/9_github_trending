# -*- coding: utf-8 -*-
from datetime import date, timedelta
import os
import time
import sys
import requests
from cachecontrol import CacheControl
from cachecontrol.caches import FileCache
from requests import ConnectionError, HTTPError, Timeout, TooManyRedirects
from os.path import join, dirname
from dotenv import load_dotenv

REPOSITORIES_CREATION_PERIOD = 7
TOP_REPOSITORIES_COUNT = 20
REQUESTS_CACHE_FOLDER = '.webcache'
GITHUB_API_DOMAIN = 'https://api.github.com/'
SECRETS_FILE_NAME = '.secrets'


def enable_win_unicode_console():
    """
    Включаем правильное отображение unicode в консоли под MS Windows
    """
    if sys.platform == 'win32':
        import win_unicode_console
        win_unicode_console.enable()


def handle_requests_library_exceptions(decorated):
    """
    Декоратор, обрабатывающий ошибки в requests
    :param decorated: Функция, в которой надо отловить requests exceptions
    :return: декоратор
    """
    def decorator(*args, **kwargs):
        try:
            return decorated(*args, **kwargs)
        except ConnectionError:
            print('Ошибка сетевого соединения')
            exit(1)
        except HTTPError as e:
            print('Сервер вернул неудачный код статуса ответа: %s %i' %
                  (e.response.reason, e.response.status_code))
            exit(1)
        except Timeout:
            print('Вышло время ожидания ответа от сервера')
            exit(1)
        except TooManyRedirects:
            print('Слишком много редиректов')
            exit(1)

    return decorator


@handle_requests_library_exceptions
def get_github_rate_limit(session: requests.Session):
    """
    Получаем статус лимита запросов к API Github
    https://developer.github.com/v3/rate_limit/
    """
    response = session.get(GITHUB_API_DOMAIN + 'rate_limit')
    response.raise_for_status()
    return response.json()


class GitHubRateLimitExceeded(Exception):
    """
    Исключение при превышении лимита запросов к API Github
    """
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


@handle_requests_library_exceptions
def get_trending_repositories(session: requests.Session,
                              top_size: int) -> list:
    """
    Получаем топовые репозитории, созданные на ранее недели назад,
    с максимальным количеством звезд
    :param session: сессия
    :param top_size: количество репозиториев
    :return: список репозиториев
    """
    week_ago = date.today() - timedelta(days=REPOSITORIES_CREATION_PERIOD)
    url = GITHUB_API_DOMAIN + 'search/repositories'
    params = {'q': 'created:>%s' % week_ago.isoformat(),
                   'sort': 'stars', 'order': 'desc'}
    response = session.get(url, params=params)
    if not int(response.headers['X-RateLimit-Remaining']):
        # Exception.value будет содержать заголовки (Headers) ответа сервера
        raise GitHubRateLimitExceeded(response.headers)
    response.raise_for_status()
    return response.json()['items'][:top_size]


@handle_requests_library_exceptions
def get_open_issues(session: requests.Session,
                    repo_owner: str,
                    repo_name: str) -> list:
    """
    Получаем открытые issue для репозитория
    :param session: сессия
    :param repo_owner: владелец репо
    :param repo_name: имя репо
    :return: список открытых issue для репозитория без учёта pull-requests
    """
    url = '%srepos/%s/%s/issues?state=open' % \
          (GITHUB_API_DOMAIN, repo_owner, repo_name)
    response = session.get(url)
    if not int(response.headers['X-RateLimit-Remaining']):
        # Exception.value будет содержать заголовки (Headers) ответа сервера
        raise GitHubRateLimitExceeded(response.headers)
    response.raise_for_status()
    issues = response.json()
    return [issue for issue in issues if 'pull_request' not in issue]


def get_open_issues_amount(session: requests.Session,
                           repo_owner: str,
                           repo_name: str) -> int:
    """
    Получаем количество открытых issue для репозитория
    :param session: сессия
    :param repo_owner: владелец репо
    :param repo_name: имя репо
    :return: количество открытых issue для репозитория без учёта pull-requests
    """
    issues = get_open_issues(session, repo_owner, repo_name)
    return len(issues)


def get_open_issues_urls(issues: list) -> list:
    """
    Получаем список всех url для issues репозитория
    :param issues: список issues
    :return: список url
    """
    return [issue['url'] for issue in issues]


def get_repos_with_issues(session: requests.Session, repos: list) -> list:
    """
    Получаем список репозиториев вместе с их issues
    :param session: сессия
    :param repos: список репозиториев
    :return: список репозиториев вместе с их issues
    """
    repos_with_issues = []
    for repo in repos:
        issues = get_open_issues(session, repo['owner']['login'], repo['name'])
        urls = get_open_issues_urls(issues) if issues else []
        repos_with_issues.append({'repo': repo, 'open_issues_urls': urls})

    return repos_with_issues


def print_repos_info(repos_with_issues: list):
    """
    Печать списка репозиториев и их issues
    """
    for item in repos_with_issues:
        print('\nВладелец репо: ', item['repo']['owner']['login'])
        print('Название репо: ', item['repo']['name'])
        print('Звёзд: ', item['repo']['stargazers_count'])
        open_issues_amount = len(item['open_issues_urls'])
        print('Количество issue: %i' % open_issues_amount)
        if open_issues_amount:
            print('Ссылки на issue:')
            for issue_url in item['open_issues_urls']:
                print(issue_url)


def print_github_api_rate_status(api_rate: dict):
    """
    Печать статуса ограничения запросов к API Github
    https://developer.github.com/v3/rate_limit/
    """
    print('Ограничение поисковых запросов: {0} из {1}'.format(
        api_rate['resources']['search']['remaining'],
        api_rate['resources']['search']['limit']))
    print('Отмена ограничений на них в %s\n' % time.strftime(
              '%H:%M:%S %d.%m.%Y ',
              time.localtime(int(api_rate['resources']['search']['reset']))))
    if 'graphql' in api_rate['resources']:
        print('Ограничение graphql запросов: {0} из {1}'.format(
            api_rate['resources']['graphql']['remaining'],
            api_rate['resources']['graphql']['limit']))
        print('Отмена ограничений на них в %s\n' % time.strftime(
              '%H:%M:%S %d.%m.%Y ',
              time.localtime(int(api_rate['resources']['search']['reset']))))
    print('Лимит всех остальных запросов: {0} из {1}'.format(
        api_rate['resources']['core']['remaining'],
        api_rate['resources']['core']['limit']))
    print('Отмена ограничений на них в %s' %
          time.strftime('%H:%M:%S %d.%m.%Y ', time.localtime(int(
              api_rate['resources']['core']['reset']))))


if __name__ == '__main__':

    enable_win_unicode_console()

    secrets_file_path = join(dirname(__file__), SECRETS_FILE_NAME)
    load_dotenv(secrets_file_path)
    github_token = os.environ.get('GITHUB_TOKEN')

    github_api_session = requests.Session()
    if github_token:
        github_api_session.headers['Authorization'] = 'token %s' % github_token

    # кешируем все запросы в сессии
    github_api_session = CacheControl(github_api_session,
                                      cache=FileCache(REQUESTS_CACHE_FOLDER))

    # Выводим лимиты Github API (для справки)
    print_github_api_rate_status(get_github_rate_limit(github_api_session))

    print('\nЗагружаем список %i репозиториев, созданных за %i дней' %
          (TOP_REPOSITORIES_COUNT, REPOSITORIES_CREATION_PERIOD))
    print('и набравших максимальное количество звёзд...')
    try:
        top_repos = get_trending_repositories(github_api_session,
                                              TOP_REPOSITORIES_COUNT)
        repos_info = get_repos_with_issues(github_api_session, top_repos)
    except GitHubRateLimitExceeded:
        print('\nПревышен текущий лимит запросов к API.')
        print_github_api_rate_status(get_github_rate_limit(github_api_session))
        exit(1)

    print_repos_info(repos_info)
