#!/usr/bin/env python3
"""
Collecte les nouveaux contenus des sources configurees dans config/sources.json
et produit un fichier JSON brut (non score) dans data/raw/YYYY-MM-DD.json

Sources supportees :
  - Reddit (endpoints JSON publics, sans authentification)
  - YouTube (YouTube Data API v3, necessite YOUTUBE_API_KEY)
  - RSS (n'importe quel flux, via feedparser)
"""
import json
import os
import sys
import hashlib
import datetime
import time
from pathlib import Path

import requests
import feedparser

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sources.json"
RAW_DIR = ROOT / "data" / "raw"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def item_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def within_lookback(published_dt: datetime.datetime, lookback_hours: int) -> bool:
    if published_dt is None:
        # Si on ne connait pas la date de publication, on garde l'item
        # plutot que de risquer de rater du contenu (les flux RSS mal formes existent).
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    if published_dt.tzinfo is None:
        published_dt = published_dt.replace(tzinfo=datetime.timezone.utc)
    return (now - published_dt) <= datetime.timedelta(hours=lookback_hours)


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------
def collect_reddit(cfg: dict, lookback_hours: int) -> list:
    items = []
    rcfg = cfg.get("reddit", {})
    if not rcfg.get("enabled", True):
        return items

    min_upvotes = rcfg.get("min_upvotes", 0)
    headers = {"User-Agent": USER_AGENT}

    for sub in rcfg.get("subreddits", []):
        url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            print(f"[reddit] Erreur sur r/{sub}: {e}", file=sys.stderr)
            continue

        for child in payload.get("data", {}).get("children", []):
            post = child.get("data", {})
            score = post.get("score", 0)
            if score < min_upvotes:
                continue

            created = datetime.datetime.fromtimestamp(
                post.get("created_utc", 0), tz=datetime.timezone.utc
            )
            if not within_lookback(created, lookback_hours):
                continue

            permalink = f"https://www.reddit.com{post.get('permalink', '')}"
            thumb = post.get("thumbnail", "")
            if thumb in ("self", "default", "nsfw", "spoiler", ""):
                thumb = None

            items.append({
                "id": item_id(permalink),
                "title": post.get("title", "").strip(),
                "url": permalink,
                "external_url": post.get("url") if not post.get("is_self") else None,
                "source": "reddit",
                "source_name": f"r/{sub}",
                "published": created.isoformat(),
                "thumbnail": thumb,
                "raw_summary": (post.get("selftext") or "")[:500],
                "meta": {"score": score, "num_comments": post.get("num_comments", 0)},
            })

        time.sleep(1)  # politesse envers l'API publique de Reddit

    return items


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------
def collect_youtube(cfg: dict, lookback_hours: int) -> list:
    items = []
    ycfg = cfg.get("youtube", {})
    if not ycfg.get("enabled", True):
        return items

    api_key = os.environ.get(ycfg.get("api_key_env", "YOUTUBE_API_KEY"))
    if not api_key:
        print("[youtube] Pas de cle API trouvee, source ignoree.", file=sys.stderr)
        return items

    max_results = ycfg.get("max_results_per_query", 6)
    published_after = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=lookback_hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    search_url = "https://www.googleapis.com/youtube/v3/search"

    def run_search(params):
        params = {
            **params,
            "part": "snippet",
            "type": "video",
            "order": "date",
            "publishedAfter": published_after,
            "maxResults": max_results,
            "key": api_key,
        }
        try:
            resp = requests.get(search_url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json().get("items", [])
        except Exception as e:
            print(f"[youtube] Erreur de requete: {e}", file=sys.stderr)
            return []

    queries = []
    for kw in ycfg.get("keywords", []):
        queries.append({"q": kw})
    for ch in ycfg.get("channels", []):
        cid = ch.get("channel_id", "")
        if cid and not cid.startswith("UCxxxx"):
            queries.append({"channelId": cid})

    seen_video_ids = set()
    for q in queries:
        for entry in run_search(q):
            vid = entry.get("id", {}).get("videoId")
            if not vid or vid in seen_video_ids:
                continue
            seen_video_ids.add(vid)

            snippet = entry.get("snippet", {})
            video_url = f"https://www.youtube.com/watch?v={vid}"
            thumbs = snippet.get("thumbnails", {})
            thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")

            items.append({
                "id": item_id(video_url),
                "title": snippet.get("title", "").strip(),
                "url": video_url,
                "external_url": None,
                "source": "youtube",
                "source_name": snippet.get("channelTitle", "YouTube"),
                "published": snippet.get("publishedAt"),
                "thumbnail": thumb,
                "raw_summary": (snippet.get("description") or "")[:500],
                "meta": {},
            })

    return items


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------
def collect_rss(cfg: dict, lookback_hours: int) -> list:
    items = []
    for feed_cfg in cfg.get("rss", []):
        name = feed_cfg.get("name", "RSS")
        url = feed_cfg.get("url")
        if not url:
            continue
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"[rss] Erreur sur {name}: {e}", file=sys.stderr)
            continue

        for entry in parsed.entries:
            link = entry.get("link")
            if not link:
                continue

            published_dt = None
            for field in ("published_parsed", "updated_parsed"):
                tm = entry.get(field)
                if tm:
                    published_dt = datetime.datetime(*tm[:6], tzinfo=datetime.timezone.utc)
                    break

            if not within_lookback(published_dt, lookback_hours):
                continue

            thumb = None
            if "media_thumbnail" in entry and entry.media_thumbnail:
                thumb = entry.media_thumbnail[0].get("url")
            elif "media_content" in entry and entry.media_content:
                thumb = entry.media_content[0].get("url")
            elif "links" in entry:
                for l in entry.links:
                    if l.get("type", "").startswith("image/"):
                        thumb = l.get("href")
                        break

            summary = entry.get("summary", "") or ""

            items.append({
                "id": item_id(link),
                "title": entry.get("title", "").strip(),
                "url": link,
                "external_url": None,
                "source": "rss",
                "source_name": name,
                "published": published_dt.isoformat() if published_dt else None,
                "thumbnail": thumb,
                "raw_summary": summary[:500],
                "meta": {},
            })

    return items


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    cfg = load_config()
    lookback_hours = cfg.get("lookback_hours", 30)

    all_items = []
    all_items += collect_reddit(cfg, lookback_hours)
    all_items += collect_youtube(cfg, lookback_hours)
    all_items += collect_rss(cfg, lookback_hours)

    # Dedoublonnage par id (= hash de l'URL)
    dedup = {item["id"]: item for item in all_items}
    result = list(dedup.values())
    result.sort(key=lambda x: x.get("published") or "", reverse=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    out_path = RAW_DIR / f"{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Collecte terminee : {len(result)} items -> {out_path}")


if __name__ == "__main__":
    main()
