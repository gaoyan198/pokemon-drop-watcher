#!/usr/bin/env python3
"""Pokemon drop watcher: Lazada restocks + Pokemon Center SG announcements -> Telegram.

Stdlib only, built to run inside GitHub Actions. State (what was in stock / already
seen) lives in state.json, which the workflow carries between runs via actions/cache.

  python watch.py                  # one pass over everything
  python watch.py --until 14:00    # poll Lazada every `interval_s` until 14:00 local
  python watch.py --auto           # inside `drop_window`: poll until it ends; else one pass
  python watch.py --test           # send a test Telegram message
  python watch.py --demo           # dry run: send one sample of every alert type
"""
import argparse
import hashlib
import html
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text())
STATE_FILE = ROOT / "state.json"
TZ = ZoneInfo(CONFIG.get("timezone", "Asia/Singapore"))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def log(msg):
    print(f"[{datetime.now(TZ):%H:%M:%S}] {msg}", flush=True)


def fetch(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


# ---------- telegram ----------

def telegram(text, button=None, silent=False):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        log(f"(no telegram creds) {text}")
        return
    payload = {"chat_id": chat, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": False, "disable_notification": silent}
    if button:
        payload["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": button[0], "url": button[1]}]]})
    data = urllib.parse.urlencode(payload).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage",
                                    data=data, timeout=15) as r:
            log(f"telegram sent (message_id={json.loads(r.read())['result']['message_id']})")
    except urllib.error.HTTPError as e:
        log(f"telegram failed: {e} {e.read().decode('utf-8', 'replace')}")
    except Exception as e:  # noqa: BLE001 - a failed alert must not kill the loop
        log(f"telegram failed: {e}")


# ---------- lazada ----------

def lazada_items(search):
    url = (f"https://www.lazada.sg/{search['shop']}/?ajax=true&from=wangpu&langFlag=en"
           f"&pageTypeId=2&q={urllib.parse.quote_plus(search['query'])}")
    body = fetch(url)
    if body.lstrip().startswith("<"):
        raise RuntimeError("got HTML instead of JSON (likely captcha/rate limit)")
    items = json.loads(body).get("mods", {}).get("listItems", [])
    return [i for i in items if i.get("sellerName") == search.get("seller", i.get("sellerName"))]


def check_lazada(state):
    """One pass over every search. Returns False if any search failed (blocked/error)."""
    seen = state.setdefault("lazada", {})
    ok = True
    for search in CONFIG["lazada"]:
        try:
            items = lazada_items(search)
        except Exception as e:  # noqa: BLE001
            ok = False
            log(f"lazada '{search['query']}': {e}")
            warn_once(state, f"lazada-error-{search['query']}",
                      f"⚠️ Lazada check failing: {e}\nSlowing down automatically, will speed back up when it recovers.")
            continue
        state.get("warned", {}).pop(f"lazada-error-{search['query']}", None)

        in_stock = 0
        for it in items:
            iid, stock = str(it["itemId"]), bool(it.get("inStock"))
            in_stock += stock
            prev = seen.get(iid)
            seen[iid] = stock
            if prev is None and not state.get("baselined"):
                continue  # first ever run: record, don't spam
            if (prev is None or prev is False) and stock:
                alert_item(it, "🟢 IN STOCK" if prev is False else "🆕 NEW + IN STOCK")
            elif prev is None:
                alert_item(it, "🆕 NEW LISTING (sold out for now)")
        log(f"lazada '{search['query']}': {len(items)} items, {in_stock} in stock")
    return ok


def alert_item(it, headline):
    url = "https:" + it["itemUrl"] if it["itemUrl"].startswith("//") else it["itemUrl"]
    text = (f"<b>{headline}</b>\n{html.escape(it['name'])}\n"
            f"S${it.get('price')}  ·  {datetime.now(TZ):%H:%M:%S}")
    telegram(text, ("Open in Lazada ⚡", url))


# ---------- announcement pages ----------

def page_lines(url):
    raw = fetch(url, accept="text/html")
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
    return [re.sub(r"\s+", " ", l).strip() for l in text.splitlines() if l.strip()]


def check_pages(state):
    for page in CONFIG.get("pages", []):
        try:
            lines = page_lines(page["url"])
        except Exception as e:  # noqa: BLE001
            log(f"page {page['name']}: {e}")
            continue
        pattern = re.compile("|".join(map(re.escape, page["keywords"])), re.I)
        hits = [l for l in lines if pattern.search(l)]
        known = set(state.setdefault("pages", {}).get(page["name"], []))
        fresh = [l for l in hits if hashlib.sha1(l.encode()).hexdigest()[:12] not in known]
        state["pages"][page["name"]] = sorted(known | {hashlib.sha1(l.encode()).hexdigest()[:12] for l in hits})
        log(f"page {page['name']}: {len(hits)} keyword lines, {len(fresh)} new")
        if fresh and state.get("baselined"):
            body = "\n".join(f"• {html.escape(l[:200])}" for l in fresh[:6])
            telegram(f"<b>📣 {html.escape(page['name'])} updated</b>\n{body}", ("Open page", page["url"]))


# ---------- main ----------

def warn_once(state, key, text):
    warned = state.setdefault("warned", {})
    if key not in warned:
        warned[key] = True
        telegram(text)


def demo():
    """Send one of each alert, built from live data, so you can see what they look like."""
    telegram("🧪 <b>DRY RUN</b>: the next 3 messages are samples, nothing actually dropped.")
    items = lazada_items(CONFIG["lazada"][0])
    etb = next((i for i in items if "elite trainer" in i["name"].lower()), items[0])
    alert_item(etb, "🧪 🟢 IN STOCK")
    alert_item(items[-1], "🧪 🆕 NEW LISTING (sold out for now)")
    page = CONFIG["pages"][0]
    hit = next(l for l in page_lines(page["url"]) if re.search("reservation|queue", l, re.I))
    telegram(f"<b>🧪 📣 {html.escape(page['name'])} updated</b>\n• {html.escape(hit[:200])}",
             ("Open page", page["url"]))


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def drop_window_end():
    """End time (HH:MM) if we're inside today's drop window, else None."""
    win = CONFIG.get("drop_window")
    now = datetime.now(TZ)
    if not win or now.weekday() not in win["weekdays"]:
        return None
    return win["end"] if win["start"] <= f"{now:%H:%M}" < win["end"] else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", help="keep polling Lazada until HH:MM local time")
    ap.add_argument("--auto", action="store_true", help="poll until drop_window ends if inside it")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.test:
        telegram("✅ <b>Pokemon watcher connected</b>\nYou'll get drops here.",
                 ("Pokémon Store on Lazada", "https://www.lazada.sg/shop/pokemon-store-online-singapore/"))
        return

    if args.demo:
        demo()
        return

    if args.auto:
        args.until = drop_window_end()

    state = load_state()
    check_pages(state)
    check_lazada(state)
    state["baselined"] = True
    STATE_FILE.write_text(json.dumps(state, indent=1))

    if args.until:
        h, m = map(int, args.until.split(":"))
        end = datetime.now(TZ).replace(hour=h, minute=m, second=0, microsecond=0)
        interval = CONFIG.get("interval_s", 20)
        if datetime.now(TZ) < end:
            telegram(f"👀 Watching Lazada every ~{interval}s until {args.until}", silent=True)
        # Back off when Lazada blocks us (double, capped), ease back toward the base rate once it recovers.
        cur, cap = interval, CONFIG.get("max_interval_s", 60)
        while datetime.now(TZ) < end:
            time.sleep(cur + random.uniform(0, cur * 0.25))
            prev, cur = cur, (max(interval, cur / 2) if check_lazada(state) else min(cur * 2, cap))
            if cur != prev:
                log(f"interval {prev:g}s -> {cur:g}s")
            STATE_FILE.write_text(json.dumps(state, indent=1))


if __name__ == "__main__":
    main()
