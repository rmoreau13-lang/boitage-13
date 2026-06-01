#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_prospects.py — Régénère prospects.json depuis l'open data ADEME (DPE).

Dataset : "DPE logements existants (depuis juillet 2021)"  ->  slug API : dpe03existant
API     : https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines
Filtre  : type_batiment = maison, code_postal_ban = 13013, date_etablissement_dpe >= aujourd'hui - 60 j

Aucune clé d'API requise. Aucune donnée personnelle : uniquement de l'open data (adresses + DPE).
Démarche signal-based : on NE vérifie PAS les annonces en ligne (pas de pige / scraping).
Les nouveaux prospects sortent donc avec statut "Aucune annonce trouvée".

--------------------------------------------------------------------------------
CE QUI EST FIDÈLEMENT REPRODUIT depuis vos données actuelles :
  • prio   : True si le quartier appartient à PRIO_QUARTIERS (quartiers cibles de l'agence).
  • tier   : chaud / tiede / froid selon la fraîcheur du DPE (seuils TIER_*).
  • quartier (q) : affecté au quartier connu le plus proche (centroïdes calculés
                   à partir du prospects.json existant -> apprentissage automatique léger).

CE QUI EST RECONSTITUÉ (le score exact n'existait pas dans le HTML, il était pré-calculé) :
  • score  : formule transparente et PARAMÉTRABLE ci-dessous (constantes W_*).
             Ajustez les poids pour coller au scoring de votre agence ; l'ordre de
             priorité (rang) en découle automatiquement.
--------------------------------------------------------------------------------

Usage :
  python3 refresh_prospects.py                 # écrit prospects.json (à côté du script)
  python3 refresh_prospects.py --days 60 --cp 13013 --out prospects.json
"""

import argparse, json, math, sys, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# ------------------------------------------------------------------ paramètres
API = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"

PRIO_QUARTIERS = {            # quartiers cibles -> prio=True (déduit de vos données)
    "Château-Gombert", "Saint-Jérôme", "Les Médecins", "Palama", "Les Mourets",
}

# Seuils de fraîcheur (en jours depuis l'établissement du DPE)
TIER_CHAUD = 21              # <= 21 j  -> chaud
TIER_TIEDE = 42              # <= 42 j  -> tiede, sinon froid

# Poids du score (PARAMÉTRABLES) — score borné ensuite à [-20 ; 100]
W_FRAICHEUR = 35.0           # bonus max pour un DPE tout frais (décroît jusqu'à 60 j)
W_SURFACE   = 22.0           # bonus max pour une grande maison (plafonné à 220 m²)
W_PRIO      = 12.0           # bonus quartier cible
W_PASSOIRE  = 8.0            # petit bonus si forte conso (levier de discours rénovation/vente)
PEN_ANNONCE = 40.0           # pénalité si une annonce est déjà active (deja=True)

# Champs ADEME récupérés (limite la charge réseau)
SELECT = ",".join([
    "numero_dpe", "type_batiment", "code_postal_ban", "date_etablissement_dpe",
    "etiquette_dpe", "etiquette_ges", "surface_habitable_logement",
    "nombre_niveau_logement", "annee_construction", "type_energie_principale_chauffage",
    "conso_5_usages_par_m2_ef", "emission_ges_5_usages_par_m2",
    "adresse_ban", "adresse_brut", "_geopoint",
])

HERE = Path(__file__).resolve().parent

# ------------------------------------------------------------------ utilitaires
def haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371.0
    r = math.pi / 180
    dla = (b_lat - a_lat) * r
    dlo = (b_lon - a_lon) * r
    h = math.sin(dla / 2) ** 2 + math.cos(a_lat * r) * math.cos(b_lat * r) * math.sin(dlo / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def load_centroids(out_path):
    """Centroïdes (lat/lon moyens) de chaque quartier à partir du prospects.json existant."""
    if not out_path.exists():
        sys.exit("ERREUR : prospects.json introuvable à côté du script ; "
                 "il sert de référence pour l'affectation par quartier. "
                 "Gardez la version livrée dans le dossier avant de lancer la recharge.")
    data = json.loads(out_path.read_text(encoding="utf-8"))
    acc = {}
    for p in data:
        if p.get("lat") is None or p.get("q") is None:
            continue
        acc.setdefault(p["q"], []).append((p["lat"], p["lon"]))
    cents = {q: (sum(x[0] for x in v) / len(v), sum(x[1] for x in v) / len(v))
             for q, v in acc.items()}
    if not cents:
        sys.exit("ERREUR : impossible de calculer des centroïdes de quartiers.")
    return cents

def nearest_quartier(lat, lon, cents):
    return min(cents.items(), key=lambda kv: haversine(lat, lon, kv[1][0], kv[1][1]))[0]

def clean_addr(rec):
    """Reconstruit '28 Traverse Collet Redon' à partir des champs ADEME."""
    a = (rec.get("adresse_ban") or "").strip()
    # adresse_ban = "Chemin des Jonquilles 13013 Marseille" -> on retire CP + ville
    for tail in (" 13013 Marseille", " 13013 MARSEILLE", "13013 Marseille", "13013"):
        a = a.replace(tail, "")
    a = a.replace("Marseille", "").strip(" ,")
    if not a:
        a = (rec.get("adresse_brut") or "").strip()
    return a.title() if a else "Adresse inconnue"

def geo(rec):
    g = rec.get("_geopoint")
    if not g:
        return None, None
    try:
        la, lo = g.split(",")
        return float(la), float(lo)
    except Exception:
        return None, None

# ------------------------------------------------------------------ API ADEME
def fetch_all(cp, since_iso, page=1000, timeout=60):
    qs = (f'type_batiment:"maison" AND code_postal_ban:"{cp}" '
          f'AND date_etablissement_dpe:[{since_iso} TO *]')
    params = {"qs": qs, "select": SELECT, "size": str(page),
              "sort": "-date_etablissement_dpe"}
    url = API + "?" + urllib.parse.urlencode(params)
    rows, seen = [], 0
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "boitage-13/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.load(r)
        batch = payload.get("results", [])
        rows.extend(batch)
        seen += len(batch)
        url = payload.get("next")          # pagination par curseur data-fair
        if not batch:
            break
    return rows

# ------------------------------------------------------------------ transform
def to_prospect(rec, today, cents):
    lat, lon = geo(rec)
    if lat is None:
        return None
    d_iso = (rec.get("date_etablissement_dpe") or "")[:10]
    try:
        jours = (today - datetime.strptime(d_iso, "%Y-%m-%d").date()).days
    except Exception:
        return None
    if jours < 0:
        jours = 0

    q = nearest_quartier(lat, lon, cents)
    prio = q in PRIO_QUARTIERS
    tier = "chaud" if jours <= TIER_CHAUD else ("tiede" if jours <= TIER_TIEDE else "froid")

    surface = rec.get("surface_habitable_logement")
    conso = rec.get("conso_5_usages_par_m2_ef")
    gesv = rec.get("emission_ges_5_usages_par_m2")

    # --- score reconstitué (paramétrable via W_*) ---
    s = 0.0
    s += W_FRAICHEUR * max(0.0, 1 - jours / 60.0)
    if surface:
        s += W_SURFACE * min(float(surface), 220.0) / 220.0
    if prio:
        s += W_PRIO
    if conso and float(conso) >= 220:        # passoire / fort levier rénovation
        s += W_PASSOIRE
    deja = False                              # signal-based : pas de vérif d'annonces
    if deja:
        s -= PEN_ANNONCE
    score = max(-20, min(100, round(s)))

    return {
        "id": rec.get("numero_dpe"),
        "q": q,
        "prio": prio,
        "date": d_iso,
        "jours": jours,
        "dpe": rec.get("etiquette_dpe"),
        "ges": rec.get("etiquette_ges"),
        "surface": round(float(surface), 1) if surface else None,
        "niv": rec.get("nombre_niveau_logement"),
        "annee": rec.get("annee_construction"),
        "adresse": clean_addr(rec),
        "statut": "Aucune annonce trouvée",
        "flags": [],
        "tier": tier,
        "score": score,
        "lat": lat,
        "lon": lon,
        "gmaps": f"https://maps.google.com/?q={lat},{lon}",
        "deja": deja,
        "conso": round(float(conso)) if conso else None,
        "gesv": round(float(gesv)) if gesv else None,
        "chauf": rec.get("type_energie_principale_chauffage"),
    }

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Recharge prospects.json depuis l'API ADEME (DPE).")
    ap.add_argument("--days", type=int, default=60, help="fenêtre d'ancienneté max du DPE (jours)")
    ap.add_argument("--cp", default="13013", help="code postal BAN")
    ap.add_argument("--out", default=str(HERE / "prospects.json"), help="fichier de sortie")
    args = ap.parse_args()

    out = Path(args.out)
    today = date.today()
    since = (today - timedelta(days=args.days)).isoformat()

    print(f"→ Centroïdes de quartiers depuis {out.name} (référence)…")
    cents = load_centroids(out)
    print(f"  {len(cents)} quartiers connus.")

    print(f"→ ADEME : maisons CP {args.cp}, DPE depuis {since} …")
    rows = fetch_all(args.cp, since)
    print(f"  {len(rows)} DPE bruts reçus.")

    seen, prospects = set(), []
    for rec in rows:
        nid = rec.get("numero_dpe")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        p = to_prospect(rec, today, cents)
        if p:
            prospects.append(p)

    prospects.sort(key=lambda p: p["score"], reverse=True)
    for i, p in enumerate(prospects, 1):
        p["rang"] = i

    out.write_text(json.dumps(prospects, ensure_ascii=False, indent=1), encoding="utf-8")
    chauds = sum(1 for p in prospects if p["tier"] == "chaud")
    stars = sum(1 for p in prospects if p["prio"])
    print(f"✓ {out} : {len(prospects)} prospects  ({stars} ⭐ · {chauds} 🔥)")
    print("  Pensez à re-pousser :  git add prospects.json && "
          'git commit -m "MAJ prospects (extraction ADEME)" && git push')

if __name__ == "__main__":
    main()
