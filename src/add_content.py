"""Merge written topics from content/*.json into topics.json, in the order of topic_plan.json.

Each content file is a list of {"id", "hook", "keywords", "hashtags", "facts": [3 facts + 1 bonus]} (English).
Also checks every topic and estimates its spoken length. Run: python src/add_content.py
"""
import json
import sys

from common import ROOT, load_config, load_json, save_json

WORDS_PER_SECOND_AT_0 = 3.0  # en-US-AndrewNeural at normal speed (same value as make_video.py)


def main():
    lang = "en"
    config = load_config()
    lang_cfg = config["languages"][lang]
    min_seconds = config.get("min_seconds", 61)
    plan = load_json(ROOT / "topic_plan.json")
    plan_ids = {p["id"]: p for p in plan}

    written, problems = {}, []
    for path in sorted((ROOT / "content").glob("*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            if item["id"] not in plan_ids:
                problems.append(f"{path.name}: '{item['id']}' is not in topic_plan.json")
            elif len(item["facts"]) != 4:
                problems.append(f"{item['id']}: needs exactly 4 facts (3 + bonus)")
            elif item["id"] in written:
                problems.append(f"{item['id']}: written twice")
            written[item["id"]] = item
    if problems:
        sys.exit("\n".join(problems))

    topics, short, problems_late = [], [], []
    for p in plan:
        item = written.get(p["id"])
        if not item:
            continue
        topics.append({"id": p["id"], "category": p["category"], "title": {lang: p["title"]},
                       "keywords": item["keywords"], "hashtags": {lang: item["hashtags"]},
                       "facts": {lang: item["facts"]}, **({"hook": {lang: item["hook"]}} if item.get("hook") else {})})
        # same hook as the video (older topics without one use the first sentence of fact 3)
        teaser = item.get("hook") or item["facts"][2].split(". ")[0].rstrip(".!?") + "."
        if len(teaser.split()) > 12:
            problems_late.append(f"  {p['id']}: hook is {len(teaser.split())} words (max 12)")
        script = " ".join([lang_cfg["hook"].format(title=p["title"], teaser=teaser), *lang_cfg["fact_labels"],
                           *item["facts"], lang_cfg["outro"]])
        frozen = end_card_seconds(len(script.split()), lang_cfg, min_seconds)
        if frozen > 3:
            short.append(f"  {p['id']}: about {frozen:.0f}s of frozen end card")
    save_json(ROOT / "topics.json", topics)
    print(f"topics.json: {len(topics)} topics written out of {len(plan)} planned.")
    if problems_late:
        sys.exit("Hooks too long:\n" + "\n".join(problems_late))
    if short:
        print("Too short for a full minute of voice (add a sentence to some facts):\n" + "\n".join(short))


def end_card_seconds(words, lang_cfg, min_seconds):
    """Same rule as the video: the voice may slow down to -10% to reach the minute; whatever is still
    missing is shown as a frozen end card. Returns those frozen seconds."""
    gaps, tail = 0.35 * 5, 1.2
    base = int(lang_cfg.get("rate", "+0%").rstrip("%"))
    needed = round((words / (WORDS_PER_SECOND_AT_0 * (min_seconds - tail - gaps)) - 1) * 100)
    rate = max(-10, min(base, needed))
    voice = words / (WORDS_PER_SECOND_AT_0 * (1 + rate / 100)) + gaps
    return min_seconds - voice


if __name__ == "__main__":
    main()
