#!/usr/bin/env python3
"""
Prend le fichier brut du jour (data/raw/YYYY-MM-DD.json), le fait scorer/tagger/
resumer par Claude, puis ecrit le digest final dans data/YYYY-MM-DD.json et
met a jour data/index.json (liste des dates disponibles pour l'archive).
"""
import json
import os
import sys
import datetime
from pathlib import Path

from anthropic import Anthropic

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DATA_DIR = ROOT / "data"
INDEX_PATH = DATA_DIR / "index.json"

MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 15

SYSTEM_PROMPT = """Tu es l'assistant de veille d'un motion designer professionnel \
(Blender, After Effects, 3D, tendances visuelles, VFX, design d'animation).

Pour chaque item de la liste fournie, evalue sa pertinence et reponds \
UNIQUEMENT avec un tableau JSON (aucun texte avant/apres, pas de balises markdown), \
un objet par item, dans le meme ordre, avec exactement ces cles :
- "id": l'id fourni, inchange
- "score": entier de 1 à 5. ATTENTION : Attribue un score de 1 ou 2 aux YouTube Shorts, formats verticaux superficiels ou contenus putaclic. Le score 5 est reserve aux vraies pépites techniques.
- "tags": tableau de 1 a 3 tags courts en francais (ex: "Blender", "rigging", "tendance")
- "summary_fr": une phrase courte en francais (20 mots maximum) pour la carte.
- "analysis_fr": un resume d'expert approfondi et structure en plusieurs puces avec des tirets (-) détaillant les aspects techniques, logiciels ou l'intérêt concret pour un motion designer. Ne répète pas le summary_fr, apporte de la profondeur technique.

Sois extrêmement exigeant sur le score."""


def load_raw(date_str: str) -> list:
    path = RAW_DIR / f"{date_str}.json"
    if not path.exists():
        print(f"Aucun fichier brut trouve pour {date_str} ({path})", file=sys.stderr)
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def curate_batch(client: Anthropic, items: list) -> dict:
    """Retourne un dict id -> {score, tags, summary_fr, analysis_fr}."""
    payload = [
        {
            "id": it["id"],
            "title": it["title"],
            "source": it["source_name"],
            "excerpt": (it.get("raw_summary") or "")[:1000],
        }
        for it in items
    ]

    message = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": "Voici les items a evaluer (JSON) :\n" + json.dumps(payload, ensure_ascii=False),
        }],
    )

    text = "".join(block.text for block in message.content if block.type == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[curate] Reponse non-JSON, batch ignore: {e}\n{text[:300]}", file=sys.stderr)
        return {}

    return {entry["id"]: entry for entry in parsed if "id" in entry}


def update_index(date_str: str):
    if INDEX_PATH.exists():
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            dates = json.load(f)
    else:
        dates = []
    if date_str not in dates:
        dates.append(date_str)
    dates.sort(reverse=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(dates, f, ensure_ascii=False, indent=2)


def main():
    today = datetime.date.today().isoformat()
    raw_items = load_raw(today)

    # Filtrer d'office les YouTube Shorts (avec protection anti-None)
    raw_items = [
        it for it in raw_items 
        if "/shorts/" not in (it.get("url") or "") and "/shorts/" not in (it.get("external_url") or "")
    ]

    if not raw_items:
        print("Rien a curer aujourd'hui.")
        with open(DATA_DIR / f"{today}.json", "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        update_index(today)
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY manquante, impossible de curer.", file=sys.stderr)
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    scores = {}
    for batch in chunk(raw_items, BATCH_SIZE):
        scores.update(curate_batch(client, batch))

    digest = []
    for it in raw_items:
        curation = scores.get(it["id"])
        if not curation:
            curation = {"score": 2, "tags": [], "summary_fr": "", "analysis_fr": ""}
        
        analysis = curation.get("analysis_fr", "")
        summary = curation.get("summary_fr", "")
        if not analysis or analysis == summary:
            analysis = f"- Analyse technique non détaillée pour cet item.\n- Consultez le lien d'origine pour en savoir plus."

        digest.append({**it, **{
            "score": curation.get("score", 2),
            "tags": curation.get("tags", []),
            "summary_fr": summary,
            "analysis_fr": analysis,
        }})

    # Filtrer pour ne garder que les scores 3, 4 et 5
    digest = [item for item in digest if item.get("score", 0) >= 3]

    digest.sort(key=lambda x: x.get("score", 0), reverse=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / f"{today}.json", "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)

    update_index(today)
    print(f"Curation terminee : {len(digest)} items pertinents (scores 3-5) -> data/{today}.json")


if __name__ == "__main__":
    main()
