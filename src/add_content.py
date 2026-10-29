"""Merge written topics from content/*.json into topics.json, in the order of topic_plan.json.

Each content file is a list of {"id", "keywords", "hashtags", "facts": [3 facts + 1 bonus]} (English).
Also checks every topic and estimates its spoken length. Run: python src/add_content.py
"""
import json
import sys

from common import ROOT, load_config, load_json, save_json

WORDS_PER_SECOND = 2.76  # measured with the en-US-AndrewNeural voice at -8%


def main():
    lang = "en"
    lang_cfg = load_config()["languages"][lang]
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

    topics, short = [], []
    for p in plan:
        item = written.get(p["id"])
        if not item:
            continue
        topics.append({"id": p["id"], "category": p["category"], "title": {lang: p["title"]},
                       "keywords": item["keywords"], "hashtags": {lang: item["hashtags"]},
                       "facts": {lang: item["facts"]}})
        script = " ".join([lang_cfg["hook"].format(title=p["title"]), *lang_cfg["fact_labels"],
                           *item["facts"], lang_cfg["outro"]])
        seconds = len(script.split()) / WORDS_PER_SECOND + 4 * 0.35
        if seconds < 58:
            short.append(f"  {p['id']}: about {seconds:.0f}s")
    save_json(ROOT / "topics.json", topics)
    print(f"topics.json: {len(topics)} topics written out of {len(plan)} planned.")
    if short:
        print("Shorter than ~58s spoken (the end card will be held longer):\n" + "\n".join(short))


if __name__ == "__main__":
    main()
