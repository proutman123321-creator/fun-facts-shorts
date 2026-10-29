"""Daily job: make one video per post time of each enabled language and send them to Zernio.

Post times come from config.json (e.g. 08:00 and 20:00), shifted by a few random minutes.
Zernio does the posting, so the computer only needs to run this once a day.

Safety:
- each slot ("2026-10-30 08:00") is remembered in state.json once sent, so a second run
  the same day (backup schedule, manual re-run) never sends it twice;
- a topic only counts as used once it really reached Zernio;
- every run first asks Zernio how the previous posts went. If one failed on TikTok or
  Instagram, today's videos are still sent, then the run ends with an error so GitHub
  emails you.

Usage:
    python src/run_daily.py              # make + send
    python src/run_daily.py --no-publish # only make the videos
    python src/run_daily.py --dry-run    # make the videos, show what would be sent
"""
import argparse
import random
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import notify
from common import OUTPUT, ROOT, STATE_FILE, load_config, load_json, save_json
from make_video import make_video
from publish import api, post_problems, publish

KEEP_VIDEOS_DAYS = 14
KEEP_SLOT_DAYS = 7
KEEP_POSTS = 30


def clean_old_videos():
    """Delete finished videos after a while (they are on Zernio already); keep their info.json."""
    limit = time.time() - KEEP_VIDEOS_DAYS * 24 * 3600
    for video in OUTPUT.glob("*/video.mp4"):
        if video.stat().st_mtime < limit:
            video.unlink()


def next_post_time(hhmm, timezone, jitter_minutes=0):
    """Today's post time, shifted by a random few minutes so posts don't look scheduled.

    If that time has already passed (e.g. GitHub started the job very late), post in about
    15 minutes instead of tomorrow, so tomorrow's run never ends up with two videos in one slot.
    """
    now = datetime.now(ZoneInfo(timezone))
    hour, minute = map(int, hhmm.split(":"))
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    when += timedelta(minutes=random.randint(-jitter_minutes, jitter_minutes))
    if when <= now + timedelta(minutes=10):
        when = now + timedelta(minutes=random.randint(15, 25))
    return when.strftime("%Y-%m-%dT%H:%M:00")


def slot_done(lang, slot):
    return slot in load_json(STATE_FILE, {}).get("slots", {}).get(lang, {})


def record_sent(lang, topic_id, slot, post_ids, when, title=None):
    """Remember that this topic and this slot were sent to Zernio (state.json is saved by GitHub)."""
    state = load_json(STATE_FILE, {})
    state.setdefault(lang, []).append(topic_id)
    slots = state.setdefault("slots", {}).setdefault(lang, {})
    slots[slot] = topic_id
    oldest = (datetime.now() - timedelta(days=KEEP_SLOT_DAYS)).strftime("%Y-%m-%d")
    for old in [s for s in slots if s < oldest]:
        del slots[old]
    posts = state.setdefault("posts", [])
    posts += [{"id": pid, "lang": lang, "topic": topic_id, "title": title, "when": when} for pid in post_ids if pid]
    state["posts"] = posts[-KEEP_POSTS:]
    save_json(STATE_FILE, state)


def check_previous_posts(timezone):
    """Ask Zernio how posts that should be live by now went. Returns a list of problems."""
    state = load_json(STATE_FILE, {})
    now = datetime.now(ZoneInfo(timezone)).replace(tzinfo=None)
    problems = []
    for post in state.get("posts", []):
        if post.get("checked"):
            continue
        due = datetime.fromisoformat(post["when"])
        if now < due + timedelta(minutes=30):
            continue  # not supposed to be live yet
        try:
            finished, issues = post_problems(post["id"])
        except SystemExit as e:
            problems.append(f"{post['topic']} ({post['when']}): could not check it on Zernio: {e}")
            continue
        if issues:
            problems += [f"{post['topic']} ({post['when']}): {i}" for i in issues]
            post["checked"] = True
        elif finished:
            post["checked"] = True
        elif now > due + timedelta(hours=3):
            problems.append(f"{post['topic']} ({post['when']}): still not published 3 hours later")
            post["checked"] = True
    save_json(STATE_FILE, state)
    return problems


def check_accounts(config):
    """Ask Zernio whether every configured account can still post. Returns a list of problems.

    Also warns 7 days before a connection that does not renew itself expires (Instagram: about 60 days).
    """
    problems = []
    for lang, lang_cfg in config["languages"].items():
        if not lang_cfg.get("enabled", True):
            continue
        for platform, account_id in lang_cfg.get("accounts", {}).items():
            if not account_id:
                continue
            try:
                _, h = api("GET", f"/accounts/{account_id}/health")
            except SystemExit as e:
                problems.append(f"{platform} ({lang}): could not check the connection on Zernio: {e}")
                continue
            token = h.get("tokenStatus") or {}
            if not h.get("permissions", {}).get("canPost", h.get("canPost", True)) or h.get("needsReconnect") \
                    or h.get("status") not in (None, "healthy"):
                problems.append(f"{platform} ({lang}): Zernio can no longer post ({h.get('status')}, "
                                f"{h.get('disconnectReason') or 'no reason given'}). Reconnect it in the Zernio dashboard.")
            elif token.get("expiresAt") and token.get("expiresIn") != "Auto-refreshes":
                expires = datetime.fromisoformat(token["expiresAt"].replace("Z", "+00:00"))
                if expires - datetime.now(expires.tzinfo) < timedelta(days=7):
                    problems.append(f"{platform} ({lang}): the connection expires on {expires:%Y-%m-%d}. "
                                    f"Reconnect it in the Zernio dashboard before then (1 minute).")
    return problems


class Tee:
    """Print to the screen and also append to run-log.txt (useful for the scheduled task)."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for s in self.streams:
            s.write(text)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    log = open(ROOT / "run-log.txt", "a", encoding="utf-8")
    sys.stdout = sys.stderr = Tee(sys.__stdout__, log)
    print(f"\n===== {datetime.now():%Y-%m-%d %H:%M} =====")
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    real_run = not (args.no_publish or args.dry_run)

    clean_old_videos()
    config = load_config()
    timezone = config["timezone"]
    print(f"Publish mode: {config['publish_mode']}"
          + ("  (PUBLIC posts!)" if config["publish_mode"] == "schedule" else "  (nothing goes public)"))

    problems = (check_accounts(config) + check_previous_posts(timezone)) if real_run else []
    for p in problems:
        print(f"PROBLEM: {p}")
    if problems:
        notify.send("❌ À vérifier :\n- " + "\n- ".join(problems))
        (ROOT / "telegram-alert-sent").touch()  # so GitHub doesn't send a second, vaguer alert

    today = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d")
    for lang, lang_cfg in config["languages"].items():
        if not lang_cfg.get("enabled", True):
            continue
        picked = []
        for post_time in lang_cfg["post_times"]:  # one new video per post time
            slot = f"{today} {post_time}"
            if real_run and slot_done(lang, slot):
                print(f"[{lang}] {slot} was already sent today, skipping.")
                continue
            info = make_video(lang, exclude=picked)
            picked.append(info["topic_id"])
            if args.no_publish:
                continue
            info["post_time"] = next_post_time(post_time, timezone, config.get("post_time_jitter_minutes", 0))
            post_ids = publish(info, dry_run=args.dry_run)
            if real_run:
                # only a topic that really reached Zernio counts as used, so a failure never skips
                # a topic and a partial failure never posts the same topic twice.
                # Drafts are never "published", so only scheduled posts are checked later.
                tracked = post_ids if config["publish_mode"] == "schedule" else []
                record_sent(lang, info["topic_id"], slot, tracked, info["post_time"], info["title"])
                if config["publish_mode"] == "schedule":
                    notify.send(f"🎬 Programmée : 3 crazy facts about {info['title']}\n"
                                f"🕗 {info['post_time'][11:16]} ({info['seconds']:.0f} s) sur TikTok + Instagram")

    if problems:
        print("\nToday's videos were sent, but something needs your attention (see PROBLEM lines above). "
              "Check the Zernio dashboard: you may need to reconnect TikTok or Instagram.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except (Exception, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code in (0, 1, None):
            raise  # normal end, or problems already sent to Telegram
        notify.send(f"❌ Le job vidéo a échoué : {str(e)[:500]}\n\nLes vidéos du créneau concerné ne sont pas parties. "
                    f"Le passage de secours réessaiera, sinon dis-le à Claude.")
        (ROOT / "telegram-alert-sent").touch()
        raise
