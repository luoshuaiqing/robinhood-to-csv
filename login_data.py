from __future__ import print_function
from Robinhood import Robinhood
import getpass
import collections
import os
import sys
import uuid
#robinhood = Robinhood()
def get_input():
    if sys.version_info[0] < 3:
        return raw_input()
    else:
        return input()


def login_error_message(response):
    if not isinstance(response, dict):
        return "Login failed."

    if response.get("mfa_required"):
        return "Robinhood requires MFA."

    for key in ("detail", "error", "message"):
        value = response.get(key)
        if value:
            return str(value)

    non_field_errors = response.get("non_field_errors")
    if non_field_errors:
        if isinstance(non_field_errors, list):
            return "; ".join(str(item) for item in non_field_errors)
        return str(non_field_errors)

    return "Login failed."


def collect_login_data(robinhood_obj, username, password, device_token, mfa_code, access_token=None):
    logged_in = False
    if access_token == "":
        access_token = None

    use_env_access_token = access_token is None
    use_env_username = username == ""
    use_env_password = password == ""
    use_env_device_token = device_token is None
    use_env_mfa = mfa_code is None

    if access_token is None and use_env_access_token:
        access_token = os.getenv("RH_ACCESS_TOKEN", "")
        use_env_access_token = False
    if access_token:
        robinhood_obj.set_auth_token(access_token)
        logged_in = robinhood_obj.validate_auth_token()
        if logged_in == True:
            return True
        print("\n{} Falling back to username/password login.\n".format(login_error_message(logged_in)))
        access_token = ""

    while logged_in != True:
        if username == "" and use_env_username:
            username = os.getenv("RH_USERNAME", "")
            use_env_username = False
        if username == "":
            print("Robinhood username:", end=' ')
            username = get_input()

        if password == "" and use_env_password:
            password = os.getenv("RH_PASSWORD", "")
            use_env_password = False
        if password == "":
            password = getpass.getpass()

        if device_token == None and use_env_device_token:
            device_token = os.getenv("RH_DEVICE_TOKEN", "")
            use_env_device_token = False
        if device_token == "":
            device_token = str(uuid.uuid4())

        logged_in = robinhood_obj.login(username=username, password=password, device_token=device_token)

        if logged_in != True and logged_in.get('non_field_errors') == None and logged_in.get('mfa_required') == True:
            if mfa_code is None and use_env_mfa:
                mfa_code = os.getenv("RH_MFA")
                use_env_mfa = False
            if mfa_code == None or mfa_code == "":
                print("Robinhood MFA:", end=' ')
                mfa_code = get_input()
            logged_in = robinhood_obj.login(username=username, password=password, device_token=device_token, mfa_code=mfa_code)

        if logged_in != True:
            print("\n{} Please try again.\n".format(login_error_message(logged_in)))
            username = ""
            password = ""
            mfa_code = None

    return True
