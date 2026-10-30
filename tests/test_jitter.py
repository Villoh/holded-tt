from holded_tt.commands.track import _hhmm_to_minutes as mins
from holded_tt.commands.track import _jitter_schedule


def _net(start, end, pauses):
    paused = sum(mins(b) - mins(a) for a, b in (p.split("-") for p in pauses))
    return mins(end) - mins(start) - paused


def _check(base, n, runs=500):
    seen_early = seen_late = False
    for _ in range(runs):
        s, e, p = _jitter_schedule(base[0], base[1], base[2], n)
        assert _net(s, e, p) >= _net(*base)  # net hours never drop
        assert all(mins(b) - mins(a) == mins(ob) - mins(oa)
                   for (a, b), (oa, ob) in zip((x.split("-") for x in p),
                                               (y.split("-") for y in base[2])))
        assert all(mins(s) <= mins(a) and mins(b) <= mins(e)
                   for a, b in (x.split("-") for x in p))  # pause inside the day
        seen_early |= s < base[0]
        seen_late |= s > base[0]
    assert seen_early and seen_late  # entry really moves both ways


def test_weekday_with_pause():
    _check(("08:30", "17:30", ("14:00-14:30",)), 20)


def test_no_pause_and_zero():
    _check(("08:30", "15:00", ()), 20)
    assert _jitter_schedule("08:30", "17:30", (), 0) == ("08:30", "17:30", ())


def test_clock_edges():
    for _ in range(200):
        s, e, p = _jitter_schedule("00:05", "23:50", ("23:40-23:50",), 30)
        assert "00:00" <= s and e <= "23:59"
        assert _net(s, e, p) >= _net("00:05", "23:50", ("23:40-23:50",))
