/* ============================================================
   FILTRES AVANCÉS PRO — Boîtage 13e
   Auteur : Agent Perplexity Computer
   Pattern : étend window.filtered() / hasActiveFilters() / resetFilters()
   sans casser l'existant. Chargé après le script principal.
   ============================================================ */
(function(){
'use strict';

/* ---------- État global avancé ---------- */
window.fAdv = {
  surfMin:0, surfMax:0,
  consoMin:0, consoMax:0,
  anneeMin:0, anneeMax:0,
  etageMin:-1, etageMax:99,
  jourMin:0, jourMax:0,
  dpe:new Set(),        // {'A','B','C','D','E','F','G'}
  ges:new Set(),
  chauf:new Set(),      // énergie de chauffage
  periode:new Set(),    // 'avant1948','1948-1974','1975-1989','1990-2005','apres2005'
  statut:new Set(),     // statut prospection (visité, RDV, etc.)
  passoire:false,       // F+G + maison
  audit:false,          // E/F/G maison (audit obligatoire vente)
  fioul2025:false,      // fioul/charbon
  isolMauvaise:false,   // iso_enveloppe = insuffisante / non_isolé
  confortEteMauvais:false,
  excluContacte:false,  // exclure si statut != 'À visiter'
  preset:null
};

/* ---------- Presets professionnels ---------- */
const PRESETS = {
  passoire:{
    label:'🔥 Passoires F/G',
    desc:'Maisons F+G > 80m² — loi Climat & Résilience',
    apply:function(){
      resetAdvOnly();
      fAdv.dpe = new Set(['F','G']);
      fAdv.surfMin = 80;
      window.fType = 'maison';
      toggleChipState('cmaison', true);
    }
  },
  audit:{
    label:'📋 Audit obligatoire',
    desc:'Maisons E/F/G — audit énergétique requis à la vente',
    apply:function(){
      resetAdvOnly();
      fAdv.dpe = new Set(['E','F','G']);
      window.fType = 'maison';
      toggleChipState('cmaison', true);
    }
  },
  fioul:{
    label:'🛢️ Chauffage fioul',
    desc:'Énergie fossile — interdiction renforcée',
    apply:function(){
      resetAdvOnly();
      fAdv.chauf = new Set(['Fioul','Fioul domestique','Charbon']);
      fAdv.dpe = new Set(['D','E','F','G']);
    }
  },
  mutation:{
    label:'🆕 Mutation récente',
    desc:'DPE < 90j + non encore boîté',
    apply:function(){
      resetAdvOnly();
      window.fDpeMax = 90;
      window.fBoite = 1;
      const s=document.getElementById('dpe-max-sel'); if(s) s.value='90';
      toggleChipState('cboite', true);
    }
  },
  gros:{
    label:'🏰 Gros volumes',
    desc:'> 150 m² + quartiers prioritaires',
    apply:function(){
      resetAdvOnly();
      fAdv.surfMin = 150;
      window.prio = 1;
      toggleChipState('cprio', true);
    }
  },
  vieux:{
    label:'🏚️ Bâti ancien',
    desc:'Construit avant 1975 + isolation insuffisante',
    apply:function(){
      resetAdvOnly();
      fAdv.anneeMax = 1974;
      fAdv.isolMauvaise = true;
    }
  },
  copro:{
    label:'🏢 Copro fragile',
    desc:'Appartements en copropriété fragile',
    apply:function(){
      resetAdvOnly();
      window.fType = 'appartement';
      window.fCopro = 1;
      toggleChipState('cappart', true);
      toggleChipState('ccoprof', true);
    }
  },
  vente:{
    label:'🎯 Signal vente',
    desc:'Signal TOP — pas d\u2019annonce active = à approcher vite',
    apply:function(){
      resetAdvOnly();
      window.fTop = 1;
      toggleChipState('ctop', true);
      fAdv._excludeVente = true; // géré dans passAdv
    }
  }
};

function resetAdvOnly(){
  fAdv.surfMin=0; fAdv.surfMax=0;
  fAdv.consoMin=0; fAdv.consoMax=0;
  fAdv.anneeMin=0; fAdv.anneeMax=0;
  fAdv.etageMin=-1; fAdv.etageMax=99;
  fAdv.jourMin=0; fAdv.jourMax=0;
  fAdv.dpe.clear(); fAdv.ges.clear();
  fAdv.chauf.clear(); fAdv.periode.clear(); fAdv.statut.clear();
  fAdv.passoire=false; fAdv.audit=false; fAdv.fioul2025=false;
  fAdv.isolMauvaise=false; fAdv.confortEteMauvais=false;
  fAdv.excluContacte=false; fAdv._excludeVente=false;
}

function toggleChipState(id, on){
  const el=document.getElementById(id);
  if(!el) return;
  if(on) el.classList.add('on'); else el.classList.remove('on');
}

/* ---------- Prédicat de filtrage avancé ---------- */
window.passAdv = function(p){
  const a = window.fAdv;
  // surface
  if(a.surfMin && (p.surface||0) < a.surfMin) return false;
  if(a.surfMax && (p.surface||0) > a.surfMax) return false;
  // conso
  if(a.consoMin && (p.conso||0) < a.consoMin) return false;
  if(a.consoMax && (p.conso||0) > a.consoMax) return false;
  // année
  if(a.anneeMin && (p.annee||0) < a.anneeMin) return false;
  if(a.anneeMax && (p.annee||9999) > a.anneeMax) return false;
  // étage
  if(a.etageMin>=0 && (p.etage==null || p.etage < a.etageMin)) return false;
  if(a.etageMax<99 && (p.etage==null || p.etage > a.etageMax)) return false;
  // DPE / GES
  if(a.dpe.size > 0 && !a.dpe.has((p.dpe||'').toUpperCase())) return false;
  if(a.ges.size > 0 && !a.ges.has((p.ges||'').toUpperCase())) return false;
  // chauffage
  if(a.chauf.size > 0){
    const e = (p.chauf||p.ecs_energie||'').toLowerCase();
    let ok=false;
    a.chauf.forEach(function(c){ if(e.includes(c.toLowerCase())) ok=true; });
    if(!ok) return false;
  }
  // période
  if(a.periode.size > 0){
    const an = p.annee||0;
    let per='';
    if(an && an<1948) per='avant1948';
    else if(an>=1948 && an<=1974) per='1948-1974';
    else if(an>=1975 && an<=1989) per='1975-1989';
    else if(an>=1990 && an<=2005) per='1990-2005';
    else if(an>2005) per='apres2005';
    if(!a.periode.has(per)) return false;
  }
  // statut prospection
  if(a.statut.size > 0){
    const r = (typeof rec==='function') ? rec(p.id) : null;
    const s = (r && r.s) || 'À visiter';
    if(!a.statut.has(s)) return false;
  }
  // isolation
  if(a.isolMauvaise){
    const iso = (p.iso_enveloppe||'').toLowerCase();
    if(!iso.includes('insuffisante') && !iso.includes('non isol') && !iso.includes('mauvaise')) return false;
  }
  // confort été
  if(a.confortEteMauvais){
    const c = (p.confort_ete||'').toLowerCase();
    if(c && !c.includes('insuffisant') && !c.includes('mauvais') && !c.includes('faible')) return false;
    if(!c) return false;
  }
  // exclure contactés
  if(a.excluContacte){
    const r = (typeof rec==='function') ? rec(p.id) : null;
    const s = (r && r.s) || 'À visiter';
    if(s !== 'À visiter') return false;
  }
  // exclure ceux qui ont déjà une annonce active (preset vente)
  if(a._excludeVente && p.annonces_actives) return false;
  return true;
};

/* ---------- Wrap des fonctions existantes ---------- */
const _origFiltered = window.filtered;
window.filtered = function(){
  const arr = _origFiltered.apply(this, arguments);
  return arr.filter(passAdv);
};

const _origHasActive = window.hasActiveFilters;
window.hasActiveFilters = function(){
  if(_origHasActive && _origHasActive()) return true;
  const a = window.fAdv;
  return a.surfMin||a.surfMax||a.consoMin||a.consoMax||a.anneeMin||a.anneeMax
    ||a.etageMin>=0 ? false : false // étage géré séparément
    ||a.dpe.size||a.ges.size||a.chauf.size||a.periode.size||a.statut.size
    ||a.passoire||a.audit||a.fioul2025||a.isolMauvaise||a.confortEteMauvais
    ||a.excluContacte||a._excludeVente||a.preset;
};
// fix: la ligne ci-dessus a un bug logique, on la remplace proprement
window.hasActiveFilters = function(){
  if(_origHasActive && _origHasActive()) return true;
  const a = window.fAdv;
  if(a.surfMin||a.surfMax) return true;
  if(a.consoMin||a.consoMax) return true;
  if(a.anneeMin||a.anneeMax) return true;
  if(a.etageMin>0 || a.etageMax<99) return true;
  if(a.dpe.size||a.ges.size||a.chauf.size||a.periode.size||a.statut.size) return true;
  if(a.isolMauvaise||a.confortEteMauvais||a.excluContacte||a._excludeVente) return true;
  if(a.preset) return true;
  return false;
};

const _origReset = window.resetFilters;
window.resetFilters = function(){
  resetAdvOnly();
  fAdv.preset = null;
  syncAdvUI();
  document.querySelectorAll('.preset-btn').forEach(function(b){b.classList.remove('on');});
  if(_origReset) return _origReset.apply(this, arguments);
};

/* ---------- UI : panneau avancé ---------- */
function buildAdvUI(){
  // bouton à côté de #fbtn
  const srow = document.getElementById('srow');
  if(!srow || document.getElementById('fbtn-adv')) return;
  const btn = document.createElement('button');
  btn.className = 'fbtn';
  btn.id = 'fbtn-adv';
  btn.innerHTML = '⚡ Pro';
  btn.title = 'Filtres avancés + presets pros';
  btn.style.background = 'linear-gradient(135deg,#6b3f99,#9333ea)';
  btn.style.color = '#fff';
  btn.style.borderColor = '#6b3f99';
  btn.onclick = function(){
    const wrap = document.getElementById('adv-panel-wrap');
    if(!wrap) return;
    const open = wrap.classList.toggle('open');
    btn.classList.toggle('on', open);
  };
  // insérer après le bouton ⚙︎ Filtres
  const refBtn = document.getElementById('fbtn');
  refBtn.parentNode.insertBefore(btn, refBtn.nextSibling);

  // panneau
  const top = document.querySelector('.top');
  if(!top) return;
  const wrap = document.createElement('div');
  wrap.id = 'adv-panel-wrap';
  wrap.className = 'adv-panel-wrap';
  wrap.innerHTML = renderAdvHTML();
  // insérer après le panneau existant
  const existingPanel = document.getElementById('panel');
  existingPanel.parentNode.insertBefore(wrap, existingPanel.nextSibling);

  attachAdvHandlers();
}

function renderAdvHTML(){
  return ''
  +'<div class="adv-panel"><div class="adv-in">'
  // Presets
  +'<div class="adv-section">'
  +'<div class="adv-h">🎯 Playbooks pros — un clic = stratégie complète</div>'
  +'<div class="adv-presets">'
    + Object.keys(PRESETS).map(function(k){
        const p = PRESETS[k];
        return '<button class="preset-btn" data-preset="'+k+'" title="'+p.desc+'">'+p.label+'</button>';
      }).join('')
  +'</div></div>'
  // DPE / GES
  +'<div class="adv-section">'
  +'<div class="adv-h">🌡️ Étiquettes DPE & GES</div>'
  +'<div class="adv-row"><span class="adv-lbl">DPE</span><div class="adv-dpe" id="adv-dpe">'
    + ['A','B','C','D','E','F','G'].map(function(l){
        return '<button class="dpe-chip dpe-'+l+'" data-dpe="'+l+'">'+l+'</button>';
      }).join('')
  +'</div></div>'
  +'<div class="adv-row"><span class="adv-lbl">GES</span><div class="adv-dpe" id="adv-ges">'
    + ['A','B','C','D','E','F','G'].map(function(l){
        return '<button class="dpe-chip dpe-'+l+'" data-ges="'+l+'">'+l+'</button>';
      }).join('')
  +'</div></div></div>'
  // Surface / Conso / Année
  +'<div class="adv-section">'
  +'<div class="adv-h">📐 Caractéristiques du bien</div>'
  +'<div class="adv-grid">'
    +rangeRow('Surface (m²)', 'surfMin', 'surfMax', 0, 500, 'm²')
    +rangeRow('Conso (kWh/m²/an)', 'consoMin', 'consoMax', 0, 800, '')
    +rangeRow('Année construction', 'anneeMin', 'anneeMax', 1800, 2025, '')
    +rangeRow('Étage', 'etageMin', 'etageMax', 0, 20, '')
  +'</div></div>'
  // Chauffage
  +'<div class="adv-section">'
  +'<div class="adv-h">🔥 Énergie de chauffage</div>'
  +'<div class="adv-row" id="adv-chauf">'
    + ['Fioul','Gaz','Électricité','Bois','Pompe à chaleur','Charbon','Réseau urbain']
        .map(function(c){ return '<button class="chip-mini" data-chauf="'+c+'">'+c+'</button>'; }).join('')
  +'</div></div>'
  // Période
  +'<div class="adv-section">'
  +'<div class="adv-h">🏛️ Période de construction</div>'
  +'<div class="adv-row" id="adv-periode">'
    +'<button class="chip-mini" data-periode="avant1948">Avant 1948</button>'
    +'<button class="chip-mini" data-periode="1948-1974">1948-1974</button>'
    +'<button class="chip-mini" data-periode="1975-1989">1975-1989</button>'
    +'<button class="chip-mini" data-periode="1990-2005">1990-2005</button>'
    +'<button class="chip-mini" data-periode="apres2005">Après 2005</button>'
  +'</div></div>'
  // Statut prospection
  +'<div class="adv-section">'
  +'<div class="adv-h">📋 Statut prospection</div>'
  +'<div class="adv-row" id="adv-statut">'
    + ['À visiter','Visité','Contacté','RDV','Pas vendeur','Sous mandat','Vendu']
        .map(function(s){ return '<button class="chip-mini" data-statut="'+s+'">'+s+'</button>'; }).join('')
  +'</div>'
  +'<div class="adv-row" style="margin-top:6px"><button class="chip-mini" id="adv-only-todo">⚡ Seulement à visiter</button></div>'
  +'</div>'
  // Qualité bâti
  +'<div class="adv-section">'
  +'<div class="adv-h">🧱 Qualité du bâti</div>'
  +'<div class="adv-row">'
    +'<button class="chip-mini" id="adv-iso">🥶 Isolation insuffisante</button>'
    +'<button class="chip-mini" id="adv-ete">🥵 Confort été dégradé</button>'
  +'</div></div>'
  // Actions
  +'<div class="adv-actions">'
    +'<div class="adv-count" id="adv-count">— prospects</div>'
    +'<button class="adv-reset" id="adv-reset">✕ Réinitialiser</button>'
    +'<button class="adv-apply" id="adv-apply">✓ Appliquer</button>'
  +'</div>'
  +'</div></div>';
}

function rangeRow(label, kMin, kMax, lo, hi, unit){
  return '<div class="adv-range">'
    +'<div class="adv-range-lbl">'+label+'</div>'
    +'<div class="adv-range-inputs">'
      +'<input type="number" class="adv-num" data-fadv="'+kMin+'" placeholder="min" min="'+lo+'" max="'+hi+'">'
      +'<span>—</span>'
      +'<input type="number" class="adv-num" data-fadv="'+kMax+'" placeholder="max" min="'+lo+'" max="'+hi+'">'
      +(unit?'<span class="adv-unit">'+unit+'</span>':'')
    +'</div></div>';
}

function attachAdvHandlers(){
  // presets
  document.querySelectorAll('.preset-btn').forEach(function(b){
    b.addEventListener('click', function(){
      const k = b.dataset.preset;
      const wasOn = b.classList.contains('on');
      document.querySelectorAll('.preset-btn').forEach(function(x){x.classList.remove('on');});
      if(wasOn){
        resetAdvOnly();
        fAdv.preset = null;
      } else {
        b.classList.add('on');
        PRESETS[k].apply();
        fAdv.preset = k;
      }
      syncAdvUI();
      window.refresh && window.refresh();
      updateAdvCount();
    });
  });
  // DPE / GES chips
  document.querySelectorAll('#adv-dpe .dpe-chip').forEach(function(c){
    c.addEventListener('click', function(){
      const l = c.dataset.dpe;
      if(fAdv.dpe.has(l)){ fAdv.dpe.delete(l); c.classList.remove('on'); }
      else { fAdv.dpe.add(l); c.classList.add('on'); }
      updateAdvCount();
    });
  });
  document.querySelectorAll('#adv-ges .dpe-chip').forEach(function(c){
    c.addEventListener('click', function(){
      const l = c.dataset.ges;
      if(fAdv.ges.has(l)){ fAdv.ges.delete(l); c.classList.remove('on'); }
      else { fAdv.ges.add(l); c.classList.add('on'); }
      updateAdvCount();
    });
  });
  // chauffage
  document.querySelectorAll('#adv-chauf .chip-mini').forEach(function(c){
    c.addEventListener('click', function(){
      const v = c.dataset.chauf;
      if(fAdv.chauf.has(v)){ fAdv.chauf.delete(v); c.classList.remove('on'); }
      else { fAdv.chauf.add(v); c.classList.add('on'); }
      updateAdvCount();
    });
  });
  // période
  document.querySelectorAll('#adv-periode .chip-mini').forEach(function(c){
    c.addEventListener('click', function(){
      const v = c.dataset.periode;
      if(fAdv.periode.has(v)){ fAdv.periode.delete(v); c.classList.remove('on'); }
      else { fAdv.periode.add(v); c.classList.add('on'); }
      updateAdvCount();
    });
  });
  // statut
  document.querySelectorAll('#adv-statut .chip-mini').forEach(function(c){
    c.addEventListener('click', function(){
      const v = c.dataset.statut;
      if(fAdv.statut.has(v)){ fAdv.statut.delete(v); c.classList.remove('on'); }
      else { fAdv.statut.add(v); c.classList.add('on'); }
      updateAdvCount();
    });
  });
  // toggles
  const t1 = document.getElementById('adv-only-todo');
  if(t1) t1.addEventListener('click', function(){
    fAdv.excluContacte = !fAdv.excluContacte;
    t1.classList.toggle('on', fAdv.excluContacte);
    updateAdvCount();
  });
  const t2 = document.getElementById('adv-iso');
  if(t2) t2.addEventListener('click', function(){
    fAdv.isolMauvaise = !fAdv.isolMauvaise;
    t2.classList.toggle('on', fAdv.isolMauvaise);
    updateAdvCount();
  });
  const t3 = document.getElementById('adv-ete');
  if(t3) t3.addEventListener('click', function(){
    fAdv.confortEteMauvais = !fAdv.confortEteMauvais;
    t3.classList.toggle('on', fAdv.confortEteMauvais);
    updateAdvCount();
  });
  // numeric inputs
  document.querySelectorAll('.adv-num').forEach(function(inp){
    inp.addEventListener('input', function(){
      const k = inp.dataset.fadv;
      const v = parseFloat(inp.value) || 0;
      if(k==='etageMin'){ fAdv.etageMin = inp.value===''?-1:v; }
      else if(k==='etageMax'){ fAdv.etageMax = inp.value===''?99:v; }
      else { fAdv[k] = v; }
      updateAdvCount();
    });
  });
  // apply / reset
  document.getElementById('adv-apply').addEventListener('click', function(){
    window.refresh && window.refresh();
    const wrap = document.getElementById('adv-panel-wrap');
    if(wrap) wrap.classList.remove('open');
    document.getElementById('fbtn-adv').classList.remove('on');
    if(typeof toast==='function') toast('✓ Filtres appliqués — '+window.filtered().length+' prospects');
  });
  document.getElementById('adv-reset').addEventListener('click', function(){
    resetAdvOnly();
    fAdv.preset=null;
    syncAdvUI();
    document.querySelectorAll('.preset-btn').forEach(function(b){b.classList.remove('on');});
    window.refresh && window.refresh();
    updateAdvCount();
  });
}

function syncAdvUI(){
  // numeric inputs
  document.querySelectorAll('.adv-num').forEach(function(inp){
    const k = inp.dataset.fadv;
    let v = fAdv[k];
    if(k==='etageMin' && v<0) v='';
    else if(k==='etageMax' && v>=99) v='';
    else if(!v) v='';
    inp.value = v;
  });
  // chips DPE/GES
  document.querySelectorAll('#adv-dpe .dpe-chip').forEach(function(c){
    c.classList.toggle('on', fAdv.dpe.has(c.dataset.dpe));
  });
  document.querySelectorAll('#adv-ges .dpe-chip').forEach(function(c){
    c.classList.toggle('on', fAdv.ges.has(c.dataset.ges));
  });
  document.querySelectorAll('#adv-chauf .chip-mini').forEach(function(c){
    c.classList.toggle('on', fAdv.chauf.has(c.dataset.chauf));
  });
  document.querySelectorAll('#adv-periode .chip-mini').forEach(function(c){
    c.classList.toggle('on', fAdv.periode.has(c.dataset.periode));
  });
  document.querySelectorAll('#adv-statut .chip-mini').forEach(function(c){
    c.classList.toggle('on', fAdv.statut.has(c.dataset.statut));
  });
  const t1=document.getElementById('adv-only-todo'); if(t1) t1.classList.toggle('on', fAdv.excluContacte);
  const t2=document.getElementById('adv-iso'); if(t2) t2.classList.toggle('on', fAdv.isolMauvaise);
  const t3=document.getElementById('adv-ete'); if(t3) t3.classList.toggle('on', fAdv.confortEteMauvais);
  updateAdvCount();
}

function updateAdvCount(){
  const el = document.getElementById('adv-count');
  if(!el) return;
  try {
    const n = window.filtered().length;
    el.textContent = n + ' prospect' + (n>1?'s':'');
    el.style.color = n>0 ? 'var(--ink)' : 'var(--accent)';
  } catch(e){ el.textContent='—'; }
}

/* ---------- Bootstrap ---------- */
function init(){
  if(!document.getElementById('srow')){
    return setTimeout(init, 100);
  }
  buildAdvUI();
  // initialiser le compteur après chargement données
  setTimeout(updateAdvCount, 500);
  setTimeout(updateAdvCount, 2000);
  // hook : recompter à chaque refresh
  const _origRefresh = window.refresh;
  if(_origRefresh){
    window.refresh = function(){
      const r = _origRefresh.apply(this, arguments);
      updateAdvCount();
      return r;
    };
  }
  // expose pour debug
  window._advReady = true;
}

if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
