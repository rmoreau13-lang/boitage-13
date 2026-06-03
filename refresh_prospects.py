#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_prospects.py — Régénère prospects.json depuis l'open data ADEME (DPE).

Dataset : "DPE logements existants Métropole Aix-Marseille-Provence"
          -> slug API : meg-83tjwtg8dyz4vv7h1dqe
API     : https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines
Filtre  : type_batiment = maison, code_postal_ban = 13013, date_etablissement_dpe >= aujourd'hui - 90 j

Aucune clé d'API requise. Aucune donnée personnelle : uniquement de l'open data (adresses + DPE).
Démarche signal-based : on NE vérifie PAS les annonces en ligne (pas de pige / scraping).
Les nouveaux prospects sortent donc avec statut "Aucune annonce trouvée".

--------------------------------------------------------------------------------
CE QUI EST FIDÈLEMENT REPRODUIT depuis vos données actuelles :
  • prio   : True si le quartier appartient à PRIO_QUARTIERS (quartiers cibles de l'agence).
  • tier   : chaud / tiede / froid selon la fraîcheur du DPE (seuils TIER_*).
  • quartier (q) : affecté au quartier connu le plus proche (centroïdes FIGÉS, CENTROIDES_REF).

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
API = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"

PRIO_QUARTIERS = {            # quartiers cibles -> prio=True (déduit de vos données)
    "Château-Gombert", "Saint-Jérôme", "Les Médecins", "Palama", "Les Mourets",
}

# Quartiers EXCLUS du boîtage : tout prospect affecté à l'un d'eux est ignoré.
EXCLUDE_QUARTIERS = {"Les Olives", "Les Martégaux"}

# --- Quartier OFFICIEL (champ "qoff" en plus) : croisement point-dans-polygone
#     avec les 111 quartiers officiels de Marseille (décret 1946, contours INSEE).
GEOJSON_QUARTIERS = ("https://static.data.gouv.fr/resources/quartiers-de-marseille-1/"
                     "20210308-145904/quartiers-marseille.geojson")
# Normalisation des libellés officiels (NOM_QUA en MAJUSCULES -> joli libellé).
NORM_QUA = {
    "SAINT MITRE": "Saint-Mitre", "LES MEDECINS": "Les Médecins",
    "SAINT JEROME": "Saint-Jérôme", "CHATEAU-GOMBERT": "Château-Gombert",
    "PALAMA": "Palama", "SAINT JUST": "Saint-Just", "LES OLIVES": "Les Olives",
    "MALPASSE": "Malpassé", "LA CROIX ROUGE": "La Croix-Rouge",
    "LES MOURETS": "Les Mourets", "LA ROSE": "La Rose", "FRAIS VALLON": "Frais Vallon",
    "MONTOLIVET": "Montolivet", "SAINT BARNABE": "Saint-Barnabé",
}

# Centroïdes de référence (lat, lon) FIGÉS — calculés une fois depuis le prospects.json
# d'origine. On les fige pour que l'affectation par quartier reste STABLE jour après jour
# (sinon, recalculer depuis un fichier régénéré ferait dériver les frontières de quartiers).
CENTROIDES_REF = {
    "Château-Gombert": (43.346314, 5.426105),
    "Saint-Jérôme":    (43.331163, 5.417234),
    "Clair Soleil":    (43.349280, 5.446723),
    "Les Médecins":    (43.359562, 5.459901),
    "Les Olives":      (43.324423, 5.453130),
    "Saint-Just":      (43.318792, 5.399255),
    "Saint-Mitre":     (43.346792, 5.416707),
    "Palama":          (43.359259, 5.440727),
    "Les Mourets":     (43.351601, 5.436561),
    "La Croix-Rouge":  (43.336171, 5.440412),
    "Malpassé":        (43.323078, 5.406721),
    "Petit Bosquet":   (43.358270, 5.428719),
}

# Garde-fou : on n'écrit PAS prospects.json si l'API renvoie moins que ce seuil
# (évite d'écraser vos données par un fichier vide en cas de souci côté ADEME).
MIN_PROSPECTS = 10

# Seuils de fraîcheur (en jours depuis l'établissement du DPE)
TIER_CHAUD = 30              # <= 30 j  -> chaud
TIER_TIEDE = 60              # <= 60 j  -> tiede, sinon froid

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
    "conso_5_usages_par_m2_ep",   # énergie primaire (nouveau dataset)
    "emission_ges_5_usages_par_m2",
    "adresse_ban", "adresse_brut", "_geopoint", "periode_construction",
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

def nearest_quartier(lat, lon, cents):
    return min(cents.items(), key=lambda kv: haversine(lat, lon, kv[1][0], kv[1][1]))[0]

def clean_addr(rec):
    """Reconstruit '28 Traverse Collet Redon' à partir des champs ADEME."""
    a = (rec.get("adresse_ban") or "").strip()
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

# ------------------------------------------------------------------ quartier officiel
def load_quartiers(timeout=60):
    """Télécharge le GeoJSON officiel des quartiers. Renvoie [] en cas d'échec."""
    try:
        req = urllib.request.Request(GEOJSON_QUARTIERS, headers={"User-Agent": "boitage-13/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            gj = json.load(r)
        return gj.get("features", [])
    except Exception as e:
        print("   (quartier officiel indisponible : %s)" % e)
        return []

def _in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def _in_poly(lon, lat, poly):           # poly = [outer, hole1, ...]
    if not _in_ring(lon, lat, poly[0]):
        return False
    return not any(_in_ring(lon, lat, h) for h in poly[1:])

def quartier_officiel(lat, lon, feats):
    for f in feats:
        gm = f.get("geometry") or {}
        t = gm.get("type")
        coords = gm.get("coordinates")
        hit = False
        if t == "Polygon":
            hit = _in_poly(lon, lat, coords)
        elif t == "MultiPolygon":
            hit = any(_in_poly(lon, lat, p) for p in coords)
        if hit:
            raw = (f.get("properties") or {}).get("NOM_QUA", "")
            return NORM_QUA.get(raw, raw.title())
    return ""

# ------------------------------------------------------------------ API ADEME
def fetch_all(cp, since_iso, page=1000, timeout=60):
    qs = ('type_batiment:maison AND code_postal_ban:%s '
          'AND date_etablissement_dpe:[%s TO *]' % (cp, since_iso))
    params = {"qs": qs, "select": SELECT, "size": str(page),
              "sort": "-date_etablissement_dpe"}
    url = API + "?" + urllib.parse.urlencode(params)
    rows = []
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "boitage-13/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.load(r)
        batch = payload.get("results", [])
        rows.extend(batch)
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
    conso = rec.get("conso_5_usages_par_m2_ep")   # énergie primaire
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
        "qoff": "",            # quartier officiel (rempli dans main via point-dans-polygone)
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
        "gmaps": "https://maps.google.com/?q=%s,%s" % (lat, lon),
        "deja": deja,
        "conso": round(float(conso)) if conso else None,
        "gesv": round(float(gesv)) if gesv else None,
        "chauf": rec.get("type_energie_principale_chauffage"),
    }

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Recharge prospects.json depuis l'API ADEME (DPE).")
    ap.add_argument("--days", type=int, default=90, help="fenetre d'anciennete max du DPE (jours)")
    ap.add_argument("--cp", default="13013", help="code postal BAN")
    ap.add_argument("--out", default=str(HERE / "prospects.json"), help="fichier de sortie")
    args = ap.parse_args()

    out = Path(args.out)
    today = date.today()
    since = (today - timedelta(days=args.days)).isoformat()

    cents = CENTROIDES_REF          # centroides figes -> affectation stable
    print("-> %d quartiers de reference (centroides figes)." % len(cents))

    print("-> ADEME : maisons CP %s, DPE depuis %s ..." % (args.cp, since))
    rows = fetch_all(args.cp, since)
    print("   %d DPE bruts recus." % len(rows))

    feats = load_quartiers()
    print("   %d quartiers officiels charges." % len(feats))

    seen, prospects = set(), []
    for rec in rows:
        nid = rec.get("numero_dpe")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        p = to_prospect(rec, today, cents)
        if p and p["q"] not in EXCLUDE_QUARTIERS:
            if feats:
                p["qoff"] = quartier_officiel(p["lat"], p["lon"], feats)
            prospects.append(p)

    if len(prospects) < MIN_PROSPECTS:
        sys.exit("ABANDON : seulement %d prospect(s) (< %d). prospects.json N'EST PAS modifie "
                 "(probable souci cote API ADEME)." % (len(prospects), MIN_PROSPECTS))

    prospects.sort(key=lambda p: p["score"], reverse=True)
    for i, p in enumerate(prospects, 1):
        p["rang"] = i

    out.write_text(json.dumps(prospects, ensure_ascii=False, indent=1), encoding="utf-8")
    chauds = sum(1 for p in prospects if p["tier"] == "chaud")
    stars = sum(1 for p in prospects if p["prio"])
    print("OK %s : %d prospects  (%d etoiles, %d chauds)" % (out, len(prospects), stars, chauds))
    print('   Pensez a re-pousser : git add prospects.json && '
          'git commit -m "MAJ prospects (extraction ADEME)" && git push')

if __name__ == "__main__":
    main()
