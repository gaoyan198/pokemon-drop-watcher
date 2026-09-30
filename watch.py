#!/usr/bin/env python3
"""Pokemon drop watcher: Lazada restocks + Pokemon Center SG announcements -> Telegram.

Stdlib only, built to run inside GitHub Actions. State (what was in stock / already
seen) lives in state.json, which the workflow carries between runs via actions/cache.

  python watch.py                  # one pass over everything
  python watch.py --until 13:25    # poll Lazada every `interval_s` until 13:25 local
  python watch.py --test           # send a test Telegram message
"""
import argparse
import hashlib
import html
import json
import os
import random
import re
import time
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

def telegram(text, button=None):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        log(f"(no telegram creds) {text}")
        return
    payload = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
    if button:
        payload["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": button[0], "url": button[1]}]]})
    data = urllib.parse.urlencode(payload).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=15)
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
    seen = state.setdefault("lazada", {})
    for search in CONFIG["lazada"]:
        try:
            items = lazada_items(search)
        except Exception as e:  # noqa: BLE001
            log(f"lazada '{search['query']}': {e}")
            warn_once(state, f"lazada-error-{search['query']}", f"⚠️ Lazada check failing: {e}")
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


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", help="keep polling Lazada until HH:MM local time")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    if args.test:
        telegram("✅ <b>Pokemon watcher connected</b>\nYou'll get drops here.",
                 ("Pokémon Store on Lazada", "https://www.lazada.sg/shop/pokemon-store-online-singapore/"))
        return

    state = load_state()
    check_pages(state)
    check_lazada(state)
    state["baselined"] = True
    STATE_FILE.write_text(json.dumps(state, indent=1))

    if args.until:
        h, m = map(int, args.until.split(":"))
        end = datetime.now(TZ).replace(hour=h, minute=m, second=0, microsecond=0)
        interval = CONFIG.get("interval_s", 20)
        while datetime.now(TZ) < end:
            time.sleep(interval + random.uniform(0, interval * 0.25))
            check_lazada(state)
            STATE_FILE.write_text(json.dumps(state, indent=1))


if __name__ == "__main__":
    main()
