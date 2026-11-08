"""Full audit of Fun Facts For Real (copied from Hidden Bible Facts, adapted).

Full audit of the channel (checklist of CHANNEL-BLUEPRINT.md section 7). Prints one line per check and
the number of problems at the end. Fix, then run again until it says 0.

Run from the project folder (needs .env for the Zernio checks and GitHub CLI for the GitHub checks):
    .venv\\Scripts\\python.exe tools\\audit.py
"""
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from common import load_config, load_env, load_json  # noqa: E402

problems = []


def check(name, ok, detail=""):
    print(f"{'OK  ' if ok else 'FAIL'} {name}{': ' + str(detail) if detail else ''}")
    if not ok:
        problems.append(name)


def gh(*args):
    exe = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
    out = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8")
    return out.returncode, out.stdout.strip()


def repo_name():
    url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], capture_output=True, text=True).stdout
    return re.search(r"github\.com[/:](?:[^@/]+@)?([^/]+/[^/.]+)", url.replace("@github.com", "/github.com")).group(1) \
        if "github.com" in url else ""


def audit_github():
    print("\n== GitHub")
    repo = re.sub(r"^.*github\.com/", "", subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                                                          capture_output=True, text=True).stdout.strip()).removesuffix(".git")
    code, out = gh("api", f"repos/{repo}", "--jq", ".private")
    check("repository is public (unlimited free Actions minutes)", code == 0 and out == "false", repo)
    code, out = gh("secret", "list", "-R", repo)
    names = {line.split()[0] for line in out.splitlines() if line.strip()}
    check("secrets present", {"ZERNIO_API_KEY", "PIXABAY_API_KEY", "TELEGRAM_BOT_TOKEN"} <= names, sorted(names))
    code, out = gh("workflow", "list", "-R", repo)
    check("both workflows active", out.count("active") >= 2 and "disabled" not in out)
    code, out = gh("run", "list", "-R", repo, "--workflow", "daily.yml", "--limit", "1", "--json", "conclusion",
                   "-q", ".[0].conclusion")
    check("last daily run succeeded", out == "success", out)
    daily = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    notify = (ROOT / ".github/workflows/notify.yml").read_text(encoding="utf-8")
    check("daily: main + backup cron", len(re.findall(r'- cron: "', daily)) == 2)
    check("fixed runner ubuntu-24.04", "ubuntu-latest" not in daily + notify and (daily + notify).count("ubuntu-24.04") == 2)
    main_ref = r"ref: (main|\$\{\{ github\.event_name == 'workflow_dispatch' && github\.ref_name \|\| 'main' \}\})"
    check("checkout of the latest main (a manual test may use its branch)",
          len(re.findall(main_ref, daily)) == 1 and len(re.findall(main_ref, notify)) == 1)
    check("state saved even if the job fails", "if: always() && (github.event.inputs.mode" in daily)
    check("posts_log.jsonl saved with state", "posts_log.jsonl" in daily)
    check("Telegram alert if the job crashes", "Telegram alert if the job failed" in daily)
    check("artifacts kept 3 days max", re.search(r"retention-days: ([0-9]+)", daily) and
          int(re.search(r"retention-days: ([0-9]+)", daily).group(1)) <= 3)
    check("concurrency groups", "concurrency:" in daily and "concurrency:" in notify)
    hist = subprocess.run(["git", "-C", str(ROOT), "log", "-p", "--all"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout
    leaks = re.findall(r"sk_[A-Za-z0-9]{12,}|[0-9]{8,}:AA[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{20,}", hist)
    check("no key in git history", not leaks, len(leaks))
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split()
    ignored = subprocess.run(["git", "-C", str(ROOT), "check-ignore", ".env"], capture_output=True, text=True).returncode == 0
    check(".env ignored and not tracked", ignored and ".env" not in tracked)
    # timing: the daily job (about 25 min with the AI voice, GitHub may start it late) must end before the earliest post,
    # and the post checker must run around every post time, in winter (UTC+1) and summer (UTC+2)
    cfg = load_config()
    jitter = cfg.get("post_time_jitter_minutes", 0)
    hours = {int(h) for h in re.search(r'cron: "\*/30 ([0-9,\-]+) ', notify).group(1).replace("-", ",").split(",")}
    span = re.search(r'cron: "\*/30 ([0-9,\-]+) ', notify).group(1)
    covered = set()
    for part in span.split(","):
        a, _, b = part.partition("-")
        covered |= set(range(int(a), int(b or a) + 1))
    ok = True
    for offset in (1, 2):
        for t in cfg["languages"]["en"]["post_times"]:
            h, m = map(int, t.split(":"))
            for delta in (-jitter, 0, jitter, jitter + 60):  # until an hour after the latest post time
                utc = (h * 60 + m + delta - offset * 60) // 60 % 24
                ok &= utc in covered
    check("post checker runs around every post time (winter and summer)", ok, f"UTC hours {sorted(covered)}")
    cron = re.search(r'cron: "([0-9]+) ([0-9]+) \* \* \*"', daily)
    start = int(cron.group(2)) * 60 + int(cron.group(1))
    # night posts (before 06:00) are made by the run of the day before: only day posts count here
    day_times = [t for t in cfg["languages"]["en"]["post_times"] if t >= "06:00"]
    earliest = min(int(t[:2]) * 60 + int(t[3:]) for t in day_times) - jitter - 120  # summer
    check("daily job has 1 h margin before the earliest post", earliest - start >= 60, f"{earliest - start} min")


def audit_config_and_code():
    print("\n== Config and code")
    cfg = load_config()
    en = cfg["languages"]["en"]
    check("public mode (schedule)", cfg["publish_mode"] == "schedule")
    ZoneInfo(cfg["timezone"])
    times = sorted(int(t[:2]) * 60 + int(t[3:]) for t in en["post_times"])
    check("post times at least 2 h apart", all(b - a >= 120 for a, b in zip(times, times[1:])), en["post_times"])
    check("TikTok and Instagram accounts set", all(en["accounts"].get(p) for p in ("tiktok", "instagram")))
    check("Telegram chat and channel name set", bool(cfg.get("telegram_chat_id")) and bool(cfg.get("channel_name")))
    check("min_seconds 61 (TikTok rewards need over 1 min)", cfg.get("min_seconds", 0) >= 61)
    bad = [p.name for p in (ROOT / "src").glob("*.py")
           if subprocess.run([sys.executable, "-m", "py_compile", str(p)]).returncode]
    check("all code compiles", not bad, bad)
    launchers = [p.name for p in ROOT.glob("*.bat")
                 if "run_daily.py" in p.read_text(errors="ignore") and "--no-publish" not in p.read_text(errors="ignore")]
    check("no PC launcher can post (would post twice)", not launchers, launchers)
    run_daily_py = (ROOT / "src/run_daily.py").read_text(encoding="utf-8")
    notify_py = (ROOT / "src/notify.py").read_text(encoding="utf-8")
    daily_yml = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    check("a broken topic is skipped, never blocks the channel", "def make_or_skip" in run_daily_py
          and "info = make_or_skip(" in run_daily_py)
    check("Telegram alert when no video was scheduled today", "check_today_scheduled()" in notify_py.split("__main__")[-1])
    check("account cut by Meta/TikTok reported within 30 min", "check_accounts_now()" in notify_py.split("__main__")[-1])
    check("exact package versions locked (constraints.txt)", (ROOT / "constraints.txt").exists()
          and "-c constraints.txt" in daily_yml)
    first_cron = re.search(r'cron: "([0-9]+) ([0-9]+) \* \* \*"', daily_yml)
    check("daily run starts by 03:00 UTC (GitHub often starts 30-60 min late)",
          bool(first_cron) and int(first_cron.group(2)) <= 3)
    check("tzdata in requirements", "tzdata" in (ROOT / "requirements.txt").read_text())
    daily = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    check("AI voice ready on GitHub (engine pinned, CPU torch, Python 3.11, models cached, reference voice)",
          "chatterbox-tts @ git+" in (ROOT / "requirements.txt").read_text() and "torch==2.6.0" in daily
          and 'python-version: "3.11"' in daily and "~/.cache/huggingface" in daily
          and (ROOT / "assets/voice/reference.wav").exists())
    footage_py = (ROOT / "src/footage.py").read_text(encoding="utf-8")
    check("stock clips capped in size (GitHub's disk and cache stay small)",
          re.search(r"^KEEP_CLIPS_MB = \d+", footage_py, re.M) is not None and "KEEP_CLIPS_MB * 1e6" in footage_py)
    check("dated topics (SEASONAL) wait for their day, whatever the number of posts a day",
          'dated.get(t["id"], today) <= today' in (ROOT / "src/make_video.py").read_text(encoding="utf-8"))
    check("local .venv ready for the .bat files", (ROOT / ".venv/Scripts/python.exe").exists())


def audit_content():
    print("\n== Content")
    cfg = load_config()["languages"]["en"]
    plan, topics = load_json(ROOT / "topic_plan.json"), load_json(ROOT / "topics.json")
    state = load_json(ROOT / "state.json", {})
    ids = [t["id"] for t in topics]
    plan_ids = [p["id"] for p in plan]
    check("730 plan topics, no duplicates", len(plan_ids) == 730 == len(set(plan_ids)))
    check("written topics: no duplicates, all in the plan", len(ids) == len(set(ids)) and set(ids) <= set(plan_ids))
    check("written topics in plan order", ids == [i for i in plan_ids if i in set(ids)])
    facts = [f for t in topics for f in t["facts"]["en"]]
    check("no fact repeated", len(facts) == len(set(facts)))
    bad = [t["id"] for t in topics if len(t["facts"]["en"]) != 4
           or not all(20 <= len(f.split()) <= 60 for f in t["facts"]["en"])]
    check("4 facts of 20-60 words each (the video length is checked by add_content.py)", not bad, bad[:5])
    bad = [t["id"] for t in topics if re.search(r'[0-9%&$"()]', t["hook"]["en"] + "".join(t["facts"]["en"]))]
    check("no digits or symbols the voice reads badly", not bad, bad[:5])
    bad = [t["id"] for t in topics if not 5 <= len(t["hook"]["en"].split()) <= 10 or "?" in t["hook"]["en"]]
    check("hooks of 6-10 words, no question", not bad, bad[:5])
    bad = [t["id"] for t in topics if len(t["hashtags"]["en"].split()) != 4 or cfg["hashtags"] in t["hashtags"]["en"]
           or not all(h.startswith("#") and h == h.lower() for h in t["hashtags"]["en"].split())]
    check("4 lowercase topic hashtags + 1 account hashtag = 5 max", not bad, bad[:5])
    used = set(state.get("en", []))
    left = [i for i in ids if i not in used]
    check("at least 30 days of topics ahead", len(left) >= 60, f"{len(left)} topics = {len(left) // 2} days")
    check("first planned topic is next", left[:1] == plan_ids[:1] or bool(used), left[:2])
    # feast days written in time: every planned topic of the next 30 days exists
    soon = [p["id"] for p in plan if date.fromisoformat(p["date"]) <= date.today() + timedelta(days=30)]
    missing = [i for i in soon if i not in set(ids)]
    check("every topic of the next 30 days is written", not missing, missing[:5])
    risky = re.compile(r"adam and eve|\bnude|naked|venus|bathsheba|susanna|saint sebastian|delilah|last judgment|"
                       r"\bdeluge|drunkenness|garden of earthly|sebastiano del piombo raising|"  # nudity
                       r"blinding|head of goliath|david and goliath|martyr|crucifixion of saint peter|burning of|"
                       r"death of jezebel|massacre|beheading|salome|judith|holofernes|flaying", re.I)  # gore
    bad = [(t["id"], s) for t in topics for s in t.get("paintings", []) if risky.search(s)]
    check("no painting search likely to show nudity or gore", not bad, bad[:5])
    bad = [t["id"] for t in topics if not isinstance(t.get("paintings", []), list)]
    check("paintings field is a list", not bad, bad)
    out = subprocess.run([sys.executable, str(ROOT / "src/add_content.py")], capture_output=True, text=True,
                         encoding="utf-8", cwd=ROOT)
    check("add_content.py: no error, no topic too short", out.returncode == 0 and "Too short" not in out.stdout,
          (out.stdout + out.stderr).strip()[-200:])
    from make_video import make_badge
    widest = max((make_badge(cfg["badge"].format(title=t["title"]["en"].upper())).width, t["id"]) for t in topics)
    check("every title fits the banner", widest[0] <= 1040, widest)
    longest = max((len(cfg["caption"].format(title=t["title"]["en"], teaser=t["hook"]["en"])) + 80, t["id"]) for t in topics)
    check("captions under 2200 characters", longest[0] < 2200, longest)


def audit_music():
    print("\n== Music")
    from make_video import MUSIC_DIR, pick_music, topic_index, track_seconds
    tracks = sorted(MUSIC_DIR.glob("*.mp3"))
    check("at least 3 tracks longer than a video (90 s)", sum(track_seconds(p) >= 90 for p in tracks) >= 3)
    moods = load_json(MUSIC_DIR / "moods.json")
    cats = {p["category"] for p in load_json(ROOT / "topic_plan.json")}
    check("every category has a mood", cats <= set(moods["categories"]), cats - set(moods["categories"]))
    check("every mood exists", set(moods["categories"].values()) <= set(moods["moods"]))
    listed = {f for v in moods["moods"].values() for f in v}
    check("every listed track exists", listed <= {p.name for p in tracks}, listed - {p.name for p in tracks})
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "assets/music"], capture_output=True, text=True).stdout
    check("tracks committed (GitHub needs them)", all(f"assets/music/{p.name}" in tracked for p in tracks))
    topics = load_json(ROOT / "topics.json")
    picks = [pick_music(t, topic_index(t["id"]), 64) for t in topics]
    seq = [p[0].name for p in picks]
    check("never the same track twice in a row", all(a != b for a, b in zip(seq, seq[1:])))
    check("music starts after its quiet intro", all(p[1] >= 8 for p in picks))
    check("no track used for most videos", max(Counter(seq).values()) <= len(seq) * 0.4, Counter(seq).most_common(1))


def audit_accounts():
    print("\n== Accounts")
    load_env()
    from publish import api
    cfg = load_config()
    for platform, account in cfg["languages"]["en"]["accounts"].items():
        try:
            _, h = api("GET", f"/accounts/{account}/health")
        except SystemExit as e:
            check(f"{platform} reachable on Zernio", False, e)
            continue
        token = h.get("tokenStatus") or {}
        check(f"{platform} healthy and can post", h.get("status") == "healthy" and h.get("permissions", {}).get("canPost"),
              h.get("status"))
        if token.get("expiresAt") and token.get("expiresIn") != "Auto-refreshes":
            left = datetime.fromisoformat(token["expiresAt"].replace("Z", "+00:00")) - datetime.now(timezone.utc)
            check(f"{platform} connection valid for over 7 days", left > timedelta(days=7), f"{left.days} days")
    run_daily = (ROOT / "src/run_daily.py").read_text(encoding="utf-8")
    check("reminders 7/3/2/1 days and 20/10/4 topics", "REMINDER_DAYS = (7, 3, 2, 1)" in run_daily
          and "REMINDER_TOPICS = (20, 10, 4)" in run_daily)
    check("Telegram reminder names the weekly task",
          "Fun facts - write next topics" in run_daily)


if __name__ == "__main__":
    for part in (audit_github, audit_config_and_code, audit_content, audit_music, audit_accounts):
        try:
            part()
        except Exception as e:  # a broken check is a problem too
            check(f"{part.__name__} ran", False, f"{type(e).__name__}: {e}")
    print(f"\n{len(problems)} problem(s)" + (": " + ", ".join(problems) if problems else ""))
    sys.exit(1 if problems else 0)
