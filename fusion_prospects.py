#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fusion_prospects.py — Fusionne maisons + appartements en un seul prospects.json.

Pipeline appelé par le GitHub Actions après :
  - refresh_prospects.py  (maisons → prospects_maisons_tmp.json ou prospects.json direct)
  - refresh_apparts_ci.py (apparts → dpe_appart_raw.json)
  - build_appartements.py (dpe_appart_raw.json → appart_prospects.json)

Ce script :
  1. Charge prospects.json existant (maisons uniquement ou mixte)
  2. Si dpe_appart_raw.json existe → lance build_appartements.py pour générer appart_prospects.json
  3. Fusionne maisons + apparts, re-numérote rang, sauvegarde prospects.json
"""
import json, subprocess, sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TODAY = date.today()


def load_json(path):
    if Path(path).exists():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"   ERR chargement {path}: {e}")
    return []


def run_build_apparts():
    """Lance build_appartements.py si dpe_appart_raw.json existe."""
    dpe_raw = HERE / "dpe_appart_raw.json"
    if not dpe_raw.exists():
        print("   dpe_appart_raw.json absent — skip build_appartements")
        return False
    print("   Lancement build_appartements.py...")
    result = subprocess.run(
        [sys.executable, str(HERE / "build_appartements.py")],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(result.stdout)
        return True
    else:
        print("   WARN build_appartements.py échoué :")
        print(result.stderr[:500])
        return False


def main():
    print("=== fusion_prospects.py ===")

    # 1. Charger prospects.json courant
    current = load_json(HERE / "prospects.json")
    print(f"-> prospects.json actuel : {len(current)} entrées")

    # Séparer maisons et apparts
    maisons = [p for p in current if p.get("type_bien") != "appartement"]
    old_apparts = [p for p in current if p.get("type_bien") == "appartement"]
    print(f"   Maisons : {len(maisons)} / Apparts existants : {len(old_apparts)}")

    # 2. Tenter de régénérer les apparts depuis dpe_appart_raw.json
    appart_regen_ok = run_build_apparts()

    # 3. Charger appart_prospects.json (généré par build_appartements.py)
    new_apparts = load_json(HERE / "appart_prospects.json")

    # Choisir la meilleure source d'apparts
    if appart_regen_ok and len(new_apparts) > max(10, len(old_apparts) // 2):
        apparts = new_apparts
        print(f"-> Nouveaux apparts : {len(apparts)} (régénérés)")
    elif old_apparts:
        apparts = old_apparts
        print(f"-> Apparts conservés (ancien) : {len(apparts)}")
    else:
        apparts = []
        print("-> Aucun appart disponible")

    # Garde-fou : si on n'a ni maisons ni apparts, on abandonne
    if not maisons and not apparts:
        print("ABANDON : prospects vides — fichier conservé")
        sys.exit(1)

    # 4. Fusionner + trier + re-numéroter
    all_prospects = maisons + apparts
    all_prospects.sort(key=lambda p: p.get("score", 0), reverse=True)
    for i, p in enumerate(all_prospects, 1):
        p["rang"] = i

    # 5. Sauvegarder
    out = HERE / "prospects.json"
    out.write_text(json.dumps(all_prospects, ensure_ascii=False, indent=1), encoding="utf-8")

    # Stats
    nb_m = sum(1 for p in all_prospects if p.get("type_bien") != "appartement")
    nb_a = sum(1 for p in all_prospects if p.get("type_bien") == "appartement")
    chauds = sum(1 for p in all_prospects if p.get("tier") == "chaud")
    dvf_ok = sum(1 for p in all_prospects if p.get("dvf_prix"))
    sci_ok = sum(1 for p in all_prospects if p.get("sci_proche"))
    print(
        f"OK {out} : {len(all_prospects)} prospects total "
        f"({nb_m} maisons + {nb_a} apparts | {chauds} chauds | {dvf_ok} DVF | {sci_ok} SCI)"
    )


if __name__ == "__main__":
    main()
