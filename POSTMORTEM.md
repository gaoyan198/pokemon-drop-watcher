# Postmortem: watcher was blind during the 2026-10-02 drop

**Status:** fix in progress · **Impact:** no Lazada coverage for the weekday 1–2pm drop on Oct 1 and Oct 2 · **Times:** SGT

## Summary

On Oct 2, every Lazada check from 12:39 onwards was refused with a captcha page. The watcher kept running and sent a "👀 Watching" message anyway, and the person debugging it reported that it was "checking" because the job was alive. The owner relied on it as a backup for the 1pm drop of the *30th Celebration Pokémon Center Elite Trainer Box* (item `13858018841`). The block was found at 13:02, only after the owner forwarded a "NOT FOUND" message. On Oct 1 there was no coverage either, because GitHub skipped the scheduled drop-time run.

## Timeline

| Time | Event |
|---|---|
| Sep 30, 20:38 | Setup. Test and demo Telegram messages delivered. |
| Oct 1, 12:40 | GitHub skipped the `40 4 * * *` drop-time run. The only check near the drop was one sweep at 12:48: 0 in stock. |
| Oct 2, 07:45 | Last successful Lazada search (11 "30th" items, 6 ETBs). |
| 12:35 | A local test from the Mac got a captcha. It was dismissed as a local-only problem, and GitHub's latest results weren't checked. **This was the missed early warning.** |
| 12:39 | First blocked check from GitHub. One ⚠️ was sent, and `warn_once` stayed silent after that. |
| 12:40–13:01 | Four deploys (20s polling, 10s polling, auto slow-down, pinned item). Every check in every run was blocked. Each deploy was "verified" only by seeing that the job was still running. |
| 13:01 | The pinned-item heartbeat showed "NOT FOUND", and the owner flagged it. |
| 13:02 | Logs confirmed the watcher had been blind since 12:39. A single check at 13:05 was still blocked. |
| 13:06 | Product pages (`/products/pdp-i<id>.html`) found to load fine, with stock in `"quantity":{"limit":{"max":N}}`. |
| 13:08 | Product-page checks and loud BLIND alerts deployed to GitHub. Its first check sent 🔴 BLIND: GitHub's servers are blocked from product pages too. |
| 13:09 | A check from the Mac read "in stock". The owner was told to buy, clicked immediately, and saw "Out of stock". |
| 13:11 | Found that about 1 in 4 product-page responses is a **stale cached copy** (`"max":5`, Add to Cart, no "Out of stock"). The 13:09 "in stock" was almost certainly one of these: a **false alert**. Adding a unique parameter to each request didn't avoid it. |
| 13:12 | "In stock" now requires 3 fetches in a row to agree. 12/12 live checks then correctly read "sold out". |

## Root causes

1. **Single fragile data source.** The watcher used only Lazada's unofficial store-search endpoint (`?ajax=true`). It sits behind Lazada's anti-bot system, which began refusing GitHub's servers and the Mac sometime between 07:45 and 12:39. Polling rate wasn't the cause, because even each run's first request was refused.
2. **Failures were quiet; the heartbeat was false.** `warn_once` sent one warning per search and then stayed silent until a check succeeded. The 👀 heartbeat said "Watching" whether or not any check had worked. So the main signal the owner saw said things were fine.
3. **Verification checked the process, not the result.** "The run is still in progress" was treated as "it's checking." No one confirmed that a check had returned real data.
4. **Early warning ignored.** The 12:35 captcha on the Mac was a sign the endpoint was being blocked. It was explained away rather than checked against GitHub's latest results.
5. **Changes under pressure aimed at the wrong problem.** Four deploys tuned speed and coverage while nothing was getting through at all.
6. **One reading from a cached page was trusted.** Lazada's edge servers sometimes return a stale page, and a single in-stock reading was sent to the owner as "buy now" without being confirmed.
7. **GitHub's scheduler is unreliable.** One drop-time trigger was skipped entirely on Oct 1. (Fixed on Oct 2 with six triggers across 12:17–13:32.)

## What we changed

- **Pinned product pages.** `watch_items` in `config.json` are checked directly on their product pages every cycle. In stock means `max > 0`. Store searches now run about once a minute as a secondary check.
- **Being blind is loud.** A 🔴 **BLIND** alert goes out with sound as soon as checks fail, repeats every 5 minutes, and a ✅ follows on recovery. The 👀 heartbeat is only sent after a check actually succeeded, and it shows each pinned item's name and stock status.
- **Failed runs are marked failed.** If no check succeeds during a run, the job exits with an error, so GitHub marks the run failed and emails.
- **Automatic slow-down when blocked.** Polling slows from 10s up to 60s and speeds back up gradually after recovery.

## Rules so this doesn't repeat

1. **"Working" means returned data.** It isn't verified until a real check from the real host has returned real data, such as the item name and stock status in Telegram.
2. **A heartbeat must report what was seen,** not just that the job is alive.
3. **Every way of going blind must alert, and keep alerting,** until it recovers.
4. **Any captcha or block anywhere is treated as an incident** until the production host is checked.
5. **During a live drop, the owner hears first:** "the watcher is blind, check manually." Fixes come after that.
6. **Keep a second data source** so one blocked endpoint doesn't take out everything.
7. **Confirm before saying "buy".** A single reading can be a stale cached copy; require repeated agreeing reads before alerting.

## Still open

- **GitHub's servers can't read Lazada at all right now** (search and product pages are both blocked). Polling has to move to a home connection: the owner's Mac during 12:30–14:00, run by a scheduled job on the Mac with the Telegram details stored locally.
- The 3-in-a-row confirmation hasn't been tested against a real restock. It's unknown whether a fresh in-stock page looks different from the stale copy.
- Why the search endpoint started refusing requests on the morning of Oct 2.
- Store searches can't find brand-new listings while they're blocked. Pin new product IDs in `watch_items` once they're known.
