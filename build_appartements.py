#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_appartements.py — Pipeline appartements 13013
  - DPE ADEME appartements (dpe_appart_raw.json)
  - DVF appartements géocodés (dvf_appart_geocoded.json)
  - Croisement par distance GPS (≤ 80m)
  - Génère appart_prospects.json
"""
import json, math, sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/home/user/workspace/boitage-13")

PRIO_QUARTIERS = {
    "Château-Gombert", "Saint-Jérôme", "Les Médecins", "Palama", "Les Mourets",
}
EXCLUDE_QUARTIERS = {"Les Olives", "Les Martégaux"}

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

TIER_CHAUD = 30
TIER_TIEDE = 60
W_FRAICHEUR = 35.0
W_SURFACE   = 22.0
W_PRIO      = 12.0
W_PASSOIRE  = 8.0


def haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371000.0
    r = math.pi / 180
    dla = (b_lat - a_lat) * r
    dlo = (b_lon - a_lon) * r
    h = math.sin(dla/2)**2 + math.cos(a_lat*r)*math.cos(b_lat*r)*math.sin(dlo/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def nearest_quartier(lat, lon, cents):
    return min(cents.items(), key=lambda kv: haversine(lat, lon, kv[1][0], kv[1][1]))[0]


def clean_addr(rec):
    a = (rec.get("adresse_ban") or "").strip()
    import re
    # Retire "<CP> <Ville>" en fin (Marseille, Allauch, Plan-de-Cuques, etc.)
    a = re.sub(r'\s*\b13\d{3}\b\s+(?:Marseille|MARSEILLE|Allauch|ALLAUCH|Plan[- ]?de[- ]?Cuques|PLAN[- ]?DE[- ]?CUQUES)\s*$', '', a, flags=re.IGNORECASE)
    # Retire un CP isolé en fin
    a = re.sub(r'\s*\b13\d{3}\b\s*$', '', a)
    # Retire un nom de ville en fin
    a = re.sub(r'\s*(?:Marseille|Allauch|Plan[- ]?de[- ]?Cuques)\s*$', '', a, flags=re.IGNORECASE)
    a = a.strip(' ,')
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


def find_dvf_match(lat, lon, dvf_list, max_dist_m=80):
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
    return best


def to_prospect(rec, today, dvf_list):
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

    q = nearest_quartier(lat, lon, CENTROIDES_REF)
    prio = q in PRIO_QUARTIERS
    tier = "chaud" if jours <= TIER_CHAUD else ("tiede" if jours <= TIER_TIEDE else "froid")

    surface = rec.get("surface_habitable_logement")
    conso_ep = rec.get("conso_5_usages_par_m2_ep")
    conso_ef = rec.get("conso_5_usages_par_m2_ef")
    gesv = rec.get("emission_ges_5_usages_par_m2")

    s = 0.0
    s += W_FRAICHEUR * max(0.0, 1 - jours / 60.0)
    if surface:
        s += W_SURFACE * min(float(surface), 150.0) / 150.0  # plafond appart = 150m²
    if prio:
        s += W_PRIO
    if conso_ep and float(conso_ep) >= 220:
        s += W_PASSOIRE
    score = max(-20, min(100, round(s)))

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

    # Croisement DVF
    dvf_match = find_dvf_match(lat, lon, dvf_list)
    dvf_data = {}
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

    # Etage
    etage_raw = rec.get("numero_etage_appartement")
    etage = intn(etage_raw)

    p = {
        "id": rec.get("numero_dpe"),
        "type_bien": "appartement",
        "q": q,
        "qoff": "",
        "prio": prio,
        "date": d_iso,
        "date_fin_validite": (rec.get("date_fin_validite_dpe") or "")[:10] or None,
        "date_visite": (rec.get("date_visite_diagnostiqueur") or "")[:10] or None,
        "jours": jours,
        "dpe": rec.get("etiquette_dpe"),
        "ges": rec.get("etiquette_ges"),
        "surface": flt(surface),
        "niv": intn(rec.get("nombre_niveau_logement")),
        "etage": etage,
        "annee": intn(rec.get("annee_construction")),
        "periode": rec.get("periode_construction"),
        "hauteur_plafond": flt(rec.get("hauteur_sous_plafond")),
        "inertie": rec.get("classe_inertie_batiment"),
        "adresse": clean_addr(rec),
        "statut": "Aucune annonce trouvée",
        "flags": [],
        "tier": tier,
        "score": score,
        "lat": lat,
        "lon": lon,
        "gmaps": "https://maps.google.com/?q=%s,%s" % (lat, lon),
        "deja": False,
        "conso": intn(conso_ep),
        "conso_ef": intn(conso_ef),
        "gesv": intn(gesv),
        "cout_total": intn(rec.get("cout_total_5_usages")),
        "chauf": rec.get("type_energie_principale_chauffage"),
        "ecs_energie": rec.get("type_energie_principale_ecs"),
        "installation_chauf": rec.get("type_installation_chauffage"),
        "installation_ecs": rec.get("type_installation_ecs"),
        "generateur_chauf": rec.get("description_generateur_chauffage_n1_installation_n1")
                             or rec.get("type_generateur_chauffage_principal"),
        "generateur_ecs": rec.get("type_generateur_n1_ecs_n1"),
        "conso_chauf_ef": flt(rec.get("conso_chauffage_ef")),
        "conso_ecs_ef": flt(rec.get("conso_ecs_ef")),
        "conso_eclairage_ef": flt(rec.get("conso_eclairage_ef")),
        "conso_refroid_ef": flt(rec.get("conso_refroidissement_ef")),
        "besoin_chauf": flt(rec.get("besoin_chauffage")),
        "besoin_ecs": flt(rec.get("besoin_ecs")),
        "besoin_refroid": flt(rec.get("besoin_refroidissement")),
        "iso_enveloppe": rec.get("qualite_isolation_enveloppe"),
        "iso_murs": rec.get("qualite_isolation_murs"),
        "iso_fenetres": rec.get("qualite_isolation_menuiseries"),
        "ubat": flt(rec.get("ubat_w_par_m2_k")),
        "dep_enveloppe": flt(rec.get("deperditions_enveloppe")),
        "dep_murs": flt(rec.get("deperditions_murs")),
        "dep_baies": flt(rec.get("deperditions_baies_vitrees")),
        "confort_ete": rec.get("indicateur_confort_ete"),
        "modele_dpe": rec.get("modele_dpe"),
        "version_dpe": rec.get("version_dpe"),
    }

    if dvf_data:
        p.update(dvf_data)

    return p


def main():
    today = date.today()

    # Charger DPE ADEME appart
    dpe_path = HERE / "dpe_appart_raw.json"
    with open(dpe_path, encoding='utf-8') as f:
        rows = json.load(f)
    print(f"-> {len(rows)} DPE appartements chargés")

    # Charger DVF appart (optionnel — fichier absent = pas d'enrichissement DVF)
    dvf_path = HERE / "dvf_appart_geocoded.json"
    if dvf_path.exists():
        with open(dvf_path, encoding='utf-8') as f:
            dvf_list = json.load(f)
        dvf_with_gps = [v for v in dvf_list if v.get('lat') and v.get('lon')]
        print(f"-> {len(dvf_with_gps)}/{len(dvf_list)} DVF appart avec GPS")
    else:
        dvf_with_gps = []
        print("-> dvf_appart_geocoded.json absent — enrichissement DVF appart désactivé")

    # Construire prospects
    seen, prospects = set(), []
    no_geo = 0
    for rec in rows:
        nid = rec.get("numero_dpe")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        p = to_prospect(rec, today, dvf_with_gps)
        if p is None:
            no_geo += 1
            continue
        if p["q"] not in EXCLUDE_QUARTIERS:
            prospects.append(p)

    print(f"-> {len(prospects)} prospects appart ({no_geo} sans GPS exclus)")

    # Dédoublonner par adresse
    addr_best = {}
    for p in prospects:
        key = p['adresse'].lower().strip()
        if key not in addr_best or p['score'] > addr_best[key]['score']:
            addr_best[key] = p
    prospects = list(addr_best.values())
    print(f"-> {len(prospects)} après dédoublonnage adresse")

    prospects.sort(key=lambda p: p["score"], reverse=True)
    for i, p in enumerate(prospects, 1):
        p["rang"] = i

    # Stats
    chauds = sum(1 for p in prospects if p["tier"] == "chaud")
    tièdes = sum(1 for p in prospects if p["tier"] == "tiede")
    froids = sum(1 for p in prospects if p["tier"] == "froid")
    dvf_ok = sum(1 for p in prospects if p.get("dvf_prix"))
    print(f"-> {len(prospects)} appart ({chauds} chauds / {tièdes} tièdes / {froids} froids | {dvf_ok} avec DVF)")

    out = HERE / "appart_prospects.json"
    out.write_text(json.dumps(prospects, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"Sauvegardé → {out}")
    return prospects


if __name__ == "__main__":
    main()
