#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_dvf.py — Régénère dvf_geocoded.json via Opendatasoft DVF géolocalisé.

Source : public.opendatasoft.com (dataset DVF géolocalisé — données DGFiP)
Avantage : coordonnées GPS incluses, accessible depuis GitHub Actions.
Aucune clé API requise.

Codes commune INSEE :
  13213 = Marseille 13e arr.
  13204 = Marseille 4e arr.
  13214 = Marseille 14e arr.
"""
import json, time, urllib.parse, urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent

ODS_BASE = "https://public.opendatasoft.com/api/records/1.0/search/"
DATASET  = "buildingref-france-demande-de-valeurs-foncieres-geolocalisee-millesime"

# Codes INSEE des communes cibles
COMMUNES = {
    "13213": ("13013", "Marseille 13e"),
    "13204": ("13004", "Marseille 4e"),
    "13214": ("13014", "Marseille 14e"),
}

# Fenêtre : mutations depuis 2022 inclus
ANNEE_MIN = "2022-01-01"

# Garde-fou : en dessous de ce seuil on conserve l'existant
SEUIL_MIN = 50


def fetch_commune(com_code, cp, nom, timeout=30):
    """
    Récupère toutes les mutations Maison/Vente d'une commune depuis ANNEE_MIN.
    L'API renvoie 100 résultats par page max.
    """
    ventes = []
    start  = 0
    rows   = 100

    while True:
        params = urllib.parse.urlencode({
            "dataset":              DATASET,
            "rows":                 rows,
            "start":                start,
            "refine.com_code":      com_code,
            "refine.nature_mutation": "Vente",
            "refine.type_local":    "Maison",
            "sort":                 "date_mutation",
        })
        url = f"{ODS_BASE}?{params}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "boitage-13/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
        except Exception as e:
            print(f"   ERR {com_code} start={start}: {e}")
            break

        records = data.get("records", [])
        if not records:
            break

        for rec in records:
            f = rec.get("fields", {})

            # Filtrer par année min
            date_raw = f.get("date_mutation", "")
            if date_raw < ANNEE_MIN:
                # Les résultats sont triés desc : on peut s'arrêter
                return ventes

            prix = f.get("valeur_fonciere")
            if not prix or prix <= 0:
                continue

            surf = f.get("surface_reelle_bati")
            terrain = f.get("surface_terrain")
            pieces  = f.get("nombre_pieces_principales")
            lat     = f.get("latitude")
            lon     = f.get("longitude")

            num_voie = str(f.get("adresse_numero") or "").strip()
            nom_voie = str(f.get("adresse_nom_voie") or "").strip().title()
            adresse  = f"{num_voie} {nom_voie}".strip() if (num_voie or nom_voie) else "Adresse inconnue"

            prix_m2 = round(prix / surf, 0) if surf and surf > 0 else None

            ventes.append({
                "date_mutation":  date_raw,
                "adresse":        adresse,
                "code_postal":    cp,
                "commune":        nom,
                "prix":           prix,
                "surface_bati":   surf,
                "surface_terrain": terrain,
                "pieces":         int(pieces) if pieces else None,
                "lat":            lat,
                "lon":            lon,
                "prix_m2":        prix_m2,
                "type_local":     "Maison",
                "_raw_code":      com_code,
            })

        nhits = data.get("nhits", 0)
        start += rows
        if start >= nhits:
            break

        time.sleep(0.2)

    return ventes


def main():
    print("=== refresh_dvf.py — Maisons DVF (Opendatasoft géolocalisé) ===")

    # Charger existant pour fallback
    out_path = HERE / "dvf_geocoded.json"
    existing = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    print(f"-> DVF existant : {len(existing)} ventes")

    # Récupérer DVF depuis ODS
    all_ventes = []
    for com_code, (cp, nom) in COMMUNES.items():
        print(f"-> {nom} ({com_code}) depuis {ANNEE_MIN}...")
        batch = fetch_commune(com_code, cp, nom)
        print(f"   {len(batch)} maisons récupérées (avec GPS : {sum(1 for v in batch if v.get('lat'))})")
        all_ventes.extend(batch)
        time.sleep(0.5)

    if not all_ventes:
        print("ABANDON : aucune vente récupérée — dvf_geocoded.json conservé.")
        return

    # Dédoublonnage
    seen, dedup = set(), []
    for v in all_ventes:
        key = f"{v['adresse']}|{v['date_mutation']}|{v['prix']}"
        if key not in seen:
            seen.add(key)
            dedup.append(v)
    print(f"-> {len(dedup)} ventes après dédoublonnage (depuis {len(all_ventes)})")

    # Garde-fou
    if len(dedup) < SEUIL_MIN:
        print(f"ABANDON : seulement {len(dedup)} ventes — probablement une erreur API. Fichier conservé.")
        return

    # Trier par date desc
    dedup.sort(key=lambda v: v.get("date_mutation", ""), reverse=True)

    # Sauvegarder
    out_path.write_text(json.dumps(dedup, ensure_ascii=False, indent=1), encoding="utf-8")
    avec_gps = sum(1 for v in dedup if v.get("lat"))
    print(f"OK {out_path} : {len(dedup)} ventes ({avec_gps} avec GPS)")


if __name__ == "__main__":
    main()
