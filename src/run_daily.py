"""Daily job: make one video per post time of each enabled language and send them to Zernio.

Post times come from config.json (e.g. 08:00 and 20:00). If a time has already passed
today, it is set for tomorrow. Zernio does the posting, so the PC only needs to be on
when this script runs. Videos older than KEEP_VIDEOS_DAYS are deleted from output/.

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

from common import OUTPUT, ROOT, load_config
from make_video import make_video, mark_used
from publish import publish

KEEP_VIDEOS_DAYS = 14


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

    clean_old_videos()
    config = load_config()
    print(f"Publish mode: {config['publish_mode']}"
          + ("  (PUBLIC posts!)" if config["publish_mode"] == "schedule" else "  (nothing goes public)"))
    for lang, lang_cfg in config["languages"].items():
        if not lang_cfg.get("enabled", True):
            continue
        picked = []
        for post_time in lang_cfg["post_times"]:  # one new video per post time
            info = make_video(lang, exclude=picked)
            picked.append(info["topic_id"])
            if args.no_publish:
                continue
            info["post_time"] = next_post_time(post_time, config["timezone"], config.get("post_time_jitter_minutes", 0))
            publish(info, dry_run=args.dry_run)
            if not args.dry_run:
                # only a topic that really reached Zernio counts as used, so a failure never skips
                # a topic and a partial failure never posts the same topic twice
                mark_used(lang, info["topic_id"])


if __name__ == "__main__":
    main()
