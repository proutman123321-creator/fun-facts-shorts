# Monday routine: "Fun facts - write next topics"

Reference copy of the prompt of the routine trig_015K6jsrb5fKSc766tFZWhys (claude.ai/code/routines), saved here so it can be
recreated if the routine is ever lost: cron `0 7 * * 1` (Monday 07:00 UTC), model `claude-sonnet-5-5`, source this
repository, tools `Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch`, no MCP connections, environment of the existing routines.
If you change the prompt, change it in the routine too (RemoteTrigger update) so the two stay identical.

## Prompt

You write the scripts for an automated English fun-facts video channel. This repository (fun-facts-shorts) is used by a daily GitHub Actions job that turns topics.json into 1-minute videos that are posted PUBLICLY on TikTok and Instagram. Format of each video: a short spoken hook that teases fact 3, then "Number one", "Number two", "Number three" and a bonus fact, then a call to comment and follow. Accuracy matters: a wrong fact damages the account.

STEP 1 - Is work needed?
With python3, compute: written = ids in topics.json; used = state.json["en"] (missing file or key = empty list); remaining = written ids not in used. If remaining >= 100, reply 'Enough topics: N left, nothing to do' and STOP (no commit).

STEP 2 - Choose topics.
Take the next 60 entries of topic_plan.json, in plan order (field n), whose id does not appear in any content/*.json file. Fewer if the plan ends. If none are left, say the yearly plan is complete and stop.

STEP 3 - Write content/monthNN.json (NN = next two-digit number after the existing month files, e.g. month03.json).
First read content/month02.json to copy the exact format and style (but not its fact length: month02 facts are too long). It is a JSON list of objects: {"id": <id from the plan>, "hook": "...", "keywords": [4 English stock-video search phrases], "hashtags": "4 topic hashtags", "facts": [fact 1, fact 2, fact 3, bonus fact]}.
Rules for the hook (the very first words of the video, also shown in big letters on screen and used in the post caption):
- 6 to 10 words, one short sentence, a surprising claim that makes people stop scrolling, true, and paid off by fact 3. Examples: "White chocolate isn't really chocolate.", "Your brain can't feel any pain.", "Rats laugh when you tickle them."
- No question marks, no numbers in digits, no clickbait lies.
Rules for facts:
- Exactly 4 facts per topic, each 32 to 40 words (the AI voice speaks fast: this gives videos of 61 to 68 seconds; longer facts make videos people leave), about the plan's title for that id. Fact 3 is the most surprising one and must explain the hook; the bonus is one more surprising fact.
- Prefer little-known facts: avoid the classic facts everyone has already seen in top 10 lists.
- Written for an AI voice reading aloud: numbers in words ("eighteen eighty nine", "three hundred"), no digits, no symbols (%, &, $), no double quotes, no emojis, no abbreviations, no parentheses.
- Simple, vivid, each fact understandable on its own.
- Only well-established facts. No myths presented as true, no disputed records, no medical advice, no politics, no brand promotion, no graphic violence. When science is uncertain, say so ("scientists think").
- Do not repeat a fact that already appears in another content file.
Rules for keywords (stock video searches on Pixabay):
- The first word of each phrase is the main visual subject, and at least two phrases contain the topic's main word (e.g. "octopus underwater", "octopus sea").
- Specific and visual. Avoid words with other meanings (an "octopus" search alone finds fairground rides) and avoid people unless the topic is about people.
Rules for hashtags: exactly 4 lowercase topic hashtags, e.g. "#octopus #ocean #marinelife #animalfacts", never #funfacts (Instagram allows 5 in total; #funfacts is added automatically).

STEP 4 - Fact-check every fact and every hook with WebSearch.
Check key claims (numbers, dates, names, records, superlatives) against reliable sources (encyclopedias, universities, museums, science agencies, major news outlets). If a claim is not confirmed by a reliable source, or sources disagree, rewrite it with the confirmed version or replace it. Keep a short list of what you changed.

STEP 5 - Validate.
Run: python3 src/add_content.py
It rebuilds topics.json, refuses hooks over 12 words, lists topics too short for a full minute, and lists videos over 75 seconds. For any topic YOU wrote that is listed, make its facts a little longer or shorter (staying within the rules) and run it again until none of your topics is listed and it finishes without errors. Older topics listed as long can stay as they are.

STEP 6 - Save.
Only commit content/monthNN.json and topics.json. Never change config.json, state.json, notified.json, posts_log.jsonl, topic_plan.json, assets/, src/ or .github/.
git add content topics.json
git commit -m "Add content monthNN (topics X to Y)"
git pull --rebase origin main
git push origin main
If pushing to main is refused, push to a new branch instead and say so clearly in your final message.

FINAL MESSAGE: the topic numbers and date range covered (from the plan's date field), how many facts or hooks were changed during fact-checking with two or three examples, and confirmation that the push to main succeeded.
