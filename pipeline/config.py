"""Configuration centrale du pipeline TikTok.

Charge les cles API depuis .env et expose les chemins/constantes.
"""
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# Utilise le magasin de certificats Windows pour HTTPS (evite les erreurs
# SSL CERTIFICATE_VERIFY_FAILED derriere antivirus/proxy).
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

# Racine du projet = dossier parent de /pipeline
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# --- Cles API ---
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "").strip()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "XB0fDUnXU5powFXDhCwa").strip()
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2").strip()

# --- Gemini (voix off prioritaire + traduction des sous-titres) ---
# Cle gratuite Google AI Studio : https://aistudio.google.com/apikey
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash").strip()
# Voix preconstruite (voir aistudio). Charon = grave, posee, ton conteur.
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Charon").strip()
# Instruction de style prefixee au texte (ton de la narration).
# IMPORTANT : viser le DYNAMISME (pas de lecture lente ni de pauses entre les
# mots), un debit naturel et accrocheur qui tient en haleine.
GEMINI_TTS_STYLE = os.getenv(
    "GEMINI_TTS_STYLE",
    "Raconte ce texte comme un conteur captivant et energique : debit "
    "dynamique et fluide, intonations vivantes et variees qui accrochent, "
    "sans jamais ralentir ni marquer de pause entre les mots. Enchaine "
    "naturellement, avec du rythme et de l'emotion :",
).strip()

# --- Format video ---
WIDTH = 1080
HEIGHT = 1920
FPS = 30
# Orientation des visuels recherches (Pexels/Pixabay) : "portrait" (9:16 TikTok)
# ou "landscape" (16:9 YouTube). Bascule via config.use_landscape().
ORIENTATION = "portrait"

# --- Decoupage en clips ---
CLIP_MIN = 61.0   # secondes
CLIP_MAX = 68.0   # secondes
TRANSITION = 0.5  # duree des fondus enchaines entre visuels (s)

# --- Audio ---
MUSIC_VOLUME = 0.10   # volume musique de fond (0-1) sous la voix
MUSIC_DIR = ROOT / "music"
# Ambiances disponibles (sous-dossiers de music/). L'ambiance d'un projet est
# definie dans segments.json ("ambiance": "...") ou via --ambiance.
AMBIANCES = ["calme", "documentaire", "epique", "energie"]
DEFAULT_AMBIANCE = "documentaire"

# --- Sous-titres (.ass burn-in TikTok, coordonnees en pixels reels) ---
# Par defaut PAS de sous-titres sur la narration (rendu storytelling, moins
# "IA"). Les extraits en langue etrangere recoivent quand meme un sous-titrage
# TRADUIT (gere segment par segment, independamment de ce reglage).
SUBTITLES_NARRATION = os.getenv("SUBTITLES_NARRATION", "0") == "1"
SUB_MAX_WORDS = 4      # mots max par ligne de sous-titre
ASS_FONT = "Arial"
ASS_FONTSIZE = 70      # px (sur 1920 de haut)
ASS_OUTLINE = 5        # epaisseur contour noir (px)
ASS_SHADOW = 1
ASS_MARGINV = 380      # px depuis le bas (au-dessus de l'UI TikTok)
ASS_PRIMARY = "&H00FFFFFF"   # blanc (AABBGGRR)
ASS_OUTLINE_COL = "&H00000000"  # noir


def use_portrait():
    """Format vertical 9:16 (1080x1920, TikTok). Valeurs par defaut."""
    global WIDTH, HEIGHT, ORIENTATION, ASS_FONTSIZE, ASS_MARGINV
    WIDTH, HEIGHT = 1080, 1920
    ORIENTATION = "portrait"
    ASS_FONTSIZE = 70
    ASS_MARGINV = 380


def use_landscape():
    """Bascule le pipeline en 16:9 paysage (1920x1080, YouTube).
    A appeler avant tout traitement (modifie les constantes du module)."""
    global WIDTH, HEIGHT, ORIENTATION, ASS_FONTSIZE, ASS_MARGINV
    WIDTH, HEIGHT = 1920, 1080
    ORIENTATION = "landscape"
    ASS_FONTSIZE = 54        # px adaptes a une hauteur de 1080
    ASS_MARGINV = 70         # marge basse pour le 16:9

# --- Modele Whisper (synchro sous-titres) ---
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")  # tiny/base/small/medium

# --- Binaires ---
_LOCAL = Path(os.path.expandvars(r"%LOCALAPPDATA%"))


def _find(name, fallbacks):
    found = shutil.which(name)
    if found:
        return found
    for fb in fallbacks:
        if Path(fb).exists():
            return str(fb)
    # Recherche recursive dans les paquets winget (ffmpeg/ffprobe)
    winget = _LOCAL / "Microsoft" / "WinGet" / "Packages"
    if winget.exists():
        hits = list(winget.rglob(f"{name}.exe"))
        if hits:
            return str(hits[0])
    return name  # dernier recours : on tente le nom nu


PYTHON = _find("python", [
    _LOCAL / "Programs" / "Python" / "Python312" / "python.exe",
])
FFMPEG = _find("ffmpeg", [])
FFPROBE = _find("ffprobe", [])


def check():
    """Verifie la presence des outils et cles indispensables."""
    problems = []
    if not PEXELS_API_KEY:
        problems.append("PEXELS_API_KEY manquante (.env)")
    if not ELEVENLABS_API_KEY:
        problems.append("ELEVENLABS_API_KEY manquante -> bascule sur gTTS")
    if shutil.which("ffmpeg") is None and not Path(FFMPEG).exists():
        problems.append("ffmpeg introuvable")
    return problems
