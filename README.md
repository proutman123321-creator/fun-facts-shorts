# Fun Facts Shorts

Makes vertical "3 crazy facts about ___ (+ a bonus)" videos (real stock footage, AI voice,
animated captions) and sends the same video to TikTok + Instagram through **Zernio**.

- Each video is **just over 1 minute** (61–70 s), so it can count for TikTok's Creator Rewards (videos over 1 minute).
- Each language has **its own accounts** (an English account, later maybe a French account).
- Right now: **English only**, 2 videos a day posted around **08:00** and **20:00** (Paris time, a few random
  minutes off), on TikTok `fun_fact_for_real` and Instagram `funfact_for_real`.
- Each video has its own caption with keywords and 5 hashtags (Instagram's maximum since December 2025).

## Video style (what each video looks like)
- **Hook (first ~3 s):** a short surprising line, shown big on screen from the first frame and spoken right away
  ("White chocolate isn't really chocolate. Wait for number three."). Each topic has its own `hook`.
- **#1, #2, #3, BONUS:** a new shot, a short flash and a zoom "punch" exactly when each fact starts;
  before the bonus, a call to comment ("comment the one you didn't know").
- **Montage:** shots of 1.5–3.4 s (faster during the hook), each with its own camera move (zooms, pans,
  punch-in, tilt, handheld), about 1 in 4 in slow motion. Only real footage that matches the topic
  (no cartoons, fair rides, fashion portraits or very dark clips).
- **Captions:** word by word, the spoken word in yellow; kept away from the app's buttons and bottom text.
- **Voice:** slightly slowed (−4% to −10%) when a text is short, so the voice fills the minute.
- **Music:** a royalty-free track from `assets\music`, chosen by mood for the topic's category
  (`assets\music\moods.json`), started after its quiet intro at a different point each time, at the same
  quiet level for every track, and dipping automatically while the voice speaks. Final sound at about −14 LUFS.
  Tracks shorter than the video are skipped. Add or move tracks between moods any time (then push to GitHub).

## The one-year plan
- `topic_plan.json`: **730 topics** (2 a day from 30 Oct 2026 to 29 Oct 2027) in 13 categories
  (Animals 120, History 80, Space 70, Human body 70, Science 60, Places 60, Food 50, Ocean 50,
  Inventions 50, Plants 40, Records 30, Words 30, Psychology 20), mixed so the same category never comes twice in a row.
- `content\`: the written topics (a hook + 4 facts each: 3 + bonus). Months 1 and 2 (120 topics) are written;
  the weekly task "Fun facts - write next topics" (Claude, every Monday) writes the next ones automatically.
- `topics.json`: what the videos are made from. Rebuild it after adding content: `.venv\Scripts\python src\add_content.py`
- When fewer than 14 topics are left, the run log shows a warning: ask Claude to write the next month.

---

## Runs in the cloud (your PC can stay off)

Everything runs on **GitHub Actions**, in the private project
https://github.com/proutman123321-creator/fun-facts-shorts

- Every day at **04:00 UTC** (05:00 Paris in winter, 06:00 in summer; GitHub can start a little late),
  GitHub makes the 2 videos and sends them to Zernio for 08:00 and 20:00. Zernio publishes them.
- Your keys are stored as **Secrets** in the project: Settings → Secrets and variables → Actions
  (`ZERNIO_API_KEY`, `PIXABAY_API_KEY`). GitHub never shows them again, not even to you.
- **See each day's run:** the project's **Actions** tab. Green = OK, red = problem (GitHub also emails you).
  Click a run → **Artifacts** → `videos` to download that day's videos and log (kept 7 days).
- **Test by hand:** Actions → "Daily fun facts videos" → **Run workflow** → choose
  `no-publish` (only make videos), `dry-run` (show what would be sent) or `run` (the real thing).
- Used topics are saved back into `state.json` in the project after each real run.
- **Backup run at 06:30 UTC:** if GitHub skipped the first run, the backup sends the day's videos.
  Each slot is remembered once sent, so nothing is ever posted twice.
- **Automatic check:** every morning the job asks Zernio how the previous posts went. If one failed
  on TikTok or Instagram (for example an expired connection), the run turns red and GitHub emails you.
  Then open the Zernio dashboard and reconnect the account.
- **Telegram alerts** (bot @Fun_Facts_alertes_bot): a message when each video is scheduled, when it
  goes live (with the TikTok / Instagram links), and when anything fails. A second job,
  "Check posts and alert on Telegram", runs every 30 minutes around the posting times (about 20 seconds each).
  The bot token is the GitHub Secret `TELEGRAM_BOT_TOKEN`; your chat id is `telegram_chat_id` in `config.json`.
  Test from the PC: `.venv\Scripts\python src\notify.py test`
- Temporary problems (network, Zernio busy, Pixabay down, voice service hiccup) are retried
  automatically; if no clips can be found, the video uses the plain colored background instead.
- Cost: free (about 750 of the 2,000 free minutes per month for private projects: ~9 min a day for
  the videos, ~16 one-minute post checks a day).
- Nothing runs from the PC anymore: `3-run-now.bat` and `4-turn-on-daily-schedule.bat` are disabled on
  purpose, because the PC's list of used topics is out of date and would post videos twice.
- After changing files on the PC (config, new content), send them to GitHub:
  `git add -A`, `git commit -m "update"`, `git pull --rebase`, `git push` (or ask Claude).

---

## Safety first

- **Current mode: public.** `config.json` has `"publish_mode": "schedule"`: videos are posted publicly
  at the post times without asking.
- To pause public posting, set `"publish_mode": "draft"` (and push it to GitHub):
  - TikTok: the video then lands in your **TikTok app inbox**. You finish and post it yourself.
  - Instagram: the video is saved as a **draft in your Zernio dashboard**.
- To stop everything: GitHub → Actions → "Daily fun facts videos" → ⋯ → **Disable workflow**.
- Your keys live only in the `.env` file on your PC (never uploaded) and in GitHub Secrets.
  Never paste them in a chat or send them to anyone.

---

## One-time setup (about 15 minutes)

### 1. Create your Zernio account
1. Go to https://zernio.com and sign up. It's free for your first 2 accounts (TikTok + Instagram).
2. In the dashboard, **connect TikTok** and **connect Instagram**.
   - Instagram must be a **Business** or **Creator** account (Instagram app → Settings → Account type).
3. Go to **API keys**, then **Create API key**. Copy it. It starts with `sk_` and is shown only once.

### 2. Put your key in the `.env` file
1. In this folder, copy `.env.example` and rename the copy to `.env`.
2. Open `.env` with Notepad and replace `paste-your-key-here` with your key. Save.

### 3. Get a free Pixabay key (video clips)
1. Create a free account at https://pixabay.com, then open https://pixabay.com/api/docs/ while logged in.
   Your key is shown on that page (look for **"Your API key"**).
2. Paste it in `.env` on the `PIXABAY_API_KEY=` line. Save.
   A Pexels key (`PEXELS_API_KEY`) also works, if Pexels reopens new keys.
   Without a key, videos use the plain colored background instead of real footage.

### 4. Put your account IDs in `config.json`
1. Double-click **`2-show-accounts.bat`**. It lists your connected accounts, for example:
   `tiktok   yourname   id = 66b2e19d8c3f...`
2. In `config.json`, paste each `id` under the language of that account, in `"accounts"`.
   (These IDs are not secret. Only the keys in `.env` are.)

---

## Daily use

| Double-click | What it does |
|---|---|
Everything runs on GitHub (see "Runs in the cloud" above). The PC files are only for tests:

| Double-click | What it does |
|---|---|
| `1-make-test-video.bat` | Makes the next 2 videos in `output\` to look at. Sends nothing, uses up no topic. |
| `2-show-accounts.bat` | Shows your Zernio accounts and their IDs. |
| `3-run-now.bat`, `4-turn-on-daily-schedule.bat` | Disabled (GitHub does it; running them could post twice). |
| `5-turn-off-daily-schedule.bat` | Removes the old PC schedule, if it was ever turned on again. |

---

## Changing things (all in `config.json`)

- **More videos per day:** add times to `"post_times"`, for example `["08:00", "20:00"]`. Each time gets a new video.
- **Adding the French account later:**
  1. Connect the French TikTok + Instagram in Zernio (accounts 3 and 4 cost $6/month each on Zernio).
  2. Run `2-show-accounts.bat` and paste their IDs in `config.json` under `"fr"` → `"accounts"`.
  3. Set `"enabled": true` for `"fr"`.
- **Hashtags:** every caption = the topic's 4 hashtags (`"hashtags"` in `content\*.json`) + `#funfacts`
  (`"hashtags"` of the language in `config.json`). Keep the total at 5 (Instagram's limit).
- **Hook template, ending, captions:** `"hook"` (`{teaser}` = the topic's hook), `"outro"`, `"caption"` of the language.
- **Voices:** e.g. `en-US-AvaNeural`, `en-GB-RyanNeural`, `fr-FR-DeniseNeural`, `fr-FR-VivienneMultilingualNeural`.
- **Minimum length:** `"min_seconds"` (61). The voice slows a little to reach it; any rest is a short end card.
- **New topics:** add a file in `content\` (same format as `month02.json`: `id` from `topic_plan.json`, `hook`
  (6–10 words, teasing fact 3), `keywords`, `hashtags`, 4 `facts` of 45–60 words), then run `src\add_content.py`.
  Topics are used once, in plan order (`state.json`). The weekly task writes them automatically.
  `keywords` are English words used to find matching stock clips (be specific: `"octopus underwater"`, not `"octopus"`).
- **Music:** add tracks to `assets\music` and list them under a mood in `assets\music\moods.json`.

## Disk space
- Downloaded clips (`assets\clips\`) not used for 30 days are deleted automatically.
- Finished videos (`output\`) are deleted after 14 days (they are already on Zernio). Each is about 30–40 MB.

## Good to know
- TikTok asks creators to label AI-generated content. The voice is AI, so turn on the "AI-generated" label when you finish a draft in the app.
- TikTok Creator Rewards needs a personal account, 10,000 followers and 100,000 views in 30 days, and only pays for videos over 1 minute.
- Limits: TikTok drafts max 5 waiting in the inbox. TikTok max 15 posts/day, Instagram 100/day.
- One video takes about 2–4 minutes to make on this PC.
- Tools used: Python (in `.venv`), FFmpeg (installed with winget), edge-tts (Microsoft's free online voices, needs internet), Pillow.

## Files
```
config.json          settings (mode, languages, accounts, times, voices, texts, hashtags)
topic_plan.json      the 730 topics for one year, in posting order
content/             the written topics (hook + 3 facts + bonus each)
assets/music/        royalty-free background tracks + moods.json (which mood for which category)
assets/fonts/        the free caption font (Archivo Black, SIL OFL)
topics.json          built from content/, used to make the videos
.env                 YOUR keys (you create it, never shared)
src/make_video.py    builds one video
src/footage.py       finds stock clips and makes the montage
src/publish.py       sends a video to Zernio
src/run_daily.py     does everything for each enabled language
src/build_plan.py    rebuilds topic_plan.json
src/add_content.py   rebuilds topics.json from content/
output/              the finished videos
```
