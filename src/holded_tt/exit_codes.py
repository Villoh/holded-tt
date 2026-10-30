"""Shared numeric exit codes for the CLI."""

EXIT_SUCCESS = 0
EXIT_USAGE = 1
EXIT_OPERATIONAL = 2
EXIT_NO_RETRY = 3  # failed in a way that retrying cannot fix (systemd skips the retry)
