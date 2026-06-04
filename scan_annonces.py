#!/usr/bin/env python3
"""
Scanner annonces Stream.Estate — 140 prospects Marseille 13e
Lance avec : python3 scan_annonces.py --key VOTRE_CLE_API

Pour chaque prospect :
- Recherche par coordonnées GPS + rayon 200m
- Type: maison (1), transaction: vente (0), non expirées
- Injecte dans prospects.json : annonces_actives, annonce_url, annonce_prix, annonce_date, annonce_source, annonce_jours
"""

import requests, json, time, argparse
from datetime import datetime, date

# ── Paramètres ──
API_BASE = 'https://api.stream.estate/documents/properties'
RAYON_KM = 0.2  # 200m
ITEMS_PER_PAGE = 5

def scan_prospect(p, api_key):
    lat = p.get('lat')
    lon = p.get('lon')
    if not lat or not lon:
        return None

    params = {
        'lat': lat,
        'lon': lon,
        'radius': RAYON_KM,
        'propertyTypes[]': 1,       # maison
        'transactionType': 0,       # vente
        'expired': 'false',         # annonces actives uniquement
        'itemsPerPage': ITEMS_PER_PAGE,
        'orderCreatedAt': 'desc',
    }

    r = requests.get(API_BASE,
        params=params,
        headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'},
        timeout=10
    )

    if r.status_code == 403:
        raise Exception('Crédits insuffisants — recharger sur stream.estate/console/billing')
    if r.status_code != 200:
        return None

    data = r.json()
    members = data.get('hydra:member', [])

    if not members:
        return {'annonces_actives': 0, 'annonce_url': None, 'annonce_prix': None,
                'annonce_date': None, 'annonce_source': None, 'annonce_jours': None,
                'annonces_details': []}

    today = date.today()
    annonces = []
    for item in members:
        # Récupérer infos annonce (adverts)
        adverts = item.get('adverts', [item])
        for adv in adverts[:1]:
            pub_date = (adv.get('createdAt') or adv.get('publishedAt') or '')[:10]
            jours = None
            if pub_date:
                try:
                    d = datetime.strptime(pub_date, '%Y-%m-%d').date()
                    jours = (today - d).days
                except:
                    pass

            annonces.append({
                'url': adv.get('url') or item.get('url'),
                'prix': item.get('price') or adv.get('price'),
                'surface': item.get('surface') or item.get('area'),
                'date': pub_date,
                'jours': jours,
                'source': adv.get('sourceSite') or adv.get('source', '?'),
                'titre': item.get('title', ''),
            })

    best = annonces[0] if annonces else {}
    return {
        'annonces_actives': len(annonces),
        'annonce_url': best.get('url'),
        'annonce_prix': best.get('prix'),
        'annonce_date': best.get('date'),
        'annonce_source': best.get('source'),
        'annonce_jours': best.get('jours'),
        'annonces_details': annonces
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', required=True, help='Clé API Stream.Estate')
    parser.add_argument('--limit', type=int, default=0, help='Limiter à N prospects (test)')
    args = parser.parse_args()

    with open('prospects.json', encoding='utf-8') as f:
        data = json.load(f)

    prospects = data[:args.limit] if args.limit else data
    found = 0
    errors = 0

    print(f'Scan de {len(prospects)} prospects...')
    for i, p in enumerate(prospects):
        try:
            result = scan_prospect(p, args.key)
            if result:
                p.update(result)
                if result['annonces_actives'] > 0:
                    found += 1
                    print(f'  ✓ [{i+1}] {p["adresse"][:40]:40} → {result["annonces_actives"]} annonce(s) — {result["annonce_source"]} {result["annonce_jours"]}j — {result["annonce_prix"]}€')
            else:
                p['annonces_actives'] = 0
        except Exception as e:
            if 'Crédits' in str(e):
                print(f'\n⛔ {e}')
                break
            errors += 1

        if (i+1) % 10 == 0:
            print(f'  Progression: {i+1}/{len(prospects)} — {found} en vente, {errors} erreurs')

        time.sleep(0.3)  # respectueux

    # Sauvegarder
    with open('prospects.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'\n=== RÉSULTATS ===')
    print(f'Scannés: {len(prospects)}')
    print(f'En vente actuellement: {found}')
    print(f'Erreurs: {errors}')

    # Stats
    en_vente = [p for p in data if p.get('annonces_actives', 0) > 0]
    if en_vente:
        print(f'\nBiens en vente:')
        for p in sorted(en_vente, key=lambda x: x.get('annonce_jours') or 999):
            print(f'  {p["adresse"][:40]:40} {p["annonce_source"]:15} {p["annonce_jours"]}j {p["annonce_prix"]}€')
            print(f'  → {p["annonce_url"]}')


if __name__ == '__main__':
    main()
