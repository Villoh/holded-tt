"""Tests for `clock install` / `clock uninstall`: unit text, file handling and CLI wiring."""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from holded_tt import autoclock, units
from holded_tt.errors import HoldedCliError, InputError

EXE = "/etc/profiles/per-user/me/bin/holded-tt"


class FakeRun:
    """Records every command and answers with a canned result."""

    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.calls: list[list[str]] = []
        self.result = SimpleNamespace(returncode=returncode, stderr=stderr)

    def __call__(self, command, **_kw):
        self.calls.append(command)
        return self.result

    @property
    def systemctl(self) -> list[list[str]]:
        return [c[2:] for c in self.calls]  # drop "<path>/systemctl --user"


@pytest.fixture(autouse=True)
def has_systemctl(monkeypatch):
    real = shutil.which
    monkeypatch.setattr(
        units.shutil, "which", lambda name: "/usr/bin/systemctl" if name == "systemctl" else real(name)
    )


def lines(text: str) -> list[str]:
    return text.splitlines()


# ---------------------------------------------------------------------------
# render_units
# ---------------------------------------------------------------------------


def test_timer_runs_on_weekdays_at_the_chosen_time() -> None:
    timer = units.render_units(EXE, "07:15")[units.TICK_TIMER]

    assert "OnCalendar=Mon..Fri *-*-* 07:15:00" in lines(timer)
    assert "Persistent=true" in lines(timer)  # recovers a plan missed while the machine was off


def test_service_runs_tick_with_schedule_and_hooks_into_login() -> None:
    service = units.render_units(EXE)[units.TICK_SERVICE]

    assert f"ExecStart={EXE} clock tick --schedule" in lines(service)
    assert "Type=oneshot" in lines(service)
    assert "WantedBy=default.target" in lines(service)  # rebuilds the chain after a reboot


def test_service_and_armed_timers_share_one_retry_policy() -> None:
    """The generated service and every timer arm_next creates must retry the same way."""
    service = lines(units.render_units(EXE)[units.TICK_SERVICE])

    assert autoclock.RETRY_PROPERTIES is units.RETRY_PROPERTIES
    for prop in units.RETRY_PROPERTIES:
        assert prop in service


def test_missed_clock_in_is_never_retried() -> None:
    service = lines(units.render_units(EXE)[units.TICK_SERVICE])

    assert "RestartPreventExitStatus=3" in service


def test_alert_unit_is_rate_limited_to_one_per_hour() -> None:
    failed = lines(units.render_units(EXE)[units.FAILED_SERVICE])

    assert "StartLimitBurst=1" in failed and "StartLimitIntervalSec=1h" in failed


def test_alert_uses_notify_send_when_available_else_the_journal() -> None:
    with_notify = units.render_units(EXE, notify="/usr/bin/notify-send")[units.FAILED_SERVICE]
    without = units.render_units(EXE, notify=None)[units.FAILED_SERVICE]

    assert "ExecStart=/usr/bin/notify-send holded-tt" in with_notify
    assert "notify-send" not in without and "echo" in without


def test_executable_path_is_quoted_and_escaped_for_systemd() -> None:
    service = units.render_units("/home/a b/100%/holded-tt")[units.TICK_SERVICE]

    assert 'ExecStart="/home/a b/100%%/holded-tt" clock tick --schedule' in lines(service)


@pytest.mark.parametrize("bad", ["25:00", "6:00", "06:60", "0600", "", "06:00:00"])
def test_invalid_plan_time_is_a_usage_error(bad) -> None:
    with pytest.raises(InputError):
        units.render_units(EXE, bad)


def test_every_unit_carries_the_marker() -> None:
    assert all(text.startswith(units.MARKER) for text in units.render_units(EXE).values())


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def test_install_writes_the_units_then_reloads_and_enables_in_order(tmp_path) -> None:
    run = FakeRun()

    out = units.install(EXE, "06:00", run=run, directory=tmp_path, notify="")

    assert {p.name for p in tmp_path.iterdir()} == {units.TICK_TIMER, units.TICK_SERVICE, units.FAILED_SERVICE}
    assert run.systemctl == [
        ["daemon-reload"],
        ["enable", "--now", units.TICK_TIMER],
        ["enable", units.TICK_SERVICE],  # never --now: starting it would clock in
    ]
    assert any("enabled" in line for line in out)


def test_install_never_starts_the_tick_service(tmp_path) -> None:
    run = FakeRun()

    units.install(EXE, run=run, directory=tmp_path)

    assert ["enable", "--now", units.TICK_SERVICE] not in run.systemctl
    assert ["start", units.TICK_SERVICE] not in run.systemctl


def test_install_creates_the_unit_directory(tmp_path) -> None:
    target = tmp_path / "deep" / "systemd" / "user"

    units.install(EXE, run=FakeRun(), directory=target)

    assert (target / units.TICK_TIMER).exists()


def test_install_is_idempotent_and_regenerates_our_own_units(tmp_path) -> None:
    units.install("/old/holded-tt", run=FakeRun(), directory=tmp_path)

    units.install(EXE, "07:00", run=FakeRun(), directory=tmp_path)

    assert f"ExecStart={EXE} clock tick --schedule" in (tmp_path / units.TICK_SERVICE).read_text()
    assert "07:00:00" in (tmp_path / units.TICK_TIMER).read_text()


def test_install_refuses_to_overwrite_a_foreign_unit(tmp_path) -> None:
    mine = tmp_path / units.TICK_SERVICE
    mine.write_text("[Service]\nExecStart=/bin/true\n")
    run = FakeRun()

    with pytest.raises(HoldedCliError, match="not generated by holded-tt"):
        units.install(EXE, run=run, directory=tmp_path)

    assert mine.read_text() == "[Service]\nExecStart=/bin/true\n"
    assert run.calls == [] and not (tmp_path / units.TICK_TIMER).exists()  # nothing half-installed


@pytest.mark.skipif(sys.platform == "win32", reason="creating symlinks needs privileges on Windows")
def test_install_refuses_a_symlinked_unit(tmp_path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / "x").write_text("x")
    link = tmp_path / units.TICK_TIMER
    link.symlink_to(store / "x")

    with pytest.raises(HoldedCliError, match="symlink"):
        units.install(EXE, run=FakeRun(), directory=tmp_path)


def test_dry_run_prints_everything_and_touches_nothing(tmp_path) -> None:
    run = FakeRun()
    target = tmp_path / "user"

    out = units.install(EXE, dry_run=True, run=run, directory=target)

    text = "\n".join(out)
    assert not target.exists() and run.calls == []
    assert "OnCalendar=Mon..Fri" in text and "would: systemctl --user enable holded-tt-tick.service" in text


def test_dry_run_still_validates_what_it_would_overwrite(tmp_path) -> None:
    (tmp_path / units.TICK_TIMER).write_text("foreign")

    with pytest.raises(HoldedCliError):
        units.install(EXE, dry_run=True, run=FakeRun(), directory=tmp_path)


def test_install_without_systemctl_says_what_to_do_instead(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(units.shutil, "which", lambda _n: None)

    with pytest.raises(HoldedCliError, match="needs systemd") as info:
        units.install(EXE, run=FakeRun(), directory=tmp_path)

    assert "every 5 minutes" in info.value.hint


def test_install_reports_a_failing_systemctl_with_its_stderr(tmp_path) -> None:
    with pytest.raises(HoldedCliError, match="daemon-reload failed") as info:
        units.install(EXE, run=FakeRun(1, "Failed to connect to bus"), directory=tmp_path)

    assert "Failed to connect to bus" in info.value.hint


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


def test_uninstall_removes_our_units_and_stops_armed_timers(tmp_path) -> None:
    units.install(EXE, run=FakeRun(), directory=tmp_path)
    run = FakeRun()

    out = units.uninstall(run=run, directory=tmp_path)

    assert list(tmp_path.iterdir()) == []
    assert ["disable", "--now", units.TICK_TIMER] in run.systemctl
    assert ["stop", units.ARMED_PATTERN] in run.systemctl  # an event armed for later must not fire
    assert run.systemctl[-1] == ["daemon-reload"]
    assert sum("removed" in line for line in out) == 3


@pytest.mark.skipif(sys.platform == "win32", reason="creating symlinks needs privileges on Windows")
def test_uninstall_leaves_foreign_and_symlinked_units_alone(tmp_path) -> None:
    (tmp_path / units.TICK_TIMER).write_text("foreign")
    target = tmp_path / "target"
    target.write_text("x")
    (tmp_path / units.TICK_SERVICE).symlink_to(target)

    out = units.uninstall(run=FakeRun(), directory=tmp_path)

    assert (tmp_path / units.TICK_TIMER).read_text() == "foreign"
    assert (tmp_path / units.TICK_SERVICE).is_symlink()
    assert sum("left" in line for line in out) == 2


def test_uninstall_with_nothing_installed_is_a_quiet_success(tmp_path) -> None:
    assert units.uninstall(run=FakeRun(), directory=tmp_path) == ["nothing to remove"]


def test_uninstall_survives_systemctl_failures(tmp_path) -> None:
    """Units that were never loaded make `disable`/`stop` fail; the files still go."""
    units.install(EXE, run=FakeRun(), directory=tmp_path)

    units.uninstall(run=FakeRun(1, "Unit not loaded"), directory=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_unit_dir_follows_xdg_config_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert units.unit_dir() == tmp_path / "systemd" / "user"


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _cli(monkeypatch, install=None, uninstall=None, exe=EXE):
    cli = importlib.import_module("holded_tt.cli")
    clock = importlib.import_module("holded_tt.commands.clock")
    monkeypatch.setattr(cli, "create_app_state", lambda: SimpleNamespace())
    monkeypatch.setattr(clock, "executable", lambda: exe)
    if install:
        monkeypatch.setattr(clock.units, "install", install)
    if uninstall:
        monkeypatch.setattr(clock.units, "uninstall", uninstall)
    return cli


def test_install_command_passes_options_and_prints_the_result(runner, monkeypatch) -> None:
    seen = {}

    def fake(exe, plan_at, dry_run):
        seen.update(exe=exe, plan_at=plan_at, dry_run=dry_run)
        return ["wrote x"]

    cli = _cli(monkeypatch, install=fake)

    result = runner.invoke(cli.app, ["clock", "install", "--plan-at", "07:30", "--dry-run"])

    assert result.exit_code == 0 and "wrote x" in result.stdout
    assert seen == {"exe": EXE, "plan_at": "07:30", "dry_run": True}


def test_install_command_defaults_to_0600_plan_time(runner, monkeypatch) -> None:
    seen = {}
    cli = _cli(monkeypatch, install=lambda exe, plan_at, dry_run: seen.update(p=plan_at, d=dry_run) or [])

    runner.invoke(cli.app, ["clock", "install"])

    assert seen == {"p": "06:00", "d": False}


def test_install_command_failure_exits_with_the_error_code(runner, monkeypatch) -> None:
    def boom(*_a):
        raise HoldedCliError(message="systemctl failed", hint="see stderr")

    cli = _cli(monkeypatch, install=boom)

    result = runner.invoke(cli.app, ["clock", "install"])

    assert result.exit_code == 2 and "systemctl failed" in result.output


def test_install_command_rejects_a_bad_time_as_a_usage_error(runner, monkeypatch) -> None:
    cli = _cli(monkeypatch)

    result = runner.invoke(cli.app, ["clock", "install", "--plan-at", "25:00", "--dry-run"])

    assert result.exit_code == 1 and "Invalid time" in result.output


def test_install_command_warns_about_an_unstable_store_path(runner, monkeypatch) -> None:
    cli = _cli(monkeypatch, install=lambda *_a: ["wrote x"], exe="/nix/store/abc-holded-tt-1.3.2/bin/holded-tt")

    result = runner.invoke(cli.app, ["clock", "install"])

    assert result.exit_code == 0 and "garbage-collected" in result.output


def test_install_command_stays_quiet_for_a_stable_path(runner, monkeypatch) -> None:
    cli = _cli(monkeypatch, install=lambda *_a: ["wrote x"])

    result = runner.invoke(cli.app, ["clock", "install"])

    assert "warning" not in result.output


def test_uninstall_command_prints_what_it_did(runner, monkeypatch) -> None:
    cli = _cli(monkeypatch, uninstall=lambda: ["removed a", "removed b"])

    result = runner.invoke(cli.app, ["clock", "uninstall"])

    assert result.exit_code == 0 and "removed a" in result.stdout and "removed b" in result.stdout


# ---------------------------------------------------------------------------
# Real systemd, when there is one
# ---------------------------------------------------------------------------


def _can_verify() -> bool:
    if shutil.which("systemd-analyze") is None:
        return False
    probe = subprocess.run(
        ["systemd-analyze", "--user", "verify", "--help"], capture_output=True, text=True
    )
    return probe.returncode == 0


@pytest.mark.skipif(not _can_verify(), reason="systemd-analyze not available")
def test_generated_units_pass_systemd_analyze_verify(tmp_path) -> None:
    units.install(sys.executable, run=FakeRun(), directory=tmp_path, notify="")
    paths = [str(tmp_path / n) for n in (units.TICK_TIMER, units.TICK_SERVICE, units.FAILED_SERVICE)]

    done = subprocess.run(
        ["systemd-analyze", "--user", "verify", *paths], capture_output=True, text=True
    )

    ours = [line for line in done.stderr.splitlines() if "holded-tt" in line]
    assert ours == [], ours
