#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Géocode les adresses DVF via l'API BAN (batch CSV).
https://adresse.data.gouv.fr/api-doc/adresse
"""
import csv, io, json, time, urllib.request, urllib.parse

DVF_FILE = '/home/user/workspace/boitage-13/dvf_raw.json'
OUT_FILE = '/home/user/workspace/boitage-13/dvf_geocoded.json'
BAN_BATCH = 'https://api-adresse.data.gouv.fr/search/csv/'

with open(DVF_FILE, encoding='utf-8') as f:
    ventes = json.load(f)

print(f'{len(ventes)} ventes à géocoder...')

# Préparer le CSV pour l'API BAN batch
# Format : id, adresse, postcode
rows_csv = [['id', 'adresse', 'postcode']]
for i, v in enumerate(ventes):
    adresse = v.get('adresse', '').strip()
    cp = v.get('code_postal', '13013').strip() or '13013'
    rows_csv.append([str(i), adresse, cp])

# Écrire en CSV en mémoire
buf = io.StringIO()
writer = csv.writer(buf)
writer.writerows(rows_csv)
csv_bytes = buf.getvalue().encode('utf-8')

# Appel API BAN batch (max 50 000 lignes)
print('Appel API BAN batch...')
BATCH_SIZE = 5000

geo_map = {}  # id -> (lat, lon, score, result_label)

for start in range(0, len(rows_csv) - 1, BATCH_SIZE):
    chunk = [rows_csv[0]] + rows_csv[1 + start: 1 + start + BATCH_SIZE]
    buf2 = io.StringIO()
    writer2 = csv.writer(buf2)
    writer2.writerows(chunk)
    csv_chunk = buf2.getvalue().encode('utf-8')

    boundary = b'----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = (
        b'--' + boundary + b'\r\n'
        b'Content-Disposition: form-data; name="data"; filename="adresses.csv"\r\n'
        b'Content-Type: text/csv\r\n\r\n' +
        csv_chunk + b'\r\n'
        b'--' + boundary + b'\r\n'
        b'Content-Disposition: form-data; name="columns"\r\n\r\nadresse\r\n'
        b'--' + boundary + b'\r\n'
        b'Content-Disposition: form-data; name="postcode"\r\n\r\npostcode\r\n'
        b'--' + boundary + b'--\r\n'
    )

    req = urllib.request.Request(
        BAN_BATCH,
        data=body,
        headers={
            'Content-Type': f'multipart/form-data; boundary={boundary.decode()}',
            'User-Agent': 'boitage-13/1.0',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result_csv = r.read().decode('utf-8')
    except Exception as e:
        print(f'  ERR batch {start}: {e}')
        continue

    reader2 = csv.DictReader(io.StringIO(result_csv))
    for row in reader2:
        rid = row.get('id', '')
        lat_s = row.get('latitude', '')
        lon_s = row.get('longitude', '')
        score_s = row.get('result_score', '0')
        label = row.get('result_label', '')
        try:
            lat = float(lat_s) if lat_s else None
            lon = float(lon_s) if lon_s else None
            score = float(score_s) if score_s else 0
        except Exception:
            lat, lon, score = None, None, 0
        geo_map[rid] = (lat, lon, score, label)

    print(f'  Batch {start//BATCH_SIZE+1}: {len(geo_map)} géocodés')
    time.sleep(0.3)

# Injecter les coordonnées dans les ventes
enriched = 0
for i, v in enumerate(ventes):
    geo = geo_map.get(str(i))
    if geo and geo[0]:
        v['lat'] = geo[0]
        v['lon'] = geo[1]
        v['ban_score'] = round(geo[2], 3)
        v['ban_label'] = geo[3]
        enriched += 1

print(f'\nGéocodés: {enriched}/{len(ventes)}')

with open(OUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(ventes, f, ensure_ascii=False, indent=1)
print(f'Sauvegardé: {OUT_FILE}')
