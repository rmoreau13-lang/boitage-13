# CHANGELOG — Cockpit Boîtage 13ᵉ

## v3.1 — 2026-06-03 — Fiabilisation de la sauvegarde + ergonomie terrain

### Priorité 1 — Sauvegarde fiable (plus de perte silencieuse)
- **Supabase = source de vérité.** À la connexion, l'app récupère les données du cloud et les
  fusionne avec le local ; chaque sauvegarde est immédiatement repoussée vers Supabase.
- **Invite claire au 1er lancement** : bannière « Activez la sauvegarde cloud » + écran de
  connexion par **code e-mail** (sans mot de passe) dans l'onglet Données.
- **Photos sorties du localStorage → IndexedDB.** C'était la cause des pertes (quota
  localStorage saturé faisait échouer TOUTES les écritures). Les photos existantes sont
  **migrées automatiquement** au démarrage (et retirées du localStorage, ce qui libère le quota).
  Compression inchangée (redimension 900 px, JPEG qualité 0,6).
- **Gestion du quota / localStorage indisponible** : toute écriture échouée bascule un drapeau
  `localBroken` et affiche une **bannière rouge persistante** « Sauvegarde locale saturée —
  connectez-vous ». Plus jamais de perte silencieuse.
- **Indicateur d'état permanent** en haut à droite : `✓ Sauvegardé` / `⏳ Synchro…` /
  `⚠️ Non sauvegardé`, mis à jour à chaque sauvegarde et à chaque synchro.
- **Fusion par enregistrement** (et non plus par comptage global) : chaque fiche et chaque
  tournée porte un horodatage `u` ; à la synchro, on garde **toujours la version la plus
  récente, fiche par fiche**. Plus aucun risque d'écraser une saisie plus récente.
  Les tournées supprimées utilisent un marqueur (tombstone) pour que la suppression se
  propage entre appareils sans réapparaître.

### Priorité 2 — Sécurité (Row-Level Security)
- La table `app_state` doit avoir la RLS activée (chaque utilisateur ne lit/écrit que SA ligne).
  Le SQL exact à exécuter dans Supabase (SQL Editor) est dans `supabase_init.sql` (rappel en
  bas de ce fichier). Déjà exécuté sur le projet : table + 3 policies vérifiées.

### Priorité 3 — Ergonomie terrain (vélo cargo)
- **Toast de confirmation à chaque enregistrement** (« ✓ Enregistré », « 📭 Boîté ✓ »,
  « 📝 Note ajoutée », « 📷 Photo ajoutée »).
- **Actions rapides en 1 geste depuis la liste** : sur chaque carte, 3 gros boutons tactiles
  **＋ (tournée) · 📭 (boîté) · 📝 (note)** ; le 📭 est aussi accessible depuis la bulle de la carte.
- Boutons et champs agrandis (cibles ≥ 40 px, police 16 px anti-zoom iOS).
- **Charte conservée** : terracotta / crème, typographie Fraunces + Hanken Grotesk, ton inchangé.

### Inchangé (par contrainte)
- `refresh_prospects.py` et la logique open data ADEME : non modifiés (pas de pige/scraping).
- Compatibilité **GitHub Pages** (statique, vanilla JS, aucune étape serveur).

---

### Rappel — SQL Row-Level Security (à coller dans Supabase → SQL Editor)
Voir `supabase_init.sql`. En résumé : table `app_state(user_id, data jsonb, updated_at)`,
RLS activée, 3 policies (`select_own`, `insert_own`, `update_own`) liant `auth.uid() = user_id`.

## v3.0 — Refonte (onglets bas, fiche enrichie, tournées nommées, quartier officiel)
## v2.x — Externalisation prospects.json, MAJ ADEME quotidienne, exclusions, vue mixte
## v1.x — Appli mono-page initiale (carte, liste, fiches, photos, statuts, tournée)
