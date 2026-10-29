"""Create one vertical (1080x1920) video: "3 crazy facts about <topic>", just over 1 minute.

Stock footage montage + AI voice + animated captions + big #1 #2 #3 numbers.

Usage:
    python src/make_video.py --lang en                    # next unused topic from topics.json
    python src/make_video.py --lang en --topic octopuses
"""
import argparse
import asyncio
import colorsys
import hashlib
import math
import subprocess
import time
import wave
from datetime import datetime
from functools import lru_cache

import edge_tts
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from common import OUTPUT, ROOT, STATE_FILE, find_ffmpeg, load_config, load_json, save_json
from footage import SEGMENT_SECONDS, background_frames, build_background

W, H, FPS = 1080, 1920, 30
FONT = str(ROOT / "assets" / "fonts" / "ArchivoBlack-Regular.ttf")  # free font (SIL OFL), works on any computer
CAPTION_SIZE = 112
MAX_LINE_WIDTH = 940
WORDS_PER_CHUNK = 3
TAIL_SECONDS = 1.2  # end card after the voice stops
SECTION_GAP = 0.35  # short silence between intro, facts and outro
HIGHLIGHT = (255, 225, 77)
WHITE = (255, 255, 255)


# ---------- choosing the topic ----------

def pick_topic(lang, topic_id=None, exclude=()):
    topics = load_json(ROOT / "topics.json")
    if topic_id:
        return next(t for t in topics if t["id"] == topic_id)
    used = set(load_json(STATE_FILE, {}).get(lang, [])) | set(exclude)
    for topic in topics:  # topics.json is in posting order
        if topic["id"] not in used and lang in topic.get("facts", {}):
            return topic
    raise SystemExit(f"No unused '{lang}' topics left in topics.json. Ask Claude to write the next batch.")


def remaining_topics(lang):
    used = set(load_json(STATE_FILE, {}).get(lang, []))
    return sum(1 for t in load_json(ROOT / "topics.json") if t["id"] not in used and lang in t.get("facts", {}))


# ---------- voice ----------

async def _synthesize(text, voice, rate, mp3_path):
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append({"text": chunk["text"], "start": start,
                              "end": start + chunk["duration"] / 1e7})
    return words


def synthesize(text, voice, rate, mp3_path, attempts=8):
    """The free voice service sometimes fails for a moment: retry for up to ~8 minutes before giving up."""
    for attempt in range(1, attempts + 1):
        try:
            return asyncio.run(_synthesize(text, voice, rate, mp3_path))
        except Exception as e:
            if attempt == attempts:
                raise
            wait = min(15 * attempt, 90)
            print(f"Voice service error ({type(e).__name__}), retrying in {wait}s...")
            time.sleep(wait)


def mark_punctuation(words, script):
    """Flag words followed by punctuation in the script (the voice timings drop punctuation)."""
    pos = 0
    for word in words:
        found = script.find(word["text"], pos)
        if found == -1:
            continue
        pos = found + len(word["text"])
        rest = script[pos:pos + 3].lstrip(" \u00a0")
        word["punct"] = bool(rest) and rest[0] in ".,:;!?"


def record_sections(sections, lang_cfg, folder):
    """Record each section separately, then join them with short pauses into voice.wav.

    Returns (all words with global timings, [(section_mark, start, end)]).
    """
    ffmpeg = find_ffmpeg()
    all_words, spans, pcm, rate = [], [], b"", 24000
    offset = 0.0
    for i, (mark, text) in enumerate(sections):
        mp3 = folder / f"voice{i}.mp3"
        words = synthesize(text, lang_cfg["voice"], lang_cfg.get("rate", "+0%"), mp3)
        mark_punctuation(words, text)
        wav = folder / f"voice{i}.wav"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(mp3), "-ar", str(rate), "-ac", "1",
                        str(wav)], check=True)
        with wave.open(str(wav)) as w:
            data = w.readframes(w.getnframes())
        duration = len(data) / 2 / rate
        for word in words:
            all_words.append({**word, "start": word["start"] + offset, "end": word["end"] + offset})
        spans.append((mark, offset, offset + duration))
        gap = b"\x00\x00" * int(SECTION_GAP * rate)
        pcm += data + gap
        offset += duration + SECTION_GAP
        mp3.unlink()
        wav.unlink()
    with wave.open(str(folder / "voice.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return all_words, spans


def group_words(words):
    """Split words into short caption chunks, breaking at pauses and punctuation."""
    chunks, current = [], []
    for i, word in enumerate(words):
        current.append(word)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = word.get("punct") or (nxt is not None and nxt["start"] - word["end"] > 0.25)
        long_text = sum(len(w["text"]) for w in current) > 14
        if nxt is None or pause or long_text or len(current) == WORDS_PER_CHUNK:
            chunks.append(current)
            current = []
    for i, chunk in enumerate(chunks):
        chunk_end = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else chunk[-1]["end"] + 0.3
        chunks[i] = {"words": chunk, "start": chunk[0]["start"], "end": chunk_end}
    return chunks


# ---------- drawing ----------

def theme_colors(seed):
    hue = int(hashlib.md5(seed.encode()).hexdigest()[:4], 16) / 0xFFFF
    def rgb(h, s, v):
        return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h % 1, s, v))
    return rgb(hue, 0.75, 0.55), rgb(hue + 0.12, 0.8, 0.35)


def make_background(seed):
    """A tall looping gradient; each frame crops a window that slowly scrolls."""
    top, bottom = theme_colors(seed)
    tall = Image.new("RGB", (1, H * 2))
    for y in range(H * 2):
        t = (math.cos(y / (H * 2) * 2 * math.pi) + 1) / 2  # 1 -> 0 -> 1, loops seamlessly
        tall.putpixel((0, y), tuple(int(bottom[c] + (top[c] - bottom[c]) * t) for c in range(3)))
    return tall.resize((W, H * 2))


def make_bubble(radius, alpha):
    size = radius * 2 + 80
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((40, 40, 40 + radius * 2, 40 + radius * 2), fill=(255, 255, 255, alpha))
    return img.filter(ImageFilter.GaussianBlur(30))


@lru_cache(maxsize=None)
def font(size):
    return ImageFont.truetype(FONT, size)


@lru_cache(maxsize=512)
def word_image(text, size, color):
    f = font(size)
    stroke = max(4, size // 14)
    box = f.getbbox(text, stroke_width=stroke)
    img = Image.new("RGBA", (box[2] - box[0] + 20, box[3] - box[1] + 20), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((10 - box[0], 10 - box[1]), text, font=f, fill=color,
                             stroke_width=stroke, stroke_fill=(0, 0, 0))
    return img


def layout_chunk(chunk):
    """Place the chunk's words on 1-2 centered lines. Returns (size, [(word, x_center, y_center)])."""
    size = CAPTION_SIZE
    space = int(size * 0.3)
    texts = [w["text"].upper() for w in chunk["words"]]
    while True:
        widths = [word_image(t, size, WHITE).width for t in texts]
        lines, line, width = [], [], 0
        for i, wdt in enumerate(widths):
            if line and width + space + wdt > MAX_LINE_WIDTH:
                lines.append(line)
                line, width = [], 0
            width += (space if line else 0) + wdt
            line.append(i)
        lines.append(line)
        if max(widths) <= MAX_LINE_WIDTH or size < 60:
            break
        size -= 8
    line_h = int(size * 1.25)
    y0 = H // 2 - (len(lines) * line_h) // 2 + line_h // 2
    placed = []
    for li, line in enumerate(lines):
        total = sum(widths[i] for i in line) + space * (len(line) - 1)
        x = (W - total) // 2
        for i in line:
            placed.append((i, x + widths[i] // 2, y0 + li * line_h))
            x += widths[i] + space
    return size, placed


def paste_center(frame, img, cx, cy):
    frame.paste(img, (int(cx - img.width / 2), int(cy - img.height / 2)), img)


def make_badge(text, max_width=900):
    """Rounded title banner. Long titles go on two lines ("3 CRAZY FACTS:" / title) instead of overflowing."""
    lines = [text]
    size = 64
    while font(size).getbbox(text)[2] > max_width and size > 48:
        size -= 4
    if font(size).getbbox(text)[2] > max_width and ": " in text:
        head, title = text.split(": ", 1)
        lines = [head + ":", title]
        size = 60
    while max(font(size).getbbox(l)[2] for l in lines) > max_width and size > 30:
        size -= 2
    f = font(size)
    line_h = int(size * 1.2)
    text_w = max(f.getbbox(l)[2] - f.getbbox(l)[0] for l in lines)
    top = f.getbbox(lines[0])[1]
    w, h = text_w + 90, line_h * (len(lines) - 1) + (f.getbbox(lines[-1])[3] - top) + 60
    img = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 10, 10 + w, 10 + h), radius=min(h // 2, 60), fill=(0, 0, 0, 150))
    for i, line in enumerate(lines):
        lw = f.getbbox(line)[2] - f.getbbox(line)[0]
        x = 10 + (w - lw) // 2 - f.getbbox(line)[0]
        d.text((x, 10 + 30 - top + i * line_h), line, font=f, fill=HIGHLIGHT)
    return img


def make_shade():
    """Darken the top, the caption area and the bottom so text stays readable over footage."""
    alpha = Image.new("L", (1, H))
    for y in range(H):
        top = max(0.0, 1 - y / 520) * 140
        middle = math.exp(-((y - H / 2) / 260) ** 2) * 110
        bottom = max(0.0, (y - 1500) / 420) * 150
        alpha.putpixel((0, y), int(min(200, top + middle + bottom)))
    return alpha.resize((W, H))


def whoosh_sound():
    """Create a short soft 'whoosh' once (filtered noise), used on every cut."""
    path = ROOT / "assets" / "whoosh.wav"
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "anoisesrc=d=0.45:c=pink:a=0.6", "-af",
                        "highpass=f=500,lowpass=f=5000,afade=t=in:d=0.2,afade=t=out:st=0.2:d=0.25,volume=0.5",
                        str(path)], check=True)
    return path


def render(words, spans, voice_wav, out_mp4, lang_cfg, badge_text, seed, total, bg_mp4=None, cut_times=()):
    chunks = group_words(words)
    speech_end = words[-1]["end"]
    n_frames = int(total * FPS)

    if bg_mp4:
        footage = background_frames(bg_mp4)
        shade = make_shade()
        bubbles = []
    else:
        background = make_background(seed)
        bubbles = [(make_bubble(r, a), x, y, sp) for r, a, x, y, sp in
                   [(220, 40, 180, 420, 0.7), (160, 35, 880, 1350, 1.1), (300, 25, 760, 300, 0.5),
                    (120, 45, 260, 1600, 1.3), (200, 30, 540, 980, 0.9)]]
    badge = make_badge(badge_text)
    end_size = 120
    while word_image(lang_cfg["end_card"], end_size, HIGHLIGHT).width > MAX_LINE_WIDTH:
        end_size -= 6
    end_text = word_image(lang_cfg["end_card"], end_size, HIGHLIGHT)
    layouts = [layout_chunk(c) for c in chunks]

    cmd = [find_ffmpeg(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(voice_wav)]
    # audio: voice + optional quiet music + a whoosh on each cut
    mix, n_inputs, filters = ["[1:a]"], 2, []
    music = ROOT / "assets" / "music.mp3"
    if music.exists():
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        filters.append(f"[{n_inputs}:a]volume=0.12[m]")
        mix.append("[m]")
        n_inputs += 1
    if cut_times:
        cmd += ["-i", str(whoosh_sound())]
        filters.append(f"[{n_inputs}:a]asplit={len(cut_times)}" + "".join(f"[w{i}]" for i in range(len(cut_times))))
        for i, ct in enumerate(cut_times):
            ms = max(0, int(ct * 1000) - 150)
            filters.append(f"[w{i}]adelay={ms}|{ms}[d{i}]")
            mix.append(f"[d{i}]")
        n_inputs += 1
    filters.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,apad[a]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[a]"]
    # capped bitrate keeps a 1-minute video around 30-40 MB (the platforms re-compress anyway)
    cmd += ["-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-maxrate", "4M", "-bufsize", "8M",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_mp4)]
    ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    chunk_i = 0
    for n in range(n_frames):
        t = n / FPS
        if bg_mp4:
            frame = Image.frombytes("RGB", (W, H), next(footage))
            frame.paste((0, 0, 0), (0, 0), shade)
        else:
            offset = int((t * 60) % H)  # background scroll speed: 60 px per second
            frame = background.crop((0, offset, W, offset + H))

        for img, x, y, speed in bubbles:
            paste_center(frame, img, x + 60 * math.sin(t * speed), y + 80 * math.cos(t * speed * 0.8))

        paste_center(frame, badge, W // 2, 330 + 10 * math.sin(t * 2.5))

        # big "#1 #2 #3 BONUS" above the captions while each fact is read
        for mark, start, end in spans:
            if mark and start <= t < end + SECTION_GAP:
                pop = max(0.0, 1 - (t - start) / 0.25)
                paste_center(frame, word_image(mark, int(170 * (1 + 0.3 * pop)), HIGHLIGHT), W // 2, 640)

        while chunk_i + 1 < len(chunks) and t >= chunks[chunk_i + 1]["start"]:
            chunk_i += 1
        chunk = chunks[chunk_i]
        if t < speech_end + 0.3 and t >= chunk["start"] - 0.05:
            size, placed = layouts[chunk_i]
            for i, cx, cy in placed:
                word = chunk["words"][i]
                active = word["start"] <= t < (chunk["words"][i + 1]["start"] if i + 1 < len(chunk["words"]) else chunk["end"])
                pop = max(0.0, 1 - (t - word["start"]) / 0.12) if active else 0
                img = word_image(word["text"].upper(), int(size * (1 + 0.15 * pop)) if active else size,
                                 HIGHLIGHT if active else WHITE)
                paste_center(frame, img, cx, cy + 60)

        if t >= speech_end:  # end card fades/zooms in
            k = min(1.0, (t - speech_end) / 0.35)
            img = end_text.resize((max(1, int(end_text.width * (0.6 + 0.4 * k))),
                                   max(1, int(end_text.height * (0.6 + 0.4 * k)))))
            paste_center(frame, img, W // 2, H // 2)

        # progress bar
        ImageDraw.Draw(frame).rounded_rectangle((90, 1760, 90 + int((W - 180) * n / n_frames), 1776),
                                                radius=8, fill=HIGHLIGHT)
        ffmpeg.stdin.write(frame.tobytes())

    if bg_mp4:
        footage.close()
    ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise SystemExit("FFmpeg failed to build the video.")
    return total


def make_video(lang, topic_id=None, exclude=()):
    """Make the video for the next unused topic. The caller marks it as used once it is published."""
    config = load_config()
    lang_cfg = config["languages"][lang]
    topic = pick_topic(lang, topic_id, exclude)
    title = topic["title"][lang]
    facts = topic["facts"][lang]

    sections = [(None, lang_cfg["hook"].format(title=title))]
    sections += [(mark, f"{label} {fact}")
                 for mark, label, fact in zip(lang_cfg["fact_marks"], lang_cfg["fact_labels"], facts)]
    sections.append((None, lang_cfg["outro"]))

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    folder = OUTPUT / f"{stamp}_{lang}_{topic['id']}"
    folder.mkdir(parents=True, exist_ok=True)
    video = folder / "video.mp4"

    print(f"[{lang}] Topic: {topic['id']}")
    print(f"[{lang}] Recording voice...")
    words, spans = record_sections(sections, lang_cfg, folder)
    # TikTok only pays for videos over 1 minute: hold the end card longer if the voice is short
    total = max(words[-1]["end"] + TAIL_SECONDS, config.get("min_seconds", 0))
    bg_mp4 = folder / "montage.mp4"
    print(f"[{lang}] Finding video clips...")
    has_footage = build_background(topic.get("keywords", []), total, bg_mp4)
    cuts = [i * SEGMENT_SECONDS for i in range(1, math.ceil(total / SEGMENT_SECONDS))] if has_footage else []
    print(f"[{lang}] Rendering video ({len(words)} words, {total:.1f}s)...")
    badge_text = lang_cfg["badge"].format(title=title.upper())
    seconds = render(words, spans, folder / "voice.wav", video, lang_cfg, badge_text, topic["id"], total,
                     bg_mp4 if has_footage else None, cuts)
    bg_mp4.unlink(missing_ok=True)
    (folder / "voice.wav").unlink(missing_ok=True)

    # topic hashtags for this video, then the account's own hashtags
    hashtags = f"{topic.get('hashtags', {}).get(lang, '')} {lang_cfg['hashtags']}".strip()
    caption = f"{lang_cfg['caption'].format(title=title)}\n\n{hashtags}"
    info = {"lang": lang, "topic_id": topic["id"], "title": title, "video": str(video), "caption": caption,
            "seconds": round(seconds, 1)}
    save_json(folder / "info.json", info)
    left = remaining_topics(lang) - len(exclude) - 1
    print(f"[{lang}] Done: {video} ({seconds:.1f}s). Topics left: {left}")
    if left <= 14:
        print(f"[{lang}] WARNING: only {left} topics left (about {left // 2} days). Ask Claude for the next batch.")
    return info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Make one '3 facts' video.")
    parser.add_argument("--lang", choices=["en", "fr"], required=True)
    parser.add_argument("--topic", help="topic id from topics.json (default: next unused)")
    args = parser.parse_args()
    make_video(args.lang, args.topic)
