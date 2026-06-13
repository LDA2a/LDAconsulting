"""Voix off et traduction via l'API Google Gemini.

- TTS : modeles `gemini-2.5-flash-preview-tts` (voix naturelles, ton controlable).
- Traduction : `gemini-2.5-flash` pour sous-titrer en FR les extraits anglais.

Necessite une cle API Google AI Studio dans .env (GEMINI_API_KEY). La cle est
gratuite et distincte de l'abonnement de l'app Gemini :
https://aistudio.google.com/apikey
"""
import base64
import json
from pathlib import Path

import requests

from . import config as C
from .media import run

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def available():
    return bool(C.GEMINI_API_KEY)


def tts(text, out_mp3):
    """Genere la voix off d'un texte via Gemini TTS -> mp3. Leve si echec."""
    model = C.GEMINI_TTS_MODEL
    prompt = f"{C.GEMINI_TTS_STYLE}\n\n{text}" if C.GEMINI_TTS_STYLE else text
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": C.GEMINI_VOICE}
                }
            },
        },
    }
    url = f"{_BASE}/{model}:generateContent"
    r = requests.post(url, params={"key": C.GEMINI_API_KEY},
                      json=payload, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini TTS {r.status_code}: {r.text[:300]}")
    part = r.json()["candidates"][0]["content"]["parts"][0]
    inline = part["inlineData"]
    pcm = base64.b64decode(inline["data"])
    rate = _rate_from_mime(inline.get("mimeType", ""))
    # Gemini renvoie du PCM brut (s16le mono) -> on encode en mp3 via ffmpeg.
    out_mp3 = Path(out_mp3)
    raw = out_mp3.with_suffix(".pcm")
    raw.write_bytes(pcm)
    run([C.FFMPEG, "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1",
         "-i", str(raw), "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)])
    raw.unlink(missing_ok=True)
    return out_mp3


def _rate_from_mime(mime):
    """Extrait le taux d'echantillonnage d'un mimeType 'audio/L16;...;rate=24000'."""
    for tok in mime.split(";"):
        tok = tok.strip()
        if tok.startswith("rate="):
            try:
                return int(tok.split("=", 1)[1])
            except ValueError:
                pass
    return 24000


def translate_lines(lines, target="français"):
    """Traduit une liste de phrases vers 'target' (par defaut le francais).
    Renvoie une liste de meme longueur. Leve si l'API echoue ou desaligne.
    """
    if not lines:
        return []
    numbered = "\n".join(f"{i+1}. {ln}" for i, ln in enumerate(lines))
    prompt = (
        f"Traduis en {target} naturel et fluide les repliques numerotees "
        f"ci-dessous (sous-titres d'une video). Reponds STRICTEMENT avec les "
        f"memes numeros, une traduction par ligne, sans rien ajouter.\n\n{numbered}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": 0.3}}
    url = f"{_BASE}/{C.GEMINI_TEXT_MODEL}:generateContent"
    r = requests.post(url, params={"key": C.GEMINI_API_KEY},
                      json=payload, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini translate {r.status_code}: {r.text[:300]}")
    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    out = {}
    for line in txt.splitlines():
        line = line.strip()
        if not line or "." not in line:
            continue
        num, _, rest = line.partition(".")
        if num.strip().isdigit():
            out[int(num.strip())] = rest.strip()
    return [out.get(i + 1, lines[i]) for i in range(len(lines))]
