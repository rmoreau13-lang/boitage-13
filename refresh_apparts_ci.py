#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_apparts_ci.py — Régénère dpe_appart_raw.json depuis l'API ADEME.
Destiné à être appelé dans le pipeline GitHub Actions (pas de dépendance externe).

Récupère les DPE appartements pour les CP de la zone de prospection :
13001 (1er), 13004 (4e), 13005 (5e), 13011 (11e), 13012 (12e), 13013 (13e),
13190 (Allauch), 13380 (Plan-de-Cuques).
Sauvegarde le brut dans dpe_appart_raw.json (utilisé ensuite par fusion_prospects.py).
"""
import json, urllib.parse, urllib.request, sys, time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

API = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
CODES_POSTAUX = ["13001", "13004", "13005", "13011", "13012", "13013", "13190", "13380"]
JOURS_FENETRE = 180   # 6 mois de DPE

SELECT = ",".join([
    "numero_dpe", "type_batiment", "code_postal_ban", "date_etablissement_dpe",
    "date_fin_validite_dpe", "date_visite_diagnostiqueur",
    "etiquette_dpe", "etiquette_ges",
    "surface_habitable_logement", "nombre_niveau_logement",
    "numero_etage_appartement",
    "annee_construction", "periode_construction",
    "type_energie_principale_chauffage", "type_energie_principale_ecs",
    "type_installation_chauffage", "type_installation_ecs",
    "conso_5_usages_par_m2_ep", "conso_5_usages_par_m2_ef",
    "emission_ges_5_usages_par_m2", "cout_total_5_usages",
    "conso_chauffage_ef", "conso_ecs_ef", "conso_eclairage_ef", "conso_refroidissement_ef",
    "besoin_chauffage", "besoin_ecs", "besoin_refroidissement",
    "qualite_isolation_enveloppe", "qualite_isolation_murs", "qualite_isolation_menuiseries",
    "ubat_w_par_m2_k", "indicateur_confort_ete", "classe_inertie_batiment",
    "deperditions_enveloppe", "deperditions_murs", "deperditions_baies_vitrees",
    "hauteur_sous_plafond",
    "type_generateur_chauffage_principal",
    "description_generateur_chauffage_n1_installation_n1",
    "type_generateur_n1_ecs_n1",
    "adresse_ban", "adresse_brut", "_geopoint",
    "nom_commune_ban", "score_ban", "statut_geocodage",
    "modele_dpe", "version_dpe", "methode_application_dpe",
])

MIN_RESULTS = 100


def fetch_ademe_apparts(cp, since_iso, timeout=90):
    """Récupère tous les DPE appartements d'un CP via pagination."""
    qs = (
        'type_batiment:appartement AND code_postal_ban:%s '
        'AND date_etablissement_dpe:[%s TO *]' % (cp, since_iso)
    )
    params = {"qs": qs, "select": SELECT, "size": "1000", "sort": "-date_etablissement_dpe"}
    url = API + "?" + urllib.parse.urlencode(params)
    rows = []
    page = 0
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "boitage-13/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.load(r)
        except Exception as e:
            print(f"   ERR page {page} CP {cp}: {e}")
            break
        batch = payload.get("results", [])
        rows.extend(batch)
        url = payload.get("next")
        page += 1
        print(f"   CP {cp} — page {page}: +{len(batch)} (total {len(rows)}/{payload.get('total', '?')})")
        if not batch:
            break
        time.sleep(0.2)
    return rows


def main():
    today = date.today()
    since = (today - timedelta(days=JOURS_FENETRE)).isoformat()
    print(f"=== refresh_apparts_ci.py — DPE appartements depuis {since} ===")

    # Charger existant pour fallback
    cache_path = HERE / "dpe_appart_raw.json"
    existing = []
    if cache_path.exists():
        try:
            existing = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    print(f"-> Cache existant : {len(existing)} DPE")

    all_rows = []
    seen_ids = set()
    for cp in CODES_POSTAUX:
        print(f"-> ADEME CP {cp}...")
        rows = fetch_ademe_apparts(cp, since)
        for r in rows:
            nid = r.get("numero_dpe")
            if nid and nid not in seen_ids:
                seen_ids.add(nid)
                all_rows.append(r)
        print(f"   Total unique après CP {cp} : {len(all_rows)}")
        time.sleep(0.5)

    if len(all_rows) < MIN_RESULTS:
        print(f"ABANDON : seulement {len(all_rows)} DPE apparts — dpe_appart_raw.json conservé.")
        # On conserve le cache existant
        return

    cache_path.write_text(json.dumps(all_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK {cache_path} : {len(all_rows)} DPE appartements sauvegardés")


if __name__ == "__main__":
    main()
