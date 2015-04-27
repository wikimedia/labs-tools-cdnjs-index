#!/usr/bin/python
import argparse
import jinja2
import re
import requests


def github_stars(user, repo):
    """Get number of github stars a repo has"""
    url = "https://api.github.com/repos/%s/%s" % (user, repo)
    data = requests.get(url).json()
    return data.get('stargazers_count', 0)

argparser = argparse.ArgumentParser()

argparser.add_argument('templatepath', help='Full path to jinja2 template')
argparser.add_argument('cdnjsurl', help='URL to CDNjs packages.json')
argparser.add_argument('outputpath', help='Path to html output')
args = argparser.parse_args()

with open(args.templatepath) as f:
    html = jinja2.Template(f.read(), autoescape=True)

all_packages = requests.get(args.cdnjsurl).json()
libraries = []

for package in all_packages:
    lib = {
        'name': package['name'],
        'description': package.get('description', None),
        'version': package['version'],
        'homepage': package.get('homepage', None),
        'keywords': package.get('keywords', []),
    }
    url = None
    if 'repositories' in package:
        if isinstance(package['repositories'], dict):
            url = package['repositories']['url']
        elif isinstance(package['repositories'], list) and len(package['repositories']) > 0:
            url = package['repositories'][0]['url']
    if 'repository' in package and 'url' in package['repository']:
        url = package['repository']['url']

    if url is not None and 'github.com/' in url:
        parts = re.sub(r'^\w+://', '', url).split('/')
        user_name, repo_name = parts[1], parts[2]
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        print 'Fetching starcount for %s/%s' % (user_name, repo_name)
        lib['stars'] = github_stars(user_name, repo_name)

    libraries.append(lib)


libraries.sort(key=lambda lib: lib.get('stars', 0), reverse=True)
with open(args.outputpath, 'wb') as f:
    f.write(html.render({
        'libraries': libraries,
    }).encode('utf-8'))
