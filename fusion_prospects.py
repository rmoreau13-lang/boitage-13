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
  3. Fusionne maisons + apparts, re-numérote rang, assigne arrondissement, sauvegarde prospects.json
"""
import json, subprocess, sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TODAY = date.today()

# ── Table de correspondance quartier (q) → arrondissement ──────────────────
# Valeurs correspondant exactement à ARR_ORDER dans index.html
Q_TO_ARR = {
    # Marseille 13e
    "Château-Gombert":    "Marseille 13e",
    "Saint-Jérôme":       "Marseille 13e",
    "Les Médecins":       "Marseille 13e",
    "Les Olives":         "Marseille 13e",
    "Saint-Just":         "Marseille 13e",
    "Saint-Mitre":        "Marseille 13e",
    "Palama":             "Marseille 13e",
    "Les Mourets":        "Marseille 13e",
    "La Croix-Rouge":     "Marseille 13e",
    "Malpassé":           "Marseille 13e",
    "La Baudouine":       "Marseille 13e",
    "La Bertrane":        "Marseille 13e",
    "La Béthéline":       "Marseille 13e",
    "La Figonne":         "Marseille 13e",
    "La Grave":           "Marseille 13e",
    "La Moussiere":       "Marseille 13e",
    "La Nègre":           "Marseille 13e",
    "La Parade":          "Marseille 13e",
    "Le Jas":             "Marseille 13e",
    "Le Jausèou":         "Marseille 13e",
    "Les Couestes":       "Marseille 13e",
    "Les Durbecs":        "Marseille 13e",
    "Les Milanais":       "Marseille 13e",
    "Les Politres":       "Marseille 13e",
    "Les Xaviers":        "Marseille 13e",
    "Mont-Louis":         "Marseille 13e",
    "Mouret-Bas":         "Marseille 13e",
    "Mouret-Haut":        "Marseille 13e",
    "Mouret-Nord":        "Marseille 13e",
    "Mouret-Ouest":       "Marseille 13e",
    "Jeandaï":            "Marseille 13e",
    "Vallon De Serre":    "Marseille 13e",
    "Section De L'Etoile": "Marseille 13e",
    "Section De La Pible": "Marseille 13e",
    "Section De Niolong": "Marseille 13e",
    "Section Du Sauveur": "Marseille 13e",
    "La Billonne":        "Marseille 13e",
    "Clair Soleil":       "Marseille 13e",
    "Bon Rencontre":      "Marseille 13e",
    "Callian":            "Marseille 13e",
    "Caguerasset":        "Marseille 13e",
    "Font De Brouqueli":  "Marseille 13e",
    "Canton Rouge":       "Marseille 13e",
    "La Grande Colle":    "Marseille 13e",
    "Le Vallon Gombert":  "Marseille 13e",
    "Peyre-Peissot":      "Marseille 13e",
    "Rascous":            "Marseille 13e",
    # Marseille 12e
    "Saint-Barnabé":      "Marseille 12e",
    "La Destrousse":      "Marseille 12e",
    "Les Trois-Lucs":     "Marseille 12e",
    "Montolivet":         "Marseille 12e",
    "La Pomme":           "Marseille 12e",
    "La Valentine":       "Marseille 12e",
    "La Salle":           "Marseille 12e",
    "Barnouin":           "Marseille 12e",
    "Blacassin":          "Marseille 12e",
    "La Bourdonniere":    "Marseille 12e",
    "La Charbonniere":    "Marseille 12e",
    "Les Barnabelles":    "Marseille 12e",
    "La Burliere":        "Marseille 12e",
    "Font-Vert":          "Marseille 12e",
    "La Pounche":         "Marseille 12e",
    "Sainte-Euphemie":    "Marseille 12e",
    "Loir D'Ambremont":  "Marseille 12e",
    "Les Camoins":        "Marseille 12e",
    "Belle-Vue Allauch":  "Marseille 12e",
    "Jas De Rhodes":      "Marseille 12e",
    # Marseille 11e
    "La Condamine":       "Marseille 11e",
    "Petit Bosquet":      "Marseille 11e",
    "Sakakini":           "Marseille 11e",
    "Quartier De La Caleche": "Marseille 11e",
    "Font Obscure":       "Marseille 11e",
    "Vallon De Gage":     "Marseille 11e",
    "Le Cavaou":          "Marseille 11e",
    "Le Brusq":           "Marseille 11e",
    "Les Molières":       "Marseille 11e",
    # Marseille 10e
    "La Timone":          "Marseille 10e",
    "Baille":             "Marseille 10e",
    "Sainte-Marguerite":  "Marseille 10e",
    # Marseille 5e
    "Le Logis Neuf":      "Marseille 5e",
    # Marseille 4e
    "Les Pinchinades":    "Marseille 4e",
    # Allauch
    "Allauch":            "Allauch",
    "Sainte-Croix Allauch": "Allauch",
    "La Tiranne":         "Allauch",
    "La Billonne Allauch": "Allauch",
    # Plan-de-Cuques
    "Plan-de-Cuques":     "Plan-de-Cuques",
    "Le Logis Neuf PDC":  "Plan-de-Cuques",
    "La Renardiere":      "Plan-de-Cuques",
}

# Déduction par code postal en fallback
CP_TO_ARR = {
    "13001": "Marseille 1er",
    "13004": "Marseille 4e",
    "13005": "Marseille 5e",
    "13009": "Marseille 9e",
    "13010": "Marseille 10e",
    "13011": "Marseille 11e",
    "13012": "Marseille 12e",
    "13013": "Marseille 13e",
    "13014": "Marseille 14e",
    "13190": "Allauch",
    "13380": "Plan-de-Cuques",
}


def guess_arrondissement(p):
    """Déduit l'arrondissement depuis le quartier q ou le code postal dans l'adresse."""
    # 1. Table de correspondance quartier
    q = p.get("q") or ""
    if q in Q_TO_ARR:
        return Q_TO_ARR[q]
    # 2. Fallback : code postal extrait de l'adresse
    adresse = p.get("adresse") or ""
    for cp, arr in CP_TO_ARR.items():
        if cp in adresse:
            return arr
    # 3. Fallback générique : si adresse sans CP explicite, c'est Marseille 13e par défaut
    # (pipeline principal est 13013)
    return "Marseille 13e"


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
        # Assigner arrondissement si absent ou vide
        if not p.get("arrondissement"):
            p["arrondissement"] = guess_arrondissement(p)

    # 5. Sauvegarder
    out = HERE / "prospects.json"
    out.write_text(json.dumps(all_prospects, ensure_ascii=False, indent=1), encoding="utf-8")

    # Stats arrondissements
    arr_cnt = {}
    for p in all_prospects:
        a = p.get("arrondissement") or "?"
        arr_cnt[a] = arr_cnt.get(a, 0) + 1
    arr_str = " | ".join(f"{k}:{v}" for k, v in sorted(arr_cnt.items()))

    # Stats générales
    nb_m = sum(1 for p in all_prospects if p.get("type_bien") != "appartement")
    nb_a = sum(1 for p in all_prospects if p.get("type_bien") == "appartement")
    chauds = sum(1 for p in all_prospects if p.get("tier") == "chaud")
    dvf_ok = sum(1 for p in all_prospects if p.get("dvf_prix"))
    sci_ok = sum(1 for p in all_prospects if p.get("sci_proche"))
    print(
        f"OK {out} : {len(all_prospects)} prospects total "
        f"({nb_m} maisons + {nb_a} apparts | {chauds} chauds | {dvf_ok} DVF | {sci_ok} SCI)"
    )
    print(f"   Arrondissements : {arr_str}")


if __name__ == "__main__":
    main()
