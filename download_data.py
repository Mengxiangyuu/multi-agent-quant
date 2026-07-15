#!/usr/bin/env python3
"""一次性下载历史数据到本地 CSV 缓存。"""

import time
import yfinance as yf
from pathlib import Path

SYMBOLS = ["AAPL", "TSLA", "MSFT", "BTC-USD", "ETH-USD"]
START = "2020-01-01"
END = "2026-01-01"
CACHE_DIR = Path(__file__).parent / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

for sym in SYMBOLS:
    out_path = CACHE_DIR / f"{sym}.csv"
    if out_path.exists():
        print(f"[SKIP] {sym} already cached")
        continue

    print(f"[FETCH] {sym}...")
    for attempt in range(5):
        try:
            df = yf.download(sym, start=START, end=END, progress=False)
            if df.empty:
                raise ValueError("empty data")
            df.to_csv(out_path)
            print(f"  -> saved {len(df)} rows to {out_path}")
            break
        except Exception as e:
            wait = 2 ** attempt
            print(f"  retry in {wait}s ({e})")
            time.sleep(wait)
    else:
        print(f"  [FAIL] {sym}")

print("\nDone!")
