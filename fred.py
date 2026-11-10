#!/usr/bin/env python3
"""美國總經數據（FRED API）：實際值、前值與發布日程。

由 fetch.py 呼叫，輸出 latest.json 兩個欄位：
  us_macro_fred  追蹤指標清單：name、period、value、prev、mode、last_updated（FRED，美國中部時間），
                 另有 release_date 與 released_prev_us_day（發布日是否為前一美國交易日，比 last_updated 準，
                 因為修正也會更新 last_updated）、actual／prev_display（已格式化的顯示值）
  us_calendar    未來 9 天美國重要數據發布：event、taipei（台北時間 MM/DD HH:MM）、metrics
預期值 FRED 沒有，仍由排程讀 tradingeconomics。
需要環境變數 FRED_API_KEY（GitHub secret）；沒有金鑰時回傳 None，不影響其他欄位。
"""
import json, os, time, datetime as dt
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
BASE = "https://api.stlouisfed.org/fred/"

# (series_id, units, 中文名稱, 顯示格式, mode)
# units：lin＝原值、chg＝較上期變動、pch＝較上期%變動、pc1＝年增率
# mode（07:45 排程讀取口徑）：mom＝月增率%、yoy＝年增率%、diff_k＝千人增減、level＝水準值、level_k＝千單位水準值
METRICS = [
    ("PAYEMS", "chg", "非農就業人數變動", "wan_k_chg", "diff_k"),
    ("UNRATE", "lin", "失業率", "pct1", "level"),
    ("CES0500000003", "pch", "平均時薪月增率", "pct1", "mom"),
    ("CES0500000003", "pc1", "平均時薪年增率", "pct1", "yoy"),
    ("CPIAUCSL", "pch", "CPI月增率", "pct1", "mom"),
    ("CPIAUCSL", "pc1", "CPI年增率", "pct1", "yoy"),
    ("CPILFESL", "pch", "核心CPI月增率", "pct1", "mom"),
    ("CPILFESL", "pc1", "核心CPI年增率", "pct1", "yoy"),
    ("PPIFIS", "pch", "PPI月增率", "pct1", "mom"),
    ("PPIFIS", "pc1", "PPI年增率", "pct1", "yoy"),
    ("PCEPI", "pc1", "PCE物價年增率", "pct1", "yoy"),
    ("PCEPILFE", "pch", "核心PCE物價月增率", "pct1", "mom"),
    ("PCEPILFE", "pc1", "核心PCE物價年增率", "pct1", "yoy"),
    ("RSAFS", "pch", "零售銷售月增率", "pct1", "mom"),
    ("A191RL1Q225SBEA", "lin", "實質GDP季增年率", "pct1", "level"),
    ("ICSA", "lin", "初領失業金人數", "wan_persons", "level"),
    ("JTSJOL", "lin", "JOLTS職缺數", "wan_k", "level_k"),
    ("INDPRO", "pch", "工業生產月增率", "pct1", "mom"),
    ("HOUST", "lin", "新屋開工（年化）", "wan_k", "level_k"),
    ("DGORDER", "pch", "耐久財訂單月增率", "pct1", "mom"),
    ("OPHNFB", "pc1", "非農生產力年增率", "pct1", "yoy"),
]
# 發布事件中文名與美東發布時間（FRED 只給日期）
EVENT = {"PAYEMS": ("美國就業報告（非農、失業率、時薪）", "08:30"), "CPIAUCSL": ("美國CPI", "08:30"),
         "PPIFIS": ("美國PPI", "08:30"), "PCEPI": ("美國個人所得與支出（PCE物價）", "08:30"),
         "RSAFS": ("美國零售銷售", "08:30"), "A191RL1Q225SBEA": ("美國GDP", "08:30"),
         "ICSA": ("美國初領失業金人數", "08:30"), "JTSJOL": ("美國JOLTS職缺", "10:00"),
         "INDPRO": ("美國工業生產", "09:15"), "HOUST": ("美國新屋開工", "08:30"),
         "DGORDER": ("美國耐久財訂單", "08:30"), "OPHNFB": ("美國生產力與單位勞動成本", "08:30")}
TPE = ZoneInfo("Asia/Taipei")



def _get(path, key, **params):
    params.update(api_key=key, file_type="json")
    url = BASE + path + "?" + urlencode(params)
    last = None
    for i in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent": "market-data/1.0"}), timeout=30) as f:
                return json.load(f)
        except HTTPError as e:  # 429／5xx 重試，4xx 其他直接拋出
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"{path} HTTP {e.code}: {e.read()[:200]!r}") from None
        except Exception as e:  # noqa
            last = e
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{path} 失敗：{last}")


def us_business_day(now_utc):
    """執行當下的紐約日期；週六、週日退回週五（美國假日當天本來就不會有發布）。"""
    d = now_utc.astimezone(NY).date()
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _sgn(v):
    return "+" if v > 0 else ("−" if v < 0 else "")


def fmt(v, kind):
    if v is None:
        return None
    if kind == "pct1":
        return f"{v:.1f}%"
    if kind == "wan_k_chg":  # 千人 → 萬人，帶正負號
        return f"{_sgn(v)}{abs(v) / 10:.1f}萬"
    if kind == "wan_k":
        return f"{v / 10:,.1f}萬"
    if kind == "wan_persons":
        return f"{v / 10000:.1f}萬"
    return f"{v:,.2f}"


def diff_text(a, b, kind):
    """實際與前值的差（排程算「與預期差」時用同樣口徑）。"""
    if a is None or b is None:
        return None
    d = a - b
    if kind == "pct1":
        return f"{_sgn(round(d, 1))}{abs(d):.1f}個百分點"
    if kind == "wan_persons":
        return f"{_sgn(d)}{abs(d) / 10000:.1f}萬"
    if kind in ("wan_k", "wan_k_chg"):
        return f"{_sgn(d)}{abs(d) / 10:.1f}萬"
    return f"{_sgn(d)}{abs(d):,.2f}"


def period_label(date_str, freq):
    d = dt.date.fromisoformat(date_str)
    if freq.startswith("W"):
        return f"{d:%m/%d}當週"
    if freq.startswith("Q"):
        return f"{d.year}Q{(d.month - 1) // 3 + 1}"
    return f"{d.year}年{d.month}月"


def build(now_utc, key=None, errors=None):
    key = key or os.environ.get("FRED_API_KEY")
    errors = errors if errors is not None else []
    if not key:
        print("FRED_API_KEY 未設定，略過美國總經數據")
        return None, None
    us_day = us_business_day(now_utc)

    # 1) 每個 series 屬於哪個 release（release_id 與名稱）
    series_ids = list(dict.fromkeys(m[0] for m in METRICS))
    sinfo, rel_of = {}, {}
    for sid in series_ids:
        try:
            s = _get("series", key, series_id=sid)["seriess"][0]
            r = _get("series/release", key, series_id=sid)["releases"][0]
            sinfo[sid] = {"freq": s.get("frequency_short", "M"), "units": s.get("units"),
                          "last_updated": s.get("last_updated")}
            rel_of[sid] = (int(r["id"]), r["name"])
        except Exception as e:  # noqa
            errors.append(f"FRED {sid} 基本資料取不到：{e}")

    # 2) 發布日程：us_day 前 7 天到後 14 天（含尚未發布的預定日）
    rel_ids = {v[0] for v in rel_of.values()}
    dates = {}
    try:
        js = _get("releases/dates", key, realtime_start=(us_day - dt.timedelta(days=7)).isoformat(),
                  realtime_end=(us_day + dt.timedelta(days=14)).isoformat(),
                  include_release_dates_with_no_data="true", limit=1000, sort_order="asc")
        for x in js.get("release_dates", []):
            rid = int(x["release_id"])
            if rid in rel_ids:
                dates.setdefault(rid, set()).add(dt.date.fromisoformat(x["date"]))
    except Exception as e:  # noqa
        errors.append(f"FRED 發布日程取不到：{e}")

    # 3) 各指標最新兩期
    latest = []
    for sid, units, name, kind, mode in METRICS:
        if sid not in rel_of:
            continue
        try:
            obs = _get("series/observations", key, series_id=sid, units=units, sort_order="desc",
                       limit=6)["observations"]
            obs = [(o["date"], _num(o["value"])) for o in obs if _num(o["value"]) is not None]
            if len(obs) < 2:
                errors.append(f"FRED {sid} {units} 資料不足"); continue
            (d1, v1), (d0, v0) = obs[0], obs[1]
            rid, rname = rel_of[sid]
            past = sorted(d for d in dates.get(rid, ()) if d <= us_day)
            latest.append({
                "name": name, "series_id": sid, "units": units, "mode": mode, "release_id": rid, "release": rname,
                "last_updated": sinfo[sid]["last_updated"],
                "release_date": past[-1].isoformat() if past else None,
                "period": period_label(d1, sinfo[sid]["freq"]), "period_date": d1,
                "value": round(v1, 4), "actual": fmt(v1, kind),
                "prev_period": period_label(d0, sinfo[sid]["freq"]),
                "prev": round(v0, 4), "prev_display": fmt(v0, kind), "chg_vs_prev": diff_text(v1, v0, kind)})
        except Exception as e:  # noqa
            errors.append(f"FRED {sid} {units} 取不到：{e}")

    for x in latest:
        x["released_prev_us_day"] = x["release_date"] == us_day.isoformat()

    # 4) 未來 9 天發布日程（依日期、事件彙整，時間換成台北）
    cal = {}
    for sid, (rid, rname) in rel_of.items():
        ev = EVENT.get(sid)
        if not ev:
            continue  # 同一 release 的其他 series（如 UNRATE）併入主事件
        for d in dates.get(rid, ()):
            if us_day < d <= us_day + dt.timedelta(days=9):
                hh, mm = map(int, ev[1].split(":"))
                tpe = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).astimezone(TPE)
                cal[(tpe, rid)] = {"event": ev[0], "taipei": tpe.strftime("%m/%d %H:%M"), "us_date": d.isoformat(),
                                   "et": ev[1], "release": rname,
                                   "metrics": [m[2] for m in METRICS if rel_of.get(m[0], (None,))[0] == rid]}
    calendar = [cal[k] for k in sorted(cal)]
    return latest, calendar

if __name__ == "__main__":
    errs = []
    items, cal = build(dt.datetime.now(dt.timezone.utc), errors=errs)
    print(json.dumps({"us_macro_fred": items, "us_calendar": cal}, ensure_ascii=False, indent=1))
    print("errors:", errs)
