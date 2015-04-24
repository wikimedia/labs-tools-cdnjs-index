#!/usr/bin/python
import argparse
import jinja2
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

html = jinja2.Template(args.templatepath, autoescape=True)

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
    if 'repositories' in package and len(package['repositories']):
        for repo in package['repositories']:
            print package['name'], repo
            if 'github.com/' in repo['url']:
                parts = repo['url'].split('/')
                user_name, repo_name = parts[3], parts[4]
                if repo_name.endswith('.git'):
                    repo_name = repo_name[:-4]
                print 'Fetching starcount for %s/%s' % (user_name, repo_name)
                lib['stars'] = github_stars(user_name, repo_name)
                break

    libraries.append(lib)


libraries.sort(key=lambda lib: lib.get('stars', 0), reverse=True)
with open(args.outputpath, 'wb') as f:
    f.write(html.render({
        'libraries': libraries,
    }).encode('utf-8'))
