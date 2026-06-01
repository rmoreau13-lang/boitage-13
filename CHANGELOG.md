# CHANGELOG — Cockpit Boîtage 13ᵉ

## v2.0 — 2026-06-01 — Package GitHub Pages
- **Externalisation des données** : les 59 prospects sortent dans `prospects.json`,
  chargé au démarrage par `fetch('prospects.json')`. Mise à jour hebdo = remplacer
  ce seul fichier.
- **Repli embarqué** : copie des données conservée dans `index.html` (`FALLBACK_DATA`).
  Si le `fetch` échoue (ouverture en `file://`, hors-ligne), l'app bascule dessus →
  le fichier reste ouvrable d'un double-clic, sans serveur.
- **Compteurs d'en-tête dynamiques** : prospects / ⭐ / 🔥 recalculés selon les données
  réellement chargées (plus de valeurs figées).
- **Ajout `.nojekyll`** : désactive le traitement Jekyll de GitHub Pages.
- **Ajout `refresh_prospects.py`** : recharge depuis l'API open data ADEME
  (DPE logements existants, maison / 13013 / 60 derniers jours). Reproduit `prio`
  (quartiers cibles), `tier` (fraîcheur) et l'affectation par quartier (plus proche
  centroïde) ; score reconstitué et paramétrable.
- **Docs** : `README.md` (déploiement web ou git + activation Pages + URL finale),
  ce `CHANGELOG.md`.
- **Vie privée** : `prospects.json` ne contient que de l'open data ADEME. Notes, statuts
  et photos restent en local (localStorage), hors du dépôt.

## v1.x — antérieur
- Application mono-page de terrain : carte Leaflet, liste triée, fiches, photos,
  7 statuts de suivi, planificateur de tournée (vélo / scooter), liens Google Maps
  + Google Earth. Données prospects embarquées dans `index.html`.
