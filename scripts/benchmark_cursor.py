"""Replay synthetic finger trajectories; no camera, GUI or real pointer input.

Optional --baseline replays the archived pre-v1.7 cursor implementation. Measurements
are algorithm-only comparisons, not end-to-end latency or real-hand accuracy.
"""
import argparse
import importlib.util
import inspect
import json
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from airmouse_ai.cursor import CursorFilter


def measure(factory):
    def run(velocity, seconds, fps=24):
        f = factory(1920, 1080)
        timed = 'now' in inspect.signature(f.update_relative).parameters
        def update(x, y, i, **kw):
            return f.update_relative(x, y, False, **({'now': i/fps} if timed else {}), **kw)
        update(0, 0, 0, anchor=(500, 500))
        events = []
        for i in range(1, round(seconds*fps)+1):
            result = update(velocity*i/fps, 0, i)
            if result is not None:
                events.append((i/fps, result))
        return f, events
    slow, moves = run(.072, 1)
    fine, fine_moves = run(.012, 2)
    fast, _ = run(.6, .3)
    slow_equal, _ = run(.06, 3)
    rates = {fps: round(run(.2, 2, fps)[0].position[0]-500, 2) for fps in (15, 20, 24, 30)}
    starts = [p[1][0] for p in moves]
    f, _ = run(.072, 1)
    timed = 'now' in inspect.signature(f.update_relative).parameters
    end = f.position
    positions = []
    started = time.perf_counter()
    for i in range(1, 10001):
        f.update_relative(.072+.007*math.sin(i*1.7), .007*math.cos(i*2.1), False,
                          **({'now': 1+i/24} if timed else {}))
        if i <= 200:
            positions.append(f.position)
    elapsed = time.perf_counter()-started
    stable = positions[6:]
    return {
        'slow_start_ms': round(moves[0][0]*1000, 1) if moves else None,
        'slow_updates_per_24_frames': len(moves),
        'slow_travel_px': round(slow.position[0]-500, 2),
        'slow_largest_update_px': max(b-a for a, b in zip(starts, starts[1:])),
        'fine_travel_px_2s': round(fine.position[0]-500, 2),
        'fine_updates_2s': len(fine_moves),
        'same_length_fast_travel_px': round(fast.position[0]-500, 2),
        'same_length_slow_travel_px': round(slow_equal.position[0]-500, 2),
        'travel_px_15_20_24_30_fps': rates,
        'fps_travel_spread_percent': round((max(rates.values())-min(rates.values()))/rates[30]*100, 2),
        'post_stop_noise_range_px_after_250ms': [round(max(p[a] for p in stable)-min(p[a] for p in stable), 3) for a in (0, 1)],
        'stop_settle_displacement_px': round(math.dist(end, positions[5]), 2),
        'filter_microseconds_per_sample': round(elapsed/10000*1e6, 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--report', type=Path, default=ROOT/'artifacts/cursor-v1.7.json')
    args = parser.parse_args()
    report = {'scope': 'Synthetic normalized finger trajectories at 1920x1080; default filter, unit direction gains; no OS input. Start timing excludes recognition/camera latency.',
              'current': measure(CursorFilter)}
    if args.baseline:
        spec = importlib.util.spec_from_file_location('airmouse_ai.cursor_baseline', args.baseline)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        old_tuning = SimpleNamespace(finger_max_step=.5, finger_deadzone=.018,
                                    finger_unlock=.030, finger_gain=1.55,
                                    finger_move_alpha=.55, cursor_max_step_px=150)
        report['v1.6'] = measure(lambda w, h: module.CursorFilter(w, h, old_tuning))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
