"""Orchestrateur : transforme un projet (segments.json) en clips TikTok 9:16.

Usage :
    python -m pipeline projets/<mon-sujet>
    python -m pipeline projets/<mon-sujet> --no-eleven   (force gTTS)
"""
import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

from . import config as C
from . import media as M
from . import build as B
from . import gemini as G
from . import youtube as Y


def log(msg):
    print(msg, flush=True)


def load_project(project_dir):
    project_dir = Path(project_dir)
    data = json.loads((project_dir / "segments.json").read_text(encoding="utf-8"))
    segs = data["segments"]
    default_cadrage = data.get("cadrage", "crop")
    for i, s in enumerate(segs):
        s.setdefault("recherche", data.get("titre", "abstract background"))
        s.setdefault("cadrage", default_cadrage)
        s["_i"] = i
    return data, segs


def _slug(x):
    return str(x).replace(":", "-").replace(".", "_")


def ensure_extract(seg, project, keep_audio):
    """Telecharge (cache) et decoupe l'extrait YouTube d'un segment. Renseigne
    seg['_clip'] (chemin video) et renvoie ce chemin, ou None si pas d'extrait."""
    url = seg.get("source")
    if not url:
        return None
    debut, fin = seg.get("debut"), seg.get("fin")
    if debut is None or fin is None:
        log(f"   [!] seg {seg['_i']:02d} : 'source' sans 'debut'/'fin', ignore.")
        return None
    meta = Y.info(url)
    clip_dir = project / "sources" / meta["id"] / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_a" if keep_audio else ""
    out = clip_dir / f"{_slug(debut)}_{_slug(fin)}{suffix}.mp4"
    if not out.exists() or out.stat().st_size == 0:
        Y.get_clip(url, debut, fin, out, project, keep_audio=keep_audio)
    seg["_clip"] = out
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("project", help="dossier du projet contenant segments.json")
    ap.add_argument("--no-gemini", action="store_true",
                    help="ne pas utiliser Gemini TTS (ElevenLabs/gTTS)")
    ap.add_argument("--no-eleven", action="store_true",
                    help="ne pas utiliser ElevenLabs")
    ap.add_argument("--subs", action="store_true",
                    help="incruster les sous-titres de la narration (off par defaut)")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--ambiance", choices=C.AMBIANCES, default=None,
                    help="ambiance musicale (sinon valeur du segments.json)")
    args = ap.parse_args(argv)

    project = Path(args.project).resolve()
    if not (project / "segments.json").exists():
        log(f"[X] {project/'segments.json'} introuvable.")
        return 1

    problems = C.check()
    for p in problems:
        log(f"[!] {p}")

    data, segs = load_project(project)
    # Le dossier audio est partage entre le rendu vertical et le rendu paysage :
    # la voix off (et son cache) est generee une seule fois, donc aucun appel
    # ElevenLabs supplementaire pour la version longue YouTube.
    audio_dir = project / "audio"; audio_dir.mkdir(exist_ok=True)
    out_dir = project / "output"; out_dir.mkdir(exist_ok=True)

    t0 = time.time()
    log(f"\n=== Projet : {data.get('titre','(sans titre)')} "
        f"| {len(segs)} segments ===\n")

    if args.subs:
        C.SUBTITLES_NARRATION = True

    # --- 1. Audio par segment : voix off (narration) OU audio d'un extrait ---
    # Voix off : cache par hash du texte (une ligne inchangee reutilise son audio,
    # ne reconsomme pas le quota TTS). Extraits "qui parlent" : on garde leur
    # audio original. Les extraits "visuels" sont coupes sans audio (voix dessus).
    use_gemini = not args.no_gemini
    use_eleven = not args.no_eleven
    if use_gemini and G.available():
        # La voix et le style font partie de la cle de cache : changer
        # GEMINI_VOICE/GEMINI_TTS_STYLE re-synthetise (pas d'audio perime).
        sig = hashlib.md5(
            f"{C.GEMINI_VOICE}|{C.GEMINI_TTS_STYLE}".encode("utf-8")).hexdigest()[:8]
        engine_tag = f"gemini-{sig}"
    elif use_eleven and C.ELEVENLABS_API_KEY:
        engine_tag = "eleven"
    else:
        engine_tag = "gtts"
    log(f"[1/5] Audio par segment (voix off : {engine_tag} | extraits YouTube)...")
    cache_dir = audio_dir / "cache"; cache_dir.mkdir(exist_ok=True)
    durations = []
    for s in segs:
        mp3 = audio_dir / f"seg_{s['_i']:02d}.mp3"
        if s.get("source") and s.get("extrait_audio"):
            # Extrait qui parle de lui-meme : video+audio, pas de voix off.
            clip = ensure_extract(s, project, keep_audio=True)
            M.extract_audio(clip, mp3)
            engine = "extrait"
            label = f"[YT {s.get('debut')}-{s.get('fin')}]"
        else:
            h = hashlib.md5(f"{engine_tag}:{s['texte']}".encode("utf-8")).hexdigest()
            cached = cache_dir / f"{h}.mp3"
            if cached.exists() and cached.stat().st_size > 0:
                shutil.copyfile(cached, mp3)
                engine = "cache"
            else:
                engine = M.synth_voice(s["texte"], mp3,
                                       use_gemini=use_gemini, use_elevenlabs=use_eleven)
                shutil.copyfile(mp3, cached)
            # Extrait utilise comme visuel sous la narration (audio coupe).
            if s.get("source"):
                ensure_extract(s, project, keep_audio=False)
            label = s["texte"][:48]
        d = M.duration(mp3)
        durations.append(d)
        s["_dur"] = d
        log(f"   seg {s['_i']:02d} [{engine:10s}] {d:5.1f}s  {label}")

    # --- 2. Decoupage en clips 61-68 s ---
    clips = B.pack_segments(durations)
    log(f"\n[2/5] Decoupage : {len(clips)} clip(s) -> "
        + ", ".join(f"{sum(durations[i] for i in g):.0f}s" for g in clips))

    ambiance = args.ambiance or data.get("ambiance") or C.DEFAULT_AMBIANCE
    music = None if args.no_music else B.pick_music(ambiance)
    log(f"      Ambiance : {ambiance} | "
        f"Musique : {music.name if music else 'aucune'}")

    # --- 3. Prep partagee : audio concatene + evenements de sous-titres.
    #        Les sous-titres sont calcules une seule fois (memes evenements pour
    #        le 9:16 et le 16:9). Par defaut PAS de sous-titres sur la narration ;
    #        les extraits en anglais recoivent un sous-titrage TRADUIT en FR. ---
    log("\n[3/5] Audio concatene + sous-titres (extraits traduits FR)...")
    specs = []
    for ci, group in enumerate(clips, start=1):
        voice_wav = audio_dir / f"clip_{ci}_voice.wav"
        B.concat_audio([audio_dir / f"seg_{i:02d}.mp3" for i in group],
                       voice_wav, audio_dir)
        events = []
        cursor = 0.0
        for gi in group:
            seg = segs[gi]
            seg_mp3 = audio_dir / f"seg_{gi:02d}.mp3"
            langue = str(seg.get("langue", "")).lower()
            is_extract_audio = bool(seg.get("source") and seg.get("extrait_audio"))
            if is_extract_audio and langue.startswith("en"):
                phrases = M.transcribe_segments(seg_mp3, language="en")
                texts = [p[0] for p in phrases]
                fr = texts
                if texts and G.available():
                    try:
                        fr = G.translate_lines(texts)
                    except Exception as e:
                        log(f"   [!] Traduction FR echouee ({str(e)[:100]}); VO.")
                elif texts:
                    log("   [!] Pas de cle Gemini : sous-titres extrait en VO (anglais).")
                for (txt, st, en), tr in zip(phrases, fr):
                    events.append((cursor + st, cursor + en, tr))
            elif C.SUBTITLES_NARRATION and not is_extract_audio:
                words = M.transcribe_words(seg_mp3, language="fr")
                events.extend(M.words_to_events(words, offset=cursor))
            cursor += durations[gi]
        events.sort(key=lambda e: e[0])
        specs.append({
            "ci": ci, "group": group,
            "seg_durs": [durations[i] for i in group],
            "voice_wav": voice_wav, "events": events,
        })
        log(f"   clip {ci}: {len(events)} sous-titre(s)")

    # --- 4. Clips courts au format vertical 9:16 (TikTok) ---
    C.use_portrait()
    log(f"\n[4/5] Clips courts vertical {C.WIDTH}x{C.HEIGHT} (TikTok)...")
    vert_clips = _render_pass(specs, segs, project, music,
                              out_dir=out_dir,
                              work_dir=project / "work",
                              assets_dir=project / "assets",
                              label="9:16")

    # --- 5. Version longue au format paysage 16:9 (YouTube), image entiere ---
    C.use_landscape()
    log(f"\n[5/5] Version longue paysage {C.WIDTH}x{C.HEIGHT} (YouTube)...")
    land_clips = _render_pass(specs, segs, project, music,
                              out_dir=project / "work_youtube" / "clips",
                              work_dir=project / "work_youtube",
                              assets_dir=project / "assets_youtube",
                              label="16:9")
    long_mp4 = out_dir / "video_longue.mp4"
    B.concat_clips(land_clips, long_mp4, project / "work_youtube")
    log(f"\nVersion longue (16:9) -> {long_mp4.name} ({M.duration(long_mp4):.1f}s)")

    log(f"\n=== Termine en {time.time()-t0:.0f}s. "
        f"{len(vert_clips)} clip(s) verticaux + 1 version longue 16:9 "
        f"dans {out_dir} ===")
    return 0


def _render_pass(specs, segs, project, music, out_dir, work_dir, assets_dir, label):
    """Rend tous les clips a l'orientation courante (C.WIDTH/HEIGHT/ORIENTATION).
    La voix et les mots Whisper viennent de 'specs' (calcules une seule fois),
    donc seuls les visuels et les sous-titres sont (re)generes a la bonne taille.
    Renvoie la liste des mp4 produits."""
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    clip_files = []
    # Visuels deja utilises dans cette video (jamais le meme clip 2 fois).
    used_visuals = set()
    for spec in specs:
        ci, group = spec["ci"], spec["group"]
        seg_durs = spec["seg_durs"]
        n = len(group)
        voice_len = sum(seg_durs)
        target = max(voice_len, C.CLIP_MIN)
        pad = target - voice_len
        cwork = work_dir / f"clip_{ci}"; cwork.mkdir(exist_ok=True)
        log(f"\n--- {label} clip {ci}/{len(specs)} ({n} segments) ---")

        # Visuels (orientation = C.ORIENTATION) + normalisation
        visuals = []
        for j, gi in enumerate(group):
            seg = segs[gi]
            query = seg.get("recherche", "")
            clip = seg.get("_clip")      # extrait YouTube deja telecharge/coupe
            local = seg.get("fichier")   # visuel local fourni par l'utilisateur
            if clip:
                path = Path(clip)
                kind = "yt" if path.exists() else None
                if kind is None:
                    log(f"   [!] Extrait YouTube introuvable : {clip}")
            elif local:
                path = project / local
                if not path.exists():
                    path = Path(local)
                kind = "local" if path.exists() else None
                if kind is None:
                    log(f"   [!] Fichier local introuvable : {local}")
            else:
                raw = assets_dir / f"c{ci}_s{gi:02d}"
                kind, path, vkey = M.download_media(query, raw, exclude=used_visuals)
                if vkey:
                    used_visuals.add(vkey)
            if not kind or path is None:
                log(f"   [!] Aucun visuel pour '{query or local}', fond noir genere.")
                path = _black(cwork / f"black_{gi}.mp4", 2.0)
                kind = "video"
            if n == 1:
                vlen = target
            else:
                vlen = seg_durs[j] + C.TRANSITION + (pad if j == n - 1 else 0.0)
            norm = cwork / f"v_{j:02d}.mp4"
            B.normalize_visual(path, norm, vlen, mode=seg.get("cadrage", "crop"))
            visuals.append(norm)
            log(f"   seg {gi:02d} [{kind:5s}|{seg.get('cadrage','crop')}] "
                f"'{query}' -> {norm.name} ({vlen:.1f}s)")

        # Voix (copiee dans le workdir du clip pour l'assemblage) + sous-titres
        # generes a l'orientation courante (PlayResX/Y, taille de police, marges).
        # subs_name = None -> aucun sous-titre incruste sur ce clip.
        voice_wav = cwork / "voice.wav"
        shutil.copyfile(spec["voice_wav"], voice_wav)
        events = spec.get("events") or []
        subs_name = None
        if events:
            ass = cwork / "subs.ass"
            M.write_ass(events, ass)
            M.write_srt(events, cwork / "subs.srt")   # reference editable
            subs_name = ass.name

        out_mp4 = out_dir / f"clip_{ci}.mp4"
        B.assemble_clip(visuals, seg_durs, voice_wav, subs_name, out_mp4,
                        cwork, music=music)
        log(f"   -> {out_mp4.name}  ({M.duration(out_mp4):.1f}s)")
        clip_files.append(out_mp4)
    return clip_files


def _black(out, dur):
    M.run([C.FFMPEG, "-y", "-f", "lavfi", "-i",
           f"color=c=black:s={C.WIDTH}x{C.HEIGHT}:r={C.FPS}",
           "-t", f"{dur}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])
    return out


if __name__ == "__main__":
    sys.exit(main())
