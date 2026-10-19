"""Domain exception taxonomy for Auto Apply.

Subclasses that replace former ``ValueError`` raises also inherit from
``ValueError`` so existing ``except ValueError`` handlers keep working.
"""


class AutoApplyError(Exception):
    """Base class for all domain errors."""

    exit_code = 1
    category = "error"


class ConfigurationError(AutoApplyError, ValueError):
    """Missing or invalid configuration, environment, or input."""

    exit_code = 1
    category = "configuration"


class DiscoveryError(AutoApplyError, ValueError):
    """Job discovery failed or produced no usable results."""

    exit_code = 3
    category = "discovery"


class VerificationError(AutoApplyError, ValueError):
    """Company/job verification failed."""

    exit_code = 4
    category = "verification"


class DocumentGenerationError(AutoApplyError, ValueError):
    """Tailored application documents could not be generated."""

    exit_code = 5
    category = "document generation"


class ApplicationRunError(AutoApplyError, RuntimeError):
    """The browser/LLM application run failed."""

    exit_code = 6
    category = "application run"


class PersistenceError(AutoApplyError, OSError):
    """Local state (JSON/SQLite) could not be read or written."""

    exit_code = 7
    category = "persistence"


class AuthenticationError(AutoApplyError):
    """Missing, malformed, expired, or otherwise invalid credentials (HTTP 401)."""

    exit_code = 8
    category = "authentication"


class AuthorizationError(AutoApplyError):
    """Authenticated caller lacks the role/permission or ownership required (HTTP 403)."""

    exit_code = 9
    category = "authorization"


def describe_error(exc):
    """Return a consistent user-facing message for a domain error."""
    category = getattr(exc, "category", "error")
    return f"{category.capitalize()} error: {exc}"


def exit_code_for(exc):
    """Map an exception to a process exit code."""
    return getattr(exc, "exit_code", 1)
