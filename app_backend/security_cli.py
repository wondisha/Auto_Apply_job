"""Generate a password hash for AUTH_LOGIN_PASSWORD_HASH: python -m app_backend.security_cli"""
import getpass

from .security import hash_password

if __name__ == "__main__":
    print(hash_password(getpass.getpass("Password: ")))
