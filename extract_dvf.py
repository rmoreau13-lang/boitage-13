#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrait les ventes de maisons Marseille 13e depuis les fichiers DVF bruts."""
import csv, json

# Code commune dans DVF = '213' pour Marseille 13e (dep 13 + commune 213)
TARGET_DEP = '13'
TARGET_COM = '213'
TARGET_COMMUNE = 'MARSEILLE 13EME'
TARGET_NATURE = 'Vente'
TARGET_TYPES = {'Maison'}

ventes = []
seen_ids = set()

for fname in [
    '/home/user/workspace/boitage-13/dvf_tmp/ValeursFoncieres-2024.txt',
    '/home/user/workspace/boitage-13/dvf_tmp/ValeursFoncieres-2025.txt',
]:
    print(f'Lecture {fname}...')
    with open(fname, encoding='latin-1') as f:
        reader = csv.DictReader(f, delimiter='|')
        count_file = 0
        for row in reader:
            if row.get('Code departement') != TARGET_DEP:
                continue
            if row.get('Code commune') != TARGET_COM:
                continue
            if row.get('Nature mutation') != TARGET_NATURE:
                continue
            if row.get('Type local') not in TARGET_TYPES:
                continue

            # Dédoublonnage par mutation + adresse
            mut_id = (row.get('No disposition', '') + '|' +
                      row.get('No voie', '') + '|' +
                      row.get('Voie', '') + '|' +
                      row.get('Date mutation', ''))
            if mut_id in seen_ids:
                continue
            seen_ids.add(mut_id)

            # Coordonnées GPS (présentes dans le fichier)
            lat_str = row.get('Latitude', '').replace(',', '.').strip()
            lon_str = row.get('Longitude', '').replace(',', '.').strip()
            try:
                lat = float(lat_str) if lat_str else None
                lon = float(lon_str) if lon_str else None
            except Exception:
                lat, lon = None, None

            # Prix
            try:
                prix_raw = row.get('Valeur fonciere', '').replace(',', '.').replace(' ', '')
                prix = float(prix_raw) if prix_raw else None
            except Exception:
                prix = None

            # Surface bâtie
            try:
                surf_raw = row.get('Surface reelle bati', '').replace(',', '.').strip()
                surf = float(surf_raw) if surf_raw else None
                surf = surf if surf and surf > 0 else None
            except Exception:
                surf = None

            # Surface terrain
            try:
                t_raw = row.get('Surface terrain', '').replace(',', '.').strip()
                terrain = float(t_raw) if t_raw else None
                terrain = terrain if terrain and terrain > 0 else None
            except Exception:
                terrain = None

            # Pièces
            try:
                p_raw = row.get('Nombre pieces principales', '').replace(',', '.').strip()
                pieces = int(float(p_raw)) if p_raw else None
                pieces = pieces if pieces and pieces > 0 else None
            except Exception:
                pieces = None

            # Date ISO
            date_raw = row.get('Date mutation', '')
            try:
                d, m, y = date_raw.split('/')
                date_iso = f'{y}-{m}-{d}'
            except Exception:
                date_iso = date_raw

            # Adresse propre
            adresse = ' '.join(filter(None, [
                row.get('No voie', '').strip(),
                row.get('B/T/Q', '').strip(),
                row.get('Type de voie', '').strip(),
                row.get('Voie', '').strip(),
            ])).strip().title()

            prix_m2 = round(prix / surf, 0) if prix and surf else None

            ventes.append({
                'date_mutation': date_iso,
                'adresse': adresse,
                'code_postal': row.get('Code postal', '').strip(),
                'commune': 'Marseille 13e',
                'prix': prix,
                'surface_bati': surf,
                'surface_terrain': terrain,
                'pieces': pieces,
                'lat': lat,
                'lon': lon,
                'prix_m2': prix_m2,
                'type_local': row.get('Type local', ''),
            })
            count_file += 1
        print(f'  -> {count_file} ventes maisons')

print(f'\nTotal ventes maisons 13e: {len(ventes)}')

with open('/home/user/workspace/boitage-13/dvf_raw.json', 'w', encoding='utf-8') as f:
    json.dump(ventes, f, ensure_ascii=False, indent=1)

if ventes:
    prix_valides = [v['prix_m2'] for v in ventes if v['prix_m2'] and 500 < v['prix_m2'] < 15000]
    if prix_valides:
        moy = sum(prix_valides) / len(prix_valides)
        med = sorted(prix_valides)[len(prix_valides) // 2]
        print(f'Prix m2 moyen: {moy:.0f} eur/m2')
        print(f'Prix m2 median: {med:.0f} eur/m2')
    geos = sum(1 for v in ventes if v['lat'])
    print(f'Avec GPS: {geos}/{len(ventes)}')
    annees = sorted(set(v['date_mutation'][:4] for v in ventes if v['date_mutation']))
    print(f'Annees: {annees}')

print('dvf_raw.json sauvegarde.')
