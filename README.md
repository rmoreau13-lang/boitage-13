# Cockpit Boîtage — 13ᵉ Marseille

Interface de terrain mono-page pour le boîtage (prospection signal-based) dans le 13013.
Carte Leaflet, liste triée, fiches détaillées, photos, 7 statuts de suivi, planificateur de
tournée (vélo / scooter), liens Google Maps + Google Earth.

- **100 % autonome** : aucune installation, aucun backend. Toutes les librairies sont chargées
  via CDN (cdnjs). Fonctionne aussi en local en ouvrant `index.html` (mode `file://`).
- **HTTPS-ready** : la photo (caméra) et le GPS (géolocalisation) nécessitent un contexte
  sécurisé → c'est exactement ce que fournit GitHub Pages.
- **Données ouvertes uniquement** : `prospects.json` ne contient que des adresses et des
  indicateurs issus de l'open data ADEME (DPE). **Vos notes et vos photos restent en local**
  (localStorage du navigateur), elles ne sont **jamais** envoyées ni publiées dans le dépôt.

---

## Contenu du dossier

| Fichier               | Rôle                                                                 |
|-----------------------|----------------------------------------------------------------------|
| `index.html`          | L'application (nom **obligatoire** pour GitHub Pages).               |
| `prospects.json`      | Les 59 prospects, chargés au démarrage par `fetch`. **À remplacer chaque semaine.** |
| `.nojekyll`           | Fichier vide qui désactive le traitement Jekyll de Pages.           |
| `refresh_prospects.py`| Script de recharge depuis l'API ADEME (optionnel, voir plus bas).   |
| `README.md`           | Ce fichier.                                                          |
| `CHANGELOG.md`        | Historique des versions.                                            |

### Comment fonctionne le chargement des données
Au démarrage, `index.html` tente `fetch('prospects.json')`.
- **En ligne (GitHub Pages)** → il charge `prospects.json` : pour mettre à jour, vous
  remplacez **ce seul fichier**.
- **Échec du fetch** (ouverture en `file://`, hors-ligne…) → repli automatique sur une copie
  des données embarquée dans `index.html` (`FALLBACK_DATA`). Le fichier reste donc ouvrable
  d'un simple double-clic, sans serveur.

---

## Déploiement — Option A : par le web (sans Git, le plus simple)

1. Connectez-vous sur https://github.com avec le compte **rmoreau13-lang**.
2. **New repository** → Nom : `boitage-13` → **Public** → *Create repository*.
3. Sur la page du dépôt vide : lien **« uploading an existing file »**.
4. Glissez-déposez **`index.html`, `prospects.json`, `.nojekyll`** (et si vous voulez
   `README.md`, `CHANGELOG.md`). ⚠️ Le `.nojekyll` commence par un point : s'il n'apparaît
   pas dans votre explorateur, activez l'affichage des fichiers cachés.
5. **Commit changes**.
6. Onglet **Settings → Pages** → *Build and deployment* → **Source : Deploy from a branch**
   → Branche **`main`**, dossier **`/ (root)`** → **Save**.
7. Patientez ~1 minute, rechargez. Pages affiche l'URL publique (voir plus bas).

### Mise à jour hebdomadaire (option A)
Dépôt → ouvrez `prospects.json` → icône crayon (ou *Add file → Upload files* en écrasant) →
collez le nouveau contenu → **Commit**. Pages se redéploie tout seul.

---

## Déploiement — Option B : par Git (ligne de commande)

Depuis le dossier qui contient `index.html` :

```bash
git init
git add index.html prospects.json .nojekyll README.md CHANGELOG.md refresh_prospects.py
git commit -m "Cockpit Boîtage 13e — déploiement initial"
git branch -M main
git remote add origin https://github.com/rmoreau13-lang/boitage-13.git
git push -u origin main
```

> **Identifiants : c'est VOUS qui les saisissez.** Au `git push`, GitHub demande votre nom
> d'utilisateur et un **mot de passe = jeton (Personal Access Token)**, pas votre mot de passe
> de compte. Créez-le sur GitHub : **Settings → Developer settings → Personal access tokens →
> Tokens (classic) → Generate new token**, portée **`repo`**. Copiez-le et collez-le comme
> mot de passe quand Git le demande. (Aucun identifiant n'est stocké dans ces fichiers.)

Puis activez Pages : **Settings → Pages → Source : Deploy from a branch → branche `main`,
dossier `/ (root)` → Save.**

### Mise à jour hebdomadaire (option B)
```bash
git add prospects.json
git commit -m "MAJ prospects (extraction ADEME)"
git push
```

---

## URL finale attendue

```
https://rmoreau13-lang.github.io/boitage-13/
```

(Si vous nommez le dépôt autrement : `https://rmoreau13-lang.github.io/<nom-du-repo>/`.)

Ouvrez-la sur votre téléphone, **autorisez la localisation** pour le bouton « Partir d'ici » de
la tournée et **autorisez la caméra** pour les photos de fiche.

---

## Vie privée & éthique

- Seules les **adresses open data ADEME** (DPE) sont publiées dans `prospects.json`.
- Vos **notes terrain, statuts et photos** sont stockés uniquement dans le navigateur de
  l'appareil (localStorage) — ils ne partent pas sur GitHub.
- Démarche **signal-based** : aucune pige, aucun cold-calling.
