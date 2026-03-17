from __future__ import print_function

import json
import os
import re
import subprocess
import time


AUTH_STATE_KEY = "web:auth_state"


def run_cmux(args):
    attempts = 4
    last_message = "cmux command failed"
    for attempt in range(attempts):
        result = subprocess.run(
            ["cmux"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()

        message = result.stderr.strip() or result.stdout.strip() or "cmux command failed"
        last_message = message
        if "Failed to connect to socket" not in message or attempt == attempts - 1:
            raise RuntimeError(message)
        time.sleep(0.25 * (attempt + 1))

    raise RuntimeError(last_message)


def _normalize_eval_output(value):
    value = value.strip()
    if value in ("", "null", "undefined"):
        return ""
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except ValueError:
            return value[1:-1]
    return value


def get_cmux_access_token(surface):
    auth_state_raw = run_cmux(
        ["browser", "eval", "--surface", surface, "localStorage.getItem('{}')".format(AUTH_STATE_KEY)]
    )
    auth_state_raw = _normalize_eval_output(auth_state_raw)
    if auth_state_raw:
        auth_state = json.loads(auth_state_raw)
        token = auth_state.get("access_token", "").strip()
        if token:
            return token

    cookies = run_cmux(["browser", "eval", "--surface", surface, "document.cookie"])
    match = re.search(r"__Host-Web-App-Secondary-Access-Token=([^;]+)", cookies)
    if match:
        return match.group(1).strip()

    raise RuntimeError("No Robinhood access token found on cmux surface {}.".format(surface))


def clear_cmux_auth(surface):
    script = r"""
(() => {
  const expire = (name, domain) => {
    let cookie = `${name}=; Max-Age=0; path=/`;
    if (location.protocol === 'https:') cookie += '; Secure';
    if (domain) cookie += `; domain=${domain}`;
    document.cookie = cookie;
  };

  try {
    localStorage.removeItem('web:auth_state');
    localStorage.removeItem('web:auth_last_accessed_time');
  } catch (err) {}

  try {
    sessionStorage.clear();
  } catch (err) {}

  const names = document.cookie
    .split(';')
    .map(part => part.split('=')[0].trim())
    .filter(Boolean);
  names.forEach(name => {
    expire(name, null);
    expire(name, location.hostname);
    expire(name, '.robinhood.com');
  });

  return true;
})()
""".strip()
    run_cmux(["browser", "eval", "--surface", surface, script])


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
