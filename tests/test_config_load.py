"""Loading config.toml must survive keys this version does not know.

Downgrading after a newer version added a key (jitter, max_late, ...) used to crash every
command with `TypeError: AppConfig.__init__() got an unexpected keyword argument`.
"""

from __future__ import annotations

import pytest

from holded_tt import config as config_module
from holded_tt.config import AppConfig, load_config, save_config


@pytest.fixture()
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config_module, "CONFIG_FILE", path)
    return path


def test_unknown_key_is_ignored_and_known_keys_survive(config_file, capsys) -> None:
    config_file.write_text(
        'start = "09:00"\nend = "18:00"\nfuture_option = 7\npause = ["14:00-14:30"]\n'
    )

    config = load_config()

    assert (config.start, config.end, config.pause) == ("09:00", "18:00", ["14:00-14:30"])
    assert not hasattr(config, "future_option")


def test_the_warning_names_the_file_and_the_keys_on_stderr(config_file, capsys) -> None:
    config_file.write_text('zeta = 1\nalpha = "x"\nstart = "09:00"\n')

    load_config()

    captured = capsys.readouterr()
    assert captured.out == ""  # stdout stays clean for scripts that parse command output
    assert str(config_file) in captured.err
    assert "alpha, zeta" in captured.err  # sorted, so the message is stable


def test_no_warning_when_every_key_is_known(config_file, capsys) -> None:
    config_file.write_text('start = "09:00"\njitter = 20\nmax_late = 60\n')

    config = load_config()

    assert (config.jitter, config.max_late) == (20, 60)
    assert capsys.readouterr().err == ""


def test_weekday_tables_still_load_next_to_unknown_keys(config_file) -> None:
    config_file.write_text('mystery = true\n\n[days.fri]\nend = "15:00"\npause = []\n')

    config = load_config()

    assert config.days == {"fri": {"end": "15:00", "pause": []}}


def test_a_config_of_only_unknown_keys_falls_back_to_defaults(config_file) -> None:
    config_file.write_text("a = 1\nb = 2\n")

    assert load_config() == AppConfig()


def test_saving_drops_what_this_version_does_not_know(config_file, capsys) -> None:
    """Documented trade-off: reading is tolerant, but a rewrite keeps only known keys."""
    config_file.write_text('start = "09:00"\nfuture_option = 7\n')
    config = load_config()
    capsys.readouterr()

    save_config(config)

    assert "future_option" not in config_file.read_text()
    load_config()
    assert capsys.readouterr().err == ""  # and the warning is gone once it is rewritten


def test_invalid_toml_is_still_an_error(config_file) -> None:
    """Only unknown keys are tolerated, not a broken file."""
    config_file.write_text("start = ")

    with pytest.raises(Exception):
        load_config()
