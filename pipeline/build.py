"""Assemblage ffmpeg : visuels normalises -> clips verticaux 9:16 avec
fondus, voix off, musique et sous-titres incrustes."""
import random
from pathlib import Path

from . import config as C
from .media import run, duration


# ----------------------------------------------------------------------------
# Normalisation d'un visuel (video ou photo) -> clip silencieux 1080x1920
# ----------------------------------------------------------------------------
def normalize_visual(src, out_mp4, dur, mode="crop"):
    """Normalise un visuel au format courant (C.WIDTH x C.HEIGHT).

    mode="crop"  : remplit tout le cadre en rognant (defaut ; ideal plans serres
                   ou stock deja au bon ratio).
    mode="entier": integre l'image ENTIERE avec un fond noir (fit/letterbox) ;
                   ideal pour les plans cinematiques larges (espace, paysages)
                   ou le rognage couperait le sujet. Le fond noir est invisible
                   sur des plans deja sombres.
    """
    src = Path(src)
    out_mp4 = Path(out_mp4)
    if mode == "entier":
        fit = (f"scale={C.WIDTH}:{C.HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={C.WIDTH}:{C.HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
               f"setsar=1,fps={C.FPS}")
    scale_crop = (f"scale={C.WIDTH}:{C.HEIGHT}:force_original_aspect_ratio=increase,"
                  f"crop={C.WIDTH}:{C.HEIGHT},setsar=1,fps={C.FPS}")
    if src.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
        # Video : on boucle si trop courte, on coupe a 'dur'
        vf = fit if mode == "entier" else scale_crop
        cmd = [C.FFMPEG, "-y", "-stream_loop", "-1", "-i", str(src),
               "-t", f"{dur:.3f}",
               "-vf", vf, "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", str(out_mp4)]
    elif mode == "entier":
        # Photo en mode entier : image fixe centree sur fond noir (pas de Ken Burns
        # car le zoom recadrerait justement ce qu'on veut garder entier).
        cmd = [C.FFMPEG, "-y", "-loop", "1", "-i", str(src),
               "-t", f"{dur:.3f}", "-vf", fit,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", str(out_mp4)]
    else:
        # Photo : effet Ken Burns (zoom progressif doux)
        frames = max(1, int(dur * C.FPS))
        zoom = (f"scale=-2:{C.HEIGHT*2},"
                f"zoompan=z='min(zoom+0.0006,1.12)':d={frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={C.WIDTH}x{C.HEIGHT}:fps={C.FPS},setsar=1")
        cmd = [C.FFMPEG, "-y", "-loop", "1", "-i", str(src),
               "-t", f"{dur:.3f}", "-vf", zoom,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", str(out_mp4)]
    run(cmd)
    return out_mp4


# ----------------------------------------------------------------------------
# Regroupement des segments en clips de 61-68 s
# ----------------------------------------------------------------------------
def pack_segments(durations):
    """Renvoie une liste de groupes d'indices de segments."""
    clips, cur, cur_d = [], [], 0.0
    for i, d in enumerate(durations):
        if cur and cur_d + d > C.CLIP_MAX:
            clips.append(cur)
            cur, cur_d = [], 0.0
        cur.append(i)
        cur_d += d
        if C.CLIP_MIN <= cur_d <= C.CLIP_MAX:
            clips.append(cur)
            cur, cur_d = [], 0.0
    if cur:
        clips.append(cur)
    return clips


# ----------------------------------------------------------------------------
# Concatenation des voix d'un clip -> piste continue
# ----------------------------------------------------------------------------
def concat_audio(mp3_list, out_wav, workdir):
    listfile = Path(workdir) / "voices.txt"
    listfile.write_text(
        "".join(f"file '{Path(p).as_posix()}'\n" for p in mp3_list),
        encoding="utf-8")
    run([C.FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
         "-ar", "44100", "-ac", "2", str(out_wav)])
    return out_wav


# ----------------------------------------------------------------------------
# Assemblage final d'un clip
# ----------------------------------------------------------------------------
def assemble_clip(visuals, seg_durs, voice_wav, subs_name, out_mp4, workdir,
                  music=None):
    """visuals : chemins des clips normalises (longueur d_i + T, dernier + pad).
    subs_name : nom du fichier .ass (relatif au workdir), ou None pour ne pas
    incruster de sous-titres.
    Tout tourne avec cwd=workdir pour eviter l'echappement des ':' Windows.
    """
    workdir = Path(workdir)
    n = len(visuals)
    voice_len = sum(seg_durs)
    target = max(voice_len, C.CLIP_MIN)

    cmd = [C.FFMPEG, "-y"]
    for v in visuals:
        cmd += ["-i", Path(v).name]            # chemins relatifs au workdir
    cmd += ["-i", Path(voice_wav).name]
    voice_idx = n
    if music:
        cmd += ["-i", str(music)]
        music_idx = n + 1

    fc = []
    # --- Chaine video : fondus enchaines xfade ---
    if n == 1:
        fc.append(f"[0:v]null[vbg]")
    else:
        cum = 0.0
        prev = "0:v"
        for k in range(1, n):
            cum += seg_durs[k - 1]
            out = f"vx{k}" if k < n - 1 else "vbg"
            fc.append(
                f"[{prev}][{k}:v]xfade=transition=fade:"
                f"duration={C.TRANSITION}:offset={cum:.3f}[{out}]")
            prev = out
    # --- Sous-titres incrustes (.ass : style + resolution embarques) ---
    if subs_name:
        fc.append(f"[vbg]subtitles={subs_name}[vout]")
        vmap = "[vout]"
    else:
        vmap = "[vbg]"

    # --- Chaine audio ---
    fc.append(f"[{voice_idx}:a]apad=whole_dur={target:.3f},"
              f"atrim=0:{target:.3f},asetpts=PTS-STARTPTS[av]")
    if music:
        fade_st = max(0.0, target - 1.0)
        fc.append(f"[{music_idx}:a]aloop=loop=-1:size=2000000000,"
                  f"volume={C.MUSIC_VOLUME},atrim=0:{target:.3f},"
                  f"afade=t=out:st={fade_st:.3f}:d=1[am]")
        fc.append("[av][am]amix=inputs=2:duration=first:"
                  "dropout_transition=0[aout]")
        amap = "[aout]"
    else:
        amap = "[av]"

    cmd += ["-filter_complex", ";".join(fc),
            "-map", vmap, "-map", amap,
            "-t", f"{target:.3f}", "-r", str(C.FPS),
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-movflags", "+faststart", str(Path(out_mp4).resolve())]
    run(cmd, cwd=workdir)
    return out_mp4


def concat_clips(clip_paths, out_mp4, workdir):
    """Assemble tous les clips en une video longue (copie sans re-encodage)."""
    listfile = Path(workdir) / "clips.txt"
    listfile.write_text(
        "".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in clip_paths),
        encoding="utf-8")
    run([C.FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
         "-c", "copy", "-movflags", "+faststart", str(out_mp4)])
    return out_mp4


def pick_music(ambiance=None):
    """Choisit une piste au hasard dans music/<ambiance>/ (fallback racine)."""
    exts = (".mp3", ".wav", ".m4a", ".ogg")
    search_dirs = []
    if ambiance:
        search_dirs.append(C.MUSIC_DIR / ambiance)
    search_dirs.append(C.MUSIC_DIR)
    for d in search_dirs:
        if d.exists():
            tracks = [p for p in d.iterdir() if p.suffix.lower() in exts]
            if tracks:
                return random.choice(tracks)
    return None
