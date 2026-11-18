"""Forecast GTA VI's launch-day Twitch viewers, hour by hour.

Reads one case file (schema makefun/twitch-ccu-case/v1) and writes, for
each of hours 2..24 of the release day, five quantiles (0.05, 0.25, 0.5,
0.75, 0.95) of the Twitch category's concurrent viewers.

Method
------
Everything is anchored on the hour-1 print (the only observed hour).
For every usable comparable launch we take its log-ratio curve
ln(viewers at hour h / viewers at hour 1) for h = 2..24.  Launch-day
shapes depend strongly on how big hour 1 already is -- a launch that
is already huge at 00:00 UTC stays comparatively flat, while a launch
with a tiny hour 1 explodes later as regions unlock -- so for each
hour we look at the K = 12 comparables whose hour-1 print is closest
in log space to the case's own hour-1 print, and take the empirical
quantiles of those neighbours' log-ratios as the forecast quantiles.
A floor spread of 0.25 in log space keeps the forecast from ever
being overconfident, and a 3-hour moving average over the log
quantiles smooths SullyGnome sampling noise out of the curve.
If no comparable is usable, we fall back to the persistence forecast
(every hour stays at the hour-1 print, spread 0.15 * sqrt(h - 1)).

Standard library only.  Deterministic: no randomness, no network,
no wall-clock dependence.  Two runs on the same input produce
byte-identical output.

Usage (grader):  python3 main.py
  reads $MAKEFUN_INPUT_DIR (default /input), writes $MAKEFUN_OUTPUT_DIR
  (default /output); every *.in file found is forecast, one output
  file per case named <id>.out.
Local testing:  python3 main.py [input_path [output_path]]
  input_path may be a single .in file or a directory of .in files;
  output_path may be a file (single case) or a directory.
"""

import json
import math
import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
Z_VALUES = (-1.645, -0.674, 0.0, 0.674, 1.645)
HOURS = tuple(range(2, 25))

# Number of nearest neighbours (in log hour-1 viewers) whose ratio
# curves set each hour's quantiles.  Tuned by leave-one-out backtest
# over the 37 usable comparables: k = 12 was best on the big-launch
# subset (the regime GTA VI sits in) and near-best overall.
K_NEIGHBOURS = 12
# Minimum log-spread (half-width factor): the 5%-95% band is never
# narrower than exp(2 * 1.645 * SPREAD_FLOOR).
SPREAD_FLOOR = 0.25
# Width of the moving-average window (in hours) applied to the log
# quantiles across neighbouring hours.
SMOOTH_WINDOW = 3


def parse_time(text):
    """Parse an ISO-8601 UTC timestamp into a naive datetime."""
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def empirical_quantile(sorted_values, tau):
    """Linear-interpolation quantile of an already sorted list."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = tau * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_values[lo]
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def usable_curves(case):
    """Extract (name, hour-1 viewers, {hour: viewers}) for each usable
    comparable launch: hour-1 viewers present and positive, and every
    hour 2..24 present and positive around its day_start."""
    curves = []
    for comp in case.get("comparables") or []:
        try:
            day_start = parse_time(comp["day_start"])
        except (KeyError, TypeError, ValueError):
            continue
        by_time = {}
        for point in comp.get("hourly") or []:
            try:
                viewers = point["viewers"]
                when = parse_time(point["from"])
            except (KeyError, TypeError, ValueError):
                continue
            if isinstance(viewers, (int, float)) and viewers > 0:
                by_time[when] = float(viewers)
        first = by_time.get(day_start)
        if not first:
            continue
        values = {}
        complete = True
        for hour in HOURS:
            viewers = by_time.get(day_start + timedelta(hours=hour - 1))
            if not viewers:
                complete = False
                break
            values[hour] = viewers
        if complete:
            curves.append((str(comp.get("name", "")), first, values))
    return curves


def hour1_print(case):
    """Hour-1 print from `known`, floored at 1 viewer."""
    known = case.get("known") or []
    if known:
        try:
            viewers = float(known[0]["viewers"])
        except (KeyError, TypeError, ValueError):
            viewers = 1.0
    else:
        viewers = 1.0
    if not math.isfinite(viewers) or viewers < 1.0:
        return 1.0
    return viewers


def persistence_forecast(print_1):
    """Fallback: every hour stays at the hour-1 print, spread growing
    as 0.15 * sqrt(h - 1).  Also the house baseline's shape."""
    rows = []
    for hour in HOURS:
        spread = 0.15 * math.sqrt(hour - 1)
        quantiles = [
            print_1 * math.exp(z * spread) for z in Z_VALUES
        ]
        rows.append((hour, quantiles))
    return rows


def neighbour_forecast(print_1, curves):
    """k-nearest-neighbour (in log hour-1 viewers) empirical-quantile
    forecast.  Returns a list of (hour, [q05, q25, q50, q75, q95])."""
    log_print = math.log(print_1)
    k = min(K_NEIGHBOURS, len(curves))
    # Neighbours are chosen once: the same launches are closest in
    # log hour-1 scale for every hour, so the set does not change.
    ranked = sorted(
        curves,
        key=lambda curve: (abs(math.log(curve[1]) - log_print), curve[0]),
    )
    neighbours = ranked[:k]

    log_quantiles = {hour: [] for hour in HOURS}
    for hour in HOURS:
        log_ratios = sorted(
            math.log(curve[2][hour] / curve[1]) for curve in neighbours
        )
        median_log = statistics.median(log_ratios)
        row = []
        for tau in LEVELS:
            row.append(empirical_quantile(log_ratios, tau))
        # Floor the spread: never narrower than the floor band around
        # the median log-ratio.
        if row[-1] - row[0] < 2.0 * 1.645 * SPREAD_FLOOR:
            row = [median_log + z * SPREAD_FLOOR for z in Z_VALUES]
        log_quantiles[hour] = row

    # Smooth each quantile's log curve over neighbouring hours with a
    # centred moving average; this removes hour-to-hour sampling noise
    # while keeping the launch-day shape (ramp, plateau, evening dip).
    half = SMOOTH_WINDOW // 2
    hour_list = list(HOURS)
    for qi in range(len(LEVELS)):
        raw = [log_quantiles[hour][qi] for hour in hour_list]
        smoothed = []
        for i in range(len(raw)):
            window = raw[max(0, i - half):i + half + 1]
            smoothed.append(sum(window) / len(window))
        for i, hour in enumerate(hour_list):
            log_quantiles[hour][qi] = smoothed[i]

    # Smoothing can narrow a band that the floor had widened, so
    # re-apply the spread floor afterwards, centred on the median.
    for hour in HOURS:
        row = log_quantiles[hour]
        if row[-1] - row[0] < 2.0 * 1.645 * SPREAD_FLOOR:
            median_log = row[2]
            log_quantiles[hour] = [
                median_log + z * SPREAD_FLOOR for z in Z_VALUES
            ]

    rows = []
    for hour in HOURS:
        quantiles = [print_1 * math.exp(v) for v in log_quantiles[hour]]
        rows.append((hour, quantiles))
    return rows


def clean_quantiles(quantiles):
    """Clamp to (0, 1e9], round to 2 decimals, enforce non-decreasing."""
    cleaned = []
    previous = 0.0
    for value in quantiles:
        if not math.isfinite(value) or value <= 0.0:
            value = 1.0
        if value > 1e9:
            value = 1e9
        value = round(float(value), 2)
        if value <= 0.0:
            value = 0.01
        if value < previous:
            value = previous
        cleaned.append(value)
        previous = value
    return cleaned


def forecast_case(case):
    """Build the output object for one parsed case."""
    print_1 = hour1_print(case)
    curves = usable_curves(case)
    if curves:
        rows = neighbour_forecast(print_1, curves)
    else:
        rows = persistence_forecast(print_1)
    hours = [
        {"hour": hour, "q": clean_quantiles(quantiles)}
        for hour, quantiles in rows
    ]
    return {"hours": hours}


def resolve_paths(argv):
    """Return (input_paths, output_path, output_is_dir).

    Precedence: command-line overrides, then $MAKEFUN_INPUT_DIR /
    $MAKEFUN_OUTPUT_DIR, then /input and /output.
    """
    input_arg = argv[1] if len(argv) > 1 else None
    output_arg = argv[2] if len(argv) > 2 else None
    input_dir = input_arg or os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    output_dir = output_arg or os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    input_path = Path(input_dir)
    if input_path.is_dir():
        input_paths = sorted(input_path.glob("*.in"))
    else:
        input_paths = [input_path]
    output_path = Path(output_dir)
    output_is_dir = output_arg is None or output_path.is_dir() or (
        len(input_paths) > 1
    )
    return input_paths, output_path, output_is_dir


def main(argv):
    input_paths, output_path, output_is_dir = resolve_paths(argv)
    if output_is_dir:
        output_path.mkdir(parents=True, exist_ok=True)
    for input_file in input_paths:
        with open(input_file, "r", encoding="utf-8") as handle:
            case = json.load(handle)
        result = forecast_case(case)
        case_id = case.get("id") or input_file.stem
        if output_is_dir:
            target = output_path / (str(case_id) + ".out")
        else:
            target = output_path
            target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(result, separators=(",", ":"))
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
