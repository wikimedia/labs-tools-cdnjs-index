#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Create a static website out of output from the cdnjs API for directing people
to a reverse proxy of the cdnjs libraries.
"""

import argparse
import logging
import os
import re
import time
import urllib3.exceptions
import urllib.parse

import jinja2
import requests


def github_request(url, token, logger=None):
    """Make a request against the GitHub REST API."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer {}".format(token),
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 403:
        reset_time = response.headers["x-ratelimit-reset"]
        sleep_duration = (
            float(reset_time)
            - time.time()
            + 10
        )
        if logger:
            logger.info(
                "GitHub returned HTTP 403, "
                "sleeping for %.1f s until @%s (plus ten seconds)",
                sleep_duration,
                reset_time,
            )
        time.sleep(sleep_duration)
        return github_request(url, token, logger=logger)
    return response.json(), response.status_code


def github_stars(user, repo, token, logger=None):
    """Get number of github stars a repo has"""
    url = "https://api.github.com/repos/%s/%s" % (user, repo)
    data, _ = github_request(url, token, logger=logger)
    return data.get("stargazers_count", 0)


def github_tree(url, token, recursive=False, logger=None):
    """Get a Git tree from the GitHub REST API."""
    if not recursive:
        data, _ = github_request(url, token, logger=logger)
        return data

    recursive_url = url + "?recursive=true"
    data, _ = github_request(recursive_url, token, logger=logger)
    if not data.get("truncated", False):
        return data

    if logger:
        logger.info(
            "GitHub returned truncated data for %s, "
            "falling back to many non-recursive requests",
            recursive_url,
        )
    # if GitHub returned a/1, a/2, b/1,
    # then we can assume the a/ subtree is complete,
    # and only do additional requests staring from b/
    truncated_data = data
    recursive_tree = []
    current_prefix = None
    current_subtree = []
    complete_subtrees = set()
    for entry in truncated_data.get("tree", []):
        [prefix, *_] = entry["path"].split("/", 1)
        if prefix != current_prefix:
            recursive_tree += current_subtree
            if current_prefix is not None:
                complete_subtrees.add(current_prefix)
            current_prefix = prefix
            current_subtree = []
        current_subtree.append(entry)

    data, _ = github_request(url, token, logger=logger)
    if "tree" not in data:
        raise KeyError(f'{url} returned data without "tree": {data}')
    for entry in data["tree"]:
        if entry["path"] in complete_subtrees:
            continue
        recursive_tree.append(entry)
        if entry["type"] == "tree":
            subtree = github_tree(entry["url"], token, recursive=True, logger=logger)
            for subentry in subtree["tree"]:
                recursive_tree.append({
                    **subentry,
                    "path": f"{entry['path']}/{subentry['path']}",
                })
    return {
        **data,
        "tree": recursive_tree,
    }


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="loglevel",
        help="Increase logging verbosity",
    )
    argparser.add_argument(
        "--token",
        dest="github_token",
        metavar="<github_token>",
        type=str,
        required=True,
        help=(
            "A filename with a GitHub personal access token"
            "with public_repos permission"
        ),
    )
    argparser.add_argument("outputpath", help="Path to html output")

    args = argparser.parse_args()

    logging.basicConfig(
        level=max(logging.DEBUG, logging.WARNING - (10 * args.loglevel)),
        format="%(asctime)s %(name)-12s %(levelname)-8s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    logging.captureWarnings(True)
    logger = logging.getLogger("generate")

    outputdir = args.outputpath

    with open("template.html.j2") as index_temp:
        html = jinja2.Template(index_temp.read(), autoescape=True)

    with open("modal-template.html.j2") as modal_temp:
        helper = jinja2.Template(modal_temp.read(), autoescape=True)

    with open(args.github_token) as token_file:
        github_token = token_file.read()

    github_token = github_token.strip()

    fields = "version,description,homepage,keywords,license,repository,author"
    upstream_url = "https://api.cdnjs.com/libraries"
    list_url = upstream_url + "?fields={}".format(fields)
    with requests.get(list_url, stream=True) as resp:
        json_resp = resp.json()

    all_packages = json_resp["results"]

    # get a github:cdnjs/cdnjs ajax/libs/ listing in preparation
    github_cdnjs_url = "https://api.github.com/repos/cdnjs/cdnjs/git/trees/master"
    github_cdnjs_tree = github_tree(github_cdnjs_url, github_token)
    github_ajax_url = [entry["url"]
                       for entry
                       in github_cdnjs_tree["tree"]
                       if entry["path"] == "ajax"][0]
    github_ajax_tree = github_tree(github_ajax_url, github_token)
    github_libs_url = [entry["url"]
                       for entry
                       in github_ajax_tree["tree"]
                       if entry["path"] == "libs"][0]
    github_libs_tree = github_tree(github_libs_url, github_token)
    github_library_urls = {
        entry["path"]: entry["url"]
        for entry in github_libs_tree["tree"]
    }

    libraries = []
    for package in all_packages:
        name = package["name"]
        logger.info("Processing %s...", name)
        lib = {
            "name": name,
            "description": package.get("description", None),
            "version": package.get("version", None),
            "homepage": package.get("homepage", None),
            "keywords": package.get("keywords", None),
            "assets": {},
        }

        # get assets from CDNjs API as preferred source
        # (note that since 2022 it only returns the latest version, see T342519)
        assets_url = (
            upstream_url
            + "/"
            + urllib.parse.quote(lib["name"])
            + "?fields=assets"
        )
        with requests.get(assets_url) as resp:
            try:
                for asset in resp.json().get("assets", []):
                    lib["assets"][asset["version"]] = asset
            except (KeyError, ValueError):
                logger.exception("Failed to fetch assets using %s", assets_url)

        # get other versions from listing GitHub instead
        # (we could get them from CDNjs but only with one request per version, way too slow)
        try:
            github_library_tree = github_tree(
                github_library_urls[name],
                github_token,
                recursive=True,
                logger=logger,
            )
            # we get a flat listing of version1/file1, version1/subdir/file2, version2/file1 etc.
            # group that into one entry per version and add it to the assets
            current_asset = None
            if "tree" not in github_library_tree:
                raise KeyError(
                    f'{github_library_urls[name]} returned data '
                    f'without "tree": {github_library_tree}',
                )
            for entry in github_library_tree["tree"]:
                if entry["path"] == "package.json":
                    continue
                [version, *_] = entry["path"].split("/", 1)
                if current_asset is None:
                    current_asset = {"version": version, "files": []}
                elif version != current_asset["version"]:
                    lib["assets"].setdefault(current_asset["version"], current_asset)
                    current_asset = {"version": version, "files": []}
                if entry["type"] == "blob":
                    current_asset["files"].append(entry["path"][len(version)+1:])
            if current_asset is not None:
                lib["assets"].setdefault(current_asset["version"], current_asset)
        except (
                KeyError,
                ValueError,
                requests.exceptions.RequestException,
                urllib3.exceptions.HTTPError,
        ):
            logger.exception("Failed to fetch additional versions for %s from GitHub", name)

        if lib["keywords"] is None:  # Found an example of this.
            lib["keywords"] = []

        if package["repository"] and "github.com/" in package["repository"].get(
            "url", ""
        ):
            url = package["repository"]["url"]
        else:
            url = None

        if url is not None:
            parts = re.sub(r"^\w+://", "", url).split("/")
            user_name, repo_name = parts[-2], parts[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            logger.debug("Fetching starcount for %s/%s", user_name, repo_name)
            lib["stars"] = github_stars(user_name, repo_name, github_token, logger=logger)
        libraries.append(lib)

        with open(
            os.path.join(outputdir, "mod" + name + ".html"),
            "w",
            encoding="utf8",
        ) as modal_file:
            modal_file.write(helper.render({"lib": lib}))
        # throw away non-latest versions to save memory, not needed in index.html
        try:
            lib["assets"] = {lib["version"]: lib["assets"][lib["version"]]}
        except KeyError:
            # happened for 'xls' library (KeyError: '1.0.0')
            pass

    libraries.sort(key=lambda lib: lib.get("stars", 0), reverse=True)
    with open(
        os.path.join(outputdir, "index.html"), "w", encoding="utf8"
    ) as index_file:
        index_file.write(html.render({"libraries": libraries}))


if __name__ == "__main__":
    main()
