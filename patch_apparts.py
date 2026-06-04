#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_apparts.py — Applique tous les patches sur les appartements dans prospects.json
Patches appliqués :
  1. DVF historique (hist_*) depuis dvf_hist_appart.json
  2. Plus-value latente (pv_*) — prix ref appartements 13e
  3. DPE signal (dpe_age_jours, dpe_frais, signal_top)
  4. Annonces (via patch_annonces existant — Stream.Estate)
  5. SCI (via sci_marseille.json)
"""
import json, math, requests, time
from datetime import date, datetime
from pathlib import Path

REPO = Path("/home/user/workspace/boitage-13")
TODAY = date.today()

def haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371000.0
    r = math.pi / 180
    dla = (b_lat - a_lat) * r
    dlo = (b_lon - a_lon) * r
    h = math.sin(dla/2)**2 + math.cos(a_lat*r)*math.cos(b_lat*r)*math.sin(dlo/2)**2
    return 2 * R * math.asin(math.sqrt(h))

# ─── Chargement prospects ─────────────────────────────────────────────────────
with open(REPO / "prospects.json") as f:
    all_prospects = json.load(f)

apparts = [p for p in all_prospects if p.get("type_bien") == "appartement"]
maisons = [p for p in all_prospects if p.get("type_bien") != "appartement"]
print(f"Prospects: {len(maisons)} maisons + {len(apparts)} appartements")

# ─── PATCH 1 : DVF historique ─────────────────────────────────────────────────
print("\n=== PATCH 1: DVF Historique ===")
with open(REPO / "dvf_hist_appart.json") as f:
    hist_list = json.load(f)
hist_gps = [v for v in hist_list if v.get('lat') and v.get('lon')]
print(f"  {len(hist_gps)} ventes DVF hist appart avec GPS")

MATURITE_SEUILS = {
    'immature': (0, 5),
    'mature': (5, 10),
    'tres_mature': (10, 20),
    'ultra_mature': (20, 999),
}

def classMaturite(age_ans):
    if age_ans < 5:   return 'immature'
    if age_ans < 10:  return 'mature'
    if age_ans < 20:  return 'tres_mature'
    return 'ultra_mature'

hist_ok = 0
for p in apparts:
    lat, lon = p.get('lat'), p.get('lon')
    if not lat or not lon:
        continue
    # Chercher achat le plus ancien (< date DPE) dans rayon 80m
    dpe_date = p.get('date', '')
    best = None
    best_age = -1
    for v in hist_gps:
        d = haversine(lat, lon, v['lat'], v['lon'])
        if d > 80:
            continue
        # Exclure ventes après le DPE (le DPE a été fait avant ou après la vente)
        # On cherche l'achat le plus ancien (propriétaire depuis longtemps)
        vdate = v.get('date', '')
        try:
            age_ans = (TODAY - datetime.strptime(vdate, '%Y-%m-%d').date()).days / 365.25
        except:
            continue
        if age_ans > best_age:
            best_age = age_ans
            best = (v, round(d, 1))
    
    if best:
        v, dist = best
        age = round((TODAY - datetime.strptime(v['date'], '%Y-%m-%d').date()).days / 365.25, 1)
        p['hist_date_achat'] = v['date']
        p['hist_annee_achat'] = v['annee']
        p['hist_age_achat_ans'] = age
        p['hist_prix_achat'] = v['prix']
        p['hist_prix_m2_achat'] = v['prix_m2']
        p['hist_surface'] = v['surface']
        p['hist_dist_m'] = dist
        p['hist_maturite'] = classMaturite(age)
        hist_ok += 1

print(f"  {hist_ok}/{len(apparts)} appartements avec hist DVF")

# ─── PATCH 2 : Plus-value latente ────────────────────────────────────────────
print("\n=== PATCH 2: Plus-value ===")

# Prix de référence appartements 13e 2024-2025 par quartier
# Source: DVF 2024-2025 appartements 13013
PV_REF_APPART = {
    "Château-Gombert": 3400,
    "Saint-Jérôme":    3200,
    "Les Médecins":    3100,
    "Palama":          3000,
    "Les Mourets":     3300,
    "La Croix-Rouge":  3000,
    "Malpassé":        2800,
    "Saint-Just":      3200,
    "Saint-Mitre":     3100,
    "Clair Soleil":    3400,
    "Petit Bosquet":   3200,
    "La Rose":         3000,
    "Frais Vallon":    2900,
    "Montolivet":      3100,
    "Saint-Barnabé":   3000,
    "DEFAULT":         3100,  # médiane 13013 appart
}

# Calculer médiane réelle depuis dvf_hist_appart 2024-2025
prices_2024 = [v['prix_m2'] for v in hist_list if v.get('annee') in (2024, 2025) and v.get('prix_m2')]
if prices_2024:
    prices_2024.sort()
    median_m2 = prices_2024[len(prices_2024)//2]
    PV_REF_APPART['DEFAULT'] = median_m2
    print(f"  Prix médian appart 13013 2024-2025: {median_m2} €/m²")

pv_ok = 0
for p in apparts:
    if not p.get('hist_prix_achat') or not p.get('hist_surface'):
        continue
    q = p.get('q', 'DEFAULT')
    prix_m2_ref = PV_REF_APPART.get(q, PV_REF_APPART['DEFAULT'])
    surface = p.get('surface') or p.get('hist_surface', 0)
    valeur_estimee = round(prix_m2_ref * surface)
    plusvalue = valeur_estimee - p['hist_prix_achat']
    pct = round(plusvalue / p['hist_prix_achat'] * 100, 1) if p['hist_prix_achat'] else 0
    p['pv_valeur_estimee'] = valeur_estimee
    p['pv_plusvalue'] = int(plusvalue)
    p['pv_pct'] = pct
    p['pv_prix_m2_ref'] = prix_m2_ref
    pv_ok += 1

print(f"  {pv_ok}/{len(apparts)} appartements avec plus-value")

# ─── PATCH 3 : DPE Signal ────────────────────────────────────────────────────
print("\n=== PATCH 3: DPE Signal ===")

dpe_ok = 0
for p in apparts:
    dpe_date = p.get('date', '')
    try:
        age_jours = (TODAY - datetime.strptime(dpe_date, '%Y-%m-%d').date()).days
    except:
        p['dpe_age_jours'] = None
        p['dpe_frais'] = 'normal'
        p['signal_top'] = False
        continue

    p['dpe_age_jours'] = age_jours
    if age_jours <= 30:
        p['dpe_frais'] = 'tres_frais'
    elif age_jours <= 90:
        p['dpe_frais'] = 'frais'
    elif age_jours <= 180:
        p['dpe_frais'] = 'recents'
    else:
        p['dpe_frais'] = 'normal'

    # Signal TOP : DPE frais + établi après la vente DVF récente
    dvf_date = p.get('dvf_date', '')
    signal = False
    if p['dpe_frais'] in ('tres_frais', 'frais') and dvf_date:
        try:
            delta = (datetime.strptime(dpe_date, '%Y-%m-%d') - 
                     datetime.strptime(dvf_date, '%d/%m/%Y')).days
            # DPE établi entre 0 et 365j après vente DVF
            if 0 <= delta <= 365:
                signal = True
        except:
            try:
                delta = (datetime.strptime(dpe_date, '%Y-%m-%d') - 
                         datetime.strptime(dvf_date[:10], '%Y-%m-%d')).days
                if 0 <= delta <= 365:
                    signal = True
            except:
                pass
    p['signal_top'] = signal
    dpe_ok += 1

signal_top_count = sum(1 for p in apparts if p.get('signal_top'))
tres_frais = sum(1 for p in apparts if p.get('dpe_frais') == 'tres_frais')
frais = sum(1 for p in apparts if p.get('dpe_frais') == 'frais')
print(f"  {dpe_ok} traités | {tres_frais} très frais | {frais} frais | {signal_top_count} signal TOP")

# ─── PATCH 4 : Annonces Stream.Estate ────────────────────────────────────────
print("\n=== PATCH 4: Annonces Stream.Estate ===")
STREAM_KEY = "535adb50a9ce7a3674cb103b81f2d1ec"
RAYON_ANNONCES = 150  # mètres

def search_annonces(lat, lon, rayon=150):
    """Cherche annonces actives dans un rayon autour d'un point GPS."""
    url = "https://api.stream.estate/documents/properties"
    params = {
        "latitude": lat,
        "longitude": lon,
        "radius": rayon,
        "transaction_type": "sale",
        "property_type": "apartment",
        "limit": 5,
    }
    headers = {"X-Api-Key": STREAM_KEY}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            items = data.get('items') or data.get('results') or []
            return items
    except:
        pass
    return []

# Appliquer en batch (avec rate limiting)
ann_ok = 0
ann_skipped = 0

# Initialiser les champs annonces à 0 pour tous les apparts
for p in apparts:
    if 'annonces_actives' not in p:
        p['annonces_actives'] = 0
        p['annonce_url'] = None
        p['annonce_prix'] = None
        p['annonce_date'] = None
        p['annonce_source'] = None
        p['annonce_jours'] = None
        p['annonces_details'] = []

# Limiter à un test rapide (50 apparts les plus prometteurs pour ne pas spammer l'API)
# Note: le cron hebdo recalculera tous
apparts_to_scan = [p for p in apparts if p.get('dpe_frais') in ('tres_frais', 'frais', 'recents')]
print(f"  Scan annonces sur {len(apparts_to_scan)} apparts récents...")

for i, p in enumerate(apparts_to_scan):
    lat, lon = p.get('lat'), p.get('lon')
    if not lat or not lon:
        ann_skipped += 1
        continue
    
    items = search_annonces(lat, lon)
    if items:
        first = items[0]
        # Extraire prix
        prix = first.get('price') or first.get('prix')
        url_ann = first.get('url') or first.get('link') or ""
        date_ann = first.get('publication_date') or first.get('date') or ""
        source = first.get('source') or first.get('portal') or ""
        
        # Calculer jours depuis publication
        jours = None
        if date_ann:
            try:
                d = datetime.strptime(date_ann[:10], '%Y-%m-%d').date()
                jours = (TODAY - d).days
            except:
                pass
        
        p['annonces_actives'] = len(items)
        p['annonce_url'] = url_ann
        p['annonce_prix'] = prix
        p['annonce_date'] = date_ann[:10] if date_ann else None
        p['annonce_source'] = source
        p['annonce_jours'] = jours
        p['annonces_details'] = [
            {'prix': it.get('price'), 'url': it.get('url', ''), 'source': it.get('source', '')}
            for it in items[:3]
        ]
        ann_ok += 1
    
    if i % 10 == 9:
        time.sleep(0.5)  # rate limit

print(f"  {ann_ok} apparts avec annonces actives")

# ─── PATCH 5 : SCI ──────────────────────────────────────────────────────────
print("\n=== PATCH 5: SCI ===")
sci_path = Path("/home/user/workspace/sci_marseille.json")
if sci_path.exists():
    with open(sci_path) as f:
        sci_list = json.load(f)
    sci_gps = [s for s in sci_list if s.get('lat') and s.get('lon')]
    print(f"  {len(sci_gps)} SCIs avec GPS")
    
    sci_ok = 0
    for p in apparts:
        lat, lon = p.get('lat'), p.get('lon')
        if not lat or not lon:
            continue
        
        proches = []
        for sci in sci_gps:
            d = haversine(lat, lon, sci['lat'], sci['lon'])
            if d <= 100:
                proches.append({**sci, '_dist_m': round(d, 1)})
        
        if proches:
            proches.sort(key=lambda s: s['_dist_m'])
            closest = proches[0]
            p['sci_proche'] = {
                'nom': closest.get('nom', ''),
                'siren': closest.get('siren', ''),
                'adresse': closest.get('adresse', ''),
                'dist_m': closest['_dist_m'],
                'dirigeants': closest.get('dirigeants', []),
                'date_creation': closest.get('date_creation', ''),
            }
            p['sci_count'] = len(proches)
            sci_ok += 1
        else:
            p['sci_proche'] = None
            p['sci_count'] = 0
    
    print(f"  {sci_ok}/{len(apparts)} appartements avec SCI proche")
else:
    print("  sci_marseille.json non trouvé, skip")
    for p in apparts:
        if 'sci_proche' not in p:
            p['sci_proche'] = None
            p['sci_count'] = 0

# ─── Période construction ────────────────────────────────────────────────────
print("\n=== Patch période construction ===")
PERIODE_MAP = {
    'avant 1948':               ('pre1948',   'Avant 1948'),
    '1948-1974':                ('p1948',     '1948–1974'),
    '1975-1977':                ('p1975',     '1975–1977'),
    '1978-1982':                ('p1978',     '1978–1982'),
    '1983-1988':                ('p1983',     '1983–1988'),
    '1989-2000':                ('p1989',     '1989–2000'),
    '2001-2005':                ('p2001',     '2001–2005'),
    '2006-2012':                ('p2006',     '2006–2012'),
    '2013-2021':                ('p2013',     '2013–2021'),
    'après 2021':               ('post2021',  'Après 2021'),
}

for p in apparts:
    per = (p.get('periode') or '').lower()
    matched = False
    for key, (cat, label) in PERIODE_MAP.items():
        if key.lower() in per or per in key.lower():
            p['periode_cat'] = cat
            p['periode_label'] = label
            matched = True
            break
    if not matched:
        p['periode_cat'] = None
        p['periode_label'] = None

# ─── Reconstruire prospects.json complet ─────────────────────────────────────
print("\n=== Reconstruction prospects.json ===")
# Re-merger avec maisons
all_updated = maisons + apparts
all_updated.sort(key=lambda p: p['score'], reverse=True)
for i, p in enumerate(all_updated, 1):
    p['rang'] = i

out = REPO / "prospects.json"
out.write_text(json.dumps(all_updated, ensure_ascii=False, indent=1), encoding='utf-8')
print(f"Sauvegardé → {out}")

# Stats finales
nb_m = sum(1 for p in all_updated if p.get('type_bien') == 'maison')
nb_a = sum(1 for p in all_updated if p.get('type_bien') == 'appartement')
nb_hist_a = sum(1 for p in all_updated if p.get('type_bien') == 'appartement' and p.get('hist_date_achat'))
nb_pv_a = sum(1 for p in all_updated if p.get('type_bien') == 'appartement' and p.get('pv_pct') is not None)
nb_top_a = sum(1 for p in all_updated if p.get('type_bien') == 'appartement' and p.get('signal_top'))
nb_sci_a = sum(1 for p in all_updated if p.get('type_bien') == 'appartement' and p.get('sci_count', 0) > 0)
print(f"\nStats appartements:")
print(f"  Total: {nb_a}")
print(f"  Avec hist DVF: {nb_hist_a}")
print(f"  Avec plus-value: {nb_pv_a}")
print(f"  Signal TOP: {nb_top_a}")
print(f"  Avec SCI: {nb_sci_a}")
print(f"\nTotal prospects: {len(all_updated)} ({nb_m} maisons + {nb_a} apparts)")
