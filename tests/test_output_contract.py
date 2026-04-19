from __future__ import annotations

import sys
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from holded_tt.errors import ConfigError, HoldedCliError, InputError
from holded_tt.exit_codes import EXIT_OPERATIONAL, EXIT_SUCCESS, EXIT_USAGE
from holded_tt.console import render_error
from holded_tt.renderers import render_key_values, render_stub_status


def test_exit_code_constants_are_locked() -> None:
    assert EXIT_SUCCESS == 0
    assert EXIT_USAGE == 1
    assert EXIT_OPERATIONAL == 2


def test_typed_cli_errors_preserve_message_and_hint() -> None:
    error = HoldedCliError("Could not reach Holded.", "Verify your network connection.")

    assert error.message == "Could not reach Holded."
    assert error.hint == "Verify your network connection."
    assert error.exit_code == EXIT_OPERATIONAL


def test_cli_error_subclasses_default_to_expected_exit_codes() -> None:
    input_error = InputError("Bad date range.", "Use --from before --to.")
    config_error = ConfigError(
        "Missing config value.", "Run: holded-tt config set defaults.start 08:30"
    )

    assert input_error.exit_code == EXIT_USAGE
    assert config_error.exit_code == EXIT_OPERATIONAL


def test_render_error_writes_error_and_hint_lines_to_stderr() -> None:
    buffer = StringIO()

    with redirect_stderr(buffer):
        render_error(InputError("Bad date range.", "Use --from before --to."))

    assert (
        buffer.getvalue() == "Error: Bad date range.\nHint: Use --from before --to.\n"
    )


def test_renderers_produce_readable_text_without_color_only_semantics() -> None:
    key_values = render_key_values(
        "Session status",
        [("Saved at", "2026-04-12 08:14:32"), ("Cookies", "present (4 of 4 required)")],
    )
    stub_status = render_stub_status(
        "workplaces",
        "This command is not wired to Holded yet.",
        "Run: holded-tt login once Phase 2 lands.",
    )

    assert "Session status" in key_values
    assert "Saved at:" in key_values
    assert "Cookies:" in key_values
    assert "workplaces" in stub_status
    assert "Status:" in stub_status
    assert "Next step:" in stub_status
    assert "Run: holded-tt login once Phase 2 lands." in stub_status
