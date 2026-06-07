#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_notion.py — Synchronise prospects.json vers la base Notion CRM.

Logique :
  - Lit prospects.json (tous les prospects)
  - Croise avec l'état Supabase (statuts, notes, contact, boîté le)
  - Pour chaque prospect :
      * Si déjà dans Notion (Boitage ID présent) → met à jour si changement
      * Sinon → crée la page
  - Priorité aux prospects boîtés et chauds (envoyés en premier)

Variables d'environnement requises :
  NOTION_TOKEN      — clé d'intégration Notion (Internal Integration Secret)
  SUPABASE_URL      — URL Supabase du projet
  SUPABASE_KEY      — clé anon publique Supabase
  SUPABASE_USER_ID  — UUID de l'utilisateur Rémi (pour lire app_state)

La base Notion cible :
  Data Source ID : 2824890c-4333-4b1c-9b27-04e08c97f1d9
"""
import json, os, time, urllib.request, urllib.parse
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── Configuration ──────────────────────────────────────────────────────────
NOTION_DS_ID = "2824890c-4333-4b1c-9b27-04e08c97f1d9"
NOTION_API   = "https://api.notion.com/v1"
NOTION_VER   = "2022-06-28"

# Limite de pages à créer/mettre à jour par run (éviter timeout CI)
BATCH_LIMIT  = 200

# ── Helpers HTTP ──────────────────────────────────────────────────────────
def notion_req(method, path, body=None, token=None):
    """Appel API Notion avec retry simple."""
    url = f"{NOTION_API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization":  f"Bearer {token}",
            "Notion-Version": NOTION_VER,
            "Content-Type":   "application/json",
        }
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body_err = e.read().decode()
            if e.code == 429:
                time.sleep(2 ** attempt)
                continue
            print(f"   NOTION ERR {e.code} {path}: {body_err[:200]}")
            return None
        except Exception as ex:
            print(f"   NOTION ERR {path}: {ex}")
            time.sleep(1)
    return None

def supabase_req(path, token, url_base, key):
    """Lecture simple Supabase REST."""
    full_url = f"{url_base}/rest/v1/{path}"
    req = urllib.request.Request(
        full_url,
        headers={
            "apikey":        key,
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception as e:
        print(f"   SUPABASE ERR {path}: {e}")
        return None

# ── Chargement données ────────────────────────────────────────────────────
def load_prospects():
    path = HERE / "prospects.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("prospects", [])

def load_state_supabase(sb_url, sb_key, user_id):
    """Récupère l'état app (statuts, notes, contacts) depuis Supabase."""
    if not all([sb_url, sb_key, user_id]):
        return {}
    path = f"app_state?select=data&user_id=eq.{user_id}"
    result = supabase_req(path, sb_key, sb_url, sb_key)
    if result and isinstance(result, list) and result:
        raw = result[0].get("data", {})
        return raw.get("state", {})
    return {}

def load_state_local():
    """Fallback : lit state depuis fichier local si présent (dev)."""
    p = HERE / "state_export.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}

# ── Lecture pages Notion existantes ──────────────────────────────────────
def fetch_existing_notion(token):
    """Retourne un dict {boitage_id: notion_page_id} pour éviter les doublons."""
    existing = {}
    cursor = None
    while True:
        body = {
            "page_size": 100,
            "filter": {
                "property": "Boitage ID",
                "rich_text": {"is_not_empty": True}
            }
        }
        if cursor:
            body["start_cursor"] = cursor
        resp = notion_req(
            "POST",
            f"/databases/{NOTION_DS_ID}/query",
            body=body,
            token=token,
        )
        if not resp:
            break
        for page in resp.get("results", []):
            props = page.get("properties", {})
            bid_prop = props.get("Boitage ID", {})
            bid = ""
            for rt in bid_prop.get("rich_text", []):
                bid += rt.get("plain_text", "")
            if bid:
                existing[bid] = page["id"]
        if resp.get("has_more"):
            cursor = resp.get("next_cursor")
        else:
            break
    return existing

# ── Construction payload Notion ──────────────────────────────────────────
def prospect_to_notion(p, r):
    """Convertit un prospect + son état local en propriétés Notion."""

    # Statuts : mapping depuis code entier → label Notion
    STATUT_MAP = {
        0: "A boîter",
        1: "Visité",      # pas dans Notion — fallback "Boîté"
        2: "Contacté",
        3: "RDV",
        4: "Pas vendeur",
        5: "Sous mandat",
        6: "Vendu",
    }
    statut_code = r.get("s", 0)
    statut = STATUT_MAP.get(statut_code, "A boîter")
    if r.get("b") and statut == "A boîter":
        statut = "Boîté"

    # Pipeline automatique selon tier + statut
    tier = p.get("tier", "froid")
    if statut in ("Sous mandat", "Vendu"):
        pipeline = "Mandat signé"
    elif statut in ("Contacté", "RDV"):
        pipeline = "En discussion"
    elif tier == "chaud":
        pipeline = "Prospect chaud"
    else:
        pipeline = "Prospect froid"

    # Type
    type_bien = p.get("type_bien", "maison")
    type_label = "Appartement" if type_bien == "appartement" else "Maison"

    # DPE / GES : seulement si valeur valide A-G
    dpe_val = p.get("dpe", "")
    ges_val = p.get("ges", "")
    valides = {"A","B","C","D","E","F","G"}
    dpe_prop = dpe_val if dpe_val in valides else None
    ges_prop = ges_val if ges_val in valides else None

    # Notes concaténées
    notes_list = r.get("notes", [])
    notes_str = "\n---\n".join(
        f"[{n.get('t','')[:10]}] {n.get('x','')}" for n in notes_list
    ) if notes_list else ""

    # Contact
    contact = r.get("contact", {})
    tel  = contact.get("tel", "") or ""
    mail = contact.get("email", "") or ""

    # Date boîté
    boite_date = None
    boite_raw = r.get("b", "")
    if boite_raw:
        try:
            boite_date = boite_raw[:10]  # YYYY-MM-DD
        except Exception:
            pass

    # SCI
    sci = p.get("sci_proche", {}) or {}
    sci_nom = sci.get("nom", "") if isinstance(sci, dict) else ""

    # Signal DVF
    dvf_sig = p.get("dvf_signal", "none") or "none"
    dvf_options = {"en_vente","vendu_recemment","ancienne_vente","none"}
    if dvf_sig not in dvf_options:
        dvf_sig = "none"

    today = date.today().isoformat()

    props = {
        "Adresse":    p.get("adresse", "Adresse inconnue"),
        "Statut":     statut,
        "Pipeline":   pipeline,
        "Quartier":   p.get("q", "") or "",
        "Type":       type_label,
        "Tier":       tier,
        "Score":      float(p.get("score", 0) or 0),
        "Surface":    float(p.get("surface", 0) or 0) or None,
        "Conso EP":   float(p.get("conso", 0) or 0) or None,
        "Chauffage":  p.get("chauf", "") or "",
        "Prioritaire": "__YES__" if p.get("prio") else "__NO__",
        "Signal TOP": "__YES__" if p.get("signal_top") else "__NO__",
        "En vente":   "__YES__" if p.get("annonces_actives") else "__NO__",
        "Signal DVF": dvf_sig,
        "SCI":        sci_nom[:100] if sci_nom else "",
        "Score SCI":  float(p.get("sci_score", 0) or 0) or None,
        "PV pct":     float(p.get("pv_pct", 0) or 0) or None,
        "Hist achat ans": float(p.get("hist_age_achat_ans", 0) or 0) or None,
        "Prix annonce":   float(p.get("annonce_prix", 0) or 0) or None,
        "Lat":        float(p.get("lat", 0) or 0) or None,
        "Lon":        float(p.get("lon", 0) or 0) or None,
        "N DPE":      str(p.get("id", "")) or "",
        "Boitage ID": str(p.get("id", "")) or "",
        "Notes":      notes_str[:1900] if notes_str else "",
        "date:Date MAJ:start":      today,
        "date:Date MAJ:is_datetime": 0,
    }

    if dpe_prop:
        props["DPE"] = dpe_prop
    if ges_prop:
        props["GES"] = ges_prop
    if tel:
        props["Telephone"] = tel[:20]
    if mail:
        props["Email"] = mail[:100]
    if p.get("gmaps"):
        props["Google Maps"] = p["gmaps"]
    if boite_date:
        props["date:Boite le:start"]      = boite_date
        props["date:Boite le:is_datetime"] = 0
    if p.get("annee"):
        try:
            props["Annee construction"] = float(p["annee"])
        except Exception:
            pass
    if p.get("etage") is not None:
        props["Etage"] = str(p["etage"])

    return props

def build_notion_page_body(p, r, parent_ds_id):
    """Construit le body complet pour créer une page Notion."""
    props = prospect_to_notion(p, r)
    title = props.pop("Adresse")

    # Propriétés Notion API format
    notion_props = {"Adresse": {"title": [{"text": {"content": title[:200]}}]}}

    # Mapping type → format Notion
    for key, val in props.items():
        if val is None or val == "":
            continue
        if key.startswith("date:"):
            # déjà géré ci-dessous
            continue
        if isinstance(val, bool):
            continue
        if isinstance(val, float):
            notion_props[key] = {"number": val}
        elif val in ("__YES__", "__NO__"):
            notion_props[key] = {"checkbox": val == "__YES__"}
        elif key in ("Statut","Pipeline","Tier","Type","DPE","GES","Signal DVF"):
            notion_props[key] = {"select": {"name": val}}
        elif key in ("Telephone",):
            notion_props[key] = {"phone_number": val}
        elif key in ("Email",):
            notion_props[key] = {"email": val}
        elif key in ("Google Maps",):
            notion_props[key] = {"url": val}
        else:
            notion_props[key] = {"rich_text": [{"text": {"content": str(val)[:2000]}}]}

    # Dates
    for prefix in ("date:Boite le", "date:Date MAJ"):
        start_key = f"{prefix}:start"
        dt_key    = f"{prefix}:is_datetime"
        prop_name = prefix.replace("date:", "")
        if props.get(start_key):
            notion_props[prop_name] = {
                "date": {
                    "start":       props[start_key],
                    "time_zone":   "Europe/Paris",
                }
            }

    return {
        "parent": {"database_id": parent_ds_id},
        "properties": notion_props,
    }

def update_notion_page(page_id, p, r, token):
    """Met à jour une page Notion existante."""
    props = prospect_to_notion(p, r)
    title = props.pop("Adresse")

    notion_props = {"Adresse": {"title": [{"text": {"content": title[:200]}}]}}
    for key, val in props.items():
        if val is None or val == "":
            continue
        if key.startswith("date:"):
            continue
        if isinstance(val, float):
            notion_props[key] = {"number": val}
        elif val in ("__YES__", "__NO__"):
            notion_props[key] = {"checkbox": val == "__YES__"}
        elif key in ("Statut","Pipeline","Tier","Type","DPE","GES","Signal DVF"):
            notion_props[key] = {"select": {"name": val}}
        elif key in ("Telephone",):
            notion_props[key] = {"phone_number": val}
        elif key in ("Email",):
            notion_props[key] = {"email": val}
        elif key in ("Google Maps",):
            notion_props[key] = {"url": val}
        else:
            notion_props[key] = {"rich_text": [{"text": {"content": str(val)[:2000]}}]}

    for prefix in ("date:Boite le", "date:Date MAJ"):
        start_key = f"{prefix}:start"
        prop_name = prefix.replace("date:", "")
        if props.get(start_key):
            notion_props[prop_name] = {"date": {"start": props[start_key]}}

    resp = notion_req(
        "PATCH", f"/pages/{page_id}",
        body={"properties": notion_props},
        token=token,
    )
    return resp is not None

# ── Main ──────────────────────────────────────────────────────────────────
def main():
    print("=== sync_notion.py — Sync prospects → Notion CRM ===")

    notion_token = os.environ.get("NOTION_TOKEN", "")
    sb_url       = os.environ.get("SUPABASE_URL", "")
    sb_key       = os.environ.get("SUPABASE_KEY", "")
    sb_user_id   = os.environ.get("SUPABASE_USER_ID", "")

    if not notion_token:
        print("ABANDON : NOTION_TOKEN manquant.")
        return

    # Chargement prospects
    prospects = load_prospects()
    if not prospects:
        print("ABANDON : prospects.json vide ou absent.")
        return
    print(f"-> {len(prospects)} prospects chargés")

    # Chargement état (Supabase en priorité, sinon local)
    if sb_url and sb_key and sb_user_id:
        state = load_state_supabase(sb_url, sb_key, sb_user_id)
        print(f"-> Etat Supabase : {len(state)} entrées")
    else:
        state = load_state_local()
        print(f"-> Etat local : {len(state)} entrées")

    # Tri : boîtés et chauds en premier
    def sort_key(p):
        r = state.get(p.get("id",""), {})
        boite = 1 if r.get("b") else 0
        tier_score = {"chaud":2,"tiede":1,"froid":0}.get(p.get("tier","froid"),0)
        return (boite * 10 + tier_score, p.get("score", 0))

    prospects_sorted = sorted(prospects, key=sort_key, reverse=True)

    # Récupération pages existantes
    print("-> Récupération pages Notion existantes…")
    existing = fetch_existing_notion(notion_token)
    print(f"   {len(existing)} pages trouvées dans Notion")

    # Sync
    created = updated = skipped = errors = 0

    for i, p in enumerate(prospects_sorted[:BATCH_LIMIT]):
        pid = p.get("id", "")
        if not pid:
            skipped += 1
            continue

        r = state.get(pid, {})
        # On n'exclut rien — tous les prospects vont dans Notion

        if pid in existing:
            # Mise à jour
            ok = update_notion_page(existing[pid], p, r, notion_token)
            if ok:
                updated += 1
            else:
                errors += 1
        else:
            # Création
            body = build_notion_page_body(p, r, NOTION_DS_ID)
            resp = notion_req("POST", "/pages", body=body, token=notion_token)
            if resp and resp.get("id"):
                created += 1
            else:
                errors += 1

        # Throttle : 3 req/s max sur l'API Notion
        if (i + 1) % 3 == 0:
            time.sleep(1)

        if (i + 1) % 50 == 0:
            print(f"   ...{i+1} traités ({created} créés, {updated} MAJ, {errors} erreurs)")

    print(f"OK — {created} créés | {updated} mis à jour | {skipped} ignorés | {errors} erreurs")
    print(f"   Notion : https://www.notion.so/{NOTION_DS_ID.replace('-','')}")


if __name__ == "__main__":
    main()
