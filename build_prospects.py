#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_prospects.py — Pipeline complet :
  1. DPE ADEME 6 mois (maisons 13013) -> ademe_raw.json  [déjà fait]
  2. DVF géocodé -> dvf_geocoded.json                     [déjà fait]
  3. Croisement DPE+DVF par distance GPS (≤ 80m)
  4. Génère prospects.json avec TOUS les champs ADEME + infos DVF
"""
import argparse, json, math, sys, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ------------------------------------------------------------------ config
API = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"

PRIO_QUARTIERS = {
    "Château-Gombert", "Saint-Jérôme", "Les Médecins", "Palama", "Les Mourets",
}
EXCLUDE_QUARTIERS = {"Les Olives", "Les Martégaux"}

GEOJSON_QUARTIERS = (
    "https://static.data.gouv.fr/resources/quartiers-de-marseille-1/"
    "20210308-145904/quartiers-marseille.geojson"
)
NORM_QUA = {
    "SAINT MITRE": "Saint-Mitre", "LES MEDECINS": "Les Médecins",
    "SAINT JEROME": "Saint-Jérôme", "CHATEAU-GOMBERT": "Château-Gombert",
    "PALAMA": "Palama", "SAINT JUST": "Saint-Just", "LES OLIVES": "Les Olives",
    "MALPASSE": "Malpassé", "LA CROIX ROUGE": "La Croix-Rouge",
    "LES MOURETS": "Les Mourets", "LA ROSE": "La Rose", "FRAIS VALLON": "Frais Vallon",
    "MONTOLIVET": "Montolivet", "SAINT BARNABE": "Saint-Barnabé",
}
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

MIN_PROSPECTS = 10
TIER_CHAUD = 30
TIER_TIEDE = 60
W_FRAICHEUR = 35.0
W_SURFACE   = 22.0
W_PRIO      = 12.0
W_PASSOIRE  = 8.0
PEN_ANNONCE = 40.0

# Tous les champs ADEME utiles
SELECT = ",".join([
    "numero_dpe", "type_batiment", "code_postal_ban", "date_etablissement_dpe",
    "date_fin_validite_dpe", "date_visite_diagnostiqueur",
    "etiquette_dpe", "etiquette_ges",
    "surface_habitable_logement", "nombre_niveau_logement",
    "annee_construction", "periode_construction",
    "type_energie_principale_chauffage", "type_energie_principale_ecs",
    "type_installation_chauffage", "type_installation_ecs",
    "conso_5_usages_par_m2_ep", "conso_5_usages_par_m2_ef",
    "emission_ges_5_usages_par_m2",
    "cout_total_5_usages",
    "conso_chauffage_ef", "conso_ecs_ef", "conso_eclairage_ef", "conso_refroidissement_ef",
    "besoin_chauffage", "besoin_ecs", "besoin_refroidissement",
    "qualite_isolation_enveloppe", "qualite_isolation_murs", "qualite_isolation_menuiseries",
    "ubat_w_par_m2_k",
    "indicateur_confort_ete", "classe_inertie_batiment",
    "deperditions_enveloppe", "deperditions_murs", "deperditions_baies_vitrees",
    "hauteur_sous_plafond",
    "type_generateur_chauffage_principal",
    "description_generateur_chauffage_n1_installation_n1",
    "type_generateur_n1_ecs_n1",
    "adresse_ban", "adresse_brut", "_geopoint",
    "nom_commune_ban", "score_ban", "statut_geocodage",
    "modele_dpe", "version_dpe", "methode_application_dpe",
])

# ------------------------------------------------------------------ utilitaires
def haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371000.0  # mètres
    r = math.pi / 180
    dla = (b_lat - a_lat) * r
    dlo = (b_lon - a_lon) * r
    h = math.sin(dla/2)**2 + math.cos(a_lat*r)*math.cos(b_lat*r)*math.sin(dlo/2)**2
    return 2 * R * math.asin(math.sqrt(h))

def nearest_quartier(lat, lon, cents):
    return min(cents.items(), key=lambda kv: haversine(lat, lon, kv[1][0], kv[1][1]))[0]

def clean_addr(rec):
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
        if ((yi > lat) != (yj > lat)) and (lon < (xj-xi)*(lat-yi)/(yj-yi)+xi):
            inside = not inside
        j = i
    return inside

def _in_poly(lon, lat, poly):
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
def fetch_ademe(cp, since_iso, timeout=60):
    qs = ('type_batiment:maison AND code_postal_ban:%s '
          'AND date_etablissement_dpe:[%s TO *]' % (cp, since_iso))
    params = {"qs": qs, "select": SELECT, "size": "1000", "sort": "-date_etablissement_dpe"}
    url = API + "?" + urllib.parse.urlencode(params)
    rows = []
    page = 0
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "boitage-13/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.load(r)
        batch = payload.get("results", [])
        rows.extend(batch)
        url = payload.get("next")
        page += 1
        print("   Page %d: +%d (total %d/%d)" % (page, len(batch), len(rows), payload.get("total", 0)))
        if not batch:
            break
    return rows

# ------------------------------------------------------------------ croisement DVF
def load_dvf(path):
    if not Path(path).exists():
        print("   (dvf_geocoded.json introuvable, croisement DVF désactivé)")
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def load_hist(path):
    if not Path(path).exists():
        print("   (dvf_hist.json introuvable, hist_maturite désactivé)")
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def find_hist_match(lat, lon, hist_list, max_dist_m=80):
    """Retourne l'achat historique le plus ancien (= plus mature) dans un rayon max_dist_m."""
    best = None
    best_dist = max_dist_m + 1
    for v in hist_list:
        vlat, vlon = v.get('lat'), v.get('lon')
        if not vlat or not vlon:
            continue
        d = haversine(lat, lon, vlat, vlon)
        if d < best_dist:
            best_dist = d
            best = (v, round(d, 1))
    return best  # None ou (achat_dict, dist_m)

def calc_dvf_signal(dvf_date_str, today):
    """Calcule dvf_signal à partir de la date de vente."""
    if not dvf_date_str:
        return 'none'
    try:
        dvf_date = datetime.strptime(dvf_date_str[:10], "%Y-%m-%d").date()
        age_jours = (today - dvf_date).days
        if age_jours <= 180:
            return 'vendu_recemment'
        elif age_jours <= 365:
            return 'vendu_recemment'
        elif age_jours <= 1095:  # ~3 ans
            return 'ancienne_vente'
        else:
            return 'none'
    except Exception:
        return 'none'

def calc_hist_maturite(achat_date_str, today):
    """Calcule hist_maturite à partir de la date d'achat historique."""
    if not achat_date_str:
        return 'nouveau'
    try:
        achat_date = datetime.strptime(achat_date_str[:10], "%Y-%m-%d").date()
        age_ans = (today - achat_date).days / 365.25
        if age_ans >= 10:
            return 'tres_mature'
        elif age_ans >= 7:
            return 'mature'
        elif age_ans >= 3:
            return 'recente'
        else:
            return 'nouveau'
    except Exception:
        return 'nouveau'

def find_dvf_match(lat, lon, dvf_list, max_dist_m=80):
    """Retourne la vente DVF la plus récente dans un rayon max_dist_m."""
    best = None
    best_dist = max_dist_m + 1
    for v in dvf_list:
        vlat, vlon = v.get('lat'), v.get('lon')
        if not vlat or not vlon:
            continue
        d = haversine(lat, lon, vlat, vlon)
        if d < best_dist:
            best_dist = d
            best = (v, round(d, 1))
    return best  # None ou (vente_dict, dist_m)

# ------------------------------------------------------------------ transform
def to_prospect(rec, today, cents, dvf_list, hist_list=None):
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
    conso_ep = rec.get("conso_5_usages_par_m2_ep")
    conso_ef = rec.get("conso_5_usages_par_m2_ef")
    gesv = rec.get("emission_ges_5_usages_par_m2")

    # Score
    s = 0.0
    s += W_FRAICHEUR * max(0.0, 1 - jours / 60.0)
    if surface:
        s += W_SURFACE * min(float(surface), 220.0) / 220.0
    if prio:
        s += W_PRIO
    if conso_ep and float(conso_ep) >= 220:
        s += W_PASSOIRE
    deja = False
    score = max(-20, min(100, round(s)))

    # Croisement DVF récent (dvf_geocoded.json)
    dvf_match = find_dvf_match(lat, lon, dvf_list)
    dvf_data = None
    if dvf_match:
        vente, dist_m = dvf_match
        dvf_date_str = vente.get("date_mutation")
        dvf_signal = calc_dvf_signal(dvf_date_str, today)
        dvf_data = {
            "dvf_signal": dvf_signal,
            "dvf_date": dvf_date_str,
            "dvf_prix": vente.get("prix"),
            "dvf_surface": vente.get("surface_bati"),
            "dvf_terrain": vente.get("surface_terrain"),
            "dvf_pieces": vente.get("pieces"),
            "dvf_prix_m2": vente.get("prix_m2"),
            "dvf_dist_m": dist_m,
            "dvf_adresse": vente.get("adresse"),
        }

    # Croisement historique (dvf_hist.json) — acheteurs anciens
    hist_data = None
    if hist_list:
        hist_match = find_hist_match(lat, lon, hist_list)
        if hist_match:
            achat, hist_dist_m = hist_match
            achat_date_str = achat.get("date")
            annee_achat = achat.get("annee")
            age_ans = round((today - datetime.strptime(achat_date_str[:10], "%Y-%m-%d").date()).days / 365.25, 1) if achat_date_str else None
            hist_data = {
                "hist_maturite": calc_hist_maturite(achat_date_str, today),
                "hist_age_achat_ans": int(age_ans) if age_ans else None,
                "hist_annee_achat": annee_achat,
                "hist_prix_achat": achat.get("prix"),
                "hist_prix_m2_achat": achat.get("prix_m2"),
            }

    # Valeur nulle -> None
    def flt(x):
        try:
            v = float(x)
            return round(v, 1) if v else None
        except Exception:
            return None
    def intn(x):
        try:
            return int(x) if x else None
        except Exception:
            return None

    p = {
        # --- Identité ---
        "id": rec.get("numero_dpe"),
        "q": q,
        "qoff": "",
        "prio": prio,

        # --- DPE dates ---
        "date": d_iso,
        "date_fin_validite": (rec.get("date_fin_validite_dpe") or "")[:10] or None,
        "date_visite": (rec.get("date_visite_diagnostiqueur") or "")[:10] or None,
        "jours": jours,

        # --- Étiquettes ---
        "dpe": rec.get("etiquette_dpe"),
        "ges": rec.get("etiquette_ges"),

        # --- Bâti ---
        "surface": flt(surface),
        "niv": intn(rec.get("nombre_niveau_logement")),
        "annee": intn(rec.get("annee_construction")),
        "periode": rec.get("periode_construction"),
        "hauteur_plafond": flt(rec.get("hauteur_sous_plafond")),
        "inertie": rec.get("classe_inertie_batiment"),

        # --- Adresse ---
        "adresse": clean_addr(rec),
        "statut": "Aucune annonce trouvée",
        "flags": [],

        # --- Scoring / tier ---
        "tier": tier,
        "score": score,
        "lat": lat,
        "lon": lon,
        "gmaps": "https://maps.google.com/?q=%s,%s" % (lat, lon),
        "deja": deja,

        # --- Énergie consommation ---
        "conso": intn(conso_ep),        # ep pour le score
        "conso_ef": intn(conso_ef),     # ef pour info
        "gesv": intn(gesv),
        "cout_total": intn(rec.get("cout_total_5_usages")),
        "chauf": rec.get("type_energie_principale_chauffage"),
        "ecs_energie": rec.get("type_energie_principale_ecs"),
        "installation_chauf": rec.get("type_installation_chauffage"),
        "installation_ecs": rec.get("type_installation_ecs"),

        # --- Générateurs ---
        "generateur_chauf": rec.get("description_generateur_chauffage_n1_installation_n1")
                             or rec.get("type_generateur_chauffage_principal"),
        "generateur_ecs": rec.get("type_generateur_n1_ecs_n1"),

        # --- Usages détaillés (kWh ef/an) ---
        "conso_chauf_ef": flt(rec.get("conso_chauffage_ef")),
        "conso_ecs_ef": flt(rec.get("conso_ecs_ef")),
        "conso_eclairage_ef": flt(rec.get("conso_eclairage_ef")),
        "conso_refroid_ef": flt(rec.get("conso_refroidissement_ef")),

        # --- Besoins thermiques (kWh/an) ---
        "besoin_chauf": flt(rec.get("besoin_chauffage")),
        "besoin_ecs": flt(rec.get("besoin_ecs")),
        "besoin_refroid": flt(rec.get("besoin_refroidissement")),

        # --- Isolation ---
        "iso_enveloppe": rec.get("qualite_isolation_enveloppe"),
        "iso_murs": rec.get("qualite_isolation_murs"),
        "iso_fenetres": rec.get("qualite_isolation_menuiseries"),
        "ubat": flt(rec.get("ubat_w_par_m2_k")),

        # --- Déperditions (W/K) ---
        "dep_enveloppe": flt(rec.get("deperditions_enveloppe")),
        "dep_murs": flt(rec.get("deperditions_murs")),
        "dep_baies": flt(rec.get("deperditions_baies_vitrees")),

        # --- Confort ---
        "confort_ete": rec.get("indicateur_confort_ete"),

        # --- Méthode DPE ---
        "modele_dpe": rec.get("modele_dpe"),
        "version_dpe": rec.get("version_dpe"),
    }

    # Injecter DVF si trouvé
    if dvf_data:
        p.update(dvf_data)
    else:
        p["dvf_signal"] = "none"

    # Injecter historique si trouvé
    if hist_data:
        p.update(hist_data)
    else:
        p["hist_maturite"] = "nouveau"

    return p

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--cp", default="13013")
    ap.add_argument("--out", default=str(HERE / "prospects.json"))
    ap.add_argument("--dvf", default=str(HERE / "dvf_geocoded.json"))
    ap.add_argument("--hist", default=str(HERE / "dvf_hist.json"))
    ap.add_argument("--use-cache", action="store_true",
                    help="Utiliser ademe_raw.json déjà téléchargé")
    args = ap.parse_args()

    out = Path(args.out)
    today = date.today()
    since = (today - timedelta(days=args.days)).isoformat()

    cents = CENTROIDES_REF
    print("-> %d quartiers de référence." % len(cents))

    # Charger ADEME (cache ou API)
    cache_path = HERE / "ademe_raw.json"
    if args.use_cache and cache_path.exists():
        print("-> Chargement cache ademe_raw.json...")
        with open(cache_path, encoding='utf-8') as f:
            rows = json.load(f)
        print("   %d DPE depuis le cache." % len(rows))
    else:
        print("-> ADEME : maisons CP %s, DPE depuis %s ..." % (args.cp, since))
        rows = fetch_ademe(args.cp, since)
        print("   %d DPE bruts reçus." % len(rows))
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False)

    # Charger DVF géocodé
    dvf_list = load_dvf(args.dvf)
    print("-> %d ventes DVF chargées." % len(dvf_list))

    # Charger historique des achats
    hist_list = load_hist(args.hist)
    print("-> %d achats historiques chargés." % len(hist_list))

    # Quartiers officiels
    feats = load_quartiers()
    print("   %d quartiers officiels." % len(feats))

    # Construire prospects
    seen, prospects = set(), []
    for rec in rows:
        nid = rec.get("numero_dpe")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        p = to_prospect(rec, today, cents, dvf_list, hist_list)
        if p and p["q"] not in EXCLUDE_QUARTIERS:
            if feats:
                p["qoff"] = quartier_officiel(p["lat"], p["lon"], feats)
            prospects.append(p)

    # Dédoublonner par adresse (garder meilleur score)
    addr_best = {}
    for p in prospects:
        addr_key = p['adresse'].lower().strip()
        if addr_key not in addr_best or p['score'] > addr_best[addr_key]['score']:
            addr_best[addr_key] = p
    prospects = list(addr_best.values())

    if len(prospects) < MIN_PROSPECTS:
        sys.exit("ABANDON : seulement %d prospect(s). prospects.json non modifié." % len(prospects))

    prospects.sort(key=lambda p: p["score"], reverse=True)
    for i, p in enumerate(prospects, 1):
        p["rang"] = i

    out.write_text(json.dumps(prospects, ensure_ascii=False, indent=1), encoding="utf-8")

    chauds = sum(1 for p in prospects if p["tier"] == "chaud")
    tièdes = sum(1 for p in prospects if p["tier"] == "tiede")
    froids = sum(1 for p in prospects if p["tier"] == "froid")
    stars  = sum(1 for p in prospects if p["prio"])
    dvf_ok = sum(1 for p in prospects if p.get("dvf_signal") and p["dvf_signal"] != "none")
    hist_ok = sum(1 for p in prospects if p.get("hist_maturite") in ("tres_mature", "mature"))
    print("OK %s : %d prospects (%d étoiles | %d chauds / %d tièdes / %d froids | %d DVF | %d hist matures)"
          % (out, len(prospects), stars, chauds, tièdes, froids, dvf_ok, hist_ok))

if __name__ == "__main__":
    main()
