# 🎬 Pipeline vidéo TikTok automatisé — LDA Consulting

Transforme un sujet en **clips courts verticaux 9:16 (1080×1920), 61–68 s** pour
TikTok/Reels/Shorts **+ une version longue paysage 16:9 (1920×1080)** pour YouTube
(image entière, vraies vidéos horizontales) : voix off, visuels Pexels **ou
extraits YouTube réels**, musique de fond.

> **Style storytelling (juin 2026)** : pas de sous-titres sur la narration par
> défaut (rendu moins « IA ») ; le visuel et la voix portent le récit. Les
> **extraits en langue étrangère** reçoivent quand même un **sous-titrage traduit
> en français**. Voix off via **Gemini TTS** (ton conteur), repli ElevenLabs → gTTS.

## ⭐ Formule validée — reproduire le rendu (toute session)

Le rendu de référence (voix dynamique, extraits réels, cadrage propre) est
**100 % reproductible** : tous les réglages vivent dans le projet, pas dans une
conversation. Pour une nouvelle vidéo :

1. **Copie le modèle** `projets/_modele/` → `projets/<ton-sujet>/`.
2. Remplis `segments.json` (le modèle contient des champs `_aide` explicatifs).
3. Lance :
   ```powershell
   python -m pipeline projets/<ton-sujet>
   ```

La formule validée appliquée par défaut :
- **Voix Gemini dynamique** (rythmée, pas lente) — réglée dans `pipeline/config.py`.
- **Vrais extraits YouTube** comme visuels (`source`/`debut`/`fin`), pas de stock générique.
- **`"cadrage": "entier"`** pour les plans larges/espace (image complète, pas de crop qui vide l'image en 9:16).
- **Pas de sous-titres** sur la narration (sauf extrait étranger → traduit FR).
- **Jamais le même plan** deux fois.
- Écriture **méthode storytelling** : hook fort, cause→conséquence, chute marquante.

Les **clés API** (`.env`) et le **code** restent sur le disque : une autre session
produit exactement le même type de rendu.

> **Double format automatique** : un seul `python -m pipeline projets/<sujet>`
> produit les deux. La voix off est générée une seule fois (cache partagé) — aucun
> appel ElevenLabs supplémentaire pour la version longue.

## Workflow

1. **Tu envoies un sujet** (texte ou fichier explicatif) à Claude.
2. **Claude écrit le script narratif** et le sauvegarde en
   `projets/<sujet>/segments.json` (narration découpée + mots-clés visuels).
3. **Le pipeline produit tout** :
   ```powershell
   python -m pipeline projets/<sujet>
   ```
4. Récupère le tout dans `projets/<sujet>/output/` :
   - `clip_1.mp4`, `clip_2.mp4`, … → **clips courts verticaux 9:16** (TikTok)
   - `video_longue.mp4` → **version longue paysage 16:9** (YouTube)
5. **Tu postes** les clips sur TikTok (TikTok Studio / Buffer) et la version
   longue sur YouTube.

## Format de `segments.json`

```json
{
  "titre": "Mon sujet",
  "langue": "fr",
  "ambiance": "documentaire",
  "segments": [
    { "texte": "Phrase de narration accrocheuse.", "recherche": "english keywords" }
  ]
}
```
- `texte` : narration FR (≈ 1 idée par segment, ~10 s parlées).
- `recherche` : mots-clés **en anglais** (cherché sur Pexels puis Pixabay).
- `fichier` *(optionnel)* : chemin d'un clip/image **local** à utiliser au lieu
  de la recherche stock (ex. `"fichier": "broll/gameplay1.mp4"`). Idéal pour le
  contenu jeu vidéo ou tout visuel propriétaire que tu fournis toi-même.
- `ambiance` : `calme` | `documentaire` | `epique` | `energie` (musique auto).
- `cadrage` *(optionnel, projet ou segment)* : `crop` (défaut, remplit en
  rognant) ou `entier` (image entière sur fond noir / letterbox). Mets
  **`entier` pour les plans cinématiques larges** (espace, paysages, extraits
  16:9) : le rognage centré couperait le sujet décentré et laisserait du noir
  vide en 9:16 ; `entier` garde toute l'image (fond noir invisible sur l'espace).
- Vise **~150 mots de narration par clip** pour remplir 61–68 s.
- **Anti-doublon** : un même clip stock n'est jamais réutilisé deux fois dans une
  vidéo (règle storytelling « jamais le même plan »).

### Extraits YouTube (visuels réels)

Pour utiliser un **extrait d'une vraie vidéo YouTube** (échec, interview, match,
archive…) au lieu du stock Pexels :

```json
{ "texte": "...", "source": "https://youtu.be/XXXX", "debut": "01:12", "fin": "01:19" }
```

| Champ | Effet |
|-------|-------|
| `source` | URL YouTube. L'extrait `[debut, fin]` devient le **visuel** du segment (recadré 9:16 / 16:9). |
| `debut` / `fin` | timecodes `mm:ss` ou `hh:mm:ss` (ou secondes). |
| `extrait_audio: true` | **garde l'audio original** de l'extrait et **supprime la voix off** dessus → « l'extrait parle de lui-même ». La durée du segment = durée de l'extrait. |
| `langue: "en"` | l'extrait est en anglais → **sous-titres traduits en FR** (Gemini), positionnés et synchronisés. |

> **Tu n'as qu'à envoyer le lien.** Claude « scoute » la vidéo (télécharge,
> récupère la transcription horodatée et une planche-contact d'images tamponnées
> au timecode), repère lui-même les moments forts et remplit `debut`/`fin`. La
> source complète est mise en cache dans `projets/<sujet>/sources/<id>/`.

## Ce que fait le pipeline (5 étapes)

| Étape | Outil | Détail |
|-------|-------|--------|
| 1. Audio | Gemini TTS (→ ElevenLabs → gTTS) | 1 audio par segment ; les extraits `extrait_audio` gardent leur son |
| 2. Découpage | — | regroupe les segments en clips de 61–68 s |
| 3. Visuels | Pexels/Pixabay **ou yt-dlp** | vidéo par segment ; extrait YouTube si `source`, sinon stock |
| 4. Sous-titres | faster-whisper + Gemini | **off par défaut** ; extraits étrangers → transcrits puis traduits FR |
| 5. Assemblage | ffmpeg | double rendu 9:16 (clips) + 16:9 (long), fondus `xfade`, musique |

## Configuration (`.env`)

```
PEXELS_API_KEY=...
GEMINI_API_KEY=...                          # voix off + traduction sous-titres
GEMINI_VOICE=Charon                         # voix conteur (optionnel)
ELEVENLABS_API_KEY=...                       # repli si Gemini absent
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb     # George (conteur)
```
⚠️ `.env` est ignoré par git — ne jamais le commiter.

### Voix off Gemini (prioritaire)
1. Crée une clé **gratuite** sur https://aistudio.google.com/apikey
   (distincte de l'abonnement de l'app Gemini).
2. Ajoute `GEMINI_API_KEY=...` dans `.env`.
3. Le pipeline l'utilise en priorité pour la voix off et pour traduire les
   sous-titres des extraits étrangers. Voix par défaut : **Charon** (grave,
   conteur) ; autres voix et ton réglables via `GEMINI_VOICE` / `GEMINI_TTS_STYLE`.

Forcer le repli : `--no-gemini` (ElevenLabs/gTTS) · `--no-eleven`.

### Voix ElevenLabs (plan gratuit)
Seules les voix **premade** sont autorisées via l'API. Quelques IDs FR-compatibles :
- `JBFqnCBsd6RMkjVDRZzb` George (conteur chaleureux) — défaut
- `nPczCjzI2devNBz1zQrb` Brian (grave, posé)
- `onwK4e9ZLuTAKqWW03F9` Daniel (broadcaster)
- `XrExE9yKIg1WjnnlVkGX` Matilda (pro, féminine)

Quota gratuit ≈ 10 000 caractères/mois. Au-delà, bascule auto sur **gTTS**.
Forcer gTTS : `python -m pipeline projets/<sujet> --no-eleven`.

## Musique de fond (par ambiance)

Range tes `.mp3` **libres de droit** dans les sous-dossiers de `music/` :
```
music/calme/         lo-fi, chill   -> philo, histoire posée
music/documentaire/  neutre, sérieux -> récit, histoire
music/epique/        cinématique     -> médiéval, épopée
music/energie/       motivation      -> sport
```
Le pipeline choisit une piste au hasard dans le dossier correspondant à
l'`ambiance` du projet (volume bas, fondu de sortie).
Sources gratuites : **YouTube Audio Library**, **Pixabay Music**.

Options : `--ambiance epique` (forcer) · `--no-music` (sans).

## Options

| Option | Effet |
|--------|-------|
| `--no-gemini` | ne pas utiliser Gemini TTS (repli ElevenLabs/gTTS) |
| `--no-eleven` | ne pas utiliser ElevenLabs |
| `--subs` | incruster les sous-titres de la narration (off par défaut) |
| `--no-music` | pas de musique de fond |

## Prérequis (déjà installés)

- Python 3.12, ffmpeg 8.x
- `pip install requests python-dotenv gTTS faster-whisper Pillow truststore yt-dlp`
