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
def to_prospect(rec, today, cents, dvf_list):
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

    # Croisement DVF
    dvf_match = find_dvf_match(lat, lon, dvf_list)
    dvf_data = None
    if dvf_match:
        vente, dist_m = dvf_match
        dvf_data = {
            "dvf_date": vente.get("date_mutation"),
            "dvf_prix": vente.get("prix"),
            "dvf_surface": vente.get("surface_bati"),
            "dvf_terrain": vente.get("surface_terrain"),
            "dvf_pieces": vente.get("pieces"),
            "dvf_prix_m2": vente.get("prix_m2"),
            "dvf_dist_m": dist_m,
            "dvf_adresse": vente.get("adresse"),
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

    return p

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--cp", default="13013")
    ap.add_argument("--out", default=str(HERE / "prospects.json"))
    ap.add_argument("--dvf", default=str(HERE / "dvf_geocoded.json"))
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
        p = to_prospect(rec, today, cents, dvf_list)
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
    dvf_ok = sum(1 for p in prospects if p.get("dvf_prix"))
    print("OK %s : %d prospects (%d étoiles | %d chauds / %d tièdes / %d froids | %d avec DVF)"
          % (out, len(prospects), stars, chauds, tièdes, froids, dvf_ok))

if __name__ == "__main__":
    main()
