#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Create a static website out of output from the cdnjs API for directing people
to a reverse proxy of the cdnjs libraries.
"""

import argparse
import os
import re

import jinja2
import requests

def github_stars(user, repo, token):
    """Get number of github stars a repo has"""
    url = "https://api.github.com/repos/%s/%s" % (user, repo)
    headers = {'Authorization': 'token {}'.format(token)}
    data = requests.get(url, headers=headers).json()
    return data.get('stargazers_count', 0)

def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        '--token', dest='github_token', metavar='<github_token>', type=str,
        required=True,
        help=(
            'A filename with a GitHub personal access token'
            'with public_repos permission'))
    argparser.add_argument('outputpath', help='Path to html output')

    args = argparser.parse_args()

    outputdir = args.outputpath

    with open('template.html.j2') as index_temp:
        html = jinja2.Template(index_temp.read(), autoescape=True)

    with open('modal-template.html.j2') as modal_temp:
        helper = jinja2.Template(modal_temp.read(), autoescape=True)

    with open(args.github_token) as token_file:
        github_token = token_file.read()

    github_token = github_token.strip()

    fields = "version,description,homepage,keywords,license,repository,author,assets"
    upstream_url = "https://api.cdnjs.com/libraries?fields={}".format(fields)
    with requests.get(upstream_url, stream=True) as resp:
        json_resp = resp.json()

    all_packages = json_resp['results']

    libraries = []

    for package in all_packages:
        lib = {
            'name': package['name'],
            'description': package.get('description', None),
            'version': package.get('version', None),
            'homepage': package.get('homepage', None),
            'keywords': package.get('keywords', []),
            'assets': package.get('assets', [])
        }
        if package['repository'] and \
            'github.com/' in package['repository'].get('url', ''):
            url = package['repository']['url']
        else:
            url = None

        if url is not None:
            parts = re.sub(r'^\w+://', '', url).split('/')
            user_name, repo_name = parts[-2], parts[-1]
            if repo_name.endswith('.git'):
                repo_name = repo_name[:-4]
            print('Fetching starcount for {}/{}'.format(user_name, repo_name))
            lib['stars'] = github_stars(user_name, repo_name, github_token)

        libraries.append(lib)


    libraries.sort(key=lambda lib: lib.get('stars', 0), reverse=True)
    with open(os.path.join(outputdir, 'index.html'), 'w') as index_file:
        index_file.write(html.render({
            'libraries': libraries,
        }))

    for lib in libraries:
        with open(os.path.join(outputdir, 'mod' + lib['name'] + '.html'), 'w') as modal_file:
            modal_file.write(
                helper.render({'lib': lib})
            )

if __name__ == '__main__':
    main()
