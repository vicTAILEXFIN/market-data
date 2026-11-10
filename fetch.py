#!/usr/bin/env python3
"""每日金融市場摘要：行情數據抓取（於 GitHub Actions 執行）。

輸出 data/latest.json 與 data/YYYY-MM-DD.json（台北日期），供 07:45 的摘要排程讀取。
來源：Yahoo Finance（yfinance）、紐約聯準銀行 EFFR API（免金鑰）、美國財政部 CSV、FRED API（需 FRED_API_KEY）。
FedWatch 以 30 天期聯邦基金期貨（ZQ）依 CME 方法推算。
"""
import json, math, os, sys, time, datetime as dt
from zoneinfo import ZoneInfo
from urllib.request import urlopen, Request

TPE = ZoneInfo("Asia/Taipei"); NY = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago"); LDN = ZoneInfo("Europe/London")

INDICES = {"^DJI": "道瓊工業指數", "^GSPC": "標準普爾500指數", "^IXIC": "那斯達克綜合指數",
           "^SOX": "費城半導體指數", "^N225": "日經225指數", "^KS11": "韓國綜合股價指數",
           "^TWII": "台灣加權指數"}
STOCKS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "GS", "CAT", "MU", "INTC", "AMD",
          "TSM", "2330.TW", "2317.TW", "2454.TW", "2308.TW", "005930.KS", "000660.KS", "373220.KS",
          "9983.T", "8035.T", "6857.T", "9984.T"]
# 匯率與商品：結算參考K棒（30分K「開始」時間，當地時區）
MACRO = {"TWD=X": ("美元兌新台幣", TPE, (15, 30), False),
         "JPY=X": ("美元兌日圓", NY, (16, 30), False),
         "BZ=F": ("布蘭特原油", LDN, (19, 0), True),
         "GC=F": ("黃金（COMEX近月期貨）", NY, (13, 0), True),
         "DX-Y.NYB": ("美元指數", NY, (16, 30), False)}
# FOMC 決議日（第二天），來源 federalreserve.gov
FOMC = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16",
        "2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
        "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08", "2028-01-26"]
FOMC = [dt.date.fromisoformat(x) for x in FOMC]
MCODE = "FGHJKMNQUVXZ"

errors = []


def r(x, n=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def treasury_curve(today):
    """美國財政部每日公債殖利率（官方 CSV）：回傳最近兩個早於台北今日的交易日的 2Y、30Y。"""
    import csv, io
    rows = []
    for year in (today.year, today.year - 1):
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
               f"{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv")
        text = urlopen(Request(url, headers={"User-Agent": "market-data/1.0"}), timeout=30).read().decode("utf-8-sig")
        rows += list(csv.DictReader(io.StringIO(text)))
        if len(rows) >= 3:
            break
    parsed = []
    for x in rows:
        d = dt.datetime.strptime(x["Date"], "%m/%d/%Y").date()
        if d < today and x.get("2 Yr") and x.get("30 Yr"):
            parsed.append((d, float(x["2 Yr"]), float(x["30 Yr"])))
    parsed.sort(reverse=True)
    (d1, y2, y30), (_d0, p2, p30) = parsed[0], parsed[1]
    return {"date": d1.isoformat(), "source": "treasury",
            "y2": {"yield": round(y2, 2), "bp": int(round((y2 - p2) * 100))},
            "y30": {"yield": round(y30, 2), "bp": int(round((y30 - p30) * 100))}}


# ---------- 下載 ----------
def yf_hist(symbol, period, interval, tries=3):
    import yfinance as yf
    for i in range(tries):
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
            if df is not None and len(df):
                return df
        except Exception as e:  # noqa
            last = e
        time.sleep(3 * (i + 1))
    errors.append(f"{symbol} {interval} 取不到")
    return None


def daily_closes(df, before):
    """回傳 [(date, close)]，只取日期早於 before 的完整日K；同日重複（盤中即時K）保留第一根。"""
    out = []
    if df is None:
        return out
    for ts, row in df.iterrows():
        d = ts.date()
        if d >= before or math.isnan(row["Close"]):
            continue
        if out and out[-1][0] == d:
            continue
        out.append((d, float(row["Close"])))
    return out


def ref_closes(df, tz, hm):
    """30分K：回傳 [(當地日期, 收盤)]，只取當地時間 = 參考開始時間的那根。"""
    out = {}
    if df is None:
        return []
    for ts, row in df.iterrows():
        lt = ts.tz_convert(tz)
        if (lt.hour, lt.minute) == hm and not math.isnan(row["Close"]):
            out.setdefault(lt.date(), float(row["Close"]))
    return sorted(out.items())


# ---------- FedWatch ----------
def zq_symbol(y, m):
    return f"ZQ{MCODE[m - 1]}{y % 100:02d}.CBT"


def month_add(y, m, k):
    m2 = m - 1 + k
    return y + m2 // 12, m2 % 12 + 1


def days_in_month(y, m):
    ny, nm = month_add(y, m, 1)
    return (dt.date(ny, nm, 1) - dt.date(y, m, 1)).days


def has_meeting(y, m):
    return any(x.year == y and x.month == m for x in FOMC)


def binary(step):
    lo = math.floor(step + 1e-9)
    w = step - lo
    return {lo: 1 - w, lo + 1: w} if w > 1e-9 else {lo: 1.0}


def convolve(a, b):
    out = {}
    for i, p in a.items():
        for j, q in b.items():
            out[i + j] = out.get(i + j, 0) + p * q
    return out


def fed_probs(asof, target, price, effr):
    """asof: 期貨結算日；target: 目標會議決議日；price(y,m)->期貨價或None；effr: asof 當日 EFFR(%)。
    回傳 {步數(以25bp計): 機率}，相對 asof 當時利率區間。"""
    chain = [x for x in FOMC if asof < x <= target]
    dist, prev_post = {0: 1.0}, None
    for i, m in enumerate(chain):
        y, mo = m.year, m.month
        N, d = days_in_month(y, mo), m.day
        py, pm = month_add(y, mo, -1)
        if i == 0 and not has_meeting(py, pm) and (py, pm) >= (asof.year, asof.month) and price(py, pm):
            pre = 100 - price(py, pm)
        elif prev_post is not None:
            pre = prev_post
        else:
            pre = effr
        if N - d >= 7 and price(y, mo):
            post = ((100 - price(y, mo)) * N - pre * d) / (N - d)
        else:
            ny_, nm_ = month_add(y, mo, 1)
            if not price(ny_, nm_):
                raise ValueError(f"缺 {zq_symbol(ny_, nm_)}")
            post = 100 - price(ny_, nm_)
        dist = convolve(dist, binary((post - pre) / 0.25))
        prev_post = post
    return dist


def bucket(dist):
    cut = sum(p for k, p in dist.items() if k < 0)
    hold = dist.get(0, 0)
    h1 = dist.get(1, 0)
    h2 = sum(p for k, p in dist.items() if k >= 2)
    vals = [cut * 100, hold * 100, h1 * 100, h2 * 100]
    vals = [round(v, 1) for v in vals]
    diff = round(100 - sum(vals), 1)
    vals[vals.index(max(vals))] = round(vals[vals.index(max(vals))] + diff, 1)
    return [0.0 if v == 0 else v for v in vals]


def nyfed_effr():
    url = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/90.json"
    with urlopen(Request(url, headers={"User-Agent": "digest-fetch"}), timeout=30) as f:
        js = json.load(f)
    rows = []
    for x in js.get("refRates", []):
        rows.append((dt.date.fromisoformat(x["effectiveDate"]), float(x["percentRate"]),
                     float(x.get("targetRateFrom", "nan")), float(x.get("targetRateTo", "nan"))))
    return sorted(rows)


def on_or_before(rows, d):
    c = [x for x in rows if x[0] <= d]
    return c[-1] if c else None


def build_fedwatch(today_tpe, effr_rows, zq):
    """zq: {(y,m): [(date, close), ...]}"""
    def price_at(day):
        def p(y, m):
            s = [c for d, c in zq.get((y, m), []) if d <= day]
            return s[-1] if s else None
        return p
    dates = sorted({d for v in zq.values() for d, _ in v})
    if not dates:
        raise ValueError("ZQ 無資料")
    asof = dates[-1]
    target = next(x for x in FOMC if x > asof)
    mo_back = asof.replace(day=1) - dt.timedelta(days=1)
    one_month = asof.replace(year=mo_back.year, month=mo_back.month, day=min(asof.day, mo_back.day))
    picks = [("最新", asof),
             ("1天前", dates[-2] if len(dates) > 1 else None),
             ("1週前", max([d for d in dates if d <= asof - dt.timedelta(days=7)], default=None)),
             ("1個月前", max([d for d in dates if d <= one_month], default=None))]
    e_now = on_or_before(effr_rows, asof)
    rows = []
    for label, day in picks:
        if day is None:
            continue
        e = on_or_before(effr_rows, day)
        if e is None:
            continue
        try:
            rows.append([label] + bucket(fed_probs(day, target, price_at(day), e[1])))
        except Exception as ex:  # noqa
            errors.append(f"FedWatch {label} 計算失敗：{ex}")
    lo, hi = e_now[2], e_now[3]
    return {"meeting": target.strftime("%m/%d"), "range": f"{lo:.2f}%–{hi:.2f}%",
            "asof": asof.strftime("%m/%d"), "rows": rows, "source": "computed_from_ZQ",
            "effr": e_now[1]}


# ---------- 主程式 ----------
def pair(series, name, digits=4):
    if len(series) < 2:
        errors.append(f"{name} 不足兩個交易日")
        return None
    (d0, c0), (d1, c1) = series[-2], series[-1]
    return {"name": name, "date": d1.isoformat(), "close": r(c1, digits), "prev_date": d0.isoformat(),
            "prev_close": r(c0, digits), "chg": r(c1 - c0, digits), "pct": r((c1 / c0 - 1) * 100, 2)}


def main():
    now = dt.datetime.now(dt.timezone.utc)
    ct = now.astimezone(CT)
    today = now.astimezone(TPE).date()
    os.makedirs("data", exist_ok=True)
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        # 兩個 cron（UTC 21:15、22:15）對應冬令／夏令；以芝加哥 16:00–17:00 CME 休市時段為準
        if ct.hour < 16:
            print("尚未到 CME 休市時段，略過（較晚的 cron 會執行）"); return
        try:
            prev = json.load(open("data/latest.json"))
            if prev.get("taipei_date") == today.isoformat() and prev.get("fedwatch"):
                print("今日已有成功資料，略過"); return
        except Exception:  # noqa
            pass
    out = {"generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "taipei_date": today.isoformat(),
           "indices": {}, "ust10y": None, "sse": None, "ust_curve": None, "stocks": {}, "macro": {}, "fedwatch": None, "us_macro_fred": None, "errors": errors}

    for s, n in INDICES.items():
        p = pair(daily_closes(yf_hist(s, "10d", "1d"), today), n, 2)
        if p:
            out["indices"][s] = p
    tnx = daily_closes(yf_hist("^TNX", "10d", "1d"), today)
    if len(tnx) >= 2:
        f = (lambda v: v / 10) if tnx[-1][1] > 20 else (lambda v: v)
        y1, y0 = f(tnx[-1][1]), f(tnx[-2][1])
        out["ust10y"] = {"date": tnx[-1][0].isoformat(), "yield": r(y1, 3), "prev": r(y0, 3),
                         "bp": int(round((y1 - y0) * 100))}
    p = pair(daily_closes(yf_hist("000001.SS", "10d", "1d"), today), "上證綜合", 2)
    if p:
        out["sse"] = p
    try:
        out["ust_curve"] = treasury_curve(today)
    except Exception as e:  # noqa
        errors.append(f"美債2Y/30Y 取不到：{e}")
    for s in STOCKS:
        p = pair(daily_closes(yf_hist(s, "10d", "1d"), today), s, 2)
        if p:
            out["stocks"][s] = {"date": p["date"], "close": p["close"], "pct": p["pct"]}

    for s, (n, tz, hm, settled_prev) in MACRO.items():
        refs = [x for x in ref_closes(yf_hist(s, "5d", "30m"), tz, hm) if x[0] < today]
        if not refs:
            errors.append(f"{n} 無參考K棒"); continue
        d1, c1 = refs[-1]
        prev = None
        if settled_prev:  # 期貨：前收用已結算日K
            dl = [x for x in daily_closes(yf_hist(s, "10d", "1d"), today) if x[0] < d1]
            prev = dl[-1] if dl else None
        if prev is None and len(refs) >= 2:
            prev = refs[-2]
        if prev is None:
            errors.append(f"{n} 無前收"); continue
        digits = 3 if s == "TWD=X" else 2
        out["macro"][s] = {"name": n, "date": d1.isoformat(), "close": r(c1, digits),
                           "prev_date": prev[0].isoformat(), "prev_close": r(prev[1], digits),
                           "chg": r(c1 - prev[1], digits), "pct": r((c1 / prev[1] - 1) * 100, 2),
                           "method": "30m參考K棒" + ("＋已結算日K前收" if settled_prev else "")}

    try:
        effr = nyfed_effr()
        y, m = today.year, today.month
        zq = {}
        for k in range(-1, 5):
            yy, mm = month_add(y, m, k)
            sr = daily_closes(yf_hist(zq_symbol(yy, mm), "3mo", "1d", tries=2), today)
            if sr:
                zq[(yy, mm)] = sr
        errors[:] = [e for e in errors if not e.startswith("ZQ")]  # 已到期合約取不到屬正常
        out["fedwatch"] = build_fedwatch(today, effr, zq)
        hist_path = "data/zq_history.json"
        hist = json.load(open(hist_path)) if os.path.exists(hist_path) else {}
        for (yy, mm), sr in zq.items():
            hist.setdefault(zq_symbol(yy, mm), {}).update({d.isoformat(): c for d, c in sr})
        json.dump(hist, open(hist_path, "w"), ensure_ascii=False, indent=0, sort_keys=True)
    except Exception as ex:  # noqa
        errors.append(f"FedWatch 失敗：{ex}")

    try:
        import fred
        out["us_macro_fred"] = fred.build(now, errors=errors)
    except Exception as ex:  # noqa
        errors.append(f"FRED 失敗：{ex}")

    for path in ("data/latest.json", f"data/{today.isoformat()}.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: (len(v) if isinstance(v, dict) else v) for k, v in out.items() if k != "errors"},
                     ensure_ascii=False))
    print("errors:", errors)


if __name__ == "__main__":
    main()
