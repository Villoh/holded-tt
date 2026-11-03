from holded_tt.schedule import hhmm_to_minutes as mins
from holded_tt.schedule import jitter_schedule

WEEKDAY = ("08:30", "17:30", ("14:00-14:30",))  # 8h30 net
FRIDAY = ("08:30", "15:00", ())  # 6h30 net


def _net(start, end, pauses):
    paused = sum(mins(b) - mins(a) for a, b in (p.split("-") for p in pauses))
    return mins(end) - mins(start) - paused


def _check(base, jitter, max_extra, runs=2000):
    seen_early = seen_late = False
    nets = set()
    for _ in range(runs):
        s, e, p = jitter_schedule(base[0], base[1], base[2], jitter, max_extra)
        extra = _net(s, e, p) - _net(*base)
        assert 0 <= extra <= max_extra  # net hours: never below, never more than max_extra above
        nets.add(extra)
        assert all(mins(b) - mins(a) == mins(ob) - mins(oa)
                   for (a, b), (oa, ob) in zip((x.split("-") for x in p),
                                               (y.split("-") for y in base[2])))
        assert all(mins(s) <= mins(a) and mins(b) <= mins(e)
                   for a, b in (x.split("-") for x in p))  # pause inside the day
        seen_early |= s < base[0]
        seen_late |= s > base[0]
    assert seen_early and seen_late  # entry really moves both ways
    return nets


def test_weekday_net_stays_within_the_ceiling():
    nets = _check(WEEKDAY, 20, 15)
    assert max(nets) > 10 and min(nets) < 5  # and the extra really varies across the range


def test_friday_net_stays_within_the_ceiling():
    _check(FRIDAY, 20, 15)


def test_ceiling_is_configurable():
    assert max(_check(WEEKDAY, 20, 5)) <= 5


def test_zero_extra_keeps_exactly_the_configured_hours():
    assert _check(WEEKDAY, 20, 0) == {0}


def test_no_pause_and_zero_jitter():
    assert jitter_schedule("08:30", "17:30", (), 0, 0) == ("08:30", "17:30", ())


def test_clock_edges():
    for _ in range(200):
        s, e, p = jitter_schedule("00:05", "23:50", ("23:40-23:50",), 30, 15)
        assert "00:00" <= s and e <= "23:59"
        assert _net(s, e, p) >= _net("00:05", "23:50", ("23:40-23:50",))
