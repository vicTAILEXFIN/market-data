# -*- coding: utf-8 -*-
"""從 Yahoo 盤中K(30m, range 5d)取各商品「結算/收盤參考時點」價格。
Usage: python3 pick_closes.py <alexandria結果檔.json> [更多檔...]
輸出：每個 symbol 每個當地日期，在參考時點結束的那根K棒收盤價（找不到則取參考時點前最後一根）。"""
import json, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

REF = {  # symbol: (時區, 參考時點, 說明)
    "BZ=F": ("Europe/London", "19:30", "ICE Brent 結算"),
    "GC=F": ("America/New_York", "13:30", "COMEX 黃金結算"),
    "DX-Y.NYB": ("America/New_York", "17:00", "紐約收盤"),
    "TWD=X": ("Asia/Taipei", "16:00", "台北收盤"),
}
STEP = {"30m": 30, "60m": 60, "15m": 15}


def load(p):
    d = json.load(open(p, encoding="utf-8"))
    d = d.get("data", d)
    for r in d.get("alexandria", []):
        if "data" in r and r["data"].get("bars"):
            yield r["data"]


for p in sys.argv[1:]:
    for x in load(p):
        sym, iv = x["symbol"], x["interval"]
        if sym not in REF or iv not in STEP:
            continue
        tz, hm, note = REF[sym]
        z = ZoneInfo(tz)
        days = {}
        for b in x["bars"]:
            st = datetime.fromisoformat(b["datetime"].replace("Z", "+00:00")).astimezone(z)
            end = st + timedelta(minutes=STEP[iv])
            days.setdefault(end.date(), []).append((end, b["close"]))
        print(f"== {sym}（{note} {tz} {hm}）")
        for day in sorted(days):
            ref = datetime.combine(day, datetime.strptime(hm, "%H:%M").time(), z)
            cand = [(e, c) for e, c in days[day] if e <= ref]
            if not cand:
                continue
            e, c = max(cand)
            flag = "" if e == ref else f"（最近K棒 {e:%H:%M}，非整點參考）"
            print(f"{day:%m/%d}\t{c}\t{flag}")
