"""One-time Garmin Connect login.

Asks for your Garmin e-mail and password (the password stays invisible while
you type) and, if Garmin asks for one, the two-factor code. Afterwards only a
login token is stored in ~/.garminconnect on this computer; the password is
never saved. sync.py uses that token from then on.
"""

from __future__ import annotations

import getpass
import sys

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from sync import TOKENSTORE, make_read_only


def main() -> int:
    print("Garmin Connect - one-time login\n")
    email = input("Garmin e-mail address: ").strip()
    password = getpass.getpass("Garmin password (invisible while typing, then press Enter): ")
    api = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Two-factor code from Garmin (e-mail or app): ").strip(),
    )
    del password
    make_read_only(api)
    try:
        api.login(TOKENSTORE)
    except GarminConnectAuthenticationError:
        print("\nLogin failed: Garmin did not accept the e-mail, password or code. Please try again.")
        return 1
    except GarminConnectTooManyRequestsError:
        print("\nGarmin is temporarily blocking logins (too many attempts). Please wait about an hour.")
        return 1
    except GarminConnectConnectionError as err:
        print(f"\nCould not reach Garmin: {err}")
        return 1

    print(f"\nSuccess! Logged in as {api.get_full_name()}.")
    print("A login token was saved on this computer, so you will not need to log in again.")
    print("You can go back to the chat now.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
