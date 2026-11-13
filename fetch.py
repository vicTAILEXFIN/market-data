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
DIAG = {}  # 檢查未過時的明細，寫進 latest.json 方便事後追查


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
        if d < today and x.get("2 Yr") and x.get("10 Yr") and x.get("30 Yr"):
            parsed.append((d, float(x["2 Yr"]), float(x["10 Yr"]), float(x["30 Yr"])))
    parsed.sort(reverse=True)
    (d1, y2, y10, y30), (_d0, p2, p10, p30) = parsed[0], parsed[1]
    q = lambda y, p: {"yield": round(y, 2), "bp": int(round((y - p) * 100))}
    return {"date": d1.isoformat(), "source": "treasury", "y2": q(y2, p2), "y10": q(y10, p10), "y30": q(y30, p30)}


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


UA = {"User-Agent": "Mozilla/5.0 (market-data digest; +https://github.com/vicTAILEXFIN/market-data)"}


def get(url, data=None, timeout=30):
    import gzip
    raw = urlopen(Request(url, data=data, headers=UA), timeout=timeout).read()
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def num(s):
    s = str(s).replace(",", "").strip()
    return float(s) if s not in ("", "-", "--") else None


def twd_official(today):
    """央行網站「新臺幣/美元銀行間收盤匯率」（資料來源：台北外匯經紀，營業日 16:00–17:00 公布）。"""
    import re
    text = re.sub(r"<[^>]+>", " ", get("https://www.cbc.gov.tw/tw/lp-645-1-1-60.html").decode("utf-8", "ignore"))
    rows = []
    for d, v in re.findall(r"(\d{4}/\d{2}/\d{2})\s+([0-9]{2}\.[0-9]{3})", text):
        dd = dt.date.fromisoformat(d.replace("/", "-"))
        if dd < today:
            rows.append((dd, float(v)))
    rows = sorted(set(rows))
    if len(rows) < 2:
        raise ValueError(f"央行收盤匯率解析不到兩筆（{len(rows)}）")
    (d0, c0), (d1, c1) = rows[-2], rows[-1]
    return {"name": "美元兌新台幣", "date": d1.isoformat(), "close": c1, "prev_date": d0.isoformat(), "prev_close": c0,
            "chg": round(c1 - c0, 3), "pct": round((c1 / c0 - 1) * 100, 2), "source": "cbc_taipeiforex_close"}


def ust_auctions(today):
    """TreasuryDirect：近期中長債標售結果與未來 8 天標售日程（13:00 ET 截標，換算台北時間）。"""
    base = "https://www.treasurydirect.gov/TA_WS/securities/"
    stype = lambda x: x.get("securityType") or x.get("announcedAsSecurityType") or ""
    keep = lambda x: stype(x) in ("Note", "Bond") or "TIPS" in stype(x)

    def tpe_time(day, x=None):
        hm = dt.time(13, 0)
        t = (x or {}).get("competitiveAuctionCloseTime") or ""
        try:
            hm = dt.datetime.strptime(t.strip().upper().replace(".", ""), "%I:%M %p").time()
        except ValueError:
            pass
        et = dt.datetime.combine(day, hm, NY)
        return et.astimezone(TPE).strftime("%m/%d %H:%M")

    def adate(x):
        for k in ("auctionDate", "competitiveAuctionCloseDate", "announcedAuctionDate"):
            v = x.get(k)
            if v and len(str(v)) >= 10:
                return dt.date.fromisoformat(str(v)[:10])
        return None

    def row(x, day, done):
        amt = num(x.get("offeringAmount"))
        r_ = {"term": x.get("securityTerm") or x.get("announcedAsSecurityTerm"), "type": stype(x), "auction_date_et": day.isoformat(),
              "taipei_time": tpe_time(day, x), "offering_bn": round(amt / 1e9, 1) if amt else None,
              "reopening": x.get("reopening") == "Yes"}
        if done:
            r_.update({"high_yield": num(x.get("highYield")), "bid_to_cover": num(x.get("bidToCoverRatio"))})
        return r_

    def rows(items, done, keep_if):
        if isinstance(items, dict):  # 有些端點包一層
            items = next((v for v in items.values() if isinstance(v, list)), [])
        out_, missing = [], 0
        for x in items:
            if not isinstance(x, dict) or not keep(x):
                continue
            day = adate(x)
            if day is None:
                missing += 1; continue
            if keep_if(x, day):
                out_.append(row(x, day, done))
        if missing and not out_:
            sample = next((x for x in items if isinstance(x, dict)), {})
            raise ValueError(f"找不到標售日期欄位；欄位={sorted(sample)}")
        return out_
    up = json.loads(get(base + "upcoming?format=json"))
    done = json.loads(get(base + "auctioned?format=json&days=10"))
    horizon = today + dt.timedelta(days=9)
    return {"upcoming": sorted(rows(up, False, lambda x, d: d <= horizon), key=lambda r_: r_["auction_date_et"]),
            "results": sorted(rows(done, True, lambda x, d: bool(x.get("highYield"))),
                              key=lambda r_: r_["auction_date_et"], reverse=True)[:6]}


def twse_institutional(today):
    """證交所三大法人買賣金額（BFI82U），取早於今天的最近交易日；單位億元。"""
    for k in range(1, 8):
        d = today - dt.timedelta(days=k)
        js = json.loads(get(f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={d:%Y%m%d}&response=json"))
        if js.get("stat") == "OK" and js.get("data"):
            net = {r_[0]: num(r_[3]) for r_ in js["data"]}
            yi = lambda v: None if v is None else round(v / 1e8, 2)
            pick = lambda key: next((v for n, v in net.items() if n.startswith(key)), None)
            return {"date": d.isoformat(), "unit": "億元",
                    "foreign": yi(pick("外資及陸資")), "trust": yi(pick("投信")),
                    "dealer": yi((pick("自營商(自行買賣)") or 0) + (pick("自營商(避險)") or 0)), "total": yi(pick("合計"))}
        time.sleep(1)
    raise ValueError("BFI82U 近7日無資料")


def taifex_foreign_tx(today):
    """期交所三大法人期貨未平倉（臺股期貨 TXF）：外資多空未平倉口數淨額。"""
    import csv, io
    from urllib.parse import urlencode
    for k in range(1, 8):
        d = today - dt.timedelta(days=k)
        form = urlencode({"queryStartDate": f"{d:%Y/%m/%d}", "queryEndDate": f"{d:%Y/%m/%d}", "commodityId": "TXF"}).encode()
        text = get("https://www.taifex.com.tw/cht/3/futContractsDateDown", data=form).decode("big5", "ignore")
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2 or "身份別" not in "".join(rows[0]):
            time.sleep(1); continue
        hdr = [h.strip() for h in rows[0]]
        i_who = next(i for i, h in enumerate(hdr) if "身份別" in h)
        i_net = [i for i, h in enumerate(hdr) if "未平倉" in h and "口數" in h and "淨額" in h]
        for r_ in rows[1:]:
            if len(r_) > i_who and "外資" in r_[i_who]:
                res = {"date": d.isoformat(), "contract": "臺股期貨", "foreign_net_oi": int(num(r_[i_net[0]])), "header": hdr[i_net[0]]}
                # 前一交易日
                for j in range(1, 8):
                    pd_ = d - dt.timedelta(days=j)
                    if pd_.weekday() >= 5:
                        continue
                    form2 = urlencode({"queryStartDate": f"{pd_:%Y/%m/%d}", "queryEndDate": f"{pd_:%Y/%m/%d}", "commodityId": "TXF"}).encode()
                    t2 = get("https://www.taifex.com.tw/cht/3/futContractsDateDown", data=form2).decode("big5", "ignore")
                    rows2 = list(csv.reader(io.StringIO(t2)))
                    if len(rows2) < 2 or "身份別" not in "".join(rows2[0]):
                        time.sleep(1); continue
                    for q in rows2[1:]:
                        if len(q) > i_who and "外資" in q[i_who]:
                            res["prev_date"] = pd_.isoformat(); res["prev_net_oi"] = int(num(q[i_net[0]]))
                            break
                    if "prev_net_oi" in res:
                        break
                return res
        raise ValueError(f"TAIFEX 找不到外資列；欄位={hdr}")
    raise ValueError("TAIFEX 近7日無資料")

def intraday_last(symbol, before):
    """Yahoo 日K缺最新一天時的補抓：用 5 天 1 小時K，取當地日期 < before 的最後一根（當地日期, 收盤）。"""
    df = yf_hist(symbol, "5d", "1h", tries=2)
    out = {}
    if df is None:
        return None
    for ts, row in df.iterrows():
        d = ts.date()
        if d >= before or math.isnan(row["Close"]):
            continue
        out[d] = float(row["Close"])
    if not out:
        return None
    d = max(out)
    return d, out[d]


def yf_daily_meta(symbol, period="10d", tries=3):
    """日K＋history_metadata（regularMarketPrice／regularMarketTime＝交易所最新正式收盤）。"""
    import yfinance as yf
    for i in range(tries):
        try:
            t = yf.Ticker(symbol)
            df = t.history(period=period, interval="1d", auto_adjust=False)
            meta = dict(t.history_metadata or {})
            if df is not None and len(df):
                return df, meta
        except Exception:  # noqa
            pass
        time.sleep(3 * (i + 1))
    errors.append(f"{symbol} 1d 取不到")
    return None, {}


def meta_close(meta):
    """metadata → (交易所當地日期, 收盤價)；盤中或欄位缺漏回傳 None。"""
    px, t = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if px is None or t is None or (isinstance(px, float) and math.isnan(px)):
        return None
    tz = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
    if isinstance(t, (int, float)):
        t = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    try:
        t = t.astimezone(tz)
    except Exception:  # noqa
        t = t.tz_convert(tz)
    period = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    end = period.get("end")
    if end is not None and not isinstance(end, (int, float)) and t.date() == end.date() and t < end:
        return None  # 盤中，尚未收盤
    return t.date(), float(px)


def prev_close_meta(symbol):
    import yfinance as yf
    try:
        t = yf.Ticker(symbol)
        t.history(period="1d", interval="1d", auto_adjust=False)
        m = t.history_metadata or {}
        v = m.get("chartPreviousClose") or m.get("previousClose")
        return float(v) if v else None
    except Exception:  # noqa
        return None


def closes(symbol, today, name=None, hourly_fallback=False):
    """收盤序列 [(date, close)]（日期 < 台北今天）。
    Yahoo 日K常缺最新一天（亞股 06:15、美股盤後數小時內都遇過），或最新一根不是正式收盤；
    以 history_metadata 的正式收盤補上／覆蓋。metadata 也拿不到時，才視需要用小時K（不含收盤競價，標記為近似）。
    回傳 (series, source)；source ∈ daily / meta_fill / meta_fix / hourly_approx。"""
    name = name or symbol
    df, meta = yf_daily_meta(symbol)
    dl = daily_closes(df, today)
    mc = meta_close(meta) if meta else None
    if mc and mc[0] < today and dl:
        d, c = mc
        if abs(c / dl[-1][1] - 1) > 0.25:
            errors.append(f"{name} metadata 收盤 {c} 與日K {dl[-1][1]} 差距過大，不採用")
        elif d > dl[-1][0]:
            return dl + [(d, c)], "meta_fill"
        elif d == dl[-1][0] and abs(c / dl[-1][1] - 1) > 0.0005:
            return dl[:-1] + [(d, c)], "meta_fix"
        else:
            return dl, "daily"
    if mc is None and meta:
        # 盤中（例如台北 08:00 後手動重跑，日韓已開盤）：前一交易日正式收盤＝1 天期圖表的 chartPreviousClose，
        # 日期取小時K中今天以前最後一個交易日
        last = intraday_last(symbol, today)
        pc = prev_close_meta(symbol)
        if last and pc and dl and last[0] >= dl[-1][0] and abs(pc / last[1] - 1) < 0.05:
            base = dl if last[0] > dl[-1][0] else dl[:-1]
            return base + [(last[0], pc)], "meta_prev"
    if hourly_fallback and dl:
        last = intraday_last(symbol, today)
        if last and last[0] > dl[-1][0]:
            return dl + [last], "hourly_approx"
    return dl, "daily"


def pair_src(symbol, today, name, digits=2, notes=None, hourly_fallback=False):
    series, src = closes(symbol, today, name, hourly_fallback)
    p = pair(series, name, digits)
    if p and src != "daily":
        p["source"] = src
        if notes is not None:
            msg = {"meta_fill": "日K缺最新一天，以交易所正式收盤補上",
                   "meta_fix": "日K最新一根與正式收盤不符，已改用正式收盤",
                   "meta_prev": "盤中重跑，日K缺前一交易日，以交易所公布的前日收盤補上",
                   "hourly_approx": "日K與正式收盤都取不到，暫用小時K最後一根（不含收盤競價，為近似值）"}[src]
            notes.append(f"{name} {p['date']}：{msg}")
    return p


def prev_business_day_local(d):
    d = d - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d = d - dt.timedelta(days=1)
    return d


def twii_official(today):
    """證交所 OpenAPI MI_INDEX：發行量加權股價指數當日收盤（官方值）。"""
    js = json.loads(get("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX", timeout=60))
    row = next((x for x in js if str(x.get("指數", "")).strip() == "發行量加權股價指數"), None)
    if not row:
        raise ValueError("MI_INDEX 找不到發行量加權股價指數")
    roc = str(row["日期"]).strip()
    d = dt.date(int(roc[:-4]) + 1911, int(roc[-4:-2]), int(roc[-2:]))
    if d >= today:
        raise ValueError(f"MI_INDEX 日期 {d} 不早於今天")
    close, pts, pct = num(row["收盤指數"]), num(row["漲跌點數"]), num(row["漲跌百分比"])
    sign = -1 if str(row.get("漲跌", "")).strip() == "-" else 1
    chg = sign * abs(pts)
    return {"name": "台灣加權指數", "date": d.isoformat(), "close": close, "prev_close": r(close - chg, 2),
            "chg": r(chg, 2), "pct": sign * abs(pct), "source": "twse_mi_index"}


# ---------- 台股籌碼面 ----------
def _bfi82u(d):
    js = json.loads(get(f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={d:%Y%m%d}&response=json"))
    if js.get("stat") != "OK" or not js.get("data"):
        return None
    net = {r_[0]: num(r_[3]) for r_ in js["data"]}
    pick = lambda key: next((v for n, v in net.items() if n.startswith(key)), None)
    return {"foreign": pick("外資及陸資"), "trust": pick("投信")}


def _t86(d):
    js = json.loads(get(f"https://www.twse.com.tw/rwd/zh/fund/T86?date={d:%Y%m%d}&selectType=ALLBUT0999&response=json", timeout=90))
    if js.get("stat") != "OK" or not js.get("data"):
        return None
    f = js["fields"]
    fi, ti = f.index("外陸資買賣超股數(不含外資自營商)"), f.index("投信買賣超股數")
    return {str(x[0]).strip(): (str(x[1]).strip(), num(x[fi]) or 0, num(x[ti]) or 0) for x in js["data"]}


def tw_chips(today, inst, tx):
    """籌碼面：法人連續買賣超天數、個股買賣超前三（金額，排除 ETF）、台積電外資連續天數、外資期貨淨未平倉前日值。
    inst/tx 為 twse_institutional、taifex_foreign_tx 的結果。"""
    if not inst:
        raise ValueError("無三大法人資料")
    d0 = dt.date.fromisoformat(inst["date"])
    out = {"date": inst["date"], "unit": "億元"}

    # 1) 連續天數（BFI82U 從最新交易日往回，同號才累計；最多 40 個交易日）
    sign = {k: (1 if inst[k] > 0 else -1) for k in ("foreign", "trust") if inst.get(k)}
    streak = {k: 0 for k in sign}
    d, tries = d0, 0
    while sign and tries < 70 and max(streak.values(), default=0) < 40:
        if d.weekday() < 5:
            row = _bfi82u(d)
            if d != d0:
                time.sleep(0.4)
            if row is not None:  # None = 休市
                for k in list(sign):
                    v = row.get(k)
                    if v is not None and (1 if v > 0 else -1) == sign[k]:
                        streak[k] += 1
                    else:
                        sign.pop(k)
        d = d - dt.timedelta(days=1); tries += 1
    out["foreign_streak"] = streak.get("foreign", 0) * (1 if (inst.get("foreign") or 0) > 0 else -1)
    out["trust_streak"] = streak.get("trust", 0) * (1 if (inst.get("trust") or 0) > 0 else -1)

    # 2) 個股前三（金額 = 買賣超股數 × 收盤價；排除 ETF 與非 4 碼代號）
    t86 = _t86(d0)
    day = json.loads(get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=90))
    px = {}
    for x in day:
        c = str(x.get("Code", "")).strip()
        p = num(x.get("ClosingPrice"))
        if p:
            px[c] = p
    roc = str(day[0].get("Date", "")).strip() if day else ""
    pday = dt.date(int(roc[:-4]) + 1911, int(roc[-4:-2]), int(roc[-2:])) if len(roc) >= 7 else None
    if pday != d0:  # 收盤價日期不符（例如下午執行時已更新為今日）：改用指定日期的 MI_INDEX 全部個股
        js = json.loads(get(f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={d0:%Y%m%d}&type=ALLBUT0999&response=json", timeout=120))
        px = {}
        for tb in js.get("tables", []):
            f = tb.get("fields") or []
            if "證券代號" in f and "收盤價" in f:
                ic, ip = f.index("證券代號"), f.index("收盤價")
                for x in tb.get("data", []):
                    p = num(x[ip])
                    if p:
                        px[str(x[ic]).strip()] = p
        if not px:
            raise ValueError(f"T86 {d0} 找不到同日收盤價（STOCK_DAY_ALL 為 {pday}）")
    if not t86:
        raise ValueError(f"T86 {d0} 無資料")
    rows = []
    for code, (name, fnet, tnet) in t86.items():
        if len(code) != 4 or code.startswith("00") or code not in px:
            continue
        rows.append({"sym": code, "name": name, "foreign_lots": round(fnet / 1000), "foreign_amt": round(fnet * px[code] / 1e8, 2),
                     "trust_lots": round(tnet / 1000), "trust_amt": round(tnet * px[code] / 1e8, 2)})
    keep = lambda r_, k: {"sym": r_["sym"], "name": r_["name"], "lots": r_[f"{k}_lots"], "amt": r_[f"{k}_amt"]}
    by = lambda k, rev: sorted(rows, key=lambda r_: r_[f"{k}_amt"], reverse=rev)[:3]
    out["foreign_sell_top"] = [keep(x, "foreign") for x in by("foreign", False) if x["foreign_amt"] < 0]
    out["foreign_buy_top"] = [keep(x, "foreign") for x in by("foreign", True) if x["foreign_amt"] > 0]
    out["trust_buy_top"] = [keep(x, "trust") for x in by("trust", True) if x["trust_amt"] > 0]
    out["trust_sell_top"] = [keep(x, "trust") for x in by("trust", False) if x["trust_amt"] < 0]

    # 3) 台積電外資連續買賣超天數（T86 往回最多 25 個交易日）
    tsmc = t86.get("2330")
    if tsmc:
        s0 = 1 if tsmc[1] > 0 else -1
        n, d, tries = 1, d0 - dt.timedelta(days=1), 0
        while n < 25 and tries < 40:
            if d.weekday() < 5:
                t = _t86(d); time.sleep(0.5)
                if t is not None:
                    v = t.get("2330")
                    if not v or (1 if v[1] > 0 else -1) != s0:
                        break
                    n += 1
            d = d - dt.timedelta(days=1); tries += 1
        out["tsmc"] = {"foreign_lots": round(tsmc[1] / 1000), "foreign_amt": round(tsmc[1] * px.get("2330", 0) / 1e8, 2),
                       "trust_lots": round(tsmc[2] / 1000), "foreign_streak": n * s0}

    # 4) 外資台指期淨未平倉：前一交易日值與變化
    if tx:
        out["tx_foreign_net_oi"] = tx["foreign_net_oi"]
        out["tx_prev_net_oi"] = tx.get("prev_net_oi")
        out["tx_chg"] = (tx["foreign_net_oi"] - tx["prev_net_oi"]) if tx.get("prev_net_oi") is not None else None
    return out


# ---------- 開盤前領先指標 ----------
def txf_night(today):
    """期交所盤後交易（夜盤，台北 15:00–05:00）臺股期貨近月：最後成交價、較前一日結算漲跌。交易日 = today。"""
    import re
    url = ("https://www.taifex.com.tw/cht/3/futDailyMarketReport?queryType=2&marketCode=1&dateaddcnt=0"
           f"&commodity_id=TX&queryDate={today:%Y/%m/%d}")
    html = get(url, timeout=60).decode("utf-8", "ignore")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    for tr in rows:
        cells = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", "").strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) >= 8 and cells[0] == "TX" and re.fullmatch(r"\d{6}", cells[1]):
            last, chg, pct = num(cells[5]), cells[6], cells[7]
            if last is None:
                continue
            sgn = -1 if "-" in chg or "▼" in chg else 1
            chg_v, pct_v = num(re.sub(r"[^\d.]", "", chg)), num(re.sub(r"[^\d.]", "", pct))
            return {"name": "台指期夜盤", "contract": cells[1], "trade_date": today.isoformat(), "last": last,
                    "chg": sgn * (chg_v or 0), "pct": sgn * (pct_v or 0), "volume": num(cells[8]),
                    "note": "最後成交價，較前一日一般交易時段結算價"}
    raise ValueError("期交所盤後行情找不到 TX 近月列（可能尚未更新或休市）")


def preopen(today, tx_night=None):
    """開盤前領先指標：台積電 ADR、CME 日經期貨（美元）、台指期夜盤。"""
    out = {}
    p = pair_src("TSM", today, "台積電ADR", 2)
    if p:
        out["TSM"] = p
    # CME 日經期貨：metadata 是即時成交價而非結算價，維持日K
    p = pair(daily_closes(yf_hist("NKD=F", "10d", "1d"), today), "日經期貨（CME）", 2)
    if p:
        out["NKD=F"] = p
    if tx_night:
        out["TXF_NIGHT"] = tx_night
    return out


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


# ---------- 固定行事曆（央行利率決策、結算日、MSCI）----------
# 來源：BoJ、ECB、BoE、MSCI 官網公布的年度日程（2026/11/10 核對）；台灣央行理監事會由排程依官網公告補入
BOJ = ["2026-01-23", "2026-03-19", "2026-04-28", "2026-06-16", "2026-07-31", "2026-09-18", "2026-10-30", "2026-12-18",
       "2027-01-22", "2027-03-18", "2027-04-28", "2027-06-11", "2027-07-22", "2027-09-22", "2027-10-29", "2027-12-17"]
ECB = ["2026-12-17", "2027-02-04", "2027-03-18", "2027-04-29", "2027-06-10", "2027-07-22", "2027-09-09", "2027-10-28", "2027-12-16"]
BOE = ["2026-11-05", "2026-12-17", "2027-02-04", "2027-03-18", "2027-04-29", "2027-06-17", "2027-07-29", "2027-09-16",
       "2027-11-04", "2027-12-16"]
MSCI = [("2026-11-11", "2026-12-01"), ("2027-02-09", "2027-03-01"), ("2027-05-10", "2027-05-28"), ("2027-08-12", "2027-09-01"),
        ("2027-11-11", "2027-12-01"), ("2028-02-10", "2028-03-01"), ("2028-05-11", "2028-06-01"), ("2028-08-14", "2028-09-01")]


def nth_weekday(y, m, weekday, n):
    d = dt.date(y, m, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def prev_business_day(d):
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def fixed_events(today, back=7, ahead=14):
    """固定行事曆：類別一律為「總經與市場」。taipei 為台北時間（日期 YYYY-MM-DD、時刻 HH:MM 或文字）。"""
    lo, hi = today - dt.timedelta(days=back), today + dt.timedelta(days=ahead)
    ev = []

    def at(day, hm, tz):
        t = dt.datetime.combine(day, dt.time(*hm), tz).astimezone(TPE)
        return t.date(), t.strftime("%H:%M")

    def add(d, t, title, note=""):
        if lo <= d <= hi:
            ev.append({"date": d.isoformat(), "time": t, "cat": "總經與市場", "title": title, "note": note})

    for x in FOMC:
        add(*at(x, (14, 0), NY), "FOMC利率決策", "聲明與主席記者會（記者會 14:30 ET）")
    for s in BOJ:
        add(dt.date.fromisoformat(s), "午間", "日銀利率決策", "公布時間不固定，通常台北 11:00–13:00；總裁記者會 14:30 JST")
    for s in ECB:
        add(*at(dt.date.fromisoformat(s), (14, 15), ZoneInfo("Europe/Berlin")), "歐洲央行利率決策", "記者會 14:45 CET")
    for s in BOE:
        add(*at(dt.date.fromisoformat(s), (12, 0), LDN), "英國央行利率決策", "")
    for a, e in MSCI:
        a, e = dt.date.fromisoformat(a), dt.date.fromisoformat(e)
        add(a + dt.timedelta(days=1), "清晨", "MSCI季度調整結果公布", f"美東 {a:%m/%d} 盤後公布；{e:%m/%d} 生效")
        add(prev_business_day(e), "收盤", "MSCI季度調整生效（今日收盤換股）", "被動資金於收盤集中交易")
    y, m = lo.year, lo.month
    for _ in range(3):
        quarter = m in (3, 6, 9, 12)
        add(nth_weekday(y, m, 2, 3), "13:30", "台股四巫日（台指期、台指選擇權、個股期貨、個股選擇權季月同步結算）" if quarter else "台指期月結算", "")
        fri = nth_weekday(y, m, 4, 3)
        add(fri, "美股收盤", "美股四巫日（季度期貨與選擇權同步到期）" if quarter else "美股月選擇權到期", "收盤前後成交量與波動放大")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return sorted(ev, key=lambda e: (e["date"], e["time"]))


# ---------- 指數貢獻度（動態權值股）----------
# 名單每月更新一次存 data/universe.json；貢獻度每天以當日價格計算。
DOW_FALLBACK = ["AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "GS", "HD", "HON", "IBM", "JNJ",
                "JPM", "KO", "MCD", "MMM", "MRK", "MSFT", "NKE", "NVDA", "PG", "SHW", "TRV", "UNH", "V", "VZ", "WMT"]
ZH = {"AAPL": "蘋果", "AMGN": "安進", "AMZN": "亞馬遜", "AXP": "美國運通", "BA": "波音", "CAT": "開拓重工", "CRM": "Salesforce",
      "CSCO": "思科", "CVX": "雪佛龍", "DIS": "迪士尼", "GS": "高盛", "HD": "家得寶", "HON": "漢威聯合", "IBM": "IBM",
      "JNJ": "嬌生", "JPM": "摩根大通", "KO": "可口可樂", "MCD": "麥當勞", "MMM": "3M", "MRK": "默克", "MSFT": "微軟",
      "NKE": "Nike", "NVDA": "輝達", "PG": "寶僑", "SHW": "宣偉", "TRV": "旅行家保險", "UNH": "聯合健康", "V": "Visa",
      "VZ": "威訊", "WMT": "沃爾瑪", "INTC": "英特爾", "AVGO": "博通", "META": "Meta", "GOOGL": "Alphabet", "TSLA": "特斯拉"}


def load_universe(today):
    path = "data/universe.json"
    u = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    if u.get("month") == today.strftime("%Y-%m"):
        return u
    import re
    new = {"month": today.strftime("%Y-%m"), "updated": today.isoformat()}
    try:
        html_ = get("https://www.slickcharts.com/dowjones").decode("utf-8", "ignore")
        etf = {"SPY", "QQQ", "DIA", "IWM", "VOO", "VTI"}
        syms = [x for x in dict.fromkeys(re.findall(r'href="/symbol/([A-Z.]+)"', html_)) if x not in etf]
        if len(syms) != 30:
            raise ValueError(f"解析到 {len(syms)} 檔")
        new["dow"], new["dow_source"] = syms, "slickcharts"
    except Exception as e:  # noqa
        new["dow"], new["dow_source"] = u.get("dow") or DOW_FALLBACK, "previous_or_fallback"
        errors.append(f"道瓊成分股名單更新失敗，沿用舊名單：{e}")
    json.dump(new, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return new


def rank(rows, n=5):
    rows = [r for r in rows if r["pts"] is not None]
    up = sorted([r for r in rows if r["pts"] > 0], key=lambda r: -r["pts"])[:n]
    dn = sorted([r for r in rows if r["pts"] < 0], key=lambda r: r["pts"])[:n]
    return up, dn


def dow_contrib(today, idx, universe):
    """道瓊：價格加權，除數＝前收價總和÷前日指數；貢獻點數＝股價變動÷除數。
    每檔成分股的收盤日必須等於指數收盤日，否則排除（11/13 曾因個股日K落後一天，排行用到前一天的漲跌）。"""
    rows, prev_sum, stale = [], 0.0, []
    for s in universe["dow"]:
        ser, src_ = closes(s, today, s)
        p = pair(ser, s, 2)
        if not p:
            continue
        if p["date"] != idx["date"]:
            stale.append(f"{s}({p['date']})"); continue
        rows.append({"sym": s, "name": ZH.get(s, s), "pct": p["pct"], "chg": p["chg"], "prev": p["prev_close"]})
        prev_sum += p["prev_close"]
    if len(rows) < 28:
        raise ValueError(f"道瓊成分股只取到 {len(rows)} 檔與指數同日（{idx['date']}）；日期不符：{', '.join(stale) or '無'}")
    prev_index = idx["close"] - idx["chg"]
    div = prev_sum / prev_index
    for r in rows:
        r["pts"] = round(r["chg"] / div, 2)
    implied = round(sum(r["pts"] for r in rows), 2)
    if abs(implied - idx["chg"]) > max(15, abs(idx["chg"]) * 0.15):
        DIAG["dow"] = {"index": idx, "divisor": div, "rows": [{k: r[k] for k in ("sym", "prev", "chg", "pct", "pts")} for r in rows]}
        raise ValueError(f"道瓊貢獻合計 {implied} 與指數漲跌 {idx['chg']} 差距過大，不輸出")
    up, dn = rank(rows)
    keep = lambda r: {k: r[k] for k in ("sym", "name", "pct", "pts")}
    return {"date": idx["date"], "method": "price_weighted_divisor", "divisor": round(div, 6), "n": len(rows),
            "excluded_stale": stale, "index_chg": idx["chg"], "implied_chg": implied,
            "top_up": [keep(r) for r in up], "top_down": [keep(r) for r in dn]}


def twse_contrib(today, idx):
    """台股加權：證交所 OpenAPI 全部上市股收盤與漲跌 × 已發行普通股數；貢獻點數＝前日市值權重×漲跌幅×前日指數。"""
    day = json.loads(get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=60))
    info = json.loads(get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=60))
    if not day or not info:
        raise ValueError("證交所 OpenAPI 回傳空資料")
    k = lambda d, *words: next((key for key in d if all(w in key for w in words)), None)
    kc, kn, ks = k(info[0], "公司代號"), k(info[0], "公司簡稱"), k(info[0], "已發行普通股數")
    if not (kc and ks):
        raise ValueError(f"t187ap03_L 欄位找不到；欄位={list(info[0])}")
    shares = {str(x[kc]).strip(): (num(x[ks]), str(x.get(kn) or "").strip()) for x in info}
    ds = {str(x.get("Date", "")).strip() for x in day[:50] if x.get("Date")}
    if ds:
        roc = max(ds)
        if roc.isdigit() and len(roc) == 7:
            d = dt.date(int(roc[:3]) + 1911, int(roc[3:5]), int(roc[5:]))
            if d.isoformat() != idx["date"]:
                raise ValueError(f"STOCK_DAY_ALL 日期 {d} 與加權指數 {idx['date']} 不同")
    rows, cap_prev = [], 0.0
    for x in day:
        code = str(x.get("Code", "")).strip()
        if code not in shares or not shares[code][0]:
            continue
        close, chg = num(x.get("ClosingPrice")), num(x.get("Change"))
        if close is None or chg is None:
            continue
        prev = close - chg
        if prev <= 0:
            continue
        cap = shares[code][0] * prev
        cap_prev += cap
        rows.append({"sym": code, "name": shares[code][1] or str(x.get("Name", "")).strip(), "pct": round(chg / prev * 100, 2),
                     "cap": cap, "ret": chg / prev})
    if len(rows) < 500:
        raise ValueError(f"上市個股只對到 {len(rows)} 檔")
    prev_index = idx["close"] - idx["chg"]
    for r in rows:
        r["pts"] = round(r["cap"] / cap_prev * r["ret"] * prev_index, 2)
        r["weight"] = round(r["cap"] / cap_prev * 100, 2)
    implied = round(sum(r["pts"] for r in rows), 2)
    up, dn = rank(rows)
    keep = lambda r: {kk: r[kk] for kk in ("sym", "name", "pct", "pts", "weight")}
    top_w = sorted(rows, key=lambda r: -r["weight"])[:10]
    return {"date": idx["date"], "method": "cap_weighted_issued_shares", "n": len(rows), "index_chg": idx["chg"],
            "implied_chg": implied, "top_up": [keep(r) for r in up], "top_down": [keep(r) for r in dn],
            "top_weights": [{"sym": r["sym"], "name": r["name"], "weight": r["weight"]} for r in top_w]}


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
           "indices": {}, "ust10y": None, "sse": None, "ust_curve": None, "stocks": {}, "macro": {}, "fedwatch": None, "us_macro_fred": None, "us_calendar": None, "errors": errors, "notes": []}

    expected = prev_business_day_local(today)  # 亞股最新應有的收盤日（不含休市）
    for s, n in INDICES.items():
        p = pair_src(s, today, n, 2, out["notes"], hourly_fallback=s in ("^N225", "^KS11", "^TWII"))
        if p:
            if s in ("^N225", "^KS11") and p["date"] < expected.isoformat():
                out["notes"].append(f"{n} 最新收盤日 {p['date']} 早於預期 {expected}（休市或資料延遲）")
            out["indices"][s] = p
    try:
        tw = twii_official(today)
        y = out["indices"].get("^TWII")
        tw["prev_date"] = y["date"] if y and y["date"] < tw["date"] else (y["prev_date"] if y and y["date"] == tw["date"] else None)
        if y and y["date"] == tw["date"] and abs(y["close"] - tw["close"]) > 1:
            out["notes"].append(f"台灣加權 Yahoo {y['close']} 與證交所 {tw['close']} 不符，採證交所")
        out["indices"]["^TWII"] = tw
    except Exception as e:  # noqa
        errors.append(f"證交所加權指數取不到，改用 Yahoo：{e}")
    tnx = daily_closes(yf_hist("^TNX", "10d", "1d"), today)
    if len(tnx) >= 2:
        f = (lambda v: v / 10) if tnx[-1][1] > 20 else (lambda v: v)
        y1, y0 = f(tnx[-1][1]), f(tnx[-2][1])
        out["ust10y"] = {"date": tnx[-1][0].isoformat(), "yield": r(y1, 3), "prev": r(y0, 3),
                         "bp": int(round((y1 - y0) * 100))}
    p = pair_src("000001.SS", today, "上證綜合", 2, out["notes"])
    if p:
        out["sse"] = p
    try:
        out["ust_curve"] = treasury_curve(today)
        c10 = out["ust_curve"]["y10"]
        out["ust10y"] = {"date": out["ust_curve"]["date"], "yield": c10["yield"], "bp": c10["bp"], "source": "treasury"}
    except Exception as e:  # noqa
        errors.append(f"美債殖利率曲線（財政部）取不到，10年期改用 ^TNX：{e}")
        if out["ust10y"]:
            out["ust10y"]["source"] = "yahoo_tnx"

    # 官方／交易所 API（各自獨立，失敗只記錄在 errors）
    for key, fn in (("twd_official", twd_official), ("ust_auctions", ust_auctions),
                    ("tw_institutional", twse_institutional), ("taifex_foreign_tx", taifex_foreign_tx)):
        try:
            out[key] = fn(today)
        except Exception as e:  # noqa
            out[key] = None
            errors.append(f"{key} 取不到：{e}")
    try:
        out["tw_chips"] = tw_chips(today, out.get("tw_institutional"), out.get("taifex_foreign_tx"))
    except Exception as e:  # noqa
        out["tw_chips"] = None
        errors.append(f"tw_chips 取不到：{e}")
    try:
        night = txf_night(today)
    except Exception as e:  # noqa
        night = None
        errors.append(f"台指期夜盤取不到：{e}")
    try:
        out["preopen"] = preopen(today, night)
    except Exception as e:  # noqa
        out["preopen"] = None
        errors.append(f"preopen 取不到：{e}")
    for s in STOCKS:
        p = pair_src(s, today, s, 2)
        if p:
            out["stocks"][s] = {"date": p["date"], "close": p["close"], "pct": p["pct"]}
            if p.get("source"):
                out["stocks"][s]["source"] = p["source"]

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
        out["us_macro_fred"], out["us_calendar"] = fred.build(now, errors=errors)
    except Exception as ex:  # noqa
        errors.append(f"FRED 失敗：{ex}")

    out["contributors"] = {}
    try:
        universe = load_universe(today)
    except Exception as ex:  # noqa
        universe = {"dow": DOW_FALLBACK}
        errors.append(f"universe 讀取失敗：{ex}")
    for sym, fn in (("^DJI", lambda i: dow_contrib(today, i, universe)), ("^TWII", lambda i: twse_contrib(today, i))):
        idx = out["indices"].get(sym)
        if not idx:
            continue
        try:
            out["contributors"][sym] = fn(idx)
        except Exception as ex:  # noqa
            errors.append(f"contributors {sym} 失敗：{ex}")

    try:
        out["fixed_events"] = fixed_events(today)
    except Exception as ex:  # noqa
        out["fixed_events"] = None
        errors.append(f"fixed_events 失敗：{ex}")

    if DIAG:
        out["diag"] = DIAG
    for path in ("data/latest.json", f"data/{today.isoformat()}.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: (len(v) if isinstance(v, dict) else v) for k, v in out.items() if k != "errors"},
                     ensure_ascii=False))
    print("errors:", errors)


if __name__ == "__main__":
    main()
