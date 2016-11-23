# -*- coding: utf-8 -*-
from datetime import date, timedelta
import requests

REPOS_CREATION_PERIOD = 7
TOP_REPOS_COUNT = 20


def get_trending_repositories(top_size):
    week_ago = date.today() - timedelta(days=REPOS_CREATION_PERIOD)
    url = 'https://api.github.com/search/repositories'
    payload = {'q': 'created:>%s' % week_ago.isoformat(),
               'sort': 'stars', 'order': 'desc'}
    return requests.get(url, params=payload).json()['items'][:top_size]


def get_open_issues(repo_owner, repo_name):
    url = 'https://api.github.com/repos/%s/%s/issues?state=open' % \
          (repo_owner, repo_name)
    issues = requests.get(url).json()
    return [issue for issue in issues if 'pull_request' not in issue]


if __name__ == '__main__':
    print('\nFetching top rated %i repositories, created in last %i days' %
          (TOP_REPOS_COUNT, REPOS_CREATION_PERIOD))
    top_repos = get_trending_repositories(TOP_REPOS_COUNT)
    for repo in top_repos:
        print('\nRepo owner: ', repo['owner']['login'])
        print('Repo name: ', repo['name'])
        issues = get_open_issues(repo['owner']['login'], repo['name'])
        if len(issues):
            print('Issues amount: %i' % len(issues))
            print('Issues urls:')
            for issue in issues:
                print(issue['url'])
