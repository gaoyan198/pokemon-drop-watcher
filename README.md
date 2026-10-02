# pokemon-drop-watcher

Sends a Telegram message when Pokémon Center Singapore drops go live. It runs on a schedule in GitHub Actions, so nothing needs to stay running on your laptop.

| What | When | Alert |
|---|---|---|
| Lazada **Pokémon Store Online Singapore**: items matching `30th` and `elite trainer box` | every ~20s from ~12:15 to 14:00 SGT on weekdays, plus a sweep every 2h | 🟢 **IN STOCK** when an item goes from sold out to available · 🆕 new listing |
| Pokémon Center SG shop page (Jewel reservations and queue tickets) | every 2h | 📣 new text mentioning reservation / ballot / queue / ETB / 30th |

Each Lazada alert has an **Open in Lazada ⚡** button. On your phone it opens straight into the Lazada app, so you can Buy Now yourself.

It reads Lazada's public search JSON (the `inStock` flag per item). It uses only Python's standard library, with no browser and no dependencies.

## Setup (≈5 min)

1. **Create the Telegram bot.** Message [@BotFather](https://t.me/BotFather), send `/newbot` and copy the token. Send your new bot any message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id`.
2. **Push this folder as its own GitHub repo.** A **public** repo gets unlimited free Actions minutes. The repo holds no secrets, only keywords. If it's private, this schedule uses about 1,600 of the 2,000 free minutes a month.
3. **Add the secrets.** In the repo, go to Settings → Secrets and variables → Actions and add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
4. **Test it.** Go to Actions → *pokemon-watch* → Run workflow and run it once with mode `test`, which sends you a message. Then run it with mode `once`, which records what's there now so you only get alerts for changes from then on.

## Tuning

- **What it watches:** edit `config.json`. Each `lazada` entry is a search inside the official store. Add queries such as `"booster bundle"` or `"Pikachu"`.
- **Drop window:** edit `drop_window` in `config.json` (weekdays 0=Mon, SGT times). If you move it, shift the weekday crons in `.github/workflows/watch.yml` too (they're in UTC, SGT−8h).
- **Run locally:** `python3 watch.py --until 14:00` prints alerts to the terminal, or sends them to Telegram if you export the two env vars.

## Things to know

- **GitHub's scheduler can run late.** Scheduled runs often start 5–45 min late or get skipped, so six triggers fire between 12:17 and 13:32. The first one that starts inside the window polls until 14:00 and sends a silent 👀 message, so you can see it's watching. If you ever need it to the second, run `watch.py --until` locally instead.
- **Keep the repo active.** GitHub pauses scheduled workflows after 60 days with no commits. Push any small change, or re-enable it in the Actions tab.
- **Lazada blocking.** If Lazada starts blocking GitHub's servers, you get a one-time ⚠️ message in Telegram.
- **Jewel announcements often appear on Instagram first.** Turn on post notifications for the official Pokémon Singapore account as well. Reservations need SMS verification and are one per person, so register yourself as soon as the alert arrives.

## Checkout faster by hand

Stay logged into the Lazada app. Save your default address and card or PayNow beforehand. When the alert arrives, tap the button, then **Buy Now** (not Add to Cart) and pay. Stick to the per-person limit, because orders over it get cancelled.
