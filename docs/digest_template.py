# -*- coding: utf-8 -*-
"""Daily market digest: data.json -> email.html + email.txt, then format/arithmetic checks.
Usage: python3 digest_template.py data.json   (exit code 1 if any check fails)"""
import json, re, sys, html, datetime as dt

F_JH = "font-family:Microsoft JhengHei,Arial,sans-serif"
F_AP = "font-family:Aptos,Arial,sans-serif"
LINK = "color:#164A73;text-decoration:underline;font-weight:bold"
D = json.load(open(sys.argv[1], encoding="utf-8"))
esc = lambda s: html.escape(s, quote=False)
W = 700  # 郵件版寬（px）：Outlook／Word 引擎不認 max-width，一律用固定寬度＋width 屬性


def p_title(n, t, u):
    return (f'<p style="{F_JH};font-size:11pt;font-weight:bold;line-height:1.4;margin:15px 0 4px">{n}. '
            f'<a href="{html.escape(u)}" style="{LINK}">{esc(t)}</a></p>')


def p_body(t):
    return f'<p style="{F_JH};font-size:11pt;color:#000;line-height:1.6;margin:0 0 11px">{esc(t)}</p>'


def h2(t, m="22px 0 10px"):
    return f'<h2 style="{F_JH};font-size:11pt;font-weight:bold;color:#000;margin:{m}">{esc(t)}</h2>'


def cell(tag, c, bg, hdr=False, align="center", w=None):
    wa = f' width="{round(W * float(w.rstrip("%")) / 100)}"' if w else ""
    return (f'<{tag}{wa} bgcolor="{bg}" align="{align}" valign="middle" style="{F_AP};font-size:11pt;text-align:{align};vertical-align:middle;border:1px solid #D9D9D9;'
            f'padding:9px 7px;overflow-wrap:break-word;background-color:{bg};color:{"#FFFFFF" if hdr else "#000000"};'
            f'font-weight:{"bold" if hdr else "normal"}">{c}</{tag}>')


def table(hdrs, widths, rows, left=()):
    o = [f'<table role="presentation" width="{W}" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;width:{W}px;table-layout:fixed">',
         "<tr>" + "".join(cell("th", esc(h), "#243B53", True, w=w) for h, w in zip(hdrs, widths)) + "</tr>"]
    for i, r in enumerate(rows):
        o.append("<tr>" + "".join(cell("td", c, "#FFFFFF" if i % 2 == 0 else "#F2F6F9", align="left" if j in left else "center") for j, c in enumerate(r)) + "</tr>")
    return "".join(o) + "</table>" + gap(12)


gap = lambda h: f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td height="{h}" style="height:{h}px;font-size:1px;line-height:1px">&nbsp;</td></tr></table>'


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
# FedWatch 低飽和玫瑰色：(底色, 字色)
FW_COL = {"cut": ("#A8D5C2", "#14532D"), "hold": ("#E5E7EB", "#374151"), "hike1": ("#F1BDBA", "#7A1F1F"), "hike2": ("#C97A78", "#FFFFFF")}
TAG = {"總經": "#1D4ED8", "政策": "#7C3AED", "個股": "#C2410C", "產業": "#15803D", "地緣": "#6B5B4B"}  # 11/12 起不收盤勢新聞，盤勢只寫在今日重點摘要
TAG_MAX = {"總經": 2, "政策": 2, "個股": 3, "產業": 2, "地緣": 2}
REGION = ("美國", "台灣", "亞洲", "歐洲", "中國", "全球")
MKT = re.compile(r"(道瓊|標普|那指|那斯達克|費半|費城半導體|日經|韓股|KOSPI|加權指數|台股|大盤|美股)[^。；，、]{0,6}(大漲|大跌|上漲|下跌|收漲|收跌|收高|收低|收黑|收紅|漲|跌)\s*[\d０-９]")
HL_RULE = [("美股", r"(道瓊|標普|那指|那斯達克|費半|美股)"), ("美國總經", r"(Fed|聯準會|CPI|PCE|PPI|非農|殖利率|美元|黃金|油|升息|降息|就業|美債)"),
           ("重大訊息", r"；"), ("亞股", r"(台股|加權)")]
IMPACT = ("美股", "那斯達克", "費半", "台股", "日股", "韓股", "陸股", "美債殖利率", "2年期殖利率", "美元", "新台幣", "油價", "黃金", "升息機率")


def heat_color(v, m):
    if v is None or v == 0: return "#E5E7EB", "#1F2937"
    t = min(abs(v) / m, 1)
    a, b = ((253, 226, 226), (185, 28, 28)) if v > 0 else ((220, 242, 232), (21, 128, 86))
    c = tuple(int(a[i] + (b[i] - a[i]) * (0.25 + 0.75 * t)) for i in range(3))
    return "#%02X%02X%02X" % c, ("#FFFFFF" if t > 0.45 else "#1F2937")


HW = (W - 20) // 2
HCOL = [round(HW * x) for x in (0.29, 0.27, 0.19, 0.25)]


def heat_rows(title, tiles):
    """tiles: [(名稱, 最新值, 主數字, 數值或None, 色階上限, 註記)]；一列一個市場，整列依漲跌上色"""
    r = [f'<tr><td colspan="4" style="{F_JH};font-size:10.5pt;font-weight:bold;color:#0B2545;padding:7px 0 3px">{esc(title)}</td></tr>']
    for n, lv, big, v, m, nt in tiles:
        bg, fg = heat_color(v, m)
        td = f'background-color:{bg};color:{fg};border-bottom:2px solid #FFFFFF;padding:4px 6px;white-space:nowrap'
        a, b, c, d = HCOL
        r.append(f'<tr><td width="{a}" bgcolor="{bg}" style="{td};{F_JH};font-size:10pt;font-weight:bold"><font color="{fg}">{esc(n)}</font></td>'
                 f'<td width="{b}" align="right" bgcolor="{bg}" style="{td};{F_AP};font-size:10pt;text-align:right"><font color="{fg}">{esc(lv) if lv else "&nbsp;"}</font></td>'
                 f'<td width="{c}" align="right" bgcolor="{bg}" style="{td};{F_AP};font-size:11pt;font-weight:bold;text-align:right"><font color="{fg}">{esc(big)}</font></td>'
                 f'<td width="{d}" align="right" bgcolor="{bg}" style="{td};{F_AP};font-size:9pt;text-align:right"><font color="{fg}">{esc(nt) if nt else "&nbsp;"}</font></td></tr>')
    return "".join(r)


def heat_block():
    col = lambda parts: (f'<table role="presentation" width="{HW}" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;width:{HW}px;table-layout:fixed">'
                         + "".join(heat_rows(*x) for x in parts) + "</table>")
    left = col([("美股", us_tiles()), ("亞股", asia_tiles())])
    right = col([("美國公債殖利率", ust_tiles()), ("匯率與商品", macro_tiles())])
    return (f'<table role="presentation" width="{W}" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;width:{W}px;table-layout:fixed"><tr>'
            f'<td width="{HW}" valign="top" style="vertical-align:top">{left}</td><td width="20" style="font-size:1px">&nbsp;</td>'
            f'<td width="{HW}" valign="top" style="vertical-align:top">{right}</td></tr></table>')


def preopen_line():
    po = D.get("preopen") or {}
    parts = []
    for key, name in (("TSM", "台積電ADR"), ("TXF_NIGHT", "台指期夜盤"), ("NKD=F", "日經期貨")):
        x = po.get(key)
        if not x: continue
        if key == "TXF_NIGHT":
            parts.append(f"{name} {x['last']:,.0f}（{sgn(x['chg'])}{abs(x['chg']):,.0f}，{pct(x['pct'])}）")
        else:
            parts.append(f"{name} {pct(x['pct'])}")
    if not parts: return ""
    return (gap(6) + f'<table role="presentation" width="{W}" cellspacing="0" cellpadding="0" border="0" style="width:{W}px"><tr>'
            f'<td bgcolor="#F3F4F6" style="background-color:#F3F4F6;{F_JH};font-size:9.5pt;color:#374151;padding:5px 8px">'
            f'<b>開盤前指標</b>　{esc("｜".join(parts))}</td></tr></table>')


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
        t.append(("10Y−2Y 利差", f"{sp}bp", f"{sgn(dif)}{abs(dif):g}bp", None, 15, "曲線趨陡" if dif > 0 else ("曲線趨平" if dif < 0 else "利差持平")))
    else:
        t.append(("10Y−2Y 利差", "", "未取得", None, 15, ""))
    return t


def macro_tiles():
    M = {m[0]: m for m in D["macro_rows"]}
    out = []
    for n in ("美元指數", "美元兌新台幣", "布蘭特原油", "黃金（COMEX近月期貨）"):
        _n, lv, ch, nt, r, a, d = M[n]
        name = "黃金" if n.startswith("黃金") else n
        if not a:
            out.append((name, "", "未取得", None, SCALE[n], ""))
            continue
        lvl = lv.split("/")[0].replace("美元", "")
        sub = nt or (D.get("brent_note") if n == "布蘭特原油" else None) or f"{sgn(a[1])}{abs(a[1]):,.2f} 美元"
        out.append((name, lvl, pct(a[2]), a[2], SCALE[n], sub))
    return out


def fedwatch():
    fw = D["fedwatch"]
    rows = []
    LW = 92; BW = W - LW
    for label, cut, hold, h1, h2_ in fw["rows"]:
        segs = "".join(f'<td width="{round(BW * p / 100)}" height="22" bgcolor="{c}" style="background-color:{c};width:{round(BW * p / 100)}px;height:22px;color:{fc};{F_AP};font-size:9.5pt;text-align:center;font-weight:bold">'
                       f'<font color="{fc}">{(f"{p:g}%") if p >= 8 else "&nbsp;"}</font></td>'
                       for p, (c, fc) in ((cut, FW_COL["cut"]), (hold, FW_COL["hold"]), (h1, FW_COL["hike1"]), (h2_, FW_COL["hike2"])) if p > 0)
        rows.append(f'<tr><td width="{LW}" nowrap style="{F_JH};font-size:10.5pt;padding:4px 8px 4px 0;width:{LW}px;white-space:nowrap;{"font-weight:bold" if label == "最新" else ""}">{esc(label)}</td>'
                    f'<td width="{BW}" style="padding:4px 0"><table role="presentation" width="{BW}" cellspacing="0" cellpadding="0" border="0" style="width:{BW}px;border-collapse:collapse;table-layout:fixed"><tr>{segs}</tr></table></td></tr>'
                    '<tr><td colspan="2" height="6" style="height:6px;font-size:1px;line-height:1px">&nbsp;</td></tr>')
    legend = ('<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;margin:6px 0 4px"><tr>' +
              "".join(f'<td nowrap style="{F_JH};font-size:9.5pt;color:#374151;padding:0 14px 0 0;white-space:nowrap">'
                      f'<font color="{c}"><span style="color:{c};font-size:11pt">■</span></font>&nbsp;{n}&nbsp;&nbsp;&nbsp;&nbsp;</td>'
                      for n, (c, _) in (("降息", FW_COL["cut"]), ("維持不變", FW_COL["hold"]), ("升息1碼", FW_COL["hike1"]), ("升息2碼以上", FW_COL["hike2"]))) + "</tr></table>")
    return (h2("FedWatch 利率預期") +
            f'<p style="{F_JH};font-size:11pt;margin:0 0 6px">{esc(fw["meeting"])} FOMC 會議｜目前利率區間 {esc(fw["range"])}｜CME {esc(fw["asof"])} 更新（依前一日期貨結算）</p>'
            f'<table role="presentation" width="{W}" cellspacing="0" cellpadding="0" border="0" style="width:{W}px;border-collapse:collapse">{"".join(rows)}</table>'
            f'{legend}'
            f'<p style="{F_JH};font-size:11pt;line-height:1.6;margin:4px 0 12px">{esc(fw["note"])}</p>')


# ---------- 重點摘要、新聞卡、台股籌碼面 ----------
def highlight_box():
    li = "".join(f'<tr><td width="22" valign="top" style="{F_AP};font-size:11pt;vertical-align:top;padding:3px 4px 3px 0;white-space:nowrap">{i}.</td>'
                 f'<td valign="top" style="{F_JH};font-size:11pt;line-height:1.6;padding:3px 0"><b>{esc(h)}：</b>{esc(t)}</td></tr>'
                 for i, (h, t) in enumerate(D["highlight"], 1))
    return (f'<table role="presentation" width="{W}" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;width:{W}px"><tr>'
            f'<td bgcolor="#FEF6D2" style="background-color:#FEF6D2;border:1px solid #E9D47A;padding:12px 16px">'
            f'<p style="{F_JH};font-size:12pt;font-weight:bold;color:#1F2937;margin:0 0 6px">今日重點摘要</p>'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">{li}</table></td></tr></table>' + gap(4))


def text_px(text, size="9pt"):
    """估算文字寬度（px），給 Outlook／Word 用的 width 屬性；CJK 約 1 個字高，其餘約 0.6。"""
    pt = float(size.rstrip("pt")) * 4 / 3
    plain = re.sub(r"&[a-z]+;", " ", re.sub(r"<[^>]+>", "", text))
    return round(sum(pt if ord(ch) > 0x2E80 else pt * 0.62 for ch in plain))


def chip_td(text, bg, fg, bold=False, size="9pt", font=F_JH):
    w = text_px(text, size) + 16
    return (f'<td width="{w}" nowrap bgcolor="{bg}" style="width:{w}px;background-color:{bg};{font};font-size:{size};{"font-weight:bold;" if bold else ""}'
            f'color:{fg};padding:1px 7px;white-space:nowrap"><font color="{fg}">{text}</font></td>')


def impact_chip(n, a):
    bg, fg = ("#FBE9E8", "#A61B1B") if a == "▲" else ("#E6F4EC", "#1E7A55")
    return '<td width="6" style="font-size:1px">&nbsp;</td>' + chip_td(f"{esc(n)}&nbsp;{a}", bg, fg)


def news_card(i, e):
    tag = e["tag"]
    chips = "".join(impact_chip(n, a) for n, a in e.get("impact") or [])
    head = (f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse"><tr>'
            + chip_td(esc(tag), TAG[tag], "#FFFFFF", bold=True, size="9.5pt")
            + f'<td width="{text_px(e["date"], "10pt") + 14}" nowrap style="{F_AP};font-size:10pt;color:#6B7280;padding:1px 4px 1px 8px;white-space:nowrap">{esc(e["date"])}</td>'
            + chips + '</tr></table>')
    bl = "".join(f'<tr><td width="18" valign="top" style="{F_JH};font-size:11pt;vertical-align:top;padding:2px 6px 2px 4px">•</td>'
                 f'<td style="{F_JH};font-size:10.5pt;line-height:1.6;padding:2px 0;color:#000">{esc(b)}</td></tr>' for b in e["bullets"])
    return (f'<table role="presentation" width="{W}" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;width:{W}px"><tr>'
            f'<td bgcolor="#FFFFFF" style="border:1px solid #E5E7EB;padding:12px 16px;background-color:#FFFFFF">{head}'
            f'<p style="{F_JH};font-size:12pt;font-weight:bold;line-height:1.4;margin:7px 0 6px">{i}. <a href="{html.escape(e["url"])}" style="{LINK}">{esc(e["title"])}</a></p>'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">{bl}</table></td></tr></table>' + gap(12))


def chips_block():
    ch, inst = D.get("chips"), D.get("inst")
    idx_date = next((r[5] for r in D["index_rows"] if r[0] == "台灣加權指數"), None)
    if not ch or not inst or not idx_date:
        return ""
    d = inst["date"][5:].replace("-", "/").lstrip("0")
    if d != idx_date and inst["date"][5:].replace("-", "/") != idx_date:
        return ""
    mx = max(1.0, *(abs(inst[k] or 0) for k in ("foreign", "trust", "dealer", "total")))
    C1, C2, C3, C4 = 130, 190, 100, W - 130 - 380 - 100
    bars = []
    for n, k, st in (("外資及陸資", "foreign", ch.get("foreign_streak")), ("投信", "trust", ch.get("trust_streak")), ("自營商", "dealer", None), ("三大法人合計", "total", None)):
        v = inst.get(k) or 0
        w = max(3, round(abs(v) / mx * C2))
        bar = lambda c: f'<td width="{w}" height="14" bgcolor="{c}" style="background-color:{c};width:{w}px;height:14px;font-size:1px;line-height:1px">&nbsp;</td>'
        pad = f'<td width="{C2 - w}" style="font-size:1px;line-height:1px">&nbsp;</td>'
        tb = lambda inner: f'<table role="presentation" width="{C2}" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;width:{C2}px"><tr>{inner}</tr></table>'
        left = tb(pad + bar("#3E9C76")) if v < 0 else "&nbsp;"
        right = tb(bar("#D9534F") + pad) if v > 0 else "&nbsp;"
        col = "#B42318" if v > 0 else "#1E7A55"
        stx = "&nbsp;"
        if st and abs(st) >= 2:
            stx = ('<table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>'
                   + chip_td(f'連{abs(st)}{"買" if st > 0 else "賣"}', "#FBE9E8" if st > 0 else "#E6F4EC", col, size="8.5pt") + '</tr></table>')
        bars.append(f'<tr><td width="{C1}" align="right" style="{F_JH};font-size:10pt;text-align:right;padding:2px 8px;white-space:nowrap;{"font-weight:bold" if "合計" in n else ""}">{n}</td>'
                    f'<td width="{C2}" style="padding:2px 0;border-right:1px solid #9CA3AF">{left}</td><td width="{C2}" style="padding:2px 0">{right}</td>'
                    f'<td width="{C3}" style="{F_AP};font-size:10pt;font-weight:bold;color:{col};padding:2px 6px;white-space:nowrap"><font color="{col}">{sgn(v)}{abs(v):,.2f}</font></td>'
                    f'<td width="{C4}" style="padding:2px 0;white-space:nowrap">{stx}</td></tr>')
    bars = f'<table role="presentation" width="{W}" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;table-layout:fixed;width:{W}px">' + "".join(bars) + "</table>"

    def top(title, rows, color):
        t = "".join(f'<tr><td style="{F_JH};font-size:10pt;padding:2px 0;white-space:nowrap">{esc(x["name"])}</td>'
                    f'<td style="{F_AP};font-size:10pt;font-weight:bold;text-align:right;color:{color};white-space:nowrap">{sgn(x["amt"])}{abs(x["amt"]):,.1f}</td>'
                    f'<td style="{F_AP};font-size:9pt;text-align:right;color:#6B7280;white-space:nowrap;padding-left:6px">{sgn(x["lots"])}{abs(x["lots"]):,}張</td></tr>'
                    for x in rows[:3]) or f'<tr><td style="{F_JH};font-size:9pt;color:#9CA3AF">—</td></tr>'
        return (f'<td width="{(W - 24) // 3}" valign="top" bgcolor="#F8FAFC" style="vertical-align:top;background-color:#F8FAFC;border:1px solid #E2E8F0;padding:5px 8px">'
                f'<div style="{F_JH};font-size:9.5pt;color:#475569;margin-bottom:2px">{title}</div>'
                f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{t}</table></td>')
    tops = (gap(6) + f'<table role="presentation" width="{W}" cellspacing="0" cellpadding="0" border="0" style="table-layout:fixed;width:{W}px"><tr>' +
            top("外資賣超前三（億元）", ch.get("foreign_sell_top") or [], "#1E7A55") + '<td width="12" style="font-size:1px">&nbsp;</td>' + top("外資買超前三（億元）", ch.get("foreign_buy_top") or [], "#B42318") +
            '<td width="12" style="font-size:1px">&nbsp;</td>' + top("投信買超前三（億元）", ch.get("trust_buy_top") or [], "#B42318") + "</tr></table>")
    extra = []
    ts = ch.get("tsmc")
    if ts and abs(ts.get("foreign_streak") or 0) >= 2:
        st = ts["foreign_streak"]
        extra.append(f'台積電外資連{abs(st)}日{"買" if st > 0 else "賣"}超（{sgn(ts["foreign_lots"])}{abs(ts["foreign_lots"]):,}張）')
    oi = ch.get("tx_foreign_net_oi")
    if oi is not None:
        chg = ch.get("tx_chg")
        extra.append(f'外資台指期淨未平倉 {oi:+,} 口' + (f'（較前日{"空單增加" if chg < 0 else "空單減少" if oi < 0 else "多單增加" if chg > 0 else "多單減少"} {abs(chg):,} 口）' if chg else ""))
    fut = (f'<p style="{F_JH};font-size:10pt;color:#374151;margin:6px 0 0">{esc("｜".join(extra))}</p>') if extra else ""
    return (h2(f"台股籌碼面（{idx_date} 上市）") +
            f'<p style="{F_JH};font-size:9.5pt;color:#6B7280;margin:0 0 4px">三大法人買賣超（億元）</p>' + bars + tops + fut)


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
        tag = ('<table role="presentation" align="center" cellspacing="0" cellpadding="0" border="0" style="margin-top:3px"><tr>'
               + chip_td("今天", "#FACC15", "#111827", bold=True, size="8.5pt") + '</tr></table>') if is_today else ""
        h = d.isoformat()
        hl = f'<div style="{F_JH};font-size:8pt;margin-top:3px">{esc(hol[h])}</div>' if h in hol else ""
        head.append(f'<th width="{round(W * w / 100)}" style="width:{round(W * w / 100)}px;background-color:{bg};color:{fg};border:1px solid #D9D9D9;padding:7px 3px;text-align:center;vertical-align:middle">'
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
            f'<table role="presentation" width="{W}" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;width:{W}px;table-layout:fixed">'
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
    P = ['<!doctype html><html><head><meta charset="UTF-8"></head><body style="margin:0;padding:0;background:#FFFFFF;color:#000">'
         f'<table role="presentation" width="{W}" align="center" cellspacing="0" cellpadding="0" border="0" style="width:{W}px;border-collapse:collapse"><tr><td style="padding:16px 0">',
         f'<h1 style="{F_JH};font-size:14pt;font-weight:bold;color:#000;margin:0 0 8px">每日金融市場摘要</h1>',
         f'<p style="{F_JH};font-size:11pt;margin:0 0 12px">{esc(D["date_line"])}</p>']
    P.append(highlight_box())
    P.append(h2("全球盤勢一覽", "14px 0 0"))
    P.append(heat_block())
    P.append(preopen_line())
    P.append(fedwatch())
    P.append(h2("重大新聞", "16px 0 8px"))
    for i, e in enumerate(D["news"], 1):
        P.append(news_card(i, e))
    rows = [[brk(n), f"{c:,.2f}<br>{lbl(d)}", f"{pts(ch)}（{pct(pc)}）", esc(r)] for n, c, ch, pc, r, d in D["index_rows"]]
    lv, bp, note, r, d = D["ust"]
    rows.append(["美國10年期公債殖利率", f"{lv}<br>{lbl(d)}", f"{bp}<br>({note})", esc(r)])
    P.append(h2("主要指數"))
    P.append(table(["指數", "最新數據", "漲跌", "主要原因說明"], ["19%", "18%", "16%", "47%"], rows, left=(3,)))
    P.append(chips_block())
    P.append(h2("匯率、商品與利率"))
    rows = [[brk(n), f"{esc(lv)}<br>{lbl(d)}", esc(ch) + (f"<br>({esc(nt)})" if nt else ""), esc(r)]
            for n, lv, ch, nt, r, _a, d in D["macro_rows"]]
    P.append(table(["項目", "最新數據", "漲跌", "主要原因說明"], ["19%", "18%", "16%", "47%"], rows, left=(3,)))
    P.append(us_macro())
    P.append(calendar())
    P.append(h2("壽險業新聞"))
    for i, (t, u, s) in enumerate(D["life"], 1):
        P += [p_title(i, t, u), p_body(s)]
    return "".join(P) + "</td></tr></table></body></html>"


def build_text():
    L = ["每日金融市場摘要", D["date_line"], "", "今日重點摘要"] + [f"{i}. {h}：{t}" for i, (h, t) in enumerate(D["highlight"], 1)]
    for title, tiles in (("美股", us_tiles()), ("亞股", asia_tiles()), ("美國公債殖利率", ust_tiles()), ("匯率與商品", macro_tiles())):
        L += ["", title, "｜".join(f"{n} {lv} {big}（{nt}）".replace("  ", " ").replace("（）", "") for n, lv, big, v, m, nt in tiles)]
    po = html.unescape(re.sub(r"<[^>]+>", "", preopen_line())).replace("\xa0", "").replace("開盤前指標", "開盤前指標：", 1).strip()
    if po: L += ["", po]
    fw = D["fedwatch"]
    L += ["", "FedWatch 利率預期", f"{fw['meeting']} FOMC 會議｜目前利率區間 {fw['range']}｜CME {fw['asof']} 更新"]
    for label, cut, hold, h1, h2_ in fw["rows"]:
        L.append(f"{label}：降息 {cut:g}%｜維持 {hold:g}%｜升息1碼 {h1:g}%｜升息2碼以上 {h2_:g}%")
    L += [fw["note"], "", "重大新聞"]
    for i, e in enumerate(D["news"], 1):
        imp = "｜影響：" + "、".join(f"{n}{a}" for n, a in e["impact"]) if e.get("impact") else ""
        L += [f"［{e['tag']}］{e['date']}{imp}", f"{i}. {e['title']}", e["url"]] + [f"• {b}" for b in e["bullets"]] + [""]
    L += ["主要指數"]
    for n, c, ch, pc, r, d in D["index_rows"]:
        L.append(f"{n}｜{c:,.2f}{lbl(d)}｜{pts(ch)}（{pct(pc)}）｜{r}")
    lv, bp, note, r, d = D["ust"]
    L += [f"美國10年期公債殖利率｜{lv}{lbl(d)}｜{bp}（{note}）｜{r}"]
    cb = chips_block()
    if cb:
        ch, inst = D["chips"], D["inst"]
        mk = lambda v: f"{sgn(v)}{abs(v):,.2f}"
        stk = lambda s_: f"（連{abs(s_)}{'買' if s_ > 0 else '賣'}）" if s_ and abs(s_) >= 2 else ""
        L += ["", f"台股籌碼面（{inst['date'][5:].replace('-', '/')} 上市，億元）",
              f"外資及陸資 {mk(inst['foreign'])}{stk(ch.get('foreign_streak'))}｜投信 {mk(inst['trust'])}{stk(ch.get('trust_streak'))}｜自營商 {mk(inst['dealer'])}｜合計 {mk(inst['total'])}"]
        for title, key in (("外資賣超前三", "foreign_sell_top"), ("外資買超前三", "foreign_buy_top"), ("投信買超前三", "trust_buy_top")):
            L.append(f"{title}：" + "、".join(f"{x['name']} {sgn(x['amt'])}{abs(x['amt']):,.1f}億（{sgn(x['lots'])}{abs(x['lots']):,}張）" for x in (ch.get(key) or [])[:3]))
        L.append(html.unescape(re.sub(r"<[^>]+>", "", cb.split("</table>")[-1])).replace("\xa0", " ").strip())
    L += ["", "匯率、商品與利率"]
    for n, lv, ch, nt, r, _a, d in D["macro_rows"]:
        L.append(f"{n}｜{lv}{lbl(d)}｜{ch}{'（' + nt + '）' if nt else ''}｜{r}")
    um = D.get("us_macro")
    if um and um.get("rows"):
        L += ["", f"美國總經數據（{um['date']} 發布）"] + [f"{n}｜實際 {a}｜預期 {e}｜前值 {p}｜與預期差 {df}｜{rd}" for n, a, e, p, df, rd in um["rows"]]
    L += [""] + calendar_text() + ["", "壽險業新聞"]
    for i, (t, u, s) in enumerate(D["life"], 1):
        L += [f"{i}. {t}", u, s, ""]
    return "\n".join(L)


def impact_value(name):
    """影響標籤對應的實際方向：>0 上漲／上升，<0 下跌／下降，None 無資料"""
    R = {r[0]: r for r in D["index_rows"]}
    M = {m[0]: m for m in D["macro_rows"]}
    idx = {"美股": "標準普爾500指數", "那斯達克": "那斯達克綜合指數", "費半": "費城半導體指數", "台股": "台灣加權指數", "日股": "日經225指數", "韓股": "韓國綜合股價指數"}
    if name in idx: return R[idx[name]][3]
    if name == "陸股": return (D.get("sse") or [None, None, None])[2]
    if name == "美債殖利率": return bp_value(D["ust"][1])
    if name == "2年期殖利率": return ((D.get("curve") or {}).get("y2") or [None, None])[1]
    if name == "美元": return (M["美元指數"][5] or [None, None, None])[2]
    if name == "新台幣":
        a = M["美元兌新台幣"][5]
        return -a[2] if a else None
    if name == "油價": return (M["布蘭特原油"][5] or [None, None, None])[2]
    if name == "黃金": return (M["黃金（COMEX近月期貨）"][5] or [None, None, None])[2]
    if name == "升息機率":
        rows = (D.get("fedwatch") or {}).get("rows") or []
        if len(rows) >= 2: return (rows[0][3] + rows[0][4]) - (rows[1][3] + rows[1][4])
        return None
    # 個股：須出現在指數表原因說明中，方向依其漲跌幅
    for r in D["index_rows"]:
        m = re.search(re.escape(name) + r"（([+−])\d+\.\d{2}%）", r[4])
        if m: return 1 if m.group(1) == "+" else -1
    return None


def checks(h):
    E = []
    N = D["news"]
    if not 7 <= len(N) <= 8: E.append("重大新聞須7–8則")
    HL = D["highlight"]
    if len(HL) != 4: E.append("今日重點摘要須固定4點：美股市場、美國總經、美國或世界重大訊息、亞股市場")
    for k, (hd, tx) in enumerate(HL[:4]):
        name, pat = HL_RULE[k]
        if not hd or not tx or len(hd) > 12: E.append(f"重點摘要第{k+1}點導語須≤12字且內文不可空：{hd}")
        lim = 80 if k == 2 else 70
        if len(tx) > lim: E.append(f"重點摘要第{k+1}點（{name}）內文{len(tx)}字，上限{lim}字：{hd}")
        if not re.search(pat, hd + tx): E.append(f"重點摘要第{k+1}點須為「{name}」：{hd}")
    if len(HL) == 4:
        if HL[2][1].count("；") < 1: E.append("重點摘要第3點須彙整2件以上重大訊息，以「；」分隔")
        if not re.search(r"昨日（\d{1,2}/\d{1,2}）", HL[3][0] + HL[3][1]): E.append("重點摘要第4點須標明「昨日（M/D）」亞股收盤時點")
    if len(D["index_rows"]) != 7: E.append("指數列須7列＋美債1列")
    if len(D["life"]) != 3: E.append("壽險新聞須3則")
    for t, u, s in D["life"]:
        if not 200 <= len(s) <= 300: E.append(f"壽險摘要字數{len(s)}：{t}")
        if not re.match(r"^https?://[^/]+/.+", u): E.append(f"連結非具體文章：{u}")
    tags = [e.get("tag") for e in N]
    if any(t not in TAG for t in tags): E.append(f"新聞主題須為{list(TAG)}：{tags}")
    for t_, mx in TAG_MAX.items():
        if tags.count(t_) > mx: E.append(f"「{t_}」新聞最多{mx}則，目前{tags.count(t_)}則")
    if len(set(tags)) < 4: E.append(f"新聞至少涵蓋4類主題，目前{sorted(set(tags))}")
    stories = [str(e.get("story") or "").strip() for e in N]
    if any(not x for x in stories): E.append("每則新聞須有 story（事件名稱），同一事件只能寫一則")
    dup_s = {x for x in stories if x and stories.count(x) > 1}
    if dup_s: E.append(f"同一事件寫成多則新聞：{sorted(dup_s)}")
    seen = {}
    for i, e in enumerate(N, 1):
        for ent in e.get("entities") or []:
            if ent in seen: E.append(f"主角「{ent}」同時出現在第{seen[ent]}則與第{i}則，請合併或改選其他新聞")
            seen.setdefault(ent, i)
        if not e.get("entities"): E.append(f"新聞須列 entities（主角公司或機構）：{e.get('title')}")
        if e.get("region") not in REGION: E.append(f"新聞 region 須為{REGION}之一：{e.get('title')}")
    regions = [e.get("region") for e in N]
    if "台灣" not in regions: E.append("至少1則台灣新聞（央行、金管會、政策、企業營收或公告；不含盤勢）")
    if not any(r_ in ("亞洲", "歐洲", "中國", "全球") for r_ in regions): E.append("至少1則美國與台灣以外的國際新聞")
    inst = D.get("inst") or {}
    inst_tokens = [f"{abs(inst[k]):,.2f}" for k in ("foreign", "trust", "dealer", "total") if inst.get(k)]
    oi = (D.get("chips") or {}).get("tx_foreign_net_oi")
    if oi is not None: inst_tokens.append(f"{abs(oi):,}")
    for e in N:
        t, b = e.get("title", ""), e.get("bullets") or []
        if not re.match(r"^https?://[^/]+/.+", e.get("url", "")): E.append(f"連結非具體文章：{e.get('url')}")
        if not e.get("date") or not re.match(r"^\d{1,2}/\d{1,2}", str(e.get("date"))): E.append(f"新聞須有日期標籤（M/D 或 M/D 盤後）：{t}")
        if not 3 <= len(b) <= 4: E.append(f"新聞須3–4點條列：{t}")
        for x in b:
            if len(x) > 60: E.append(f"條列超過60字（{len(x)}）：{x[:20]}…")
        if b and not b[-1].startswith("後續觀察"): E.append(f"最後一點須以「後續觀察」開頭：{t}")
        body = t + "".join(b)
        for n, c, ch, pc, r, d in D["index_rows"]:
            for tok in (f"{c:,.2f}", f"{abs(ch):,.2f}點", f"{abs(ch):,.2f} 點"):
                if tok in body: E.append(f"新聞重複表格指數數字「{tok}」：{t}")
        for tok in inst_tokens:
            if tok in body: E.append(f"新聞重複籌碼面數字「{tok}」（法人金額／期貨口數交給籌碼面區塊）：{t}")
        dup = [x for x in STK.findall(body) if any(x in r[4] for r in D["index_rows"])]
        if len(dup) > 1: E.append(f"新聞重複表格個股漲跌幅{dup}：{t}")
        m_ = MKT.search(body)
        if m_: E.append(f"重大新聞不寫盤勢（指數漲跌寫在今日重點摘要與指數表）：「{m_.group(0)}」｜{t}")
        imp = e.get("impact") or []
        if len(imp) > 3: E.append(f"影響標籤最多3個：{t}")
        for n, a in imp:
            if a not in ("▲", "▼"): E.append(f"影響方向須為▲或▼：{n}{a}")
            v = impact_value(n)
            if v is None: E.append(f"影響標籤「{n}」無數據可核對，不得標示：{t}")
            elif (v > 0) != (a == "▲") or v == 0: E.append(f"影響標籤「{n}{a}」與數據方向不符：{t}")
    for n, c, ch, pc, r, d in D["index_rows"]:
        if abs(round(ch / (c - ch) * 100, 2) - pc) > 0.011: E.append(f"百分比不符：{n}")
        if "（" not in r: E.append(f"原因說明缺個股漲跌幅：{n}")
        if n in ("日經225指數", "韓國綜合股價指數", "台灣加權指數") and re.search(r"(延續|跟進|同步|呼應).{0,6}(美股|CPI|華爾街)", r):
            E.append(f"亞股原因說明不得把收盤後才發生的美國事件寫成因果：{n}")
    for n, lv, ch, nt, r, a, d in D["macro_rows"]:
        if a and abs(round(a[1] / (a[0] - a[1]) * 100, 2) - a[2]) > 0.011: E.append(f"百分比不符：{n}")
    se = D.get("sse")
    if se and abs(round(se[1] / (se[0] - se[1]) * 100, 2) - se[2]) > 0.011: E.append("百分比不符：上證綜合")
    idx = h.split("匯率、商品與利率")[0]
    if len(re.findall(r"\(\d{2}/\d{2}市場收盤\)", idx)) != 8: E.append("指數表日期標籤須8個")
    if D["ust"][2] not in ("殖利率上升", "殖利率下降", "殖利率持平"): E.append("美債升降註記")
    if "今日重點摘要" not in h or "本期重點摘要" in h: E.append("重點摘要標題須為「今日重點摘要」")
    for bad in ("主要指數變動", "資料截至"):
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
        # 已發生的事件：須有 result；法說／財報與總經且有 result 者，須登記 followups
        fu_events = {str(f.get("event") or "") for f in (D.get("followups") or []) if isinstance(f, dict)}
        for e in evs:
            past = e.get("date") < today.isoformat() or (e.get("date") == today.isoformat() and TWORD.get(e.get("time"), str(e.get("time"))) <= "07:45")
            if past and not e.get("result"): E.append(f"已發生事件須附 result：{e.get('title')}")
            if past and e.get("cat") in ("法說／財報", "總經與市場", "政策公布") and e.get("result") and not any(str(e.get("title"))[:6] in x for x in fu_events):
                E.append(f"已發生事件須在 followups 登記並於新聞／摘要分析：{e.get('title')}")
    except Exception as ex:  # noqa
        E.append(f"日曆資料錯誤：{ex}")
    fu = D.get("followups")
    if not isinstance(fu, list): E.append("缺 followups（無已發生事件時填 []）")
    hl_text = "".join(h_ + t_ for h_, t_ in D["highlight"])
    for f in fu or []:
        w, kw = f.get("where"), f.get("keyword") or ""
        if w == "news":
            i = f.get("idx")
            if not isinstance(i, int) or not 1 <= i <= len(N): E.append(f"followups 新聞編號錯誤：{f.get('event')}")
            elif not kw or kw not in N[i - 1]["title"] + "".join(N[i - 1]["bullets"]): E.append(f"followups 關鍵字不在第{i}則新聞：{f.get('event')}")
        elif w == "highlight":
            if not kw or kw not in hl_text: E.append(f"followups 關鍵字不在重點摘要：{f.get('event')}")
        elif w == "us_macro":
            um = D.get("us_macro") or {}
            if not kw or kw not in json.dumps(um, ensure_ascii=False): E.append(f"followups 關鍵字不在美國總經數據：{f.get('event')}")
        else:
            E.append(f"followups where 須為 news／highlight／us_macro：{f.get('event')}")
    if [m[0] for m in D["macro_rows"]] != MACRO: E.append("匯率、商品與利率清單須依序為：" + "、".join(MACRO))
    if "收盤／數據日" in h or h.count(">最新數據<") != 2: E.append("欄名須為「最新數據」")
    reasons = [r[4] for r in D["index_rows"]] + [D["ust"][3]] + [m[4] for m in D["macro_rows"]]
    for r in reasons:
        m = SRC.search(r)
        if m: E.append(f"原因說明不得括號註明來源：{m.group(0)}")
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
    order = ["全球盤勢一覽", "FedWatch 利率預期", "重大新聞", "主要指數", "匯率、商品與利率", "未來關注事件", "壽險業新聞"]
    pos = [h.find(f">{x}</h2>") for x in order]
    if -1 in pos or pos != sorted(pos): E.append("區塊順序須為：今日重點摘要→" + "→".join(order))
    if h.find("今日重點摘要") > pos[0]: E.append("今日重點摘要須在最上方")
    if D.get("chips") and not chips_block(): E.append("籌碼面資料日期與台股指數日期不符，區塊已略過（請確認 inst／chips 日期）")
    return E


if __name__ == "__main__":
    h, t = build(), build_text()
    open("email.html", "w", encoding="utf-8").write(h)
    open("email.txt", "w", encoding="utf-8").write(t)
    e = checks(h)
    print("html bytes", len(h.encode()), "| text bytes", len(t.encode()), "| life", [len(x[2]) for x in D["life"]])
    print("CHECKS:", "PASS" if not e else e)
    sys.exit(1 if e else 0)
