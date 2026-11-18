# gta6-twitch-ccu-forecast-01

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/dhany999/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/dhany999/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts, hour by hour, how many concurrent viewers the "Grand Theft Auto VI" Twitch category has over the 24 UTC hours of release day 2026-11-19, from everything recorded up to the end of hour 1. For each of hours 2..24 it outputs five quantiles (5%, 25%, 50%, 75%, 95%) of that hour's viewer count. Standard library only, deterministic, no network.

## Method

Everything is anchored on the hour-1 print. For each usable comparable launch (38 past big game launches, minus the one pre-release GTA VI series with no complete day-1 window), the program takes its log-ratio curve: ln(viewers at hour h / viewers at hour 1) for h = 2..24.

Launch-day shapes depend strongly on how big hour 1 already is — a launch that is already huge at 00:00 UTC stays comparatively flat, while one with a tiny hour 1 explodes later as regions unlock — so for each hour the forecast uses the 12 comparables whose hour-1 print is closest in log space to the case's own hour-1 print, and takes the empirical quantiles of those neighbours' log-ratios. A floor spread of 0.25 in log space keeps the forecast from ever being overconfident, and a 3-hour moving average over the log quantiles smooths out sampling noise. If no comparable is usable, it falls back to the persistence forecast (every hour stays at the hour-1 print, spread 0.15 * sqrt(h - 1)).

Leave-one-out backtest over the 37 usable comparables (each launch forecast from the other 36 only, scored by mean pinball loss on the log scale): **0.449** for this method vs **0.930** for the persistence baseline. On the big-launch subset (hour-1 print ≥ 50,000 viewers, the regime GTA VI sits in): **0.206** vs **0.251**.

## Run it

```sh
python3 main.py
```

Reads every `*.in` case in `$MAKEFUN_INPUT_DIR` (default `/input`) and writes one `<id>.out` forecast per case to `$MAKEFUN_OUTPUT_DIR` (default `/output`). For local testing you can also pass paths directly:

```sh
python3 main.py input/p00.in out/p00.out
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=dhpnw6yp&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
