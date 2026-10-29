"""Build the background montage: free stock clips (Pixabay or Pexels), cut every few seconds, slow zoom.

Clips are downloaded once into assets/clips/ and reused. Only FFmpeg is used for editing.
"""
import json
import math
import os
import subprocess
import time
import urllib.parse
import urllib.request

from common import ROOT, find_ffmpeg, load_env, load_json, save_json

CLIPS = ROOT / "assets" / "clips"
SEARCH_CACHE = ROOT / "assets" / "search_cache.json"
SEGMENT_SECONDS = 2.8
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
        {"key": key, "q": query, "safesearch": "true", "per_page": 20}))
    found = []
    for hit in data.get("hits", []):
        # prefer 4K (sharp after cropping to vertical) unless the file is very big
        for size in ("large", "medium"):
            f = hit["videos"].get(size) or {}
            if f.get("url") and f.get("size", 0) <= MAX_DOWNLOAD_MB * 1e6:
                found.append({"id": f"pixabay_{hit['id']}", "duration": hit.get("duration", 0),
                              "url": f["url"], "height": f.get("height", 0)})
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
    """Return up to `needed` (path, duration) clips, taking the fact's keywords in turn."""
    name, key = provider()
    results = {q: [c for c in search(q, name, key) if c["duration"] >= 4] for q in keywords}
    clips, used = [], set()
    while len(clips) < needed and any(results.values()):
        for q in keywords:
            while results[q]:
                clip = results[q].pop(0)
                if clip["id"] not in used:
                    used.add(clip["id"])
                    clips.append((download(clip), clip["duration"]))
                    break
            if len(clips) >= needed:
                break
    return clips


def build_background(keywords, seconds, out_mp4):
    """Make a silent 1080x1920 montage `seconds` long. Returns False if no stock-video key is set."""
    name, _ = provider()
    if not name:
        print("No PIXABAY_API_KEY or PEXELS_API_KEY in .env: using the plain animated background.")
        return False
    clean_old_clips()
    count = math.ceil(seconds / SEGMENT_SECONDS)
    clips = find_clips(keywords, math.ceil(count / CUTS_PER_CLIP))
    if not clips:
        print("No stock clips found: using the plain animated background.")
        return False

    ffmpeg = find_ffmpeg()
    parts = []
    for i in range(count):
        path, duration = clips[(i // CUTS_PER_CLIP) % len(clips)]
        # 1st cut skips the first second (often a fade-in); 2nd cut takes a later moment of the same clip
        start = 1.0 + (i % CUTS_PER_CLIP) * (SEGMENT_SECONDS + 0.5)
        start = min(start, max(0.0, duration - SEGMENT_SECONDS - 0.2))
        zoom_in = i % 2 == 0  # alternate zoom in / zoom out between cuts
        z = f"(1+0.10*t/{SEGMENT_SECONDS})" if zoom_in else f"(1.10-0.10*t/{SEGMENT_SECONDS})"
        part = out_mp4.parent / f"part{i:02d}.mp4"
        # eq must come before the per-frame zoom: FFmpeg 9.0.2 crashes when it follows it
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
              f"eq=brightness=-0.06:saturation=1.15,"
              f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,crop={W}:{H},"
              f"fps={FPS},setsar=1")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(path),
                        "-t", f"{SEGMENT_SECONDS}", "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "18", "-pix_fmt", "yuv420p", str(part)], check=True)
        parts.append(part)

    concat_list = out_mp4.parent / "parts.txt"
    concat_list.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-t", f"{seconds:.2f}", "-c", "copy", str(out_mp4)], check=True)
    for p in parts:
        p.unlink()
    concat_list.unlink()
    print(f"Montage: {count} cuts from {len(clips)} {name} clips")
    return True


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
