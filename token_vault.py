"""Keeps the Garmin login token encrypted inside the repository for the cloud sync.

  py -3.13 token_vault.py upload    on your PC, once after login.py:
                                    new key -> GitHub secret VAULT_KEY,
                                    token   -> vault/tokens.enc
  python token_vault.py restore     in GitHub Actions: vault -> ~/.garminconnect
  python token_vault.py store       in GitHub Actions: refreshed token -> vault

The key exists only in the GitHub secret and is never printed or written to disk.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent
VAULT = ROOT / "vault" / "tokens.enc"
TOKEN_FILE = Path.home() / ".garminconnect" / "garmin_tokens.json"
SECRET_NAME = "VAULT_KEY"


def cipher_from_env() -> Fernet:
    key = os.environ.get(SECRET_NAME)
    if not key:
        sys.exit(f"The GitHub secret {SECRET_NAME} is missing. Run 'token_vault.py upload' on your PC.")
    return Fernet(key.encode())


def upload() -> None:
    if not TOKEN_FILE.exists():
        sys.exit("No Garmin login token found. Run login.py first.")
    key = Fernet.generate_key()
    VAULT.parent.mkdir(exist_ok=True)
    VAULT.write_bytes(Fernet(key).encrypt(TOKEN_FILE.read_bytes()))
    subprocess.run(["gh", "secret", "set", SECRET_NAME], input=key, check=True, cwd=ROOT)
    print(f"Token encrypted into {VAULT.relative_to(ROOT)}; key stored as GitHub secret {SECRET_NAME}.")


def restore() -> None:
    try:
        data = cipher_from_env().decrypt(VAULT.read_bytes())
    except (OSError, InvalidToken):
        sys.exit("Could not decrypt the Garmin token. Run login.py and 'token_vault.py upload' on your PC.")
    TOKEN_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    print("Garmin token restored.")


def store() -> None:
    """Re-encrypt only if Garmin refreshed the token, to avoid a commit on every run."""
    if not TOKEN_FILE.exists():
        print("No Garmin token to save.")
        return
    cipher = cipher_from_env()
    current = TOKEN_FILE.read_bytes()
    try:
        if cipher.decrypt(VAULT.read_bytes()) == current:
            print("Garmin token unchanged.")
            return
    except (OSError, InvalidToken):
        pass
    VAULT.write_bytes(cipher.encrypt(current))
    print("Garmin token was refreshed and saved.")


if __name__ == "__main__":
    actions = {"upload": upload, "restore": restore, "store": store}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        sys.exit("Usage: token_vault.py upload|restore|store")
    actions[sys.argv[1]]()
