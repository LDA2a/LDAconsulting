"""Scouting et extraction d'extraits YouTube (yt-dlp + ffmpeg).

Workflow agent-native : l'utilisateur envoie une URL, Claude « scoute » la video
(telechargement + transcription horodatee + planche-contact d'images tamponnees
au timecode) pour reperer lui-meme les moments forts, puis decoupe les extraits
choisis. L'utilisateur n'a jamais a fournir de timecode.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as C
from .media import run, duration


# Police Windows pour le tampon timecode sur les images de la planche-contact.
_FONT = None
for _f in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
    if Path(_f).exists():
        # Dans un filtergraph ffmpeg, les ':' du chemin doivent etre echappes.
        _FONT = _f.replace("\\", "/").replace(":", r"\:")
        break


def _ytdlp(args):
    """Lance yt-dlp via l'interpreteur Python courant (evite l'alias
    Microsoft Store que shutil.which peut renvoyer dans config.PYTHON).

    --no-check-certificates : le subprocess yt-dlp ne beneficie pas de
    truststore.inject_into_ssl() (applique en-process dans config.py), donc il
    echoue en CERTIFICATE_VERIFY_FAILED derriere l'antivirus/proxy qui inspecte
    le TLS sur cette machine. On desactive la verification cote yt-dlp."""
    return run([sys.executable, "-m", "yt_dlp", "--no-check-certificates", *args])


_INFO_CACHE = {}


def info(url):
    """Renvoie {id, duration, title} d'une video sans la telecharger (cache)."""
    if url in _INFO_CACHE:
        return dict(_INFO_CACHE[url])
    proc = _ytdlp(["--skip-download", "--no-warnings",
                   "--print", "%(id)s\t%(duration)s\t%(title)s", url])
    line = proc.stdout.strip().splitlines()[-1]
    vid, dur, title = (line.split("\t") + ["", "", ""])[:3]
    meta = {"id": vid, "duration": float(dur or 0), "title": title}
    _INFO_CACHE[url] = dict(meta)
    return meta


def fetch_source(url, dest_dir, max_height=1080):
    """Telecharge la video complete (cache par id). Renvoie le chemin du .mp4."""
    meta = info(url)
    vid = meta["id"]
    vdir = Path(dest_dir) / vid
    vdir.mkdir(parents=True, exist_ok=True)
    src = vdir / "source.mp4"
    if not src.exists() or src.stat().st_size == 0:
        _ytdlp([
            "-f", f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
            "--merge-output-format", "mp4",
            "-o", str(vdir / "source.%(ext)s"),
            url,
        ])
        # yt-dlp peut sortir .mkv/.webm selon les flux : on normalise le nom.
        if not src.exists():
            for cand in vdir.glob("source.*"):
                if cand.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"):
                    cand.rename(src)
                    break
    meta["source"] = src
    return meta


def fetch_transcript(url, dest_dir):
    """Recupere les sous-titres (manuels puis auto, fr/en) et les convertit en
    transcription horodatee lisible. Renvoie le chemin .txt, ou None si aucun
    sous-titre (frequent pour les extraits sport/action) ou si YouTube throttle.
    """
    meta = info(url)
    vdir = Path(dest_dir) / meta["id"]
    vdir.mkdir(parents=True, exist_ok=True)
    # Liste de langues exacte (pas de wildcard) pour limiter le nombre de
    # requetes et eviter les 429 dus aux pistes auto-traduites.
    try:
        _ytdlp([
            "--skip-download", "--no-warnings",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", "fr,en,en-orig,en-US,en-GB",
            "--sub-format", "vtt/best",
            "-o", str(vdir / "subs.%(ext)s"),
            url,
        ])
    except Exception as e:
        print(f"   [!] Transcription indisponible ({str(e)[:120]}).")
    vtts = sorted(vdir.glob("subs*.vtt"))
    if not vtts:
        return None
    # Priorite fr puis en.
    def lang_rank(p):
        n = p.name.lower()
        return (0 if ".fr" in n else 1 if ".en" in n else 2, n)
    vtt = sorted(vtts, key=lang_rank)[0]
    txt = _vtt_to_transcript(vtt)
    out = vdir / "transcript.txt"
    out.write_text(txt, encoding="utf-8")
    return out


def _vtt_to_transcript(vtt_path):
    """Convertit un .vtt (souvent redondant pour l'auto-sub) en lignes
    '[mm:ss] texte' dedupliquees."""
    raw = Path(vtt_path).read_text(encoding="utf-8", errors="ignore")
    ts_re = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.\d{3}\s+-->")
    tag_re = re.compile(r"<[^>]+>")
    out, last_text, cur_ts = [], None, None
    for line in raw.splitlines():
        m = ts_re.search(line)
        if m:
            h, mn, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            cur_ts = f"{h*60+mn:02d}:{s:02d}"
            continue
        if not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        text = tag_re.sub("", line).strip()
        if not text or text == last_text:
            continue
        out.append(f"[{cur_ts}] {text}")
        last_text = text
    return "\n".join(out)


def contact_sheets(source_mp4, out_dir, interval=5.0, cols=4, rows=5, thumb_w=360):
    """Genere des planches-contact : 1 image toutes 'interval' secondes, tamponnee
    avec son timecode, assemblees en grille cols x rows. Renvoie la liste des .jpg.
    """
    source_mp4 = Path(source_mp4)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("contact_*.jpg"):
        old.unlink()
    draw = ""
    if _FONT:
        draw = (f",drawtext=fontfile='{_FONT}':text='%{{pts\\:hms}}':"
                f"x=8:y=8:fontsize=22:fontcolor=yellow:box=1:boxcolor=black@0.7")
    vf = (f"fps=1/{interval},scale={thumb_w}:-1{draw},tile={cols}x{rows}")
    run([C.FFMPEG, "-y", "-i", str(source_mp4), "-vf", vf,
         "-qscale:v", "3", str(out_dir / "contact_%02d.jpg")])
    return sorted(out_dir.glob("contact_*.jpg"))


def scout(url, project_dir, interval=5.0):
    """Prepare tout le materiel pour reperer les moments forts d'une URL :
    telecharge la source, la transcription horodatee et les planches-contact.
    Renvoie un dict {id, title, duration, source, transcript, sheets}.
    """
    project_dir = Path(project_dir)
    sources = project_dir / "sources"
    meta = fetch_source(url, sources)
    meta["transcript"] = fetch_transcript(url, sources)
    sheet_dir = sources / meta["id"] / "contact"
    meta["sheets"] = contact_sheets(meta["source"], sheet_dir, interval=interval)
    return meta


def _hms(t):
    """Accepte 12, '01:12', '00:01:12', '1:12.5' -> secondes (float)."""
    if isinstance(t, (int, float)):
        return float(t)
    parts = str(t).strip().split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return h * 3600 + m * 60 + s


def get_clip(url, start, end, out_mp4, project_dir, keep_audio=True):
    """Extrait l'intervalle [start, end] d'une video YouTube vers out_mp4.
    Coupe depuis la source locale en cache si disponible (sinon telecharge la
    section). 'start'/'end' acceptent secondes ou 'mm:ss'/'hh:mm:ss'.
    """
    start_s, end_s = _hms(start), _hms(end)
    dur = max(0.1, end_s - start_s)
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    sources = Path(project_dir) / "sources"

    meta = info(url)
    src = sources / meta["id"] / "source.mp4"
    if not src.exists():
        meta = fetch_source(url, sources)
        src = meta["source"]

    acodec = ["-c:a", "aac", "-b:a", "192k"] if keep_audio else ["-an"]
    run([C.FFMPEG, "-y", "-ss", f"{start_s:.3f}", "-i", str(src),
         "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", *acodec, str(out_mp4)])
    return out_mp4
