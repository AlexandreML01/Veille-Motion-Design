# Veille · Motion Design

Outil de veille journalière automatisée pour une activité de motion design (Blender, After Effects, 3D, tendances visuelles). Un script tourne chaque matin via GitHub Actions, collecte du contenu récent (Reddit, YouTube, flux RSS), le fait scorer/tagger/résumer par l'API Claude, et publie le résultat sur une page GitHub Pages en forme de galerie.

## Mise en route (une seule fois)

1. **Créer le dépôt GitHub**
   Crée un nouveau dépôt (public ou privé) et pousse-y le contenu de ce dossier.

   ```bash
   cd veille-motion-design
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<ton-compte>/<ton-repo>.git
   git push -u origin main
   ```

2. **Ajouter les secrets** (Settings → Secrets and variables → Actions → New repository secret)
   - `ANTHROPIC_API_KEY` — obligatoire, pour la curation IA.
   - `YOUTUBE_API_KEY` — optionnel, seulement si tu veux suivre YouTube (clé gratuite via [Google Cloud Console](https://console.cloud.google.com/), activer "YouTube Data API v3").

3. **Activer GitHub Pages**
   Settings → Pages → Source : `Deploy from a branch` → Branch : `main` / `/(root)`.
   Ta page sera disponible à `https://<ton-compte>.github.io/<ton-repo>/`.

4. **Adapter les sources** dans `config/sources.json` :
   - `reddit.subreddits` : liste déjà pré-remplie avec des subreddits pertinents, à ajuster librement.
   - `youtube.keywords` : mots-clés de recherche (fonctionne sans configuration supplémentaire).
   - `youtube.channels` : optionnel, remplace l'exemple par de vrais `channel_id` si tu veux suivre des chaînes précises.
   - `rss` : liste de flux RSS (blogs déjà pré-remplis). Voir la note ci-dessous pour ArtStation/Behance/Dribbble.

5. **Premier lancement manuel**
   Onglet **Actions** → workflow "Veille quotidienne" → **Run workflow**. Ça évite d'attendre le lendemain matin pour voir le résultat, et ça te permet de vérifier que tout est bien configuré.

Ensuite, le workflow tourne automatiquement tous les jours à 6h UTC (7h ou 8h heure de Paris selon la saison) — modifiable dans `.github/workflows/daily-veille.yml`.

## À propos d'ArtStation, Behance et Dribbble

Ces plateformes n'offrent plus de flux RSS ou d'API publique exploitable gratuitement pour une recherche automatisée (Dribbble a supprimé ses flux RSS par tag ; ArtStation et Behance n'ont jamais eu d'API de recherche publique stable). Deux options concrètes :

- Utiliser un service tiers comme [rss.app](https://rss.app) ou [FeedSpot](https://rss.feedspot.com) qui génère un flux RSS à partir de n'importe quelle URL (recherche ArtStation, profil Behance, etc.), puis coller ce flux dans `config/sources.json` → `rss`. Il sera traité comme n'importe quelle autre source.
- Laisser ces plateformes de côté pour l'automatisation et les consulter manuellement — le reste de la veille (Reddit, YouTube, blogs) couvre déjà une bonne partie des tendances qui y circulent.

## Structure du projet

```
config/sources.json      → sources à surveiller (à éditer librement)
scripts/collect.py       → collecte brute (Reddit, YouTube, RSS)
scripts/curate.py        → scoring/tags/résumé via Claude
data/                    → digests quotidiens générés (data/YYYY-MM-DD.json)
data/index.json          → liste des dates disponibles (alimente l'archive du site)
index.html / style.css / app.js → le site statique servi par GitHub Pages
.github/workflows/       → l'automatisation quotidienne
```

## Développement local

```bash
pip install -r scripts/requirements.txt --break-system-packages
export ANTHROPIC_API_KEY=sk-ant-...
export YOUTUBE_API_KEY=...   # optionnel
python scripts/collect.py
python scripts/curate.py
python -m http.server 8000   # puis ouvrir http://localhost:8000
```

## Coûts

- Reddit et les flux RSS : gratuits, aucune clé requise.
- YouTube Data API v3 : gratuit dans la limite du quota quotidien (10 000 unités/jour, largement suffisant pour cet usage).
- Anthropic (Claude Haiku pour la curation) : de l'ordre de quelques centimes par jour selon le volume d'items collectés.

## Limites connues

- Les flux RSS de blogs peuvent changer d'URL avec le temps ; si un flux ne remonte plus rien, vérifie son URL directement sur le site du blog.
- Le scoring IA est une aide à la priorisation, pas une vérité absolue — les filtres par source et par tag permettent de reprendre la main facilement.
