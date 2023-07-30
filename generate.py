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

    libraries = []
    for package in all_packages:
        logger.info("Processing %s...", package["name"])
        lib = {
            "name": package["name"],
            "description": package.get("description", None),
            "version": package.get("version", None),
            "homepage": package.get("homepage", None),
            "keywords": package.get("keywords", None),
            "assets": package.get("assets", None),
        }

        assets_url = (
            upstream_url
            + "/"
            + urllib.parse.quote(lib["name"])
            + "?fields=assets"
        )
        with requests.get(assets_url) as resp:
            try:
                lib["assets"] = resp.json()["assets"]
            except (KeyError, ValueError):
                logger.exception("Failed to fetch assets using %s", assets_url)

        # Why this is a thing, I don't know. However, it is.
        # so far we don't need
        # "or any([x["files"] is None for x in lib["assets"]])""
        # but keeping that at the ready in comments seems prudent :(
        if lib["assets"] is None:
            continue

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

    libraries.sort(key=lambda lib: lib.get("stars", 0), reverse=True)
    with open(
        os.path.join(outputdir, "index.html"), "w", encoding="utf8"
    ) as index_file:
        index_file.write(html.render({"libraries": libraries}))
    for lib in libraries:
        with open(
            os.path.join(outputdir, "mod" + lib["name"] + ".html"),
            "w",
            encoding="utf8",
        ) as modal_file:
            modal_file.write(helper.render({"lib": lib}))


if __name__ == "__main__":
    main()
