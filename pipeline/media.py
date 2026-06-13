"""Voix off (ElevenLabs / gTTS), telechargement Pexels, sous-titres Whisper."""
import json
import subprocess
import time
from pathlib import Path

import requests

from . import config as C


# ----------------------------------------------------------------------------
# Utilitaires ffmpeg
# ----------------------------------------------------------------------------
def run(cmd, cwd=None):
    """Lance une commande, leve une erreur lisible si echec."""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Commande echouee ({proc.returncode}):\n{' '.join(str(c) for c in cmd)}\n"
            f"--- stderr ---\n{proc.stderr[-2000:]}"
        )
    return proc


def duration(path):
    """Duree d'un fichier media en secondes (float)."""
    out = subprocess.run(
        [C.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


# ----------------------------------------------------------------------------
# 1. Voix off
# ----------------------------------------------------------------------------
def tts_elevenlabs(text, out_mp3):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{C.ELEVENLABS_VOICE_ID}"
    headers = {"xi-api-key": C.ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": C.ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.75,
                           "style": 0.0, "use_speaker_boost": True},
    }
    params = {"output_format": "mp3_44100_128"}
    r = requests.post(url, headers=headers, json=payload, params=params, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    Path(out_mp3).write_bytes(r.content)


def tts_gtts(text, out_mp3):
    from gtts import gTTS
    gTTS(text=text, lang="fr", slow=False).save(str(out_mp3))


def synth_voice(text, out_mp3, use_gemini=True, use_elevenlabs=True):
    """Genere la voix off. Ordre de priorite : Gemini -> ElevenLabs -> gTTS.
    Renvoie le moteur reellement utilise."""
    from . import gemini
    if use_gemini and gemini.available():
        try:
            gemini.tts(text, out_mp3)
            return "gemini"
        except Exception as e:
            print(f"   [!] Gemini TTS indisponible ({str(e)[:160]}). Bascule.")
    if use_elevenlabs and C.ELEVENLABS_API_KEY:
        try:
            tts_elevenlabs(text, out_mp3)
            return "elevenlabs"
        except Exception as e:
            print(f"   [!] ElevenLabs indisponible ({str(e)[:160]}). Bascule sur gTTS.")
    tts_gtts(text, out_mp3)
    return "gtts"


def extract_audio(src, out_mp3):
    """Extrait la piste audio d'un media (extrait video) vers un mp3."""
    run([C.FFMPEG, "-y", "-i", str(src), "-vn", "-ac", "2", "-ar", "44100",
         "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)])
    return out_mp3


# ----------------------------------------------------------------------------
# 2. Medias (video verticale prioritaire, fallback photo) -- Pexels + Pixabay
# ----------------------------------------------------------------------------
def _pexels_video(query, out_path, exclude):
    landscape = C.ORIENTATION == "landscape"
    headers = {"Authorization": C.PEXELS_API_KEY}
    r = requests.get("https://api.pexels.com/videos/search", headers=headers,
                     params={"query": query, "orientation": C.ORIENTATION,
                             "per_page": 15, "size": "medium"}, timeout=60)
    r.raise_for_status()
    candidates = []  # (score, link, key)
    for v in r.json().get("videos", []):
        key = f"pexels-vid:{v.get('id')}"
        best_file = None
        for f in v.get("video_files", []):
            h, w = f.get("height") or 0, f.get("width") or 0
            ok = (w >= h) if landscape else (h >= w)
            if ok and f.get("file_type") == "video/mp4":
                score = abs(h - C.HEIGHT) + abs(w - C.WIDTH)
                if best_file is None or score < best_file[0]:
                    best_file = (score, f["link"])
        if best_file:
            candidates.append((best_file[0], best_file[1], key))
    return _pick(candidates, out_path, ".mp4", "video(pexels)", exclude)


def _pexels_photo(query, out_path, exclude):
    headers = {"Authorization": C.PEXELS_API_KEY}
    r = requests.get("https://api.pexels.com/v1/search", headers=headers,
                     params={"query": query, "orientation": C.ORIENTATION,
                             "per_page": 15}, timeout=60)
    r.raise_for_status()
    candidates = []
    for i, p in enumerate(r.json().get("photos", [])):
        link = p["src"].get("large2x") or p["src"]["large"]
        candidates.append((i, link, f"pexels-photo:{p.get('id')}"))
    return _pick(candidates, out_path, ".jpg", "photo(pexels)", exclude)


def _pixabay_video(query, out_path, exclude):
    if not C.PIXABAY_API_KEY:
        return None, None, None
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": C.PIXABAY_API_KEY, "q": query,
                             "per_page": 15, "safesearch": "true"}, timeout=60)
    r.raise_for_status()
    landscape = C.ORIENTATION == "landscape"
    candidates = []
    for hit in r.json().get("hits", []):
        key = f"pixabay-vid:{hit.get('id')}"
        best = None
        for variant in hit.get("videos", {}).values():
            w, h = variant.get("width") or 0, variant.get("height") or 0
            if not variant.get("url"):
                continue
            # privilegie l'orientation cible, sinon le plus grand (recadrage ensuite)
            ok = (w >= h) if landscape else (h >= w)
            orient_bonus = 0 if ok else 100000
            score = orient_bonus + abs(h - C.HEIGHT) + abs(w - C.WIDTH)
            if best is None or score < best[0]:
                best = (score, variant["url"])
        if best:
            candidates.append((best[0], best[1], key))
    return _pick(candidates, out_path, ".mp4", "video(pixabay)", exclude)


def _pixabay_photo(query, out_path, exclude):
    if not C.PIXABAY_API_KEY:
        return None, None, None
    r = requests.get("https://pixabay.com/api/",
                     params={"key": C.PIXABAY_API_KEY, "q": query,
                             "orientation": ("horizontal" if C.ORIENTATION == "landscape"
                                             else "vertical"),
                             "per_page": 15,
                             "image_type": "photo", "safesearch": "true"},
                     timeout=60)
    r.raise_for_status()
    candidates = []
    for i, hit in enumerate(r.json().get("hits", [])):
        link = hit.get("largeImageURL") or hit.get("webformatURL")
        candidates.append((i, link, f"pixabay-photo:{hit.get('id')}"))
    return _pick(candidates, out_path, ".jpg", "photo(pixabay)", exclude)


def _pick(candidates, out_path, suffix, kind, exclude):
    """Telecharge le meilleur candidat (score le plus bas) dont la cle n'est PAS
    dans 'exclude' (evite de reutiliser un meme visuel). Renvoie (kind, chemin, cle)."""
    for score, link, key in sorted(candidates, key=lambda c: c[0]):
        if key in exclude:
            continue
        dest = out_path.with_suffix(suffix)
        _stream_to(link, dest)
        return kind, dest, key
    return None, None, None


def download_media(query, out_path, exclude=None):
    """Cherche un visuel pour 'query' : videos Pexels puis Pixabay, sinon photos.
    'exclude' = ensemble de cles de visuels deja utilises (pour ne jamais
    reutiliser le meme clip dans une video). Renvoie (source, chemin, cle) ou
    (None, None, None).
    """
    exclude = exclude if exclude is not None else set()
    out_path = Path(out_path)
    for fn in (_pexels_video, _pixabay_video, _pexels_photo, _pixabay_photo):
        try:
            kind, path, key = fn(query, out_path, exclude)
            if path:
                return kind, path, key
        except Exception as e:
            print(f"   [!] {fn.__name__} echoue pour '{query}' ({e}).")
    return None, None, None


def _stream_to(url, dest, retries=3):
    for attempt in range(retries):
        try:
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        f.write(chunk)
            return
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5)


# ----------------------------------------------------------------------------
# 3. Sous-titres synchronises (faster-whisper -> SRT)
# ----------------------------------------------------------------------------
_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(C.WHISPER_MODEL, device="cpu",
                                      compute_type="int8")
    return _whisper_model


def _fmt_ts(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_ass(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _chunks(words, max_words):
    i = 0
    while i < len(words):
        yield words[i:i + max_words]
        i += max_words


def transcribe_words(audio_path, language="fr"):
    """Renvoie une liste de mots [(mot, debut, fin), ...]."""
    model = _get_whisper()
    segments, _ = model.transcribe(str(audio_path), language=language,
                                   word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append((w.word.strip(), w.start, w.end))
    return words


def transcribe_segments(audio_path, language="en"):
    """Renvoie des phrases [(texte, debut, fin), ...] (granularite phrase, plus
    adaptee aux sous-titres traduits d'un extrait parle)."""
    model = _get_whisper()
    segments, _ = model.transcribe(str(audio_path), language=language,
                                   vad_filter=True)
    out = []
    for seg in segments:
        t = seg.text.strip()
        if t:
            out.append((t, seg.start, seg.end))
    return out


def words_to_events(words, max_words=None, offset=0.0):
    """Regroupe des mots [(mot, debut, fin)] en evenements de sous-titre
    [(start, end, texte)] de max_words mots, decales de 'offset' secondes."""
    max_words = max_words or C.SUB_MAX_WORDS
    events = []
    for chunk in _chunks(words, max_words):
        start = chunk[0][1] + offset
        end = chunk[-1][2] + offset
        text = " ".join(w[0] for w in chunk)
        events.append((start, end, text))
    return events


def write_srt(events, out_srt):
    """Ecrit une liste d'evenements [(start, end, texte)] en .srt (reference)."""
    lines = []
    for idx, (start, end, text) in enumerate(events, start=1):
        lines.append(f"{idx}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{text}\n")
    Path(out_srt).write_text("\n".join(lines), encoding="utf-8")
    return out_srt


def write_ass(events, out_ass):
    """Ecrit une liste d'evenements [(start, end, texte)] en .ass, a la
    resolution video courante (PlayResX/Y, police, marges depuis C)."""
    style = (
        f"Style: Default,{C.ASS_FONT},{C.ASS_FONTSIZE},"
        f"{C.ASS_PRIMARY},&H000000FF,{C.ASS_OUTLINE_COL},&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,{C.ASS_OUTLINE},{C.ASS_SHADOW},"
        f"2,60,60,{C.ASS_MARGINV},1"
    )
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {C.WIDTH}\n"
        f"PlayResY: {C.HEIGHT}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    dialogues = []
    for start, end, text in events:
        s = _fmt_ass(start)
        e = _fmt_ass(end)
        txt = str(text).replace("\n", " ")
        dialogues.append(f"Dialogue: 0,{s},{e},Default,,0,0,0,,{txt}")
    Path(out_ass).write_text(header + "\n".join(dialogues) + "\n", encoding="utf-8")
    return out_ass
