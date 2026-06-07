#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_dvf.py — Régénère dvf_geocoded.json depuis l'API DVF open data (data.gouv.fr).

Source : https://api.gouv.fr/les-api/api_dvf
Endpoint : https://api.pagesjaunes.fr/... non — on utilise data.gouv.fr DVF API ouverte
API réelle : https://dvf.data.gouv.fr/api/ — filtres par code_commune

Code commune Marseille 13e = 13213 (code INSEE)
On filtre : type_local = Maison, code_commune = 13213
Fenêtre : 3 ans glissants

Aucune clé API requise.
"""
import json, math, time, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

# API DVF open data data.gouv.fr
DVF_API = "https://api.gouv.fr/api/dvf"
# URL correcte (testée)
DVF_BASE = "https://dvf.data.gouv.fr/api/dv3f/mutations/csv/"

# Paramètres
CODE_COMMUNE_13 = "13213"   # Marseille 13e arr.
CODE_COMMUNE_4  = "13204"   # Marseille 4e arr.
CODE_COMMUNE_14 = "13214"   # Marseille 14e arr.
COMMUNES = [CODE_COMMUNE_13, CODE_COMMUNE_4, CODE_COMMUNE_14]
TYPE_LOCAL = "Maison"
ANNEES = [2022, 2023, 2024, 2025]   # 4 ans glissants

# BAN batch geocoding
BAN_BATCH = "https://api-adresse.data.gouv.fr/search/csv/"


def fetch_dvf_commune(code_commune, annee, timeout=60):
    """
    Récupère les mutations DVF d'une commune pour une année donnée.
    On interroge l'API DVF de data.gouv.fr format JSON.
    """
    # L'API DVF open data expose un endpoint par commune + année
    # Format : https://dvf.data.gouv.fr/api/dv3f/communes/{code}/mutations/?annee={annee}
    url = f"https://dvf.data.gouv.fr/api/dv3f/communes/{code_commune}/mutations/?annee={annee}&page_size=500"
    ventes = []
    page = 1
    while url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "boitage-13/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
        except Exception as e:
            print(f"   ERR {code_commune}/{annee} page {page}: {e}")
            break

        results = data.get("results", [])
        for row in results:
            # Filtrer type maison
            lib_type = (row.get("libtypbien") or "").lower()
            if "maison" not in lib_type:
                continue
            # Exclure sans valeur
            valeur = row.get("valeurfonc")
            if not valeur:
                continue
            try:
                prix = float(valeur)
            except Exception:
                continue
            if prix <= 0:
                continue

            # Surface bâtie
            surf = row.get("sbati")
            try:
                surf = float(surf) if surf else None
            except Exception:
                surf = None

            # Surface terrain
            sterrain = row.get("sterr")
            try:
                sterrain = float(sterrain) if sterrain else None
            except Exception:
                sterrain = None

            # Pièces
            pieces = row.get("nbpiecp")
            try:
                pieces = int(pieces) if pieces else None
            except Exception:
                pieces = None

            # Date ISO
            date_raw = row.get("datemut", "")
            try:
                # format attendu YYYY-MM-DD
                d_obj = date.fromisoformat(date_raw[:10])
                date_iso = d_obj.isoformat()
            except Exception:
                date_iso = date_raw

            # Adresse reconstruite
            numvoie = str(row.get("l2_normalisee") or "").strip()
            voie    = str(row.get("l3_normalisee") or "").strip()
            cp      = str(row.get("l5_normalisee") or "").strip()[:5] or "13013"
            adresse = f"{numvoie} {voie}".strip().title() if (numvoie or voie) else "Adresse inconnue"

            prix_m2 = round(prix / surf, 0) if prix and surf and surf > 0 else None

            ventes.append({
                "date_mutation": date_iso,
                "adresse": adresse,
                "code_postal": cp,
                "commune": f"Marseille {code_commune[-2:]}e",
                "prix": prix,
                "surface_bati": surf,
                "surface_terrain": sterrain,
                "pieces": pieces,
                "lat": None,
                "lon": None,
                "prix_m2": prix_m2,
                "type_local": "Maison",
                "_raw_code": code_commune,
            })

        # Pagination
        next_url = data.get("next")
        if next_url:
            url = next_url
            page += 1
            time.sleep(0.2)
        else:
            break

    return ventes


def geocode_ban_batch(ventes, batch_size=5000):
    """Géocode les adresses via l'API BAN batch (data.gouv.fr)."""
    import csv, io

    rows_csv = [["id", "adresse", "postcode"]]
    for i, v in enumerate(ventes):
        rows_csv.append([str(i), v.get("adresse", ""), v.get("code_postal", "13013")])

    geo_map = {}

    for start in range(0, len(ventes), batch_size):
        chunk = [rows_csv[0]] + rows_csv[1 + start: 1 + start + batch_size]
        buf = io.StringIO()
        csv.writer(buf).writerows(chunk)
        csv_bytes = buf.getvalue().encode("utf-8")

        boundary = b"----boitage13boundary"
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="data"; filename="adresses.csv"\r\n'
            b"Content-Type: text/csv\r\n\r\n" +
            csv_bytes + b"\r\n"
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="columns"\r\n\r\nadresse\r\n'
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="postcode"\r\n\r\npostcode\r\n'
            b"--" + boundary + b"--\r\n"
        )
        req = urllib.request.Request(
            BAN_BATCH, data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
                "User-Agent": "boitage-13/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                result_csv = r.read().decode("utf-8")
        except Exception as e:
            print(f"   BAN batch ERR: {e}")
            continue

        reader = csv.DictReader(io.StringIO(result_csv))
        for row in reader:
            rid = row.get("id", "")
            try:
                lat = float(row["latitude"]) if row.get("latitude") else None
                lon = float(row["longitude"]) if row.get("longitude") else None
                score = float(row.get("result_score", 0) or 0)
            except Exception:
                lat, lon, score = None, None, 0.0
            geo_map[rid] = (lat, lon, score, row.get("result_label", ""))

        print(f"   BAN batch {start//batch_size + 1}: {len(geo_map)} géocodés")
        time.sleep(0.3)

    # Injecter
    enriched = 0
    for i, v in enumerate(ventes):
        geo = geo_map.get(str(i))
        if geo and geo[0]:
            v["lat"] = geo[0]
            v["lon"] = geo[1]
            v["ban_score"] = round(geo[2], 3)
            v["ban_label"] = geo[3]
            enriched += 1

    print(f"   Géocodés : {enriched}/{len(ventes)}")
    return ventes


def main():
    print("=== refresh_dvf.py — Maisons DVF (API data.gouv.fr) ===")

    # Charger existant pour fallback
    existing = []
    out_path = HERE / "dvf_geocoded.json"
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    print(f"-> DVF existant : {len(existing)} ventes")

    # Récupérer DVF depuis l'API
    all_ventes = []
    for commune in COMMUNES:
        for annee in ANNEES:
            print(f"-> {commune} / {annee}...")
            batch = fetch_dvf_commune(commune, annee)
            print(f"   {len(batch)} maisons récupérées")
            all_ventes.extend(batch)
            time.sleep(0.5)

    if not all_ventes:
        print("ABANDON : aucune vente récupérée — dvf_geocoded.json conservé.")
        return

    # Dédoublonnage
    seen = set()
    dedup = []
    for v in all_ventes:
        key = f"{v['adresse']}|{v['date_mutation']}|{v['prix']}"
        if key not in seen:
            seen.add(key)
            dedup.append(v)
    print(f"-> {len(dedup)} ventes après dédoublonnage (depuis {len(all_ventes)})")

    # Garde-fou
    if len(dedup) < 50:
        print(f"ABANDON : seulement {len(dedup)} ventes — probablement une erreur API. Fichier conservé.")
        return

    # Géocodage BAN
    print("-> Géocodage BAN batch...")
    dedup = geocode_ban_batch(dedup)

    # Trier par date desc
    dedup.sort(key=lambda v: v.get("date_mutation", ""), reverse=True)

    # Sauvegarder
    out_path.write_text(json.dumps(dedup, ensure_ascii=False, indent=1), encoding="utf-8")
    avec_gps = sum(1 for v in dedup if v.get("lat"))
    print(f"OK {out_path} : {len(dedup)} ventes ({avec_gps} avec GPS)")


if __name__ == "__main__":
    main()
