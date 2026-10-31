"""The channel voice: Chatterbox Nano (the engine of Alpha Mindset) copying a license-free reference voice,
checked sentence by sentence with whisper. Chosen by the owner by ear on 1 Nov 2026 (sample "B").

Runs on GitHub's servers, which have no graphics card: Nano was measured at about 2.6x slower than real time
on a laptop CPU. If anything here fails, make_video falls back to the Microsoft voice (edge-tts) so the day's
video still goes out, and Telegram says so.
"""
import difflib
import os
import re
import subprocess
import wave

from common import ROOT, find_ffmpeg

REFERENCE = ROOT / "assets" / "voice" / "reference.wav"  # Kokoro am_michael at 0.95 (Apache-2.0 voice, not a real person)
SEEDS = (42, 7, 123, 2024, 99, 555)
LEAD_IN = 0.1         # the hook is spoken at once
SENTENCE_GAP = 0.25   # pause between two sentences of the same section
MATCH_OK = 0.9        # share of the sentence's words whisper must hear
MATCH_MINIMUM = 0.75  # below this, after every seed, the sentence is broken: give up (make_video falls back)
MAX_GAP_SCALE = 1.8   # longer pauses first, before slowing the voice down
MIN_TEMPO = 0.88      # never slower than this (atempo): Nano at 0.85 started to sound dragged
RATE = 24000          # voice.wav as the montage expects it: mono, 16-bit, 24 kHz

_models = {}


def models():
    """Load Chatterbox Nano and whisper once per run (the first run downloads them, then GitHub caches them)."""
    if not _models:
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        from faster_whisper import WhisperModel
        device = os.environ.get("VOICE_DEVICE", "cpu")  # cuda only on a PC whose graphics card is free
        _models["tts"] = ChatterboxTurboTTS.from_pretrained(device=device, nano=True)
        _models["whisper"] = WhisperModel("small.en", device="cpu", compute_type="int8")
    return _models["tts"], _models["whisper"]


def words_of(text):
    """Lowercase words without punctuation, with common contractions opened ("it's" = "it is")."""
    text = text.lower().replace("’", "'")
    text = re.sub(r"\b(\w+)'s\b", r"\1 is", text)
    text = re.sub(r"\b(\w+)'re\b", r"\1 are", text)
    text = re.sub(r"\b(\w+)'ll\b", r"\1 will", text)
    text = re.sub(r"\b(\w+)'ve\b", r"\1 have", text)
    text = re.sub(r"\b(\w+)'m\b", r"\1 am", text)
    text = re.sub(r"\bcan't\b", "can not", text)
    text = re.sub(r"\b(\w+)n't\b", r"\1 not", text)
    return re.findall(r"[a-z0-9]+", text)


NUMBER_WORDS = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                   "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
                   "hundred hundreds thousand thousands million millions billion billions twenties thirties "
                   "forties fifties sixties seventies eighties nineties".split())


def match(script, heard):
    """Share of the script's words whisper heard. Numbers are left out on both sides: whisper writes
    "five hundred" as "500" ("Number one." came back as "Number 1.", 50%, and was generated again for nothing)."""
    def plain(text):
        return [w for w in words_of(text) if w not in NUMBER_WORDS and not any(c.isdigit() for c in w)]
    return difflib.SequenceMatcher(None, plain(script), plain(heard)).ratio()


def sentences_of(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def say(text, seed, wav_path):
    """One take of one sentence, leading and trailing silence cut. Returns its length in seconds."""
    import librosa
    import torch
    import torchaudio
    tts, _ = models()
    torch.manual_seed(seed)
    wav = tts.generate(text, audio_prompt_path=str(REFERENCE))
    audio, _ = librosa.effects.trim(wav.squeeze(0).cpu().numpy(), top_db=35)
    torchaudio.save(str(wav_path), torch.from_numpy(audio).unsqueeze(0), tts.sr)
    return len(audio) / tts.sr


def listen(wav_path):
    _, whisper = models()
    segments, _ = whisper.transcribe(str(wav_path), language="en", word_timestamps=True)
    return [w for s in segments for w in s.words]


def record_line(text, wav_path):
    """Generate the sentence until whisper hears it right. Returns (seconds, heard words, match)."""
    best = None
    for seed in SEEDS:
        take = wav_path.with_name(f"{wav_path.stem}-{seed}.wav")
        seconds = say(text, seed, take)
        heard = listen(take)
        score = match(text, " ".join(w.word for w in heard))
        if not best or score > best[2]:
            best = (take, seconds, score, heard)
        if score >= MATCH_OK:
            break
        print(f"  voice: '{text}' heard as '{' '.join(w.word.strip() for w in heard)}' ({score:.0%}), trying again")
    take, seconds, score, heard = best
    if score < MATCH_MINIMUM:
        raise RuntimeError(f"the voice kept garbling '{text}' ({score:.0%} understood)")
    take.replace(wav_path)
    for leftover in wav_path.parent.glob(f"{wav_path.stem}-*.wav"):
        leftover.unlink()
    return seconds, heard, score


def ffmpeg(*args):
    subprocess.run([find_ffmpeg(), "-v", "error", "-y", *args], check=True)


def silence(seconds):
    return b"\x00\x00" * int(seconds * RATE)


def record_sections(sections, folder, target_seconds, section_gap):
    """Record every sentence, then lay them out on voice.wav, long enough for TikTok's 1-minute rule.

    Same result as the Microsoft voice: (words with global timings and punctuation flags, [(mark, start, end)]).
    """
    takes = []
    for s, (_, text) in enumerate(sections):
        for k, sentence in enumerate(sentences_of(text)):
            wav = folder / f"voice{s:02d}_{k:02d}.wav"
            seconds, heard, score = record_line(sentence, wav)
            takes.append({"section": s, "text": sentence, "file": wav, "seconds": seconds, "heard": heard})
            print(f"  voice {len(takes)}: {seconds:.1f}s, {score:.0%} understood")

    # fit the 1-minute rule: first longer pauses, then a slightly slower voice (pitch unchanged)
    gaps = [section_gap if b["section"] != a["section"] else SENTENCE_GAP for a, b in zip(takes, takes[1:])]
    speech, pauses = sum(t["seconds"] for t in takes), sum(gaps)
    gap_scale, tempo = 1.0, 1.0
    if LEAD_IN + speech + pauses < target_seconds:
        gap_scale = min(MAX_GAP_SCALE, (target_seconds - LEAD_IN - speech) / pauses) if pauses else 1.0
        if LEAD_IN + speech + pauses * gap_scale < target_seconds:
            tempo = max(MIN_TEMPO, speech / (target_seconds - LEAD_IN - pauses * gap_scale))
    print(f"  voice: {speech:.1f}s of speech, pauses x{gap_scale:.2f}, tempo {tempo:.2f}")

    pcm, words, starts, ends = silence(LEAD_IN), [], {}, {}
    for i, take in enumerate(takes):
        # each sentence at the same loudness, slowed if needed
        norm = take["file"].with_suffix(".norm.wav")
        ffmpeg("-i", str(take["file"]), "-af", f"atempo={tempo},loudnorm=I=-16:TP=-2:LRA=7",
               "-ar", str(RATE), "-ac", "1", "-sample_fmt", "s16", str(norm))
        with wave.open(str(norm)) as w:
            data = w.readframes(w.getnframes())
        t, seconds = len(pcm) / 2 / RATE, len(data) / 2 / RATE
        want, heard = take["text"].split(), take["heard"]
        for k, word in enumerate(want):
            # caption words are the script's words, timed by whisper when it heard as many words
            if len(heard) == len(want):
                start, end = heard[k].start / tempo, min(heard[k].end / tempo, seconds)
            else:
                start, end = seconds * k / len(want), seconds * (k + 1) / len(want)
            words.append({"text": word.strip(".,!?;:\"“”()"), "start": round(t + start, 3),
                          "end": round(t + end, 3), "punct": word.rstrip("\"”)")[-1:] in tuple(".,:;!?")})
        starts.setdefault(take["section"], t)
        ends[take["section"]] = t + seconds
        pcm += data
        if i + 1 < len(takes):
            pcm += silence(gaps[i] * gap_scale)
        take["file"].unlink()
        norm.unlink()

    with wave.open(str(folder / "voice.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    spans = [(sections[s][0], starts[s], ends[s]) for s in sorted(starts)]
    return words, spans
