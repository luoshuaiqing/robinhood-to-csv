from __future__ import print_function

import json
import subprocess


BROWSER_APPS = [
    "Google Chrome",
    "Arc",
    "Brave Browser",
    "Microsoft Edge",
]


def run_osascript(lines):
    command = ["osascript"]
    for line in lines:
        command.extend(["-e", line])

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "osascript failed"
        raise RuntimeError(message)
    return result.stdout.strip()


def _normalize_result(value):
    value = value.strip()
    if value in ("", "null", "undefined"):
        return ""
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except ValueError:
            return value[1:-1]
    return value


def get_active_browser_origin(app_name):
    return _normalize_result(
        run_osascript(
            [
                'with timeout of 5 seconds',
                'tell application "{}" to execute active tab of front window javascript "window.location.origin"'.format(app_name),
                'end timeout',
            ]
        )
    )


def read_active_browser_script(app_name, script):
    return _normalize_result(
        run_osascript(
            [
                'with timeout of 5 seconds',
                'tell application "{}" to execute active tab of front window javascript "{}"'.format(
                    app_name, script.replace("\\", "\\\\").replace('"', '\\"')
                ),
                'end timeout',
            ]
        )
    )


def get_browser_tab_access_token():
    errors = []

    scripts = [
        "localStorage.getItem('web:auth_state')",
        "sessionStorage.getItem('web:auth_state')",
        "JSON.stringify(Object.fromEntries(Object.keys(localStorage).map(function(k){ return [k, localStorage.getItem(k)]; })))",
        "JSON.stringify(Object.fromEntries(Object.keys(sessionStorage).map(function(k){ return [k, sessionStorage.getItem(k)]; })))",
        "document.cookie",
    ]

    for app_name in BROWSER_APPS:
        try:
            origin = get_active_browser_origin(app_name)
        except Exception as exc:
            errors.append("{}: {}".format(app_name, exc))
            continue

        if "robinhood.com" not in origin:
            errors.append("{}: active tab is {}".format(app_name, origin or "not readable"))
            continue

        for script in scripts:
            try:
                value = read_active_browser_script(app_name, script)
            except Exception as exc:
                errors.append("{}: {}".format(app_name, exc))
                break

            if not value:
                continue

            if script in ("localStorage.getItem('web:auth_state')", "sessionStorage.getItem('web:auth_state')"):
                try:
                    payload = json.loads(value)
                    token = (payload.get("access_token") or "").strip()
                    if token:
                        return token, app_name
                except Exception:
                    pass

            if script == "document.cookie":
                for part in value.split(";"):
                    name, _, cookie_value = part.strip().partition("=")
                    if "Access-Token" in name and cookie_value:
                        return cookie_value.strip(), app_name

            if script.startswith("JSON.stringify("):
                try:
                    payload = json.loads(value)
                except Exception:
                    continue
                for key, candidate in payload.items():
                    if not isinstance(candidate, str):
                        continue
                    if key == "web:auth_state":
                        try:
                            auth_state = json.loads(candidate)
                            token = (auth_state.get("access_token") or "").strip()
                            if token:
                                return token, app_name
                        except Exception:
                            pass
                    if "token" in key.lower() and candidate.count(".") >= 2:
                        return candidate.strip(), app_name

        errors.append("{}: Robinhood tab found, but no access token was discovered".format(app_name))

    raise RuntimeError("Unable to read a Robinhood browser tab access token. {}".format(" | ".join(errors)))
