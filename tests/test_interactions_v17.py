"""Deterministic pointer quality checks, with no camera or operating-system input."""
from dataclasses import replace
import math
import pytest
from airmouse_ai.config import Settings
from airmouse_ai.controller import Controller, State
from airmouse_ai.cursor import CursorFilter
from airmouse_ai.gestures import Mode, classify
from conftest import hand_pose
from test_both_hands import sample


def trace(rate=24, velocity=.12, seconds=1., **kwargs):
    f = CursorFilter(1920, 1080)
    f.update_relative(0, 0, False, anchor=(500, 500), now=0, **kwargs)
    points = []
    for i in range(1, round(rate*seconds)+1):
        p = f.update_relative(velocity*i/rate, 0, False, now=i/rate, **kwargs)
        points.append((i/rate, p, f.position))
    return f, points


def test_slow_start_and_continuous_motion_without_old_threshold_stutter():
    _, points = trace(velocity=.072)
    moves = [(t, p) for t, p, _ in points if p is not None]
    assert moves[0][0] <= .15
    # Once acquired, a smooth stroke produces an update on every inference frame.
    assert len(moves) >= 19
    steps = [b[1][0]-a[1][0] for a, b in zip(moves, moves[1:])]
    assert min(steps) >= 1 and max(steps) <= 8


@pytest.mark.parametrize('fps', [15, 20, 24, 30])
def test_same_physical_stroke_is_consistent_at_supported_fps(fps):
    f, _ = trace(rate=fps, velocity=.2, seconds=2)
    baseline, _ = trace(rate=30, velocity=.2, seconds=2)
    assert f.position[0]-500 == pytest.approx(baseline.position[0]-500, rel=.05)


def test_fast_stroke_covers_more_distance_than_same_length_slow_stroke():
    slow, _ = trace(velocity=.06, seconds=3)
    fast, _ = trace(velocity=.6, seconds=.3)
    assert fast.position[0]-500 > (slow.position[0]-500)*1.7


def test_subpixel_accumulation_allows_small_fine_corrections():
    f, points = trace(velocity=.012, seconds=2)
    moves = [p for _, p, _ in points if p]
    assert 15 <= f.position[0]-500 <= 40
    assert len(moves) >= 10
    assert any(b[0]-a[0] == 1 for a, b in zip(moves, moves[1:]))


def test_reversal_has_no_old_velocity_tail_and_stop_settles():
    f, _ = trace(velocity=.2)
    positions = []
    for i in range(1, 7):
        f.update_relative(.2-i*.2/24, 0, False, now=1+i/24)
        positions.append(f.position[0])
    assert positions[2] < positions[1]
    assert all(b < a for a, b in zip(positions[2:], positions[3:]))
    for i in range(7, 14):
        f.update_relative(.15, 0, False, now=1+i/24)
    position = f.position
    for i in range(14, 60):
        assert f.update_relative(.15, 0, False, now=1+i/24) is None
    assert f.position == position


@pytest.mark.parametrize('fps', [15, 24, 30])
@pytest.mark.parametrize('gain', [.5, 1., 10.])
def test_stationary_noise_is_rejected_at_each_rate_and_gain(fps, gain):
    f = CursorFilter(1920, 1080)
    speeds = dict(up_speed=gain, down_speed=gain, left_speed=gain, right_speed=gain)
    f.update_relative(0, 0, False, anchor=(800, 500), now=0, **speeds)
    for i in range(1, 301):
        assert f.update_relative(.007*math.sin(i*1.7), .007*math.cos(i*2.1),
                                 False, now=i/fps, **speeds) is None
    assert f.position == (800, 500)


def test_axis_noise_does_not_leak_into_horizontal_stroke():
    f = CursorFilter(1920, 1080)
    f.update_relative(0, 0, False, anchor=(500, 500), now=0)
    for i in range(1, 80):
        f.update_relative(i*.003, .007*math.sin(i*1.7), False, now=i/24)
    assert f.position[0] > 650 and f.position[1] == 500


def test_physical_mouse_reanchors_without_pulling_cursor_back():
    f, _ = trace()
    assert f.update_relative(.12, 0, False, anchor=(100, 100), now=1.05) is None
    assert f.position == (100, 100)
    for i in range(1, 8):
        f.update_relative(.12+i*.003, 0, False, now=1.05+i/24)
    assert 100 < f.position[0] < 160 and f.position[1] == 100


@pytest.mark.parametrize('bad_time', [0., -.1, 1., float('nan')])
def test_invalid_duplicate_or_stalled_sample_cannot_jump(bad_time):
    f = CursorFilter(1920, 1080)
    f.update_relative(0, 0, False, anchor=(500, 500), now=0)
    assert f.update_relative(.4, .4, False, anchor=(500, 500), now=bad_time) is None


@pytest.mark.parametrize('side', ['Left', 'Right'])
@pytest.mark.parametrize('kind', ['point', 'middle', 'ring'])
def test_small_finger_motion_responds_without_large_hand_swing(backend, side, kind):
    c = Controller(backend, Settings(mirror=False))
    c.set_state(State.RUNNING)
    for i in range(12):
        c.process(sample(side, kind), i/24)
    start = backend.pos
    direction = 1 if side == 'Right' else -1
    for i in range(1, 6):
        c.process(sample(side, kind, finger_dx=direction*i*.001), (11+i)/24)
    assert backend.pos[0] > start[0]


def test_controller_uses_capture_interval_and_reanchors_on_setting_change(backend):
    c = Controller(backend, Settings(mirror=False))
    c.set_state(State.RUNNING)
    for i in range(12):
        c.process(hand_pose(), i/24, captured_at=10+i/30)
    c.process(hand_pose(finger_dx=.004), .5, captured_at=10.5)
    assert c.cursor.last_time == 10.5
    c.configure(replace(c.settings, mirror=True))
    backend.events.clear()
    c.process(hand_pose(finger_dx=.04), .55, captured_at=10.55)
    assert backend.events == []


def test_large_relocalization_is_discarded_then_new_movement_resumes():
    f, _ = trace()
    for i in range(1, 5):
        assert f.update_relative(1., 1., False, now=1+i/24) is None
    for i in range(5, 15):
        f.update_relative(1.+(i-4)*.003, 1., False, now=1+i/24)
    assert f.position[1] == 500


def test_stop_with_tremor_settles_instead_of_wandering():
    f, _ = trace(velocity=.072)
    positions = []
    for i in range(1, 201):
        f.update_relative(.072+.007*math.sin(i*1.7), .007*math.cos(i*2.1),
                          False, now=1+i/24)
        if i > 6:
            positions.append(f.position)
    assert max(p[0] for p in positions)-min(p[0] for p in positions) <= 1.1
    assert all(p[1] == 500 for p in positions)


def flex(hand, finger, degrees=40):
    p = list(hand.points)
    mcp = (5, 9, 13)[finger]
    x, y, z = p[mcp]
    theta = math.radians(degrees)
    p[mcp+1] = (x, y-.18, z)
    p[mcp+2] = (x, y-.18-.15*math.cos(theta), z+.15*math.sin(theta))
    p[mcp+3] = (x, y-.18-.15*math.cos(theta)-.15*math.cos(2*theta),
                z+.15*math.sin(theta)+.15*math.sin(2*theta))
    return replace(hand, points=tuple(p))


@pytest.mark.parametrize('side', ['Left', 'Right'])
@pytest.mark.parametrize('finger,kind', [(0, 'point'), (1, 'middle'), (2, 'ring')])
def test_acquired_single_finger_survives_slight_bend_but_pinky_still_locks(backend, side, finger, kind):
    c = Controller(backend, Settings())
    c.set_state(State.RUNNING)
    for i in range(12):
        c.process(sample(side, kind), i/24)
    assert c.engine.mode == Mode.POINTING
    for i in range(1, 12):
        h = flex(sample(side, kind, dx=i*.001), finger)
        assert classify(h).geometry.fingers[finger] == -1
        c.process(h, (11+i)/24)
        assert c.engine.mode == Mode.POINTING
    backend.events.clear()
    for i in range(12, 18):
        h = flex(sample(side, kind, clutch=True), finger)
        c.process(h, (11+i)/24)
    # Ring+pinky remains the dedicated shortcut candidate; its uncertain ring
    # cannot send Ctrl+Q. In either case the cursor is immediately locked.
    assert c.engine.mode == (Mode.SHORTCUT if finger==2 else Mode.PINKY_STOP)
    assert c.engine.pointer_blocked and backend.events == []


def test_uncertain_finger_cannot_start_pointer_and_folding_exits_it(backend):
    c = Controller(backend, Settings())
    c.set_state(State.RUNNING)
    for i in range(12):
        c.process(flex(hand_pose(), 0), i/24)
    assert c.engine.mode != Mode.POINTING and backend.events == []
    for i in range(12, 24):
        c.process(hand_pose(), i/24)
    assert c.engine.mode == Mode.POINTING
    c.process(flex(hand_pose(), 0, 65), 1.)
    assert c.engine.mode != Mode.POINTING
