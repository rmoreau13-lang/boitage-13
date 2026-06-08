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
    # Nouveaux secteurs étendus
    "Allauch", "Plan-de-Cuques", "La Pounche", "Le Logis-Neuf", "La Barasse",
    "Saint-Barnabé", "Montolivet", "La Valentine", "Saint-Marcel",
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
    # ── 13013 — lieux-dits cadastraux officiels ──────────────────────────────
    "Château-Gombert":           (43.346314, 5.426105),
    "Saint-Jérôme":             (43.331163, 5.417234),
    "Clair Soleil":             (43.349280, 5.446723),
    "Les Médecins":             (43.360288, 5.459193),  # cadastre
    "Les Olives":               (43.324423, 5.453130),
    "Saint-Just":               (43.318792, 5.399255),
    "Saint-Mitre":              (43.346792, 5.416707),
    "Palama":                   (43.359259, 5.440727),
    "Les Mourets":              (43.351601, 5.436561),
    "La Croix-Rouge":           (43.336171, 5.440412),
    "Malpassé":                 (43.323078, 5.406721),
    "Petit Bosquet":            (43.358270, 5.428719),
    # Lieux-dits cadastraux 13013
    "Jeandaï":                  (43.354957, 5.428769),
    "La Baudouine":             (43.356490, 5.436936),
    "La Bertrane":              (43.356485, 5.450875),
    "La Béthéline":            (43.359167, 5.451118),
    "La Figonne":               (43.364107, 5.443848),
    "La Grave":                 (43.355157, 5.456858),
    "La Moussiere":             (43.355300, 5.438320),
    "La Nègre":                 (43.374141, 5.450724),
    "La Parade":                (43.359935, 5.439199),
    "Le Cavaou":                (43.354740, 5.457583),
    "Le Jas":                   (43.366499, 5.454094),
    "Le Jausèou":               (43.361833, 5.459256),
    "Le Vallon Gombert":        (43.357044, 5.424915),
    "Les Couestes":             (43.360718, 5.444707),
    "Les Durbecs":              (43.355984, 5.455381),
    "Les Milanais":             (43.366291, 5.443170),
    "Les Molières":             (43.352175, 5.453998),
    "Les Politres":             (43.359726, 5.455449),
    "Les Xaviers":              (43.361928, 5.446286),
    "Mont-Louis":               (43.362743, 5.443008),
    "Mouret-Bas":               (43.359365, 5.431797),
    "Mouret-Haut":              (43.359897, 5.429041),
    "Mouret-Nord":              (43.361800, 5.429863),
    "Mouret-Ouest":             (43.358617, 5.426542),
    "Section De L'Etoile":      (43.381322, 5.433522),
    "Section De La Pible":      (43.384608, 5.442428),
    "Section De Niolong":       (43.379358, 5.444996),
    "Section Du Chateau Palama":(43.371702, 5.438794),
    "Section Du Sauveur":       (43.372010, 5.446078),
    "Vallon De Serre":          (43.355245, 5.419651),
    "Varsi":                    (43.366811, 5.444616),
    # ── Allauch (13190) — lieux-dits cadastraux ──────────────────────────────
    "Allauch":                  (43.335510, 5.481471),  # Le Village
    "Le Village Allauch":       (43.335510, 5.481471),
    "La Pounche":               (43.334013, 5.462193),  # cadastre
    "Font-Vert":                (43.335800, 5.470943),
    "La Rigonne":               (43.336443, 5.467561),
    "Canton Rouge":             (43.338915, 5.464329),
    "Blacassin":                (43.340548, 5.468897),
    "Caguerasset":              (43.346223, 5.484746),
    "Sainte-Croix Allauch":     (43.334847, 5.492375),
    "Les Claous":               (43.340815, 5.491886),
    "Le Logis Neuf":            (43.359811, 5.486445),
    "La Bourdonniere":          (43.359258, 5.490651),
    "Les Barnabelles":          (43.356001, 5.475197),
    "Vallon De Gage":           (43.359421, 5.475414),
    "Bon Rencontre":            (43.352865, 5.478014),
    "La Barasse":               (43.322000, 5.474000),
    "Belle-Vue Allauch":        (43.321684, 5.486725),
    "Callian":                  (43.318385, 5.483142),
    "L'Andouiller":             (43.318929, 5.486213),
    "La Salle":                 (43.323179, 5.482848),
    "Font De Brouqueli":        (43.332095, 5.459568),
    "La Tiranne":               (43.337553, 5.468645),
    "Rascous":                  (43.343923, 5.475429),
    "Loir D'Ambremont":         (43.343753, 5.484099),
    "Peyre-Peissot":            (43.346724, 5.489237),
    "Quartier De La Caleche":   (43.351622, 5.489529),
    "Sainte-Euphemie":          (43.343400, 5.472621),
    # ── Plan-de-Cuques (13380) — lieux-dits cadastraux ───────────────────────
    "Plan-de-Cuques":           (43.409725, 5.307863),  # Le Village PDC
    "La Renardiere":            (43.417052, 5.304041),
    "Le Logis Neuf PDC":        (43.409142, 5.327885),
    "La Condamine":             (43.410069, 5.316232),
    "Plan De Campagne":         (43.419214, 5.353668),
    "Les Cadeneaux":            (43.391527, 5.341620),
    "La Gavotte":               (43.379001, 5.350255),
    "Calas":                    (43.377837, 5.343851),
    "La Charbonniere":          (43.418173, 5.368198),
    "Barnouin":                 (43.422841, 5.317026),
    "La Burliere":              (43.411676, 5.315952),
    "Les Pinchinades":          (43.427343, 5.295937),
    "La Billonne":              (43.417866, 5.296598),
    "Le Brusq":                 (43.406537, 5.297511),
    "La Grande Colle":          (43.397846, 5.310411),
    "Jas De Rhodes":            (43.387419, 5.309704),
    # ── 13012 — quartiers / secteurs ───────────────────────────────────────
    "La Valentine":             (43.298000, 5.448000),
    "Saint-Marcel":             (43.303000, 5.427000),
    "Les Accates":              (43.310135, 5.436019),
    "La Destrousse":            (43.315000, 5.445000),
    "Les Camoins":              (43.307000, 5.453000),
    "Font Obscure":             (43.319000, 5.440000),
    "Roy D'Espagne":            (43.297000, 5.427000),
    # ── 13004 — quartiers ───────────────────────────────────────────────────
    "Saint-Barnabé":           (43.306945, 5.402527),
    "Montolivet":               (43.313000, 5.413000),
    "La Pomme":                 (43.307000, 5.421000),
    "Saint-Tronc":              (43.299000, 5.410000),
    "Les Trois-Lucs":           (43.310000, 5.397000),
    # ── 13005 — quartiers ───────────────────────────────────────────────────
    "Baille":                   (43.292483, 5.397472),
    "Castellane":               (43.289000, 5.395000),
    "Sakakini":                 (43.295000, 5.395000),
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
    """Reconstruit l'adresse propre depuis les champs ADEME."""
    a = (rec.get("adresse_ban") or "").strip()
    for cp in ["13013", "13004", "13014"]:
        for suffix in [" %s Marseille" % cp, " %s MARSEILLE" % cp, "%s Marseille" % cp, cp]:
            a = a.replace(suffix, "")
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
    ap.add_argument("--days", type=int, default=360, help="fenetre d'anciennete max du DPE (jours)")
    ap.add_argument("--cp",  default="13013", help="code postal BAN principal")
    ap.add_argument("--cp2", default="", help="2e code postal BAN (optionnel)")
    ap.add_argument("--cp3", default="", help="3e code postal BAN (optionnel)")
    ap.add_argument("--cp4", default="", help="4e code postal BAN (optionnel)")
    ap.add_argument("--cp5", default="", help="5e code postal BAN (optionnel)")
    ap.add_argument("--cp6", default="", help="6e code postal BAN (optionnel)")
    ap.add_argument("--out", default=str(HERE / "prospects.json"), help="fichier de sortie")
    args = ap.parse_args()

    out = Path(args.out)
    today = date.today()
    since = (today - timedelta(days=args.days)).isoformat()

    cents = CENTROIDES_REF          # centroides figes -> affectation stable
    print("-> %d quartiers de reference (centroides figes)." % len(cents))

    # Interroge tous les codes postaux et dédoublonne
    codes = [c for c in [args.cp, args.cp2, args.cp3, args.cp4, args.cp5, args.cp6] if c]
    rows_all, seen_ids = [], set()
    for cp in codes:
        print("-> ADEME : maisons CP %s, DPE depuis %s ..." % (cp, since))
        batch = fetch_all(cp, since)
        print("   %d DPE bruts recus." % len(batch))
        for r in batch:
            nid = r.get("numero_dpe")
            if nid and nid not in seen_ids:
                seen_ids.add(nid)
                rows_all.append(r)
    rows = rows_all
    print("-> Total unique DPE maisons : %d" % len(rows))

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
