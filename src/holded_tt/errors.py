"""Typed CLI errors with stable exit-code behavior."""

from __future__ import annotations

from holded_tt.exit_codes import EXIT_OPERATIONAL, EXIT_USAGE


class HoldedCliError(Exception):
    """Base exception for user-facing CLI failures."""

    def __init__(
        self, message: str, hint: str, exit_code: int = EXIT_OPERATIONAL
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.exit_code = exit_code


class InputError(HoldedCliError):
    """Raised for invalid command usage or user input."""

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message=message, hint=hint, exit_code=EXIT_USAGE)


class ConfigError(HoldedCliError):
    """Raised when configuration is missing or invalid."""

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message=message, hint=hint, exit_code=EXIT_OPERATIONAL)
