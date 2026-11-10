# -*- coding: utf-8 -*-
"""Daily market digest: data.json -> email.html + email.txt, then format/arithmetic checks.
Usage: python3 digest_template.py data.json   (exit code 1 if any check fails)"""
import json, re, sys, html, datetime as dt

F_JH = "font-family:Microsoft JhengHei,Arial,sans-serif"
F_AP = "font-family:Aptos,Arial,sans-serif"
LINK = "color:#164A73;text-decoration:underline;font-weight:bold"
D = json.load(open(sys.argv[1], encoding="utf-8"))
esc = lambda s: html.escape(s, quote=False)


def p_title(n, t, u):
    return (f'<p style="{F_JH};font-size:11pt;font-weight:bold;line-height:1.4;margin:15px 0 4px">{n}. '
            f'<a href="{html.escape(u)}" style="{LINK}">{esc(t)}</a></p>')


def p_body(t):
    return f'<p style="{F_JH};font-size:11pt;color:#000;line-height:1.6;margin:0 0 11px">{esc(t)}</p>'


def h2(t, m="22px 0 10px"):
    return f'<h2 style="{F_JH};font-size:11pt;font-weight:bold;color:#000;margin:{m}">{esc(t)}</h2>'


def cell(tag, c, bg, hdr=False, align="center"):
    return (f'<{tag} style="{F_AP};font-size:11pt;text-align:{align};vertical-align:middle;border:1px solid #D9D9D9;'
            f'padding:9px 7px;overflow-wrap:break-word;background-color:{bg};color:{"#FFFFFF" if hdr else "#000000"};'
            f'font-weight:{"bold" if hdr else "normal"}">{c}</{tag}>')


def table(hdrs, widths, rows, left=()):
    o = ['<table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;table-layout:fixed;margin:9px 0 12px">',
         "<colgroup>" + "".join(f'<col style="width:{w}">' for w in widths) + "</colgroup>",
         "<tr>" + "".join(cell("th", esc(h), "#243B53", True) for h in hdrs) + "</tr>"]
    for i, r in enumerate(rows):
        o.append("<tr>" + "".join(cell("td", c, "#FFFFFF" if i % 2 == 0 else "#F2F6F9", align="left" if j in left else "center") for j, c in enumerate(r)) + "</tr>")
    return "".join(o) + "</table>"


# 名稱欄：括號說明一律換到下一行，例如「黃金<br>（COMEX近月期貨）」
brk = lambda s: esc(s).replace("（", "<br>（", 1) if "（" in s[1:] else esc(s)
sgn = lambda v: "+" if v > 0 else ("−" if v < 0 else "")
pts = lambda v: f"{sgn(v)}{abs(v):,.2f}點"
pct = lambda v: f"{sgn(v)}{abs(v):.2f}%"
lbl = lambda d: f"({d}市場收盤)"
MACRO = ["美元兌新台幣", "布蘭特原油", "黃金（COMEX近月期貨）", "美元指數"]
SRC = re.compile(r"[（(][^）)]*(路透|中央社|鉅亨|經濟日報|株探|CNBC|Reuters|Yahoo|investingLive|Kitco|AP|口徑|來源)[^）)]*[）)]")
STK = re.compile(r"[一-鿿A-Za-z]+（[+−]\d+\.\d{2}%）")

SHORT = {"道瓊工業指數": "道瓊", "標準普爾500指數": "標普500", "那斯達克綜合指數": "那斯達克", "費城半導體指數": "費城半導體",
         "日經225指數": "日經225", "韓國綜合股價指數": "韓國綜合", "台灣加權指數": "台灣加權"}
SCALE = {"美元兌新台幣": 1, "布蘭特原油": 5, "黃金（COMEX近月期貨）": 3, "美元指數": 1}
HIKE, HIKE2, HOLD, CUT = "#DC2626", "#7F1D1D", "#94A3B8", "#15803D"


def heat_color(v, m):
    if v is None or v == 0: return "#E5E7EB", "#1F2937"
    t = min(abs(v) / m, 1)
    a, b = ((253, 226, 226), (185, 28, 28)) if v > 0 else ((220, 242, 232), (21, 128, 86))
    c = tuple(int(a[i] + (b[i] - a[i]) * (0.25 + 0.75 * t)) for i in range(3))
    return "#%02X%02X%02X" % c, ("#FFFFFF" if t > 0.45 else "#1F2937")


def heatmap(title, tiles):
    """tiles: [(名稱, 最新值, 主數字, 數值或None, 色階上限, 註記)]；紅漲綠跌，一列4格"""
    out = [h2(title, "10px 0 4px"), '<table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;table-layout:fixed;margin:0"><tr>']
    for n, lv, big, v, m, nt in tiles:
        bg, fg = heat_color(v, m)
        out.append(f'<td bgcolor="{bg}" style="background-color:{bg};color:{fg};text-align:center;vertical-align:middle;border:2px solid #FFFFFF;padding:7px 4px">'
                   f'<div style="{F_JH};font-size:10.5pt;font-weight:bold">{esc(n)}</div>'
                   f'<div style="{F_AP};font-size:10pt;margin-top:2px">{esc(lv) if lv else "&nbsp;"}</div>'
                   f'<div style="{F_AP};font-size:15pt;font-weight:bold;line-height:1.25">{esc(big)}</div>'
                   f'<div style="{F_JH};font-size:9pt">{esc(nt) if nt else "&nbsp;"}</div></td>')
    return "".join(out) + "</tr></table>"


def bp_value(s):
    m = re.search(r"([+−-]?)(\d+(?:\.\d+)?)bp", s)
    return 0 if not m else (-1 if m.group(1) in "−-" and m.group(1) else 1) * float(m.group(2))


def idx_tile(n, c, ch, pc):
    return (SHORT[n], f"{c:,.2f}", pct(pc), pc, 6, f"{sgn(ch)}{abs(ch):,.2f} 點")


def us_tiles():
    return [idx_tile(*r[:4]) for r in D["index_rows"][:4]]


def asia_tiles():
    R = {r[0]: r for r in D["index_rows"]}
    t = [idx_tile(*R[n][:4]) for n in ("台灣加權指數", "日經225指數", "韓國綜合股價指數")]
    se = D.get("sse")
    return t + [("上證綜合", f"{se[0]:,.2f}", pct(se[2]), se[2], 6, f"{sgn(se[1])}{abs(se[1]):,.2f} 點") if se else ("上證綜合", "", "未取得", None, 6, "")]


def ust_tiles():
    def note(b): return "殖利率上升" if b > 0 else ("殖利率下降" if b < 0 else "殖利率持平")
    def tile(n, q):
        return (n, f"{q[0]:.2f}%", f"{sgn(q[1])}{abs(q[1]):g}bp", q[1], 15, note(q[1])) if q else (n, "", "未取得", None, 15, "")
    lv, bp, _n, _r, _d = D["ust"]
    y10 = [float(lv.rstrip("%")), bp_value(bp)]
    c = D.get("curve") or {}
    y2, y30 = c.get("y2"), c.get("y30")
    t = [tile("2年期", y2), tile("10年期", y10), tile("30年期", y30)]
    if y2:
        sp, dif = round((y10[0] - y2[0]) * 100), y10[1] - y2[1]
        nt = f"擴大 {dif:g}bp，曲線趨陡" if dif > 0 else (f"收窄 {abs(dif):g}bp，曲線趨平" if dif < 0 else "利差持平")
        t.append(("10Y−2Y 利差", "", f"{sp}bp", None, 15, nt))
    else:
        t.append(("10Y−2Y 利差", "", "未取得", None, 15, ""))
    return t


def macro_tiles():
    M = {m[0]: m for m in D["macro_rows"]}
    out = []
    for n in ("美元指數", "美元兌新台幣", "布蘭特原油", "黃金（COMEX近月期貨）"):
        _n, lv, ch, nt, r, a, d = M[n]
        name = "黃金（COMEX）" if n.startswith("黃金") else n
        if not a:
            out.append((name, "", "未取得", None, SCALE[n], ""))
            continue
        lvl = lv.split("/")[0].replace("美元", " 美元")
        sub = nt or (D.get("brent_note") if n == "布蘭特原油" else None) or f"{sgn(a[1])}{abs(a[1]):,.2f} 美元"
        out.append((name, lvl, pct(a[2]), a[2], SCALE[n], sub))
    return out


def fedwatch():
    fw = D["fedwatch"]
    rows = []
    for label, cut, hold, h1, h2_ in fw["rows"]:
        segs = "".join(f'<td width="{p:g}%" height="22" bgcolor="{c}" style="background-color:{c};width:{p:g}%;height:22px;color:#FFFFFF;{F_AP};font-size:9.5pt;text-align:center;font-weight:bold">'
                       f'<font color="#FFFFFF">{(f"{p:g}%") if p >= 8 else "&nbsp;"}</font></td>'
                       for p, c in ((cut, CUT), (hold, HOLD), (h1, HIKE), (h2_, HIKE2)) if p > 0)
        rows.append(f'<tr><td width="16%" nowrap style="{F_JH};font-size:10.5pt;padding:4px 8px 4px 0;width:16%;white-space:nowrap;{"font-weight:bold" if label == "最新" else ""}">{esc(label)}</td>'
                    f'<td style="padding:4px 0"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;border-collapse:collapse;table-layout:fixed"><tr>{segs}</tr></table></td></tr>'
                    '<tr><td colspan="2" height="6" style="height:6px;font-size:1px;line-height:1px">&nbsp;</td></tr>')
    # 圖例用表格＋彩色「■」字元：不依賴 inline-block 尺寸，轉寄或整頁複製時不會跑版
    legend = ('<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;margin:6px 0 4px"><tr>' +
              "".join(f'<td nowrap style="{F_JH};font-size:9.5pt;color:#374151;padding:0 14px 0 0;white-space:nowrap">'
                      f'<font color="{c}"><span style="color:{c};font-size:11pt">■</span></font>&nbsp;{n}&nbsp;&nbsp;&nbsp;&nbsp;</td>'
                      for n, c in (("降息", CUT), ("維持不變", HOLD), ("升息1碼", HIKE), ("升息2碼以上", HIKE2))) + "</tr></table>")
    return (h2("FedWatch 利率預期") +
            f'<p style="{F_JH};font-size:11pt;margin:0 0 6px">{esc(fw["meeting"])} FOMC 會議｜目前利率區間 {esc(fw["range"])}｜CME {esc(fw["asof"])} 更新（依前一日期貨結算）</p>'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
            f'{legend}'
            f'<p style="{F_JH};font-size:11pt;line-height:1.6;margin:4px 0 12px">{esc(fw["note"])}</p>')


def us_macro():
    um = D.get("us_macro")
    if not um or not um.get("rows"): return ""
    rows = [[brk(n), f"<b>{esc(a)}</b>", esc(e), esc(p), esc(df), esc(rd)] for n, a, e, p, df, rd in um["rows"]]
    return h2(f"美國總經數據（{um['date']} 發布）") + table(["指標", "實際", "預期", "前值", "與預期差", "解讀"], ["24%", "10%", "10%", "10%", "14%", "32%"], rows, left=(5,))


# ---------- 未來關注事件：日曆（以天為欄；週五＝今天＋週六到下週五，其餘＝本週一到週五）----------
CAT = {"總經與市場": "#1D4ED8", "政策公布": "#7C3AED", "法說／財報": "#C2410C", "產品發布": "#15803D"}
WD = "一二三四五六日"
CAT_SHORT = {"總經與市場": "總經", "政策公布": "政策", "法說／財報": "財報", "產品發布": "發布"}
TWORD = {"全日": "00:00", "清晨": "05:00", "午間": "12:00", "收盤": "13:30", "美股收盤": "23:59"}


def cal_days():
    t = dt.date.fromisoformat(D["today"])
    if t.weekday() == 4:
        return t, [t] + [t + dt.timedelta(days=k) for k in range(1, 8)]
    mon = t - dt.timedelta(days=t.weekday())
    return t, [mon + dt.timedelta(days=k) for k in range(5)]


def cal_events(d):
    return sorted([e for e in D["events"] if e["date"] == d.isoformat()], key=lambda e: TWORD.get(e["time"], e["time"]))


def ev_card(e, past):
    c = CAT.get(e["cat"], "#6B7280")
    res = (f'<div style="{F_JH};font-size:9pt;color:#065F46;font-weight:bold;margin-top:3px">已公布：{esc(e["result"])}</div>'
           if e.get("result") else "")
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin:0 0 6px">'
            f'<tr><td style="border-left:4px solid {c};background-color:#FFFFFF;padding:6px 6px 6px 7px">'
            f'<div style="{F_AP};font-size:9.5pt;font-weight:bold;color:{c}">{esc(e["time"])}'
            f'<span style="{F_JH};font-size:8.5pt;font-weight:normal;color:#6B7280">&nbsp;｜{esc(CAT_SHORT.get(e["cat"], e["cat"]))}</span></div>'
            f'<div style="{F_JH};font-size:10pt;font-weight:bold;color:{"#6B7280" if past else "#111827"};line-height:1.35;margin-top:2px">{esc(e["title"])}</div>'
            f'<div style="{F_JH};font-size:9pt;color:#374151;line-height:1.45;margin-top:3px">{esc(e["note"])}</div>'
            f'{res}</td></tr></table>')


def calendar():
    try:
        return _calendar()
    except Exception as ex:  # noqa  資料格式錯誤時仍輸出區塊，由 checks 擋下
        return h2("未來關注事件") + p_body(f"日曆資料錯誤：{ex}")


def _calendar():
    today, days = cal_days()
    fri = today.weekday() == 4
    hol = D.get("holidays") or {}
    sub = (f"今天＋下週 {days[1]:%m/%d}（六）–{days[-1]:%m/%d}（五）｜時間為台北時間" if fri
           else f"本週 {days[0]:%m/%d}（一）–{days[-1]:%m/%d}（五）｜時間為台北時間")
    fixed = {d: (16 if fri and d == today else 6) for d in days if (fri and d == today) or d.weekday() >= 5}
    flex = round((100 - sum(fixed.values())) / (len(days) - len(fixed)), 2)
    head, body = [], []
    for d in days:
        w = fixed.get(d, flex)
        is_today, past, wknd = d == today, d < today, d.weekday() >= 5
        bg = "#164A73" if is_today else ("#E5E7EB" if past or wknd else "#243B53")
        fg = "#FFFFFF" if is_today or not (past or wknd) else "#6B7280"
        tag = (f'<div style="{F_JH};font-size:8.5pt;font-weight:bold;background-color:#FACC15;color:#111827;'
               f'display:inline-block;padding:1px 6px;margin-top:3px">今天</div>') if is_today else ""
        h = d.isoformat()
        hl = f'<div style="{F_JH};font-size:8pt;margin-top:3px">{esc(hol[h])}</div>' if h in hol else ""
        head.append(f'<th width="{w:g}%" style="width:{w:g}%;background-color:{bg};color:{fg};border:1px solid #D9D9D9;padding:7px 3px;text-align:center;vertical-align:middle">'
                    f'<div style="{F_JH};font-size:10pt;font-weight:bold">{"週" if not wknd else ""}{WD[d.weekday()]}</div>'
                    f'<div style="{F_AP};font-size:{9 if wknd else 10}pt">{d:%m/%d}</div>{tag}{hl}</th>')
        evs = cal_events(d)
        cbg = "#FFF8DB" if is_today else ("#F3F4F6" if past or wknd else "#F8FAFC")
        inner = "".join(ev_card(e, past) for e in evs) or f'<div style="{F_JH};font-size:9pt;color:#9CA3AF;text-align:center;padding-top:8px">—</div>'
        border = "border:2px solid #164A73" if is_today else "border:1px solid #D9D9D9"
        body.append(f'<td valign="top" style="{border};background-color:{cbg};padding:6px 5px;vertical-align:top">{inner}</td>')
    legend = "".join(f'<td nowrap style="{F_JH};font-size:9pt;color:#374151;padding:0 12px 0 0;white-space:nowrap">'
                     f'<font color="{c}"><span style="color:{c};font-size:11pt">■</span></font>&nbsp;{t}</td>' for t, c in CAT.items())
    return (h2("未來關注事件") +
            f'<p style="{F_JH};font-size:9.5pt;color:#4B5563;margin:-4px 0 8px">{esc(sub)}</p>'
            f'<table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;table-layout:fixed">'
            f'<tr>{"".join(head)}</tr><tr>{"".join(body)}</tr></table>'
            f'<table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin:6px 0 4px"><tr>{legend}</tr></table>')


def calendar_text():
    try:
        today, days = cal_days()
    except Exception:  # noqa
        return ["未來關注事件（日曆資料錯誤）"]
    hol = D.get("holidays") or {}
    L = ["未來關注事件（台北時間）"]
    for d in days:
        tag = "（今天）" if d == today else ""
        h = f"［{hol[d.isoformat()]}］" if d.isoformat() in hol else ""
        L.append(f"{d:%m/%d}（{WD[d.weekday()]}）{tag}{h}")
        for e in cal_events(d):
            r = f"｜已公布：{e['result']}" if e.get("result") else ""
            L.append(f"  {e['time']}｜{e['cat']}｜{e['title']}｜{e['note']}{r}")
    return L


def build():
    P = ['<!doctype html><html><head><meta charset="UTF-8"></head><body style="margin:0;padding:20px;background:#fff;color:#000"><div style="max-width:900px;margin:0 auto">',
         f'<h1 style="{F_JH};font-size:14pt;font-weight:bold;color:#000;margin:0 0 8px">每日金融市場摘要</h1>',
         f'<p style="{F_JH};font-size:11pt;margin:0 0 10px">{esc(D["date_line"])}</p>']
    P.append(h2("今日新聞重點摘要", "14px 0 6px"))
    P.append(f'<p style="{F_JH};font-size:11pt;color:#000;line-height:1.6;margin:0 0 6px"><span style="background-color:#FFFF00">{esc(D["highlight"])}</span></p>')
    P.append(heatmap("美股", us_tiles()))
    P.append(heatmap("亞股", asia_tiles()))
    P.append(heatmap("美國公債殖利率", ust_tiles()))
    P.append(heatmap("匯率與商品", macro_tiles()))
    P.append(fedwatch())
    for i, (t, u, s) in enumerate(D["news"], 1):
        P += [p_title(i, t, u), p_body(s)]
    rows = [[brk(n), f"{c:,.2f}<br>{lbl(d)}", f"{pts(ch)}（{pct(pc)}）", esc(r)] for n, c, ch, pc, r, d in D["index_rows"]]
    lv, bp, note, r, d = D["ust"]
    rows.append(["美國10年期公債殖利率", f"{lv}<br>{lbl(d)}", f"{bp}<br>({note})", esc(r)])
    P.append(h2("主要指數"))
    P.append(table(["指數", "最新數據", "漲跌", "主要原因說明"], ["19%", "18%", "16%", "47%"], rows, left=(3,)))
    P.append(h2("匯率、商品與利率"))
    rows = [[brk(n), f"{esc(lv)}<br>{lbl(d)}", esc(ch) + (f"<br>({esc(nt)})" if nt else ""), esc(r)]
            for n, lv, ch, nt, r, _a, d in D["macro_rows"]]
    P.append(table(["項目", "最新數據", "漲跌", "主要原因說明"], ["19%", "18%", "16%", "47%"], rows, left=(3,)))
    P.append(us_macro())
    P.append(calendar())
    P.append(h2("壽險業新聞"))
    for i, (t, u, s) in enumerate(D["life"], 1):
        P += [p_title(i, t, u), p_body(s)]
    return "".join(P) + "</div></body></html>"


def build_text():
    L = ["每日金融市場摘要", D["date_line"], "", "今日新聞重點摘要", D["highlight"]]
    for title, tiles in (("美股", us_tiles()), ("亞股", asia_tiles()), ("美國公債殖利率", ust_tiles()), ("匯率與商品", macro_tiles())):
        L += ["", title, "｜".join(f"{n} {lv} {big}（{nt}）".replace("  ", " ").replace("（）", "") for n, lv, big, v, m, nt in tiles)]
    fw = D["fedwatch"]
    L += ["", "FedWatch 利率預期", f"{fw['meeting']} FOMC 會議｜目前利率區間 {fw['range']}｜CME {fw['asof']} 更新"]
    for label, cut, hold, h1, h2_ in fw["rows"]:
        L.append(f"{label}：降息 {cut:g}%｜維持 {hold:g}%｜升息1碼 {h1:g}%｜升息2碼以上 {h2_:g}%")
    L += [fw["note"], ""]
    for i, (t, u, s) in enumerate(D["news"], 1):
        L += [f"{i}. {t}", u, s, ""]
    L += ["主要指數"]
    for n, c, ch, pc, r, d in D["index_rows"]:
        L.append(f"{n}｜{c:,.2f}{lbl(d)}｜{pts(ch)}（{pct(pc)}）｜{r}")
    lv, bp, note, r, d = D["ust"]
    L += [f"美國10年期公債殖利率｜{lv}{lbl(d)}｜{bp}（{note}）｜{r}", "", "匯率、商品與利率"]
    for n, lv, ch, nt, r, _a, d in D["macro_rows"]:
        L.append(f"{n}｜{lv}{lbl(d)}｜{ch}{'（' + nt + '）' if nt else ''}｜{r}")
    um = D.get("us_macro")
    if um and um.get("rows"):
        L += ["", f"美國總經數據（{um['date']} 發布）"] + [f"{n}｜實際 {a}｜預期 {e}｜前值 {p}｜與預期差 {df}｜{rd}" for n, a, e, p, df, rd in um["rows"]]
    L += [""] + calendar_text() + ["", "壽險業新聞"]
    for i, (t, u, s) in enumerate(D["life"], 1):
        L += [f"{i}. {t}", u, s, ""]
    return "\n".join(L)


def checks(h):
    E = []
    if not 5 <= len(D["news"]) <= 8: E.append("重大新聞須5–8則")
    if len(D["index_rows"]) != 7: E.append("指數列須7列＋美債1列")
    if len(D["life"]) != 3: E.append("壽險新聞須3則")
    for t, u, s in D["life"]:
        if not 200 <= len(s) <= 300: E.append(f"壽險摘要字數{len(s)}：{t}")
    for t, u, s in D["news"] + D["life"]:
        if not re.match(r"^https?://[^/]+/.+", u): E.append(f"連結非具體文章：{u}")
        if re.match(r"^\S{1,12}｜\d{1,2}/\d{1,2}：", s): E.append(f"摘要含來源日期標籤：{t}")
    for n, c, ch, pc, r, d in D["index_rows"]:
        if abs(round(ch / (c - ch) * 100, 2) - pc) > 0.011: E.append(f"百分比不符：{n}")
        if "（" not in r: E.append(f"原因說明缺個股漲跌幅：{n}")
    for n, lv, ch, nt, r, a, d in D["macro_rows"]:
        if a and abs(round(a[1] / (a[0] - a[1]) * 100, 2) - a[2]) > 0.011: E.append(f"百分比不符：{n}")
    se = D.get("sse")
    if se and abs(round(se[1] / (se[0] - se[1]) * 100, 2) - se[2]) > 0.011: E.append("百分比不符：上證綜合")
    idx = h.split("匯率、商品與利率")[0]
    if len(re.findall(r"\(\d{2}/\d{2}市場收盤\)", idx)) != 8: E.append("指數表日期標籤須8個")
    if D["ust"][2] not in ("殖利率上升", "殖利率下降", "殖利率持平"): E.append("美債升降註記")
    if "background-color:#FFFF00" not in h or "今日新聞重點摘要：" in h: E.append("重點摘要亮黃／前綴")
    for bad in ("重大新聞", "主要指數變動", "資料截至"):
        if bad in h: E.append(f"不應出現：{bad}")
    if "未來關注事件" not in h: E.append("缺未來關注事件")
    try:
        today, days = cal_days()
        win = {d.isoformat() for d in days}
        evs = D["events"]
        if len(evs) < 3: E.append("未來關注事件至少3項")
        for e in evs:
            if e.get("date") not in win: E.append(f"事件日期不在日曆範圍：{e.get('date')} {e.get('title')}")
            if e.get("cat") not in CAT: E.append(f"事件類別須為四類之一：{e.get('cat')}")
            if not e.get("title") or not e.get("note"): E.append(f"事件缺標題或觀察重點：{e.get('title')}")
            if e.get("time") not in TWORD and not re.match(r"^\d{2}:\d{2}$", str(e.get("time"))): E.append(f"事件時間格式：{e.get('time')}")
        for d in win:
            n = sum(1 for e in evs if e.get("date") == d)
            if n > 4: E.append(f"{d} 事件卡超過4張（{n}）")
    except Exception as ex:  # noqa
        E.append(f"日曆資料錯誤：{ex}")
    fu = D.get("followups")
    if not isinstance(fu, list): E.append("缺 followups（無已發生事件時填 []）")
    for f in fu or []:
        w, kw = f.get("where"), f.get("keyword") or ""
        if w == "news":
            i = f.get("idx")
            if not isinstance(i, int) or not 1 <= i <= len(D["news"]): E.append(f"followups 新聞編號錯誤：{f.get('event')}")
            elif not kw or kw not in D["news"][i - 1][0] + D["news"][i - 1][2]: E.append(f"followups 關鍵字不在第{i}則新聞：{f.get('event')}")
        elif w == "highlight":
            if not kw or kw not in D["highlight"]: E.append(f"followups 關鍵字不在重點摘要：{f.get('event')}")
        elif w == "us_macro":
            um = D.get("us_macro") or {}
            if not kw or kw not in json.dumps(um, ensure_ascii=False): E.append(f"followups 關鍵字不在美國總經數據：{f.get('event')}")
        else:
            E.append(f"followups where 須為 news／highlight／us_macro：{f.get('event')}")
    if [m[0] for m in D["macro_rows"]] != MACRO: E.append("匯率、商品與利率清單須依序為：" + "、".join(MACRO))
    if "text-align:right" in h: E.append("主要原因說明／觀察重點須靠左對齊")
    if "收盤／數據日" in h or h.count(">最新數據<") != 2: E.append("欄名須為「最新數據」")
    reasons = [r[4] for r in D["index_rows"]] + [D["ust"][3]] + [m[4] for m in D["macro_rows"]]
    for r in reasons:
        m = SRC.search(r)
        if m: E.append(f"原因說明不得括號註明來源：{m.group(0)}")
    for t, u, s in D["news"]:
        for n, c, ch, pc, r, d in D["index_rows"]:
            for tok in (f"{c:,.2f}", f"{abs(ch):,.2f}點"):
                if tok in s: E.append(f"新聞摘要重複表格指數數字「{tok}」：{t}")
        dup = [x for x in STK.findall(s) if any(x in r[4] for r in D["index_rows"])]
        if len(dup) > 1: E.append(f"新聞摘要重複表格個股漲跌幅{dup}：{t}")
    fw = D.get("fedwatch") or {}
    labels = [r[0] for r in fw.get("rows", [])]
    if labels and (labels[0] != "最新" or any(x not in ("最新", "1天前", "1週前", "1個月前") for x in labels)): E.append("FedWatch列名須為：最新、1天前、1週前、1個月前")
    if not labels and "未取得" not in fw.get("note", ""): E.append("FedWatch無資料時note須寫明未取得")
    for r in fw.get("rows", []):
        if abs(sum(r[1:]) - 100) > 0.6: E.append(f"FedWatch機率加總≠100：{r[0]}")
    for k in ("meeting", "range", "asof", "note"):
        if not fw.get(k): E.append(f"FedWatch缺欄位：{k}")
    um = D.get("us_macro")
    if um and any(len(r) != 6 for r in um.get("rows", [])): E.append("美國總經數據每列須6欄")
    order = ["今日新聞重點摘要", "美股", "亞股", "美國公債殖利率", "匯率與商品", "FedWatch 利率預期", "主要指數", "匯率、商品與利率", "未來關注事件", "壽險業新聞"]
    pos = [h.find(f">{x}</h2>") for x in order]
    if -1 in pos or pos != sorted(pos): E.append("區塊順序須為：" + "→".join(order))
    if pos[5] != -1 and h.find(p_title(1, *D["news"][0][:2])) < pos[5]: E.append("重大新聞須在FedWatch之後")
    return E


if __name__ == "__main__":
    h, t = build(), build_text()
    open("email.html", "w", encoding="utf-8").write(h)
    open("email.txt", "w", encoding="utf-8").write(t)
    e = checks(h)
    print("html bytes", len(h.encode()), "| text bytes", len(t.encode()), "| life", [len(x[2]) for x in D["life"]])
    print("CHECKS:", "PASS" if not e else e)
    sys.exit(1 if e else 0)
