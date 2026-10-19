"""Small secrets abstraction so backend code never reads secrets ad hoc."""
import os
from abc import ABC, abstractmethod

from core.errors import ConfigurationError


class Secret:
    """Wrapper whose repr/str never reveal the value; call ``reveal()`` at the point of use."""

    __slots__ = ("_value",)

    def __init__(self, value):
        self._value = value

    def reveal(self):
        return self._value

    def __repr__(self):
        return "Secret([REDACTED])"

    __str__ = __repr__

    def __len__(self):
        return len(self._value)

    def __bool__(self):
        return bool(self._value)


class SecretProvider(ABC):
    @abstractmethod
    def get(self, name):
        """Return the secret value for ``name`` or None if unset."""

    def require(self, name):
        value = self.get(name)
        if not value:
            raise ConfigurationError(f"Required secret {name} is not set. Configure it in your environment or .env.")
        return Secret(value)


class EnvSecretProvider(SecretProvider):
    def get(self, name):
        value = os.getenv(name, "").strip()
        return value or None


_provider = EnvSecretProvider()


def get_secret_provider():
    return _provider


def set_secret_provider(provider):
    """Swap in another backend (e.g. a vault client)."""
    global _provider
    _provider = provider
