# -*- coding: utf-8 -*-
"""產業板塊（11/26 新增）
- 美股：SPDR 11 大產業 ETF ＋ 細分產業 ETF（Yahoo 正式收盤，沿用 fetch.closes）
- 台股官方：證交所 OpenAPI MI_INDEX 的「類指數」（排除報酬指數、槓桿／反向、大類合併指數）
- 台股自編族群：docs/sector_baskets.json 成分股 × 證交所／櫃買中心當日收盤
  只算當日報酬（不維護點位），所以不受除權息、換股、基期影響。
  市值加權＝Σ(前日市值×漲跌幅)/Σ前日市值；等權＝成分股漲跌幅平均；廣度＝上漲家數/有效家數。
  上市股數取 t187ap03_L「已發行普通股數」；上櫃股數取櫃買中心收盤行情的 Capitals 欄（實測為發行股數，例：雙鴻 93,661,403 股、世界 1,878,502,192 股）。
"""
import json, datetime as dt

US_SECTORS = [("XLK", "科技"), ("XLC", "通訊服務"), ("XLY", "非必需消費"), ("XLP", "必需消費"), ("XLF", "金融"), ("XLV", "醫療保健"),
              ("XLI", "工業"), ("XLE", "能源"), ("XLB", "原物料"), ("XLU", "公用事業"), ("XLRE", "不動產")]
US_SUB = [("SOXX", "半導體"), ("IGV", "軟體"), ("KRE", "區域銀行"), ("XBI", "生技"), ("ITA", "航太國防")]

# 大類合併指數（與細類重複）不列入熱力格
TW_SKIP = {"水泥窯製類指數", "塑膠化工類指數", "機電類指數", "化學生技醫療類指數", "電子工業類指數"}
TW_SHORT = {"電腦及週邊設備": "電腦週邊"}
TW_HEAD = ("電子工業類指數", "金融保險類指數", "未含金融電子指數")


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("+", "").strip())
    except Exception:  # noqa
        return None


def _roc(s):
    s = str(s).strip()
    return dt.date(int(s[:-4]) + 1911, int(s[-4:-2]), int(s[-2:]))


def us_sectors(today, pair_src, notes):
    def one(sym, name):
        p = pair_src(sym, today, name, 2, notes)
        return {"sym": sym, "name": name, "close": p["close"], "pct": p["pct"], "date": p["date"]} if p else None
    main = [x for x in (one(*a) for a in US_SECTORS) if x]
    sub = [x for x in (one(*a) for a in US_SUB) if x]
    if len(main) < 9:
        raise ValueError(f"美股產業 ETF 只取到 {len(main)} 檔")
    return {"date": max(x["date"] for x in main), "source": "yahoo_spdr_etf", "main": main, "sub": sub}


def tw_official(mi_index, today):
    rows, head, d = [], [], None
    for x in mi_index:
        n = str(x.get("指數", "")).strip()
        if "報酬" in n or "兩倍" in n or "反向" in n:
            continue
        sign = -1 if str(x.get("漲跌", "")).strip() == "-" else 1
        pct, close = _num(x.get("漲跌百分比")), _num(x.get("收盤指數"))
        if pct is None:
            continue
        nm = n.replace("類指數", "").replace("指數", "")
        rec = {"name": TW_SHORT.get(nm, nm), "close": close, "pct": round(sign * abs(pct), 2)}
        if n in TW_HEAD:
            head.append(rec)
        if n.endswith("類指數") and n not in TW_SKIP:
            rows.append(rec)
            d = d or _roc(x["日期"])
    if len(rows) < 25:
        raise ValueError(f"MI_INDEX 類股指數只對到 {len(rows)} 個")
    if d >= today:
        raise ValueError(f"MI_INDEX 日期 {d} 不早於今天")
    rows.sort(key=lambda r: -r["pct"])
    head.sort(key=lambda r: [TW_SHORT.get(h, h) for h in (x.replace("類指數", "").replace("指數", "") for x in TW_HEAD)].index(r["name"]))
    return {"date": d.isoformat(), "source": "twse_mi_index", "sectors": rows, "head": head}


def stock_table(day_all, info, tpex):
    """{代號: (名稱, 前日收盤, 漲跌幅%, 前日市值)}；上市＋上櫃"""
    k = lambda d, *w: next((key for key in d if all(x in key for x in w)), None)
    kc, kn, ks = k(info[0], "公司代號"), k(info[0], "公司簡稱"), k(info[0], "已發行普通股數")
    shares = {str(x[kc]).strip(): (_num(x[ks]), str(x.get(kn) or "").strip()) for x in info}
    out, dates = {}, set()
    for x in day_all:
        c = str(x.get("Code", "")).strip()
        close, chg = _num(x.get("ClosingPrice")), _num(x.get("Change"))
        if c not in shares or close is None or chg is None or close - chg <= 0:
            continue
        prev = close - chg
        out[c] = ((shares[c][1] or str(x.get("Name", "")).strip()).rstrip("*"), prev, chg / prev * 100, (shares[c][0] or 0) * prev)
        if x.get("Date"):
            dates.add(_roc(x["Date"]))
    for x in tpex or []:
        c = str(x.get("SecuritiesCompanyCode", "")).strip()
        close, chg, cap = _num(x.get("Close")), _num(x.get("Change")), _num(x.get("Capitals"))
        if not c or c in out or close is None or chg is None or close - chg <= 0:
            continue
        prev = close - chg
        out[c] = (str(x.get("CompanyName", "")).strip(), prev, chg / prev * 100, (cap or 0) * prev)
        if x.get("Date"):
            dates.add(_roc(x["Date"]))
    return out, (max(dates).isoformat() if dates else None)


def baskets(cfg, table, date):
    res, missing = [], []
    for b in cfg["baskets"]:
        mem = [(c, table[c]) for c in b["codes"] if c in table]
        missing += [f'{b["name"]}:{c}' for c in b["codes"] if c not in table]
        if not mem:
            continue
        cap = sum(v[3] for _, v in mem)
        cw = sum(v[3] * v[2] for _, v in mem) / cap if cap else None
        ew = sum(v[2] for _, v in mem) / len(mem)
        up = sum(1 for _, v in mem if v[2] > 0)
        srt = sorted(mem, key=lambda m: -m[1][2])
        lead = lambda m: {"sym": m[0], "name": m[1][0], "pct": round(m[1][2], 2)}
        res.append({"name": b["name"], "cap_w": round(cw, 2) if cw is not None else None, "eq_w": round(ew, 2), "up": up, "n": len(mem),
                    "best": lead(srt[0]), "worst": lead(srt[-1]),
                    "members": [{"sym": c, "name": v[0], "pct": round(v[2], 2), "w": round(v[3] / cap * 100, 1) if cap else None} for c, v in mem]})
    res.sort(key=lambda r: -(r["cap_w"] if r["cap_w"] is not None else r["eq_w"]))
    return {"date": date, "method": "cap_weighted_prev_close; otc_shares=tpex_capitals", "baskets": res, "missing": missing}


def build(today, get, pair_src, notes, errors, basket_path="docs/sector_baskets.json"):
    out = {}
    try:
        out["us"] = us_sectors(today, pair_src, notes)
    except Exception as ex:  # noqa
        errors.append(f"美股產業 ETF 失敗：{ex}")
    try:
        mi = json.loads(get("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX", timeout=60))
        out["tw"] = tw_official(mi, today)
    except Exception as ex:  # noqa
        errors.append(f"台股類股指數失敗：{ex}")
    try:
        day = json.loads(get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=60))
        info = json.loads(get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=60))
        try:
            tpex = json.loads(get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", timeout=90))
        except Exception as ex:  # noqa
            tpex = None
            errors.append(f"櫃買中心收盤失敗，自編族群只含上市股：{ex}")
        table, d = stock_table(day, info, tpex)
        if d and d >= today.isoformat():
            raise ValueError(f"個股收盤日期 {d} 不早於今天")
        if out.get("tw") and d and d != out["tw"]["date"]:
            raise ValueError(f"個股收盤日期 {d} 與類股指數 {out['tw']['date']} 不同")
        out["baskets"] = baskets(json.load(open(basket_path, encoding="utf-8")), table, d)
        if out["baskets"]["missing"]:
            notes.append("自編族群缺成分股：" + "、".join(out["baskets"]["missing"]))
    except Exception as ex:  # noqa
        errors.append(f"台股自編族群失敗：{ex}")
    return out
