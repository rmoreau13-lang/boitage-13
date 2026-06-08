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
    # ── 13013 — lieux-dits cadastraux officiels ──
    "Château-Gombert":                    (43.348332, 5.441877),  # quartier 13013 [Chateau-Gombert]
    "Saint-Jérôme":                       (43.334528, 5.415972),  # quartier 13013 [Saint Jerome]
    "Clair Soleil":                       (43.326940, 5.453000),  # OSM Boulevard Clair Soleil (Les Olives)
    "Les Médecins":                       (43.360332, 5.459994),  # cadastre 13013 [Les Médecins]
    "Les Olives":                         (43.325971, 5.449584),  # quartier 13013 [Les Olives]
    "Saint-Just":                         (43.320481, 5.405266),  # quartier 13013 [Saint Just]
    "Saint-Mitre":                        (43.346347, 5.423655),  # quartier 13013 [Saint Mitre]
    "Palama":                             (43.374316, 5.439438),  # quartier 13013 [Palama]
    "Les Mourets":                        (43.366961, 5.422854),  # quartier 13013 [Les Mourets]
    "La Croix-Rouge":                     (43.335927, 5.445285),  # quartier 13013 [La Croix Rouge]
    "Malpassé":                           (43.325456, 5.414625),  # quartier 13013 [Malpasse]
    "Petit Bosquet":                      (43.315490, 5.411870),  # OSM Avenue du Petit Bosquet (Saint-Just)
    "Jeandaï":                            (43.355299, 5.428945),  # cadastre 13013 [Jeandaï]
    "La Baudouine":                       (43.357678, 5.436810),  # cadastre 13013 [La  Baudouine]
    "La Bertrane":                        (43.356386, 5.450959),  # cadastre 13013 [La Bertrane]
    "La Béthéline":                       (43.360483, 5.452160),  # cadastre 13013 [La Bétheline]
    "La Figonne":                         (43.364202, 5.443509),  # cadastre 13013 [La Figonne]
    "La Grave":                           (43.355261, 5.456886),  # cadastre 13013 [La Grave]
    "La Moussiere":                       (43.355215, 5.438385),  # cadastre 13013 [La Moussière]
    "La Nègre":                           (43.374981, 5.451919),  # cadastre 13013 [La Nègre]
    "La Parade":                          (43.369615, 5.433113),  # cadastre 13013 [La Parade]
    "Le Cavaou":                          (43.354710, 5.458500),  # OSM Le Cavaou-Centre (Les Médecins)
    "Le Jas":                             (43.367946, 5.454181),  # cadastre 13013 [Le Jas]
    "Le Jausèou":                         (43.362879, 5.458044),  # cadastre 13013 [Le Jausèou]
    "Le Vallon Gombert":                  (43.353330, 5.430000),  # estimation au pied du vallon Château-Gombert
    "Les Couestes":                       (43.360540, 5.444435),  # cadastre 13013 [Les Couestes]
    "Les Durbecs":                        (43.355970, 5.454862),  # cadastre 13013 [Les Durbecs]
    "Les Milanais":                       (43.366232, 5.442598),  # cadastre 13013 [Les Milanais]
    "Les Molières":                       (43.352180, 5.454000),  # conservé (proche La Grave/Cavaou)
    "Les Politres":                       (43.360914, 5.454955),  # cadastre 13013 [Les Politres]
    "Les Xaviers":                        (43.361521, 5.446638),  # cadastre 13013 [Les Xaviers]
    "Mont-Louis":                         (43.362940, 5.442815),  # cadastre 13013 [Mont-Louis]
    "Mouret-Bas":                         (43.359165, 5.432517),  # cadastre 13013 [Mouret-Bas]
    "Mouret-Haut":                        (43.359434, 5.428670),  # cadastre 13013 [Mouret-Haut]
    "Mouret-Nord":                        (43.362075, 5.429794),  # cadastre 13013 [Mouret-Nord]
    "Mouret-Ouest":                       (43.358417, 5.426703),  # cadastre 13013 [Mouret-Ouest]
    "Section De L'Etoile":                (43.381766, 5.432629),  # cadastre 13013 [Section de l'Étoile]
    "Section De La Pible":                (43.386194, 5.441703),  # cadastre 13013 [Section de la Pible]
    "Section De Niolong":                 (43.380021, 5.446314),  # cadastre 13013 [Section de Niolong]
    "Section Du Chateau Palama":          (43.371100, 5.439320),  # OSM Château de Palama
    "Section Du Sauveur":                 (43.371782, 5.445989),  # cadastre 13013 [Section du Sauveur]
    "Vallon De Serre":                    (43.355111, 5.419465),  # cadastre 13013 [Vallon de Serre]
    "Varsi":                              (43.367534, 5.444260),  # cadastre 13013 [Varsi]
    # ── Allauch (13190) — lieux-dits cadastraux ──
    "Allauch":                            (43.335918, 5.485481),  # cadastre Allauch [Le Village]
    "Le Village Allauch":                 (43.335918, 5.485481),  # cadastre Allauch [Le Village]
    "La Pounche":                         (43.333975, 5.461430),  # cadastre Allauch [LA POUNCHE]
    "Font-Vert":                          (43.335607, 5.470924),  # cadastre Allauch [FONT-VERT]
    "La Rigonne":                         (43.336200, 5.467804),  # cadastre Allauch [LA RIGONNE]
    "Canton Rouge":                       (43.338988, 5.464491),  # cadastre Allauch [Canton Rouge]
    "Blacassin":                          (43.340528, 5.468819),  # cadastre Allauch [Blacassin]
    "Caguerasset":                        (43.346368, 5.484740),  # cadastre Allauch [CAGUERASSET]
    "Sainte-Croix Allauch":               (43.334740, 5.493221),  # cadastre Allauch [Sainte-Croix]
    "Les Claous":                         (43.341222, 5.491548),  # cadastre Allauch [Les Claous]
    "Le Logis Neuf":                      (43.359309, 5.487081),  # cadastre Allauch [LE LOGIS NEUF]
    "La Bourdonniere":                    (43.360964, 5.492088),  # cadastre Allauch [LA BOURDONNIERE]
    "Les Barnabelles":                    (43.356316, 5.475497),  # cadastre Allauch [LES BARNABELLES]
    "Vallon De Gage":                     (43.359121, 5.475033),  # cadastre Allauch [VALLON DE GAGE]
    "Bon Rencontre":                      (43.352753, 5.478097),  # cadastre Allauch [Bon Rencontre]
    "La Barasse":                         (43.285960, 5.483760),  # OSM Gare de La Barasse (Marseille 11e)
    "Belle-Vue Allauch":                  (43.321666, 5.487176),  # cadastre Allauch [Belle-Vue]
    "Callian":                            (43.316775, 5.481131),  # cadastre Allauch [Callian]
    "L'Andouiller":                       (43.318926, 5.485829),  # cadastre Allauch [L'ANDOUILLER]
    "La Salle":                           (43.322590, 5.482685),  # cadastre Allauch [La Salle]
    "Font De Brouqueli":                  (43.331975, 5.459780),  # cadastre Allauch [Font de Brouqueli]
    "La Tiranne":                         (43.338755, 5.470123),  # cadastre Allauch [La Tiranne]
    "Rascous":                            (43.347836, 5.477635),  # cadastre Allauch [RASCOUS]
    "Loir D'Ambremont":                   (43.344195, 5.483997),  # cadastre Allauch [LOIR D'AMBREMONT]
    "Peyre-Peissot":                      (43.346455, 5.490020),  # cadastre Allauch [PEYRE PEISSOT]
    "Quartier De La Caleche":             (43.352195, 5.490586),  # cadastre Allauch [QUARTIER DE LA CALECHE]
    "Sainte-Euphemie":                    (43.343372, 5.472439),  # cadastre Allauch [Sainte-Euphémie]
    # ── Plan-de-Cuques (13380) — lieux-dits cadastraux ──
    "Plan-de-Cuques":                     (43.345680, 5.461900),  # OSM Mairie de Plan-de-Cuques
    "La Renardiere":                      (43.347280, 5.461410),  # cadastre PDC [Le Village Nord] (renommé : La Renardière n'existe pas au cadastre PDC)
    "Le Logis Neuf PDC":                  (43.359310, 5.487080),  # cadastre Allauch [Le Logis Neuf] (en fait à Allauch)
    "La Condamine":                       (43.343390, 5.456370),  # cadastre PDC [La Bourgade]
    "Plan De Campagne":                   (43.417930, 5.360990),  # OSM Plan-de-Campagne (Cabriès) — HORS ZONE PDC
    "Les Cadeneaux":                      (43.394280, 5.340600),  # OSM Les Cadeneaux (Pennes-Mirabeau) — HORS ZONE PDC
    "La Gavotte":                         (43.379870, 5.350950),  # OSM La Gavotte (Pennes-Mirabeau) — HORS ZONE PDC
    "Calas":                              (43.460450, 5.353590),  # OSM Calas (Cabriès) — HORS ZONE PDC
    "La Charbonniere":                    (43.353460, 5.465440),  # cadastre PDC [Les Petits Roubauds]
    "Barnouin":                           (43.353250, 5.460930),  # cadastre PDC [Les Briands]
    "La Burliere":                        (43.345630, 5.459190),  # cadastre PDC [Les Cuques]
    "Les Pinchinades":                    (43.348610, 5.455680),  # cadastre PDC [L'Annonciade]
    "La Billonne":                        (43.350570, 5.463230),  # cadastre PDC [Les Dragons]
    "Le Brusq":                           (43.347800, 5.466140),  # cadastre PDC [Le Stade]
    "La Grande Colle":                    (43.351050, 5.466390),  # cadastre PDC [Bompard]
    "Jas De Rhodes":                      (43.354400, 5.473040),  # cadastre PDC [Les Figons]
    # ── 13012 — quartiers / secteurs ──
    "La Valentine":                       (43.302080, 5.482031),  # quartier 13011 [La Valentine]
    "Saint-Marcel":                       (43.283451, 5.463413),  # quartier 13011 [Saint Marcel]
    "Les Accates":                        (43.304816, 5.495182),  # quartier 13011 [Les Accates]
    "La Destrousse":                      (43.303300, 5.430910),  # quartier officiel La Fourragère (13012) — La Destrousse est une autre commune (13112)
    "Les Camoins":                        (43.305391, 5.512294),  # quartier 13011 [Les Camoins]
    "Font Obscure":                       (43.329170, 5.402610),  # OSM Parc Font Obscure (14e/13013)
    "Roy D'Espagne":                      (43.241060, 5.385280),  # OSM Roy d'Espagne (Marseille 8e) — HORS ZONE 13012
    # ── 13004 — quartiers ──
    "Saint-Barnabé":                      (43.304664, 5.417388),  # quartier 13012 [Saint Barnabe]
    "Montolivet":                         (43.316811, 5.424743),  # quartier 13012 [Montolivet]
    "La Pomme":                           (43.291082, 5.438565),  # quartier 13011 [La Pomme]
    "Saint-Tronc":                        (43.272430, 5.428250),  # OSM Saint-Tronc (Marseille 10e) — HORS ZONE 13004
    "Les Trois-Lucs":                     (43.310321, 5.465206),  # quartier 13012 [Les Trois Lucs]
    # ── 13005 — quartiers ──
    "Baille":                             (43.288494, 5.398746),  # quartier 13005 [Baille]
    "Castellane":                         (43.285860, 5.384020),  # OSM Place Castellane (Marseille 6e)
    "Sakakini":                           (43.296190, 5.393630),  # quartier officiel Le Camas (13005) — Sakakini = nom d'avenue
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
