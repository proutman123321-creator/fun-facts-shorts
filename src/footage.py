"""Build the background montage: free stock clips (Pixabay or Pexels), cut every few seconds, slow zoom.

Clips are downloaded once into assets/clips/ and reused. Only FFmpeg is used for editing.
"""
import json
import math
import random
import os
import subprocess
import time
import urllib.parse
import urllib.request

from common import ROOT, find_ffmpeg, load_env, load_json, save_json

CLIPS = ROOT / "assets" / "clips"
SEARCH_CACHE = ROOT / "assets" / "search_cache.json"
BRIGHTNESS_CACHE = ROOT / "assets" / "clips" / "brightness.json"
CUTS_PER_CLIP = 2  # each downloaded clip gives 2 different cuts (fewer downloads)
MAX_DOWNLOAD_MB = 40
KEEP_CLIPS_DAYS = 30
W, H, FPS = 1080, 1920, 30
HEADERS = {"User-Agent": "fun-facts-shorts"}


def env_key(name):
    load_env()
    key = os.environ.get(name, "").strip()
    return "" if key.startswith("paste") else key


def get_json(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers={**HEADERS, **(headers or {})}),
                                timeout=60) as resp:
        return json.load(resp)


def search_pixabay(query, key):
    data = get_json("https://pixabay.com/api/videos/?" + urllib.parse.urlencode(
        {"key": key, "q": query, "video_type": "film", "safesearch": "true", "per_page": 20}))
    found = []
    for hit in data.get("hits", []):
        # prefer 4K (sharp after cropping to vertical) unless the file is very big
        for size in ("large", "medium"):
            f = hit["videos"].get(size) or {}
            if f.get("url") and f.get("size", 0) <= MAX_DOWNLOAD_MB * 1e6:
                found.append({"id": f"pixabay_{hit['id']}", "duration": hit.get("duration", 0),
                              "url": f["url"], "height": f.get("height", 0), "tags": hit.get("tags", "")})
                break
    return found


def search_pexels(query, key):
    data = get_json("https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
        {"query": query, "orientation": "portrait", "size": "medium", "per_page": 15}),
        {"Authorization": key})
    found = []
    for video in data.get("videos", []):
        files = [f for f in video.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
                 and f["height"] > f["width"] and f["height"] >= 1280]
        best = min(files, key=lambda f: abs(f["height"] - 1920), default=None)
        if best:
            found.append({"id": f"pexels_{video['id']}", "duration": video.get("duration", 0),
                          "url": best["link"], "height": best["height"]})
    return found


def provider():
    if env_key("PIXABAY_API_KEY"):
        return "pixabay", env_key("PIXABAY_API_KEY")
    if env_key("PEXELS_API_KEY"):
        return "pexels", env_key("PEXELS_API_KEY")
    return None, ""


def search(query, name, key):
    """Search with a 24-hour cache (required by Pixabay's terms, and saves requests)."""
    cache = load_json(SEARCH_CACHE, {})
    entry = cache.get(f"{name}:{query}")
    if entry and time.time() - entry["time"] < 24 * 3600:
        return entry["results"]
    results = (search_pixabay if name == "pixabay" else search_pexels)(query, key)
    cache[f"{name}:{query}"] = {"time": time.time(), "results": results}
    SEARCH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    save_json(SEARCH_CACHE, cache)
    return results


def clean_old_clips():
    """Delete clips not used for KEEP_CLIPS_DAYS days, so the folder doesn't keep growing."""
    if not CLIPS.exists():
        return
    limit = time.time() - KEEP_CLIPS_DAYS * 24 * 3600
    for path in CLIPS.glob("*.mp4"):
        if path.stat().st_mtime < limit:
            path.unlink()


def download(clip):
    CLIPS.mkdir(parents=True, exist_ok=True)
    path = CLIPS / f"{clip['id']}.mp4"
    if path.exists():
        os.utime(path)  # mark as recently used so the cleanup keeps it
    else:
        tmp = path.with_suffix(".part")
        with urllib.request.urlopen(urllib.request.Request(clip["url"], headers=HEADERS), timeout=600) as resp, \
                open(tmp, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        tmp.rename(path)
    return path


def find_clips(keywords, needed):
    """Return up to `needed` (path, duration) clips, taking the fact's keywords in turn.

    A search or download that fails (network, rate limit) is skipped instead of stopping the video.
    """
    name, key = provider()
    subject = subject_root(keywords)
    results = {}
    for q in keywords:
        try:
            found = [c for c in search(q, name, key) if c["duration"] >= 4]
            # best: tags mention every important word; if that leaves too few, accept any of them
            strict = [c for c in found if relevant(c, q, strict=True)]
            results[q] = strict if len(strict) >= 3 else [c for c in found if relevant(c, q, subject=subject)]
        except Exception as e:
            print(f"Clip search '{q}' failed ({type(e).__name__}), skipping it.")
            results[q] = []
    clips, used = [], set()
    while len(clips) < needed and any(results.values()):
        for q in keywords:
            while results[q]:
                clip = results[q].pop(0)
                if clip["id"] in used:
                    continue
                used.add(clip["id"])
                try:
                    path = download(clip)
                except Exception as e:
                    print(f"Clip download failed ({type(e).__name__}), trying another one.")
                    continue
                if too_dark(path):
                    continue
                clips.append((path, clip["duration"]))
                break
            if len(clips) >= needed:
                break
    return clips


# clips that look out of place on a real-facts channel (fair rides named "Octopus", cartoons, logos...)
OFF_TOPIC_TAGS = {"carousel", "fairground", "fair", "funfair", "amusement park", "ride", "cartoon", "animation",
                  "animated", "illustration", "logo", "toy", "toys", "anime", "clipart", "emoji",
                  "makeup", "make-up", "fashion", "model", "beauty", "glamour", "cosmetics", "portrait"}

PERSON_TAGS = {"woman", "women", "man", "men", "girl", "girls", "boy", "boys", "kid", "kids", "child", "children",
               "people", "person", "lady", "guy", "couple", "family", "baby", "teenager", "human", "face"}

STOP_WORDS = {"with", "from", "into", "under", "over", "slow", "motion", "close", "macro", "time", "lapse",
              "timelapse", "aerial", "view", "the", "and"}


def relevant(clip, query, strict=False, subject=""):
    """Keep a clip only if its tags mention the words of the search (e.g. 'cocoa' for 'cocoa beans'),
    so a search does not return soy beans. strict=True needs every word. Clips without tags are kept."""
    tags = clip.get("tags")
    if not tags:
        return True
    tag_list = [t.strip() for t in tags.lower().split(",")]
    tags = ", ".join(tag_list)
    if set(tag_list) & OFF_TOPIC_TAGS:
        return False
    # the first tag is the clip's main subject: skip clips about a person unless the search asks for people
    if tag_list and tag_list[0] in PERSON_TAGS and not set(query.lower().split()) & PERSON_TAGS:
        return False
    roots = word_roots(query)
    if not roots:
        return True
    if strict:
        return all(r in tags for r in roots)
    # loose: the video's subject must be there ('melted chocolate' needs chocolate, not just melting ice),
    # or the first word when the search doesn't name the subject ('cocoa beans' needs cocoa)
    return (subject if subject in roots else roots[0]) in tags


def word_roots(text):
    """First 4 letters of each meaningful word, so 'melted' matches 'melting' and 'beans' matches 'bean'."""
    return [w[:4] for w in text.lower().split() if len(w) > 2 and w not in STOP_WORDS]


def subject_root(keywords):
    """The video's subject: the word root that comes back most often in its search words."""
    roots = [r for k in keywords for r in word_roots(k)]
    return max(roots, key=roots.count) if roots else ""


def too_dark(path, limit=40):
    """True if the clip is mostly black (night shots look empty behind the captions). Result is cached."""
    cache = load_json(BRIGHTNESS_CACHE, {})
    if path.name not in cache:
        frame = subprocess.run([find_ffmpeg(), "-v", "error", "-ss", "1.5", "-i", str(path), "-frames:v", "1",
                                "-vf", "scale=16:16,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        cache[path.name] = round(sum(frame) / len(frame), 1) if frame else 255
        save_json(BRIGHTNESS_CACHE, cache)
    if cache[path.name] < limit:
        print(f"Skipping a very dark clip ({path.name}).")
        return True
    return False


def build_background(keywords, durations, out_mp4, seed=""):
    """Make a silent 1080x1920 montage from shots of the given `durations` (seconds).

    Every shot gets its own camera move (zooms, pans, punch-in, tilt, handheld) and about one in four
    is in slow motion, so the background never feels static or repetitive.
    Returns False if no stock-video key is set or no clip can be used.
    """
    name, _ = provider()
    if not name:
        print("No PIXABAY_API_KEY or PEXELS_API_KEY in .env: using the plain animated background.")
        return False
    clean_old_clips()
    count = len(durations)
    seconds = sum(durations)
    clips = find_clips(keywords, math.ceil(count / CUTS_PER_CLIP))
    if not clips:
        print("No stock clips found: using the plain animated background.")
        return False

    rng = random.Random(f"{seed}-montage")
    ffmpeg = find_ffmpeg()
    parts, previous = [], None
    for i, shot in enumerate(durations):
        move = "punch_in" if i == 0 else rng.choice([m for m in MOVES if m != previous])
        previous = move
        speed = SLOW_MOTION if i >= 2 and rng.random() < 0.25 else 1.0
        vf = camera_move(move, shot, speed)
        part = out_mp4.parent / f"part{i:02d}.mp4"
        # if a clip is broken, delete it and use the next one instead
        for attempt in range(len(clips)):
            path, duration = clips[(i // CUTS_PER_CLIP + attempt) % len(clips)]
            need = shot * speed  # source seconds used (less in slow motion)
            # 1st shot skips the first second (often a fade-in); 2nd shot takes a later moment of the same clip
            start = 1.0 + (i % CUTS_PER_CLIP) * 3.5
            start = min(start, max(0.0, duration - need - 0.2))
            done = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{need:.3f}",
                                   "-i", str(path), "-vf", vf, "-t", f"{shot:.3f}", "-an", "-c:v", "libx264",
                                   "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(part)])
            if done.returncode == 0 and part.exists():
                break
            print(f"Broken clip {path.name}, using another one.")
            path.unlink(missing_ok=True)
        else:
            print("No usable clips: using the plain animated background.")
            for p in parts:
                p.unlink(missing_ok=True)
            return False
        parts.append(part)

    concat_list = out_mp4.parent / "parts.txt"
    concat_list.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-t", f"{seconds:.2f}", "-c", "copy", str(out_mp4)], check=True)
    for p in parts:
        p.unlink()
    concat_list.unlink()
    print(f"Montage: {count} shots from {len(clips)} {name} clips")
    return True


MOVES = ["zoom_in", "zoom_out", "punch_in", "pan_left", "pan_right", "pan_up", "pan_down", "tilt", "handheld"]
SLOW_MOTION = 0.75  # slow-motion shots play the clip at 75% speed
BW, BH = int(W * 1.2), int(H * 1.2)  # oversized frame, so pans / tilt / shake never show an edge


def camera_move(move, shot, speed=1.0):
    """FFmpeg filter for one shot: fill the vertical frame, light grade, then a camera move.

    Note: in filter expressions a comma must be written as \\, (it separates filters otherwise).
    """
    d = f"{shot:.3f}"
    head = f"setpts=PTS/{speed}," if speed != 1.0 else ""
    grade = "eq=brightness=-0.06:saturation=1.15"  # eq must come before per-frame scaling (FFmpeg 9.0.2 crash)
    if move in ("zoom_in", "zoom_out", "punch_in"):
        z = {"zoom_in": f"(1+0.12*t/{d})",
             "zoom_out": f"(1.12-0.12*t/{d})",
             "punch_in": "(1+0.12*min(t/0.35\\,1))"}[move]  # quick zoom in the first 0.35 s, then holds
        body = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},{grade},"
                f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,crop={W}:{H}")
    else:
        x, y = "(iw-ow)/2", "(ih-oh)/2"
        rotate = ""
        if move == "pan_left":
            x = f"(iw-ow)*(1-t/{d})"
        elif move == "pan_right":
            x = f"(iw-ow)*t/{d}"
        elif move == "pan_up":
            y = f"(ih-oh)*(1-t/{d})"
        elif move == "pan_down":
            y = f"(ih-oh)*t/{d}"
        elif move == "handheld":  # gentle irregular shake, like a camera held by hand
            x = "(iw-ow)/2+18*sin(2*PI*0.6*t)+7*sin(2*PI*1.7*t)"
            y = "(ih-oh)/2+14*sin(2*PI*0.45*t+1)+6*sin(2*PI*1.3*t)"
        elif move == "tilt":  # slow 1.7 degree rotation
            rotate = f"rotate=a='0.03*t/{d}':ow=iw:oh=ih:c=black,"
        body = (f"scale={BW}:{BH}:force_original_aspect_ratio=increase:flags=lanczos,crop={BW}:{BH},{grade},"
                f"{rotate}crop={W}:{H}:x='{x}':y='{y}'")
    return f"{head}{body},fps={FPS},setsar=1"


def background_frames(bg_mp4):
    """Yield the montage's frames as raw RGB bytes."""
    proc = subprocess.Popen([find_ffmpeg(), "-loglevel", "quiet", "-i", str(bg_mp4),
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = W * H * 3
    last = None
    try:
        while True:
            data = proc.stdout.read(size)
            if len(data) < size:
                break
            last = data
            yield data
        while last:  # if the montage is a frame short, hold the last frame
            yield last
    finally:  # runs when the video is done, even if frames are left over
        proc.kill()
        proc.wait()
        proc.stdout.close()
