from __future__ import print_function

import os

import browser_cookie3
from browser_tab_auth import get_browser_tab_access_token


PRIMARY_COOKIE_NAMES = [
    "__Host-Web-App-Secondary-Access-Token",
    "__Host-Web-App-Access-Token",
]


def _browser_readers():
    readers = {}
    for name in ["chrome", "brave", "chromium", "edge", "firefox", "opera", "safari"]:
        reader = getattr(browser_cookie3, name, None)
        if reader is not None:
            readers[name] = reader
    return readers


def available_browsers():
    return sorted(_browser_readers().keys())


def _candidate_browsers(browser_name):
    readers = _browser_readers()
    if browser_name and browser_name != "auto":
        if browser_name not in readers:
            raise RuntimeError(
                "Unsupported browser '{}'. Available: {}".format(
                    browser_name, ", ".join(sorted(readers.keys()))
                )
            )
        return [(browser_name, readers[browser_name])]

    preferred = ["chrome", "brave", "edge", "chromium", "firefox", "opera", "safari"]
    return [(name, readers[name]) for name in preferred if name in readers]


def _cookie_matches(cookie):
    domain = (cookie.domain or "").lstrip(".")
    return domain.endswith("robinhood.com")


def get_browser_access_token(browser_name="auto"):
    errors = []

    for name, reader in _candidate_browsers(browser_name):
        try:
            cookie_jar = reader(domain_name="robinhood.com")
        except Exception as exc:
            errors.append("{}: {}".format(name, exc))
            continue

        cookies = [cookie for cookie in cookie_jar if _cookie_matches(cookie)]
        if not cookies:
            errors.append("{}: no Robinhood cookies found".format(name))
            continue

        for cookie_name in PRIMARY_COOKIE_NAMES:
            for cookie in cookies:
                if cookie.name == cookie_name and cookie.value:
                    return cookie.value.strip(), name

        for cookie in cookies:
            if "Access-Token" in cookie.name and cookie.value:
                return cookie.value.strip(), name

        errors.append("{}: Robinhood cookies found, but no access token cookie matched".format(name))

    try:
        return get_browser_tab_access_token()
    except Exception as exc:
        errors.append("browser tab automation: {}".format(exc))

    raise RuntimeError("Unable to read a Robinhood browser access token. {}".format(" | ".join(errors)))


def clear_env_access_token(env_path):
    if not env_path or not os.path.exists(env_path):
        return False

    with open(env_path, "r") as infile:
        lines = infile.readlines()

    updated_lines = []
    changed = False
    for line in lines:
        if line.startswith("RH_ACCESS_TOKEN="):
            updated_lines.append("RH_ACCESS_TOKEN=\n")
            changed = True
        else:
            updated_lines.append(line)

    if not changed:
        return False

    with open(env_path, "w") as outfile:
        outfile.writelines(updated_lines)
    return True
