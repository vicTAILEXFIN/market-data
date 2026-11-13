import json, urllib.request, re
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read()
try:
    d = json.loads(get("https://api.nasdaq.com/api/ipo/calendar?date=2026-11"))
    data = d.get("data") or {}
    print("NASDAQ keys", list(data))
    for sec in ("upcoming", "priced", "filed"):
        blk = data.get(sec) or {}
        rows = (blk.get("upcomingTable") or blk).get("rows") if isinstance(blk, dict) else None
        rows = rows or (blk.get("rows") if isinstance(blk, dict) else None) or []
        print(sec, len(rows))
        for r in rows:
            if "nthrop" in json.dumps(r): print("  ANT", r)
        if rows: print("  sample", rows[0])
except Exception as e:
    print("NASDAQ fail", e)
try:
    x = get("https://news.google.com/rss/search?q=Anthropic+IPO+when:7d&hl=en-US&gl=US&ceid=US:en").decode()
    t = re.findall(r"<item><title>(.*?)</title>.*?<pubDate>(.*?)</pubDate>", x)
    print("GNEWS", len(t)); [print("  ", a[:110], "|", b) for a, b in t[:6]]
except Exception as e:
    print("GNEWS fail", e)
try:
    import yfinance as yf
    for s in ("NVDA", "2330.TW", "CRWV"):
        t = yf.Ticker(s)
        print("YF", s, t.calendar.get("Earnings Date") if isinstance(t.calendar, dict) else t.calendar)
except Exception as e:
    print("YF fail", e)
