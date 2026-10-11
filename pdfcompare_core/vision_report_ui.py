from __future__ import annotations

import json
from collections.abc import Sequence
from html import escape
from typing import Any

from .vision_review_ui import REVIEW_SCRIPT, INDEX_REVIEW_SCRIPT


_BASE_CSS = """
:root {
  --bg:#f8fafc;--surface:#fff;--surface2:#f1f5f9;--border:#e2e8f0;
  --border-strong:#cbd5e1;--text:#0f172a;--muted:#475569;--brand:#2563eb;
  --real:#dc2626;--real-soft:#fef2f2;--noise:#0284c7;--noise-soft:#e0f2fe;
  --uncertain:#ea580c;--uncertain-soft:#fff7ed;--shadow:0 8px 24px #0f172a1a;
  --split:50%;
}
*{box-sizing:border-box}*[hidden]{display:none!important}html,body{height:100%;margin:0}
body{font-family:Inter,"Segoe UI",system-ui,sans-serif;color:var(--text);background:var(--bg)}
button,input{font:inherit}.btn{min-height:32px;display:inline-flex;align-items:center;justify-content:center;
gap:8px;border:1px solid var(--border-strong);border-radius:6px;padding:7px 12px;background:var(--surface);
color:var(--text);font-weight:700;box-shadow:0 1px 2px #0f172a0f;cursor:pointer;text-decoration:none}
.btn:hover{background:var(--surface2);border-color:#94a3b8}.btn.primary{color:#fff;background:var(--brand);
border-color:var(--brand)}.btn.noise-toggle{color:#fff;background:var(--noise);border-color:var(--noise)}
.btn.noise-toggle:not(.active){color:#075985;background:#f0f9ff;border-color:#7dd3fc}.btn:disabled{opacity:.38;cursor:not-allowed}
.chip{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:999px;padding:5px 9px;
background:var(--surface2);font-size:12px;font-weight:800}.chip.real{color:#991b1b;background:#fee2e2}
.chip.noise{color:#075985;background:var(--noise-soft)}.chip.uncertain{color:#9a3412;background:var(--uncertain-soft)}
"""


_INDEX_CSS = _BASE_CSS + """
body{min-height:100%;padding-bottom:40px}.hero{padding:20px 28px 16px;border-bottom:1px solid var(--border);
background:var(--surface)}.hero-row{display:flex;align-items:center;gap:14px;max-width:1500px;margin:auto}
.hero-mark{display:grid;place-items:center;width:42px;height:42px;border-radius:10px;background:#0f172a;color:#fff;
font-weight:900}.hero h1{margin:0;font-size:22px}.hero p{margin:4px 0 0;color:var(--muted);font-size:13px}
.wrap{max-width:1500px;margin:auto;padding:18px 28px}
.documents{display:grid;grid-template-columns:minmax(0,1fr) 28px minmax(0,1fr);gap:10px;align-items:center}
.doc{display:flex;align-items:center;gap:12px;border:1px solid var(--border);border-left:4px solid var(--doc);border-radius:10px;
padding:12px 15px;background:var(--surface);box-shadow:0 1px 2px #0f172a0f;min-width:0}.doc.old{--doc:var(--real)}.doc.new{--doc:var(--brand)}
.doc-pill{flex:0 0 auto;border-radius:999px;padding:3px 9px;background:var(--doc);color:#fff;font-size:11px;font-weight:900;letter-spacing:.6px}
.doc-name{font-weight:700;overflow-wrap:anywhere}.doc-rev{color:var(--muted);font-size:12px}.doc-arrow{text-align:center;color:#94a3b8;font-size:18px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}
.kpi{border:1px solid var(--border);border-top:3px solid var(--accent,var(--border-strong));border-radius:10px;background:var(--surface);
padding:13px 15px;box-shadow:0 1px 2px #0f172a0f}.kpi.real{--accent:var(--real)}.kpi.uncertain{--accent:var(--uncertain)}.kpi.noise{--accent:var(--noise)}
.kpi span{display:block;color:var(--muted);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.4px}
.kpi strong{display:block;font-size:28px;line-height:1.15;margin-top:2px}.kpi small{color:var(--muted);font-size:12px}
.matrix-title{margin:22px 0 0;font-size:16px}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:10px 0}
.seg{display:inline-flex;gap:3px;padding:3px;border:1px solid var(--border);border-radius:9px;background:var(--surface)}
.seg button{border:0;border-radius:6px;padding:6px 11px;background:transparent;color:var(--muted);font-weight:700;cursor:pointer}
.seg button:hover{background:var(--surface2);color:var(--text)}.seg button.active{background:#334155;color:#fff}
.seg button b{margin-left:5px;font-variant-numeric:tabular-nums;opacity:.75}
.defaults{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:13px}.defaults small{color:var(--muted);font-size:12px}
.matrix{width:100%;border-collapse:separate;border-spacing:0;background:var(--surface);border:1px solid var(--border);
border-radius:10px;overflow:hidden}.matrix th,.matrix td{padding:11px 12px;border-bottom:1px solid var(--border);
text-align:left;vertical-align:top}.matrix th{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);background:var(--surface2)}
.matrix tr:last-child td{border-bottom:0}.matrix tbody tr{cursor:pointer}.matrix tbody tr:hover{background:#f8fafc}
.matrix td.mid{vertical-align:middle}.sheet-no{font-size:20px;font-weight:900}
.counts{display:flex;gap:5px;flex-wrap:wrap}.chip.zero{color:#94a3b8;background:transparent;border-color:var(--border)}
.hl{list-style:none;margin:0;padding:0;display:grid;gap:4px;max-width:520px;font-size:13px;line-height:1.35}
.hl li{position:relative;padding-left:14px}.hl li:before{content:"";position:absolute;left:0;top:.45em;width:7px;height:7px;border-radius:2px;background:var(--real)}
.hl li.uncertain:before{background:var(--uncertain)}.hl li.more,.hl li.none{color:var(--muted)}.hl li.more:before,.hl li.none:before{display:none}
.hl li.none{padding-left:0}
.preview{display:grid;grid-template-columns:1fr 1fr;gap:5px;width:250px}
.preview figure{margin:0;position:relative;border:1px solid var(--border);border-radius:6px;overflow:hidden;background:#e2e8f0}
.preview img{display:block;width:100%;height:58px;object-fit:contain;background:#fff}.preview figcaption{position:absolute;left:4px;
top:4px;padding:2px 5px;border-radius:4px;background:#0f172ad9;color:#fff;font-size:9px;font-weight:900}
.open{white-space:nowrap;color:var(--brand);font-weight:800;text-decoration:none}.open:hover{text-decoration:underline}
.empty{padding:22px;text-align:center;color:var(--muted)}.footnote{margin:14px 2px 0;color:var(--muted);font-size:12px;line-height:1.5}
@media(max-width:1100px){.preview{width:180px}}
@media(max-width:900px){.kpis{grid-template-columns:1fr 1fr}.wrap{padding:14px}.matrix{display:block;
overflow-x:auto}.documents{grid-template-columns:1fr}.doc-arrow{display:none}}@media(max-width:560px){.kpis{grid-template-columns:1fr}.hero{padding:16px}}
"""


_SHEET_CSS = _BASE_CSS + """
body{overflow:hidden}.app{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr) auto}.topbar{display:flex;
align-items:center;gap:8px;min-height:58px;padding:9px 14px;border-bottom:1px solid var(--border);background:var(--surface);z-index:20}
.brand{display:flex;align-items:center;gap:10px;min-width:0;margin-right:auto}.brand-mark{display:grid;place-items:center;
width:34px;height:34px;border-radius:8px;background:#0f172a;color:#fff;font-weight:900}.title{font-weight:850;white-space:nowrap}
.subtitle{color:var(--muted);font-size:12px;white-space:nowrap}.workspace{min-height:0;display:grid;
grid-template-columns:292px minmax(500px,1fr) 390px;gap:10px;padding:10px}.panel{min-height:0;border:1px solid var(--border);
border-radius:10px;background:var(--surface);overflow:hidden}.summary{display:grid;grid-template-rows:auto auto minmax(0,1fr)}
.panel-head{padding:14px 15px;border-bottom:1px solid var(--border)}.panel-head h2{font-size:15px;margin:0 0 5px}
.panel-head p{font-size:12px;color:var(--muted);margin:0;line-height:1.45}.summary-metrics{display:grid;grid-template-columns:repeat(3,1fr);
gap:6px;padding:10px 12px;border-bottom:1px solid var(--border)}.metric{padding:8px 6px;text-align:center;border-radius:8px;
background:var(--surface2)}.metric b{display:block;font-size:17px}.metric span{font-size:10px;color:var(--muted);text-transform:uppercase}
.filters{display:flex;gap:5px;padding:9px 10px;border-bottom:1px solid var(--border)}.filter{flex:1;border:1px solid var(--border);
border-radius:6px;padding:6px;background:#fff;font-size:11px;font-weight:700;cursor:pointer}.filter.active{color:#fff;background:#334155;
border-color:#334155}.zone-list{overflow:auto;padding:7px}.zone-row{width:100%;display:grid;grid-template-columns:28px minmax(0,1fr) auto;
gap:8px;align-items:center;border:1px solid transparent;border-radius:7px;padding:8px;text-align:left;background:transparent;cursor:pointer}
.zone-row:hover{background:var(--surface2)}.zone-row.active{border-color:var(--brand);background:#eff6ff}.zone-no{display:grid;
place-items:center;width:25px;height:25px;border-radius:6px;color:#fff;font-size:11px;font-weight:900}.real .zone-no,.big-no.real{background:var(--real)}
.noise .zone-no,.big-no.noise{background:var(--noise)}.uncertain .zone-no,.big-no.uncertain{background:var(--uncertain)}
.zone-label{overflow:hidden}.zone-label b{display:block;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.zone-label span{display:block;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap;color:var(--muted);font-size:10px}.confidence{font-size:10px;font-weight:800;color:var(--muted)}
.viewer{display:grid;grid-template-rows:auto minmax(0,1fr);position:relative}.toolbar{display:flex;align-items:center;gap:7px;
min-height:52px;padding:8px 10px;border-bottom:1px solid var(--border);background:var(--surface);flex-wrap:wrap}.zoom-label{min-width:58px;
text-align:center;font-size:12px;font-weight:800}.slider-help{flex:1;color:var(--muted);font-size:11px;text-align:center;white-space:nowrap}
.quality{color:#166534;background:#dcfce7;border-radius:999px;padding:5px 8px;font-size:11px;font-weight:800}.stage{min-height:0;
position:relative;overflow:auto;background-color:#dbe4ee;background-image:linear-gradient(45deg,#cbd5e1 25%,transparent 25%),
linear-gradient(-45deg,#cbd5e1 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#cbd5e1 75%),
linear-gradient(-45deg,transparent 75%,#cbd5e1 75%);background-size:20px 20px;background-position:0 0,0 10px,10px -10px,-10px 0}
.surface{position:relative;margin:24px;box-shadow:var(--shadow);background:#fff;transform-origin:top left;cursor:col-resize}
.stage.panning,.stage.panning .surface{cursor:grabbing;user-select:none}.sheet{position:absolute;inset:0;width:100%;height:100%;
display:block;user-select:none;-webkit-user-drag:none}.sheet.old{z-index:2;clip-path:inset(0 calc(100% - var(--split)) 0 0)}.sheet.new{z-index:1}
.split-line{position:absolute;left:var(--split);top:0;bottom:0;width:2px;transform:translateX(-1px);background:var(--brand);z-index:6;
pointer-events:none}.split-knob{position:absolute;left:var(--split);top:18px;z-index:7;transform:translateX(-50%);padding:4px 7px;
border-radius:999px;background:var(--brand);color:#fff;font-size:10px;font-weight:800;pointer-events:none}.corner-label{position:absolute;
z-index:5;top:8px;padding:4px 7px;border-radius:6px;color:#fff;font-size:10px;font-weight:900}.corner-label.old{left:8px;background:var(--real)}
.corner-label.new{right:8px;background:var(--brand)}.zones-layer{position:absolute;inset:0;z-index:4;pointer-events:none}.zone-box{position:absolute;
border:2px solid;border-radius:3px;opacity:.6}.zone-box.real{border-color:#ef4444}.zone-box.noise{border-color:var(--noise);border-style:dashed}
.zone-box.uncertain{border-color:var(--uncertain);border-style:dotted}.zone-box.selected{opacity:1;border-width:4px;box-shadow:0 0 0 2px #fff,
0 0 0 5px #0f172ac7}.zone-tag{position:absolute;left:-2px;top:-25px;min-width:24px;height:22px;display:grid;place-items:center;
border-radius:6px 6px 6px 0;background:#111827;color:#fff;font-size:11px;font-weight:900}.zone-box.near-top .zone-tag{top:0;left:0}
.shape-layer{position:absolute;inset:0;width:100%;height:100%;overflow:visible}.object-shape{fill:#ef44441c;stroke:var(--real);stroke-width:2}.object-shape polygon{vector-effect:non-scaling-stroke}.object-shape.noise{stroke:var(--noise);fill:#0284c70a;stroke-dasharray:6 4}.object-shape.uncertain{stroke:var(--uncertain);fill:#ea580c15;stroke-dasharray:5 3}.object-shape.selected{stroke-width:4;fill:#ef444430}.object-shape.selected.uncertain{fill:#ea580c25}.zone-box.has-shape,.zone-box.has-shape.selected{border:0;box-shadow:none}.zone-box.object-bound:not(.has-shape){border-radius:24px;border-style:dashed}
.inspector{display:flex;flex-direction:column;overflow:hidden}.zone-header{flex:0 0 auto;padding:12px 15px;border-bottom:1px solid var(--border)}
.zone-heading{display:flex;align-items:center;gap:9px}.big-no{display:grid;place-items:center;width:34px;height:34px;border-radius:8px;
color:#fff;font-weight:900}.zone-header h2{margin:0;font-size:16px}.class-badge{display:inline-flex;border-radius:999px;padding:4px 8px;
font-size:10px;font-weight:900;text-transform:uppercase}.class-badge.real{color:#991b1b;background:#fee2e2}.class-badge.noise{color:#075985;
background:var(--noise-soft)}.class-badge.uncertain{color:#9a3412;background:var(--uncertain-soft)}.structured{flex:1 1 auto;min-height:150px;
overflow:auto;padding:14px 15px;border-bottom:1px solid var(--border);font-size:13px;line-height:1.55}.structured h3{margin:0 0 7px;font-size:13px}
.structured .lead{margin:0 0 13px;font-weight:750}.structured ul{margin:0 0 14px;padding-left:19px}.structured li{margin:0 0 6px}
.structured strong{color:#0f172a;background:#fef3c7;border-radius:3px;padding:0 2px}.facts{display:grid;grid-template-columns:repeat(2,1fr);gap:6px}
.delta{display:grid;gap:6px;margin:0 0 14px}.delta-row{display:grid;grid-template-columns:44px minmax(0,1fr);gap:8px;align-items:start;border-radius:7px;padding:7px 9px;background:var(--surface2)}.delta-row span{justify-self:start;border-radius:4px;padding:1px 6px;color:#fff;font-size:10px;font-weight:900}.delta-row.old span{background:var(--real)}.delta-row.new span{background:var(--brand)}.delta-row p{margin:0;overflow-wrap:anywhere}.delta-impact{border-left:3px solid var(--border-strong);padding:2px 0 2px 10px}.delta-impact b{font-size:12px}.delta-impact p{margin:2px 0 0;color:var(--muted)}.fact{padding:7px 8px;border-radius:7px;background:var(--surface2);font-size:10px;color:var(--muted)}.fact b{display:block;color:var(--text);
font-size:12px;margin-top:2px}.detail{flex:0 0 228px;min-height:0;padding:13px 15px;border-bottom:1px solid var(--border);overflow:hidden}
.detail-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.detail-title b{font-size:13px}.detail-slider{position:relative;
overflow:hidden;aspect-ratio:1.8;border:1px solid var(--border);border-radius:8px;background:#e2e8f0}.detail-slider img{position:absolute;inset:0;
width:100%;height:100%;object-fit:contain;background:#fff}.detail-slider .detail-old{z-index:2;clip-path:inset(0 50% 0 0)}.detail-line{position:absolute;
left:50%;top:0;bottom:0;width:2px;background:var(--brand);z-index:3}.detail-range{width:100%;margin-top:8px;accent-color:var(--brand)}
.detail-empty{display:grid;place-items:center;min-height:130px;padding:18px;text-align:center;border:1px dashed var(--border-strong);border-radius:8px;
color:var(--muted);font-size:12px}.zone-nav{flex:0 0 auto;display:grid;grid-template-columns:44px minmax(0,1fr) 44px;gap:7px;padding:12px 15px}
.sheet-pager{display:flex;align-items:center;justify-content:center;gap:7px;padding:8px 14px;border-top:1px solid var(--border);background:var(--surface)}
.page-count{min-width:110px;text-align:center;font-size:12px;font-weight:800}.hint{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);
z-index:10;border-radius:999px;padding:6px 11px;background:#0f172adb;color:#fff;font-size:10px;pointer-events:none;white-space:nowrap}.toast{position:fixed;
right:18px;top:70px;z-index:99;border-radius:8px;padding:10px 13px;background:#0f172a;color:#fff;box-shadow:var(--shadow);font-size:12px;
opacity:0;transform:translateY(-8px);transition:.18s;pointer-events:none}.toast.show{opacity:1;transform:none}
.verdict{display:grid;gap:6px;margin-top:11px}.verdict-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.verdict-label{color:var(--muted);font-size:11px;font-weight:800;letter-spacing:.4px;text-transform:uppercase}
.verdict-seg{display:grid;grid-template-columns:repeat(3,1fr);gap:3px;padding:3px;border:1px solid var(--border);border-radius:9px;background:var(--surface2)}
.verdict-seg button{display:flex;align-items:center;justify-content:center;gap:6px;min-height:32px;border:0;border-radius:6px;padding:0 6px;
background:transparent;color:var(--muted);font-size:12px;font-weight:800;cursor:pointer}.verdict-seg button:hover:not(:disabled){background:var(--surface);color:var(--text)}
.verdict-seg button i{width:9px;height:9px;border-radius:3px}.verdict-seg .v-real i{background:var(--real)}.verdict-seg .v-uncertain i{background:var(--uncertain)}
.verdict-seg .v-noise i{background:var(--noise)}.verdict-seg button.active{color:#fff}.verdict-seg button.active i{background:#fff}
.verdict-seg .v-real.active{background:var(--real)}.verdict-seg .v-uncertain.active{background:var(--uncertain)}.verdict-seg .v-noise.active{background:var(--noise)}
.verdict-seg button:disabled{opacity:.4;cursor:not-allowed}.verdict-note{margin:0;color:var(--muted);font-size:11px;line-height:1.4}.verdict-note b{color:var(--text)}
.verdict-note small{opacity:.8}.link-btn{border:0;padding:0;background:none;color:var(--brand);font-size:11px;font-weight:800;cursor:pointer}
.link-btn:hover{text-decoration:underline}.zone-row .meta{display:flex;align-items:center;gap:4px}.manual-mark{color:var(--brand);font-size:11px;font-weight:900}
.shape-tools{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 15px 0}
.btn.editing{color:#fff;background:var(--brand);border-color:var(--brand)}.edit-hint{flex:1;color:var(--brand);font-size:11px;font-weight:700;text-align:center}
.surface.editing{cursor:default}.edit-layer *{pointer-events:all}.edit-body{fill:#2563eb1a;stroke:var(--brand);stroke-width:2;vector-effect:non-scaling-stroke;cursor:move}
.edit-vertex{fill:#fff;stroke:var(--brand);stroke-width:2;vector-effect:non-scaling-stroke;cursor:grab}.edit-vertex:hover{fill:#bfdbfe}
.object-shape.is-editing,.zone-box.is-editing{visibility:hidden}.zone-box.is-editing .zone-tag{visibility:visible}
.detail-slider canvas{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#fff}
.sheet-switcher{position:relative}.nav-pos{color:var(--muted);font-weight:700}.sheet-nav{position:absolute;top:42px;left:0;z-index:60;
width:min(660px,calc(100vw - 24px));height:min(460px,72vh);display:grid;grid-template-columns:minmax(0,1fr) 230px;overflow:hidden;
border:1px solid var(--border-strong);border-radius:12px;background:var(--surface);box-shadow:0 20px 50px #0f172a33}
.sheet-nav-list{overflow:auto;padding:6px;border-right:1px solid var(--border)}.sheet-nav-item{display:grid;grid-template-columns:42px minmax(0,1fr);
gap:8px;align-items:center;border-radius:8px;padding:7px 8px;color:var(--text);text-decoration:none}.sheet-nav-item:hover,.sheet-nav-item:focus-visible{
background:var(--surface2);outline:0}.sheet-nav-item.current{background:#eff6ff;box-shadow:inset 0 0 0 1px var(--brand)}.sheet-nav-no{font-size:18px;
font-weight:900;text-align:center}.sheet-nav-item .counts{display:flex;gap:3px;flex-wrap:wrap}.sheet-nav-item .chip{padding:2px 7px;font-size:10px}
.sheet-nav-item .chip.zero{color:#94a3b8;background:transparent}.sheet-nav-labels{margin-top:3px;overflow:hidden;color:var(--muted);font-size:11px;
text-overflow:ellipsis;white-space:nowrap}.sheet-nav-preview{display:grid;grid-template-rows:auto minmax(0,1fr) minmax(0,1fr);gap:6px;padding:10px;
background:var(--surface2)}.sheet-nav-preview b{font-size:12px}.sheet-nav-preview figure{position:relative;margin:0;overflow:hidden;border:1px solid var(--border);
border-radius:6px;background:#fff}.sheet-nav-preview img{display:block;width:100%;height:100%;object-fit:contain}.sheet-nav-preview figcaption{position:absolute;
left:5px;top:5px;padding:2px 6px;border-radius:4px;background:#0f172ad9;color:#fff;font-size:9px;font-weight:900}
@media(max-width:1200px){.workspace{grid-template-columns:245px minmax(440px,1fr) 340px}.subtitle{display:none}}
@media(max-width:900px){body{overflow:auto}.app{height:auto;min-height:100%}.workspace{display:flex;flex-direction:column}.summary{max-height:380px}
.viewer{height:68vh;min-height:520px}.inspector{overflow:visible}.topbar{position:sticky;top:0;flex-wrap:wrap}.sheet-pager{position:sticky;bottom:0}.slider-help{display:none}
.sheet-nav{position:fixed;top:64px;right:10px;left:10px;width:auto;grid-template-columns:1fr}.sheet-nav-preview{display:none}}
"""


# Reader's decisions, hand-corrected outlines and the sheet switcher. Function declarations only at the
# top level: the main sheet script calls them while it starts, before this block's statements run.
_SHEET_TOOLS_SCRIPT = r"""
function toastMsg(text){const t=document.getElementById('toast');t.textContent=text;t.classList.add('show');clearTimeout(toastMsg.timer);
toastMsg.timer=setTimeout(()=>t.classList.remove('show'),2600)}
function manualMarks(z){return(z.manual_classification?`<span class="manual-mark" title="Решение изменено вами; AI: ${esc(kindLabel({classification:z.ai_classification}))}">✎</span>`:'')+
(z.manual_shape?'<span class="manual-mark" title="Контур поправлен вручную">◇</span>':'')}
function updateVerdict(z){document.querySelectorAll('[data-verdict]').forEach(b=>{b.disabled=!z;b.classList.toggle('active',!!z&&b.dataset.verdict===z.classification)});
const note=document.getElementById('aiVerdict');document.getElementById('resetVerdict').hidden=!z||!z.manual_classification;
note.innerHTML=!z?'':z.manual_classification?`Изменено вами · AI: <b>${esc(kindLabel({classification:z.ai_classification}))}</b>.`:'Совпадает с выводом AI.'}
function setVerdict(value){const z=report.zones[selectedIndex];if(!z||document.querySelector('[data-verdict]').disabled)return;const key=reviewZoneKey(report,z);
if(!value||value===z.ai_classification)delete reviewState.overrides[key];else reviewState.overrides[key]=value;pinnedIndex=selectedIndex;
updateReviewCounts([report]);saveReview();selectZone(selectedIndex,false);
if(!((showNoise||kind(z)!=='noise')&&(activeFilter==='all'||z.classification===activeFilter)))
toastMsg(`Зона ${z.id}: ${kindLabel(z).toLowerCase()}. Текущий фильтр её скрывает — она останется в списке, пока выбрана.`)}
function rectPolys(r){return r?[[[r.x,r.y],[r.x+r.w,r.y],[r.x+r.w,r.y+r.h],[r.x,r.y+r.h]]]:[]}
function aiPolys(z){return z.ai_polygons&&z.ai_polygons.length?z.ai_polygons:rectPolys(z.ai_rect)}
function zonePolys(z){return(z.polygons_px&&z.polygons_px.length?z.polygons_px:rectPolys(z.rect)).map(p=>p.map(q=>[q[0],q[1]]))}
function roundPolys(polys){return polys.map(p=>p.map(q=>[Math.round(Math.max(0,Math.min(W,q[0]))),Math.round(Math.max(0,Math.min(H,q[1])))]))}
function boundsOf(polys){const pts=polys.flat(),xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),x=Math.min(...xs),y=Math.min(...ys);
return[x,y,Math.max(1,Math.max(...xs)-x),Math.max(1,Math.max(...ys)-y)]}
function commitShape(z,polys){const key=reviewZoneKey(report,z),rounded=roundPolys(polys);reviewState.shapes=reviewState.shapes||{};
if(JSON.stringify(rounded)===JSON.stringify(roundPolys(aiPolys(z))))delete reviewState.shapes[key];
else reviewState.shapes[key]={rect:boundsOf(rounded),polygons:rounded};applyReviews(report);saveReview();selectZone(selectedIndex,false)}
function resetShape(){const z=report.zones[selectedIndex];if(!z)return;if(reviewState.shapes)delete reviewState.shapes[reviewZoneKey(report,z)];
editHistory=[];applyReviews(report);saveReview();selectZone(selectedIndex,false);toastMsg('Контур возвращён к варианту AI')}
function showShapeState(z){document.getElementById('editShape').disabled=!z||!z.rect;document.getElementById('resetShape').hidden=!z||!z.manual_shape}
function stopEditing(){editing=false;editDrag=null;editHistory=[];surface.classList.remove('editing');const b=document.getElementById('editShape');
b.classList.remove('editing');b.textContent='✎ Править контур';document.getElementById('editHint').hidden=true;document.getElementById('sliderHelp').hidden=false}
function setEditing(on){const z=report.zones[selectedIndex];if(!on){stopEditing();renderBoxes();return}
if(!z||!z.rect||document.getElementById('editShape').disabled)return;editing=true;editHistory=[];surface.classList.add('editing');
const b=document.getElementById('editShape');b.classList.add('editing');b.textContent='✓ Готово';document.getElementById('editHint').hidden=false;
document.getElementById('sliderHelp').hidden=true;renderBoxes()}
function renderEdit(svg){if(!editing)return;const z=report.zones[selectedIndex];if(!z||!z.rect)return;const ns=svg.namespaceURI,g=document.createElementNS(ns,'g'),
radius=Math.max(3,7/scale),polys=zonePolys(z);g.setAttribute('class','edit-layer');polys.forEach((poly,pi)=>{const body=document.createElementNS(ns,'polygon');
body.setAttribute('class','edit-body');body.setAttribute('points',poly.map(p=>p.join(',')).join(' '));body.dataset.poly=pi;g.appendChild(body)});
polys.forEach((poly,pi)=>poly.forEach((p,vi)=>{const c=document.createElementNS(ns,'circle');c.setAttribute('class','edit-vertex');c.setAttribute('cx',p[0]);
c.setAttribute('cy',p[1]);c.setAttribute('r',radius);c.dataset.poly=pi;c.dataset.vertex=vi;g.appendChild(c)}));svg.appendChild(g)}
function drawDraft(polys){const g=zonesLayer.querySelector('.edit-layer');if(!g)return;g.querySelectorAll('.edit-body').forEach(b=>{const p=polys[+b.dataset.poly];
if(p)b.setAttribute('points',p.map(q=>q.join(',')).join(' '))});g.querySelectorAll('.edit-vertex').forEach(c=>{const q=(polys[+c.dataset.poly]||[])[+c.dataset.vertex];
if(q){c.setAttribute('cx',q[0]);c.setAttribute('cy',q[1])}})}
function sheetPoint(e){const r=surface.getBoundingClientRect();return[(e.clientX-r.left)/r.width*W,(e.clientY-r.top)/r.height*H]}
function drawDetail(z){const manual=!!(z&&z.manual_shape&&z.rect);['Old','New'].forEach(role=>{const img=document.getElementById('detail'+role),
canvas=document.getElementById('detail'+role+'Canvas');img.hidden=manual;canvas.hidden=!manual;if(!manual)return;
const source=document.querySelector('.sheet.'+role.toLowerCase()),r=z.rect,pad=Math.max(40,Math.round(Math.max(r.w,r.h)*.12)),sx=Math.max(0,r.x-pad),
sy=Math.max(0,r.y-pad),sw=Math.max(1,Math.min(W,r.x+r.w+pad)-sx),sh=Math.max(1,Math.min(H,r.y+r.h+pad)-sy),k=Math.min(1,1000/Math.max(sw,sh));
canvas.width=Math.max(1,Math.round(sw*k));canvas.height=Math.max(1,Math.round(sh*k));const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';
ctx.fillRect(0,0,canvas.width,canvas.height);const draw=()=>{const fx=source.naturalWidth/W,fy=source.naturalHeight/H;
try{ctx.drawImage(source,sx*fx,sy*fy,sw*fx,sh*fy,0,0,canvas.width,canvas.height)}catch(err){}};
if(source.complete&&source.naturalWidth)draw();else source.addEventListener('load',draw,{once:true})})}
function shortcut(e){const key=String(e.key||'').toLowerCase();if((e.ctrlKey||e.metaKey)&&editing&&(key==='z'||key==='я')){e.preventDefault();
const previous=editHistory.pop();if(previous)commitShape(report.zones[selectedIndex],previous);return}if(e.ctrlKey||e.metaKey||e.altKey)return;
if(key==='escape'){if(!document.getElementById('sheetNav').hidden)toggleSheetNav(false);else if(editing)setEditing(false);return}
if(key==='1')setVerdict('real_change');else if(key==='2')setVerdict('uncertain');else if(key==='3')setVerdict('alignment_or_rendering_noise');
else if(key==='e'||key==='у')setEditing(!editing)}
function sheetIndexData(){if(!sheetIndexData.cache)sheetIndexData.cache=JSON.parse(document.getElementById('sheetIndex').textContent);return sheetIndexData.cache}
function sheetDir(seq){return seq===report.seq?'':`../sheet_${String(seq).padStart(3,'0')}/`}
function renderSheetNav(){const list=document.getElementById('sheetNavList'),summary=reviewState.summary||{};list.innerHTML=sheetIndexData().map(s=>{
const current=s.seq===report.seq,c=current?report.counts:summary[s.seq]||s.counts,labels=(s.labels||[]).join(' · ');
const chips=c?[['real_change','real','правок'],['uncertain','uncertain','проверить']].map(([k,css,w])=>`<span class="chip ${css}${c[k]?'':' zero'}">${c[k]||0} ${w}</span>`).join(''):'';
return `<a class="sheet-nav-item${current?' current':''}" data-seq="${s.seq}" href="${sheetDir(s.seq)}comparison.html"${current?' aria-current="page"':''}>`+
`<span class="sheet-nav-no">${s.seq}</span><span><span class="counts">${chips}</span>${labels?`<div class="sheet-nav-labels" title="${esc(labels)}">${esc(labels)}</div>`:''}</span></a>`}).join('');
list.querySelectorAll('.sheet-nav-item').forEach(a=>{a.onmouseenter=a.onfocus=()=>previewSheet(+a.dataset.seq);
if(a.classList.contains('current'))a.onclick=e=>{e.preventDefault();toggleSheetNav(false)}});reviewLinks()}
function previewSheet(seq){const dir=sheetDir(seq),hide="this.closest('figure').hidden=true";document.getElementById('sheetNavPreview').innerHTML=`<b>Лист ${seq}</b>`+
`<figure><img src="${dir}old_thumb.png" alt="OLD, лист ${seq}" onerror="${hide}"><figcaption>OLD</figcaption></figure>`+
`<figure><img src="${dir}new_thumb.png" alt="NEW, лист ${seq}" onerror="${hide}"><figcaption>NEW</figcaption></figure>`}
function toggleSheetNav(open){const nav=document.getElementById('sheetNav'),button=document.getElementById('sheetNavBtn');if(open===undefined)open=nav.hidden;
nav.hidden=!open;button.setAttribute('aria-expanded',String(open));if(!open)return;renderSheetNav();previewSheet(report.seq);
const current=nav.querySelector('.current');if(current){current.scrollIntoView({block:'nearest'});current.focus({preventScroll:true})}}
zonesLayer.addEventListener('pointerdown',e=>{if(!editing||e.button!==0||!e.target.closest||!e.target.closest('.edit-layer'))return;
e.preventDefault();e.stopPropagation();const z=report.zones[selectedIndex],polys=zonePolys(z),start=sheetPoint(e),t=e.target;
if(t.classList.contains('edit-vertex')){const pi=+t.dataset.poly,vi=+t.dataset.vertex;if(e.altKey){if(polys[pi].length>3){editHistory.push(zonePolys(z));
polys[pi].splice(vi,1);commitShape(z,polys)}else toastMsg('В контуре должно остаться не меньше трёх вершин');return}
editDrag={type:'vertex',pi,vi,polys,start,before:zonePolys(z)}}else editDrag={type:'move',orig:polys,polys,start,before:zonePolys(z)}},true);
zonesLayer.addEventListener('dblclick',e=>{if(!editing||!e.target.classList||!e.target.classList.contains('edit-body'))return;e.preventDefault();e.stopPropagation();
const z=report.zones[selectedIndex],polys=zonePolys(z),poly=polys[+e.target.dataset.poly],p=sheetPoint(e);let best=0,bestDistance=Infinity,bestPoint=p;
poly.forEach((a,k)=>{const b=poly[(k+1)%poly.length],vx=b[0]-a[0],vy=b[1]-a[1],t=Math.max(0,Math.min(1,((p[0]-a[0])*vx+(p[1]-a[1])*vy)/((vx*vx+vy*vy)||1))),
q=[a[0]+t*vx,a[1]+t*vy],d=(q[0]-p[0])**2+(q[1]-p[1])**2;if(d<bestDistance){bestDistance=d;best=k;bestPoint=q}});
editHistory.push(zonePolys(z));poly.splice(best+1,0,bestPoint);commitShape(z,polys)},true);
window.addEventListener('pointermove',e=>{const d=editDrag;if(!d)return;const p=sheetPoint(e);if(d.type==='vertex')d.polys[d.pi][d.vi]=[Math.max(0,Math.min(W,p[0])),
Math.max(0,Math.min(H,p[1]))];else{const pts=d.orig.flat(),xs=pts.map(q=>q[0]),ys=pts.map(q=>q[1]),dx=Math.max(-Math.min(...xs),Math.min(W-Math.max(...xs),p[0]-d.start[0])),
dy=Math.max(-Math.min(...ys),Math.min(H-Math.max(...ys),p[1]-d.start[1]));d.polys=d.orig.map(poly=>poly.map(q=>[q[0]+dx,q[1]+dy]))}
d.moved=d.moved||Math.hypot(p[0]-d.start[0],p[1]-d.start[1])*scale>2;drawDraft(d.polys)});
window.addEventListener('pointerup',()=>{const d=editDrag;if(!d)return;editDrag=null;if(!d.moved){drawDraft(d.before);return}editHistory.push(d.before);
commitShape(report.zones[selectedIndex],d.polys)});
document.querySelectorAll('[data-verdict]').forEach(b=>b.onclick=()=>setVerdict(b.dataset.verdict));
document.getElementById('resetVerdict').onclick=()=>setVerdict(null);document.getElementById('editShape').onclick=()=>setEditing(!editing);
document.getElementById('resetShape').onclick=resetShape;document.getElementById('sheetNavBtn').onclick=e=>{e.stopPropagation();toggleSheetNav()};
document.addEventListener('pointerdown',e=>{if(!document.getElementById('sheetNav').hidden&&!e.target.closest('#sheetSwitcher'))toggleSheetNav(false)});
"""


_SHEET_SCRIPT = r"""
const report=JSON.parse(document.getElementById('reportData').textContent),W=report.size_px[0],H=report.size_px[1];
const stage=document.getElementById('stage'),surface=document.getElementById('surface'),zoneList=document.getElementById('zoneList');
const zonesLayer=document.getElementById('zonesLayer'),splitKnob=document.getElementById('splitKnob');
""" + REVIEW_SCRIPT + r"""
applyReviews(report);updateReviewCounts([report]);
let scale=.1,selectedIndex=0,activeFilter=reviewState.onlyChanges?'real_change':'all',showNoise=report.report_schema!=='semantic-v1'&&!reviewState.onlyChanges,spaceDown=false,panning=false,splitDragging=false,panStart=null;
// A zone the reader just re-classified stays listed while selected, even if the active filter now hides it.
let pinnedIndex=-1,editing=false,editDrag=null,editHistory=[];
const kind=z=>z.classification==='real_change'?'real':z.classification==='uncertain'?'uncertain':'noise';
const kindLabel=z=>kind(z)==='real'?'Реальное изменение':kind(z)==='uncertain'?'Требует проверки':'Шум / локальный сдвиг';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const emphasize=s=>esc(s).replace(/\b(OLD|NEW)\b|→|->|удален[а-яё]*|добавлен[а-яё]*|заменен[а-яё]*|изменен[а-яё]*/gi,'<strong>$&</strong>');
function structure(z){let text=z.description.replace(/\*\*/g,'').trim(),title=`Зона ${z.id}`,body=text;const colon=text.indexOf(':');
if(colon>0&&colon<115){title=text.slice(0,colon).trim().replace(/[«»]/g,'').replace(/\s*OLD\s*(?:->|→)\s*NEW\s*$/i,'');
body=text.slice(colon+1).trim()}let facts=body.split(/;\s*/).map(x=>x.trim()).filter(Boolean);if(facts.length===1&&body.length>180)
facts=body.split(/\.\s+(?=[А-ЯA-Z«])/).map(x=>x.trim()).filter(Boolean);if(hasDelta(z))facts=facts.filter((x,n)=>n===0||!/^(OLD|NEW|Следствие|Последствие)\s*:/i.test(x));return{title,facts:facts.length?facts:[body]}}
const hasDelta=z=>!!(String(z.old_value||'').trim()||String(z.new_value||'').trim());
function zoneLabel(z){const ref=String(z.object_ref||'').trim();return ref||structure(z).title}
function visibleZones(){return report.zones.map((z,i)=>({z,i})).filter(({z,i})=>i===pinnedIndex||((showNoise||kind(z)!=='noise')&&
(activeFilter==='all'||z.classification===activeFilter)))}function ensureSelection(){const v=visibleZones();if(!v.some(x=>x.i===selectedIndex)&&v.length)selectedIndex=v[0].i}
function renderList(){ensureSelection();zoneList.innerHTML='';visibleZones().forEach(({z,i})=>{const b=document.createElement('button');
b.className=`zone-row ${kind(z)} ${i===selectedIndex?'active':''}`;b.innerHTML=`<span class="zone-no">${z.id}</span><span class="zone-label">
<b>${esc(zoneLabel(z))}</b><span>${esc(structure(z).facts[0].slice(0,96))}${structure(z).facts[0].length>96?'…':''}</span></span><span class="meta">${manualMarks(z)}<span class="confidence">${z.confidence}%</span></span>`;
b.onclick=()=>selectZone(i,true);zoneList.appendChild(b)});if(!zoneList.children.length)zoneList.innerHTML='<div class="detail-empty">В этом фильтре зон нет.</div>'}
function renderBoxes(){zonesLayer.innerHTML='';const visible=new Set(visibleZones().map(v=>v.i));const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.setAttribute('class','shape-layer');zonesLayer.appendChild(svg);report.zones.forEach((z,i)=>{if(!z.rect||!visible.has(i))return;const r=z.rect,b=document.createElement('div');
const shapes=z.polygons_px||[],edited=editing&&i===selectedIndex?'is-editing':'';if(shapes.length){const group=document.createElementNS(ns,'g');group.setAttribute('class',`object-shape ${kind(z)} ${i===selectedIndex?'selected':''} ${edited}`);shapes.forEach(points=>{const poly=document.createElementNS(ns,'polygon');poly.setAttribute('points',points.map(p=>p.join(',')).join(' '));group.appendChild(poly)});svg.appendChild(group)}
b.className=`zone-box ${shapes.length?'has-shape':''} ${report.report_schema==='semantic-v1'?'object-bound':''} ${kind(z)} ${i===selectedIndex?'selected':''} ${edited} ${r.y<120?'near-top':''}`;b.style.cssText=`left:${r.x/W*100}%;top:${r.y/H*100}%;
width:${r.w/W*100}%;height:${r.h/H*100}%`;b.innerHTML=`<span class="zone-tag">${z.id}</span>`;zonesLayer.appendChild(b)});renderEdit(svg)}
function updateNoiseLabel(){const b=document.getElementById('noiseToggle');b.classList.toggle('active',showNoise);b.textContent=showNoise?`Скрыть шум (${report.counts.alignment_or_rendering_noise})`:`Показать оформление/шум (${report.counts.alignment_or_rendering_noise})`}
function selectZone(i,focus=false){updateNoiseLabel();if(i!==pinnedIndex)pinnedIndex=-1;if(editing&&i!==selectedIndex)stopEditing();if(!report.zones.length||!visibleZones().length){const hasChanges=report.zones.some(z=>z.classification==='real_change'||z.classification==='uncertain');document.getElementById('zoneTitle').textContent=hasChanges?'В этом фильтре зон нет':'Содержательных правок не выявлено';document.getElementById('observationTitle').textContent='Результат просмотра';document.getElementById('observationLead').textContent=hasChanges?'Выберите другой фильтр для просмотра наблюдений.':'В прочитанных фрагментах AI не выявил содержательных изменений. Техническое покрытие отдельно указано в отчёте.';document.getElementById('changesSection').hidden=true;document.getElementById('deltaBlock').hidden=true;document.getElementById('observationTitle').hidden=false;document.getElementById('classBadge').hidden=true;document.getElementById('detailSlider').hidden=true;document.getElementById('detailRange').hidden=true;document.getElementById('detailEmpty').hidden=false;document.getElementById('detailEmpty').textContent='Выберите наблюдение в другом фильтре.';document.getElementById('focusZone').disabled=true;document.getElementById('bigNo').textContent='—';document.getElementById('confidence').textContent='—';document.getElementById('rect').textContent='—';updateVerdict(null);showShapeState(null);renderBoxes();return}const visible=visibleZones();selectedIndex=visible.some(v=>v.i===i)?i:visible[0].i;const z=report.zones[selectedIndex],r=z.rect,k=kind(z),s=structure(z);
updateVerdict(z);showShapeState(z);
document.getElementById('bigNo').textContent=z.id;document.getElementById('bigNo').className=`big-no ${k}`;document.getElementById('zoneTitle').textContent=zoneLabel(z);
const badge=document.getElementById('classBadge');badge.hidden=false;badge.textContent=kindLabel(z);badge.className=`class-badge ${k}`;document.getElementById('observationTitle').textContent=s.title;document.getElementById('observationTitle').hidden=s.title===zoneLabel(z);const delta=document.getElementById('deltaBlock');delta.hidden=!hasDelta(z);document.getElementById('deltaOld').textContent=String(z.old_value||'').trim()||'—';document.getElementById('deltaNew').textContent=String(z.new_value||'').trim()||'—';const impact=String(z.design_impact||'').trim();document.getElementById('deltaImpact').hidden=!impact;document.getElementById('deltaImpactText').textContent=impact;
document.getElementById('observationLead').innerHTML=emphasize(s.facts[0]);const changes=document.getElementById('changesSection');changes.hidden=s.facts.length<2;
document.getElementById('observationFacts').innerHTML=s.facts.slice(1).map(x=>`<li>${emphasize(x)}</li>`).join('');document.getElementById('confidence').textContent=`${z.confidence}%`;
document.getElementById('rect').textContent=r?`${r.x}, ${r.y} · ${r.w}×${r.h}${z.manual_shape?' · вручную':''}`:'весь лист';const slider=document.getElementById('detailSlider'),range=document.getElementById('detailRange');
const empty=document.getElementById('detailEmpty'),focusBtn=document.getElementById('focusZone');slider.hidden=!r;range.hidden=!r;empty.hidden=!!r;empty.textContent='Вывод относится ко всему листу; локальная область не задана.';focusBtn.disabled=!r;
if(r&&z.images){document.getElementById('detailOld').src=z.images.old||'';document.getElementById('detailNew').src=z.images.new||''}drawDetail(z);renderList();renderBoxes();if(focus&&r)requestAnimationFrame(focusSelected)}
function setScale(n,a){n=Math.max(.025,Math.min(2.5,n));const old=scale,ax=a?.x??(stage.scrollLeft+stage.clientWidth/2)/old,ay=a?.y??(stage.scrollTop+stage.clientHeight/2)/old;
scale=n;surface.style.width=`${W*scale}px`;surface.style.height=`${H*scale}px`;document.getElementById('zoomLabel').textContent=`${Math.round(scale*100)}%`;if(editing)renderBoxes();
requestAnimationFrame(()=>{stage.scrollLeft=ax*scale-(a?.clientX??stage.clientWidth/2);stage.scrollTop=ay*scale-(a?.clientY??stage.clientHeight/2)})}
function fit(){const p=52;setScale(Math.min((stage.clientWidth-p)/W,(stage.clientHeight-p)/H));requestAnimationFrame(()=>{stage.scrollLeft=0;stage.scrollTop=0})}
function focusSelected(){const r=report.zones[selectedIndex]?.rect;if(!r)return;const p=Math.max(100,Math.min(350,Math.max(r.w,r.h)*.18));
const target=Math.min((stage.clientWidth*.76)/(r.w+p*2),(stage.clientHeight*.76)/(r.h+p*2),1.35);setScale(Math.max(target,.08),{x:r.x+r.w/2,y:r.y+r.h/2,
clientX:stage.clientWidth/2,clientY:stage.clientHeight/2})}function setSplit(v){v=Math.max(0,Math.min(100,v));surface.style.setProperty('--split',`${v}%`);splitKnob.textContent=`${Math.round(v)}%`}
function splitAt(e){const r=surface.getBoundingClientRect();setSplit((e.clientX-r.left)/r.width*100)}function toggleNoise(){showNoise=!showNoise;if(showNoise&&activeFilter==='real_change')activeFilter='all';const b=document.getElementById('noiseToggle');
b.classList.toggle('active',showNoise);b.textContent=showNoise?`Скрыть шум (${report.counts.alignment_or_rendering_noise})`:`Показать оформление/шум (${report.counts.alignment_or_rendering_noise})`;
if(!showNoise&&activeFilter==='alignment_or_rendering_noise'){activeFilter='all';document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x.dataset.filter==='all'))}
document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x.dataset.filter===activeFilter));renderList();renderBoxes();ensureSelection();selectZone(selectedIndex,false)}function markdown(){if(!visibleZones().length)return `Лист ${report.seq}: в текущем фильтре нет наблюдений.`;const z=report.zones[selectedIndex],s=structure(z),r=z.rect;
const lines=[`### Лист ${report.seq} — зона ${z.id}`,`**Тип:** ${kindLabel(z)}`,`**Уверенность:** ${z.confidence}%`,`**Область:** ${r?`${r.x}, ${r.y}; ${r.w}×${r.h} px`:'весь лист'}`,
'**Классификация:** '+(z.manual_classification?'ручная; вывод AI: '+kindLabel({classification:z.ai_classification}):'AI'),
...(z.manual_shape?['**Контур:** поправлен вручную']:[]),
'',`#### ${s.title}`,...s.facts.map(x=>`- ${x}`)];return lines.join('\n')}async function copyMarkdown(){const text=markdown();let copied=false;
const onCopy=e=>{e.clipboardData.setData('text/plain',text);e.preventDefault()};document.addEventListener('copy',onCopy);try{copied=document.execCommand('copy')}finally{
document.removeEventListener('copy',onCopy)}if(!copied&&navigator.clipboard){try{await navigator.clipboard.writeText(text);copied=true}catch(e){copied=false}}
const toast=document.getElementById('toast');toast.textContent=copied?'Markdown скопирован':'Не удалось скопировать — повторите';toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),1800)}
document.getElementById('noiseToggle').onclick=toggleNoise;document.getElementById('copyMarkdown').onclick=copyMarkdown;document.getElementById('zoomIn').onclick=()=>setScale(scale*1.18);
document.getElementById('zoomOut').onclick=()=>setScale(scale/1.18);document.getElementById('fit').onclick=fit;document.getElementById('focusZone').onclick=focusSelected;
function adjacent(d){const v=visibleZones();let p=v.findIndex(x=>x.i===selectedIndex);p=(p+d+v.length)%v.length;if(v.length)selectZone(v[p].i,true)}
document.getElementById('prevZone').onclick=()=>adjacent(-1);document.getElementById('nextZone').onclick=()=>adjacent(1);document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{
activeFilter=b.dataset.filter;if(activeFilter==='alignment_or_rendering_noise'&&!showNoise)toggleNoise();document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x===b));
renderList();ensureSelection();selectZone(selectedIndex,false)});const dr=document.getElementById('detailRange');dr.oninput=()=>{document.querySelectorAll('.detail-slider .detail-old').forEach(x=>x.style.clipPath=
`inset(0 ${100-dr.value}% 0 0)`);document.getElementById('detailLine').style.left=`${dr.value}%`};stage.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();
const r=stage.getBoundingClientRect(),cx=e.clientX-r.left,cy=e.clientY-r.top;setScale(scale*(e.deltaY<0?1.12:1/1.12),{x:(stage.scrollLeft+cx)/scale,y:(stage.scrollTop+cy)/scale,
clientX:cx,clientY:cy})},{passive:false});stage.oncontextmenu=e=>e.preventDefault();stage.onpointerdown=e=>{if(e.button===0&&!spaceDown&&!editing&&surface.contains(e.target)){
splitDragging=true;stage.setPointerCapture(e.pointerId);splitAt(e);e.preventDefault();return}if(e.button===1||e.button===2||(e.button===0&&(spaceDown||editing))){panning=true;
stage.classList.add('panning');panStart={x:e.clientX,y:e.clientY,left:stage.scrollLeft,top:stage.scrollTop};stage.setPointerCapture(e.pointerId);e.preventDefault()}};
stage.onpointermove=e=>{if(splitDragging){splitAt(e);return}if(panning){stage.scrollLeft=panStart.left-(e.clientX-panStart.x);stage.scrollTop=panStart.top-(e.clientY-panStart.y)}};
stage.onpointerup=stage.onpointercancel=()=>{splitDragging=false;panning=false;stage.classList.remove('panning')};window.onkeydown=e=>{if(e.target.closest&&e.target.closest('input,select,textarea'))return;if(e.code==='Space')spaceDown=true;
if(e.key==='0')fit();if(e.key===']')adjacent(1);if(e.key==='[')adjacent(-1);shortcut(e)};window.onkeyup=e=>{if(e.code==='Space')spaceDown=false};document.querySelector('.sheet.new').onload=()=>{fit();selectZone(0,false)};
document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x.dataset.filter===activeFilter));
const noiseButton=document.getElementById('noiseToggle');noiseButton.classList.toggle('active',showNoise);noiseButton.textContent=showNoise?`Скрыть шум (${report.counts.alignment_or_rendering_noise})`:`Показать оформление/шум (${report.counts.alignment_or_rendering_noise})`;
setSplit(50);renderList();renderBoxes();ensureSelection();selectZone(selectedIndex,false);
""" + _SHEET_TOOLS_SCRIPT


_INDEX_UI_SCRIPT = r"""
const sheetRows=[...document.querySelectorAll('tr[data-seq]')],emptyRow=document.getElementById('emptySheets');
const escHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function zoneLabel(z){const ref=String(z.object_ref||'').trim();if(ref)return ref;const d=String(z.description||'').replace(/\*\*/g,'').trim(),c=d.indexOf(':');
return(c>0&&c<115?d.slice(0,c):d).trim()}
const clip=(t,n)=>t.length>n?t.slice(0,n-1)+'…':t;
function renderHighlights(){reviewReport.sheets.forEach(s=>{const el=document.querySelector('[data-highlights="'+s.seq+'"]');if(!el)return;
const seen=new Set(),items=[];['real_change','uncertain'].forEach(k=>s.zones.forEach(z=>{if(z.classification!==k)return;const t=zoneLabel(z);
if(t&&!seen.has(k+t)){seen.add(k+t);items.push([k==='real_change'?'real':'uncertain',t])}}));const noise=s.zones.filter(z=>z.classification==='alignment_or_rendering_noise').length;
let html=items.slice(0,4).map(([k,t])=>`<li class="${k}" title="${escHtml(t)}">${escHtml(clip(t,72))}</li>`).join('');
if(items.length>4)html+=`<li class="more">и ещё ${items.length-4}</li>`;if(!items.length)html=`<li class="none">${noise?`Только оформление / шум (${noise})`:'Правок не найдено'}</li>`;el.innerHTML=html})}
const sheetKind=s=>s.counts.real_change?'real':s.counts.uncertain?'uncertain':'none';let sheetFilter='all';
function applySheetFilter(){const bySeq=new Map(reviewReport.sheets.map(s=>[String(s.seq),s]));let shown=0;sheetRows.forEach(r=>{const s=bySeq.get(r.dataset.seq);
const ok=sheetFilter==='all'||(sheetFilter==='real'&&s.counts.real_change>0)||(sheetFilter==='uncertain'&&s.counts.uncertain>0)||(sheetFilter==='none'&&sheetKind(s)==='none');
r.hidden=!ok;if(ok)shown++});emptyRow.hidden=shown>0;document.querySelectorAll('.seg button').forEach(b=>b.classList.toggle('active',b.dataset.sheets===sheetFilter))}
function refreshIndex(){const n={all:reviewReport.sheets.length,real:0,uncertain:0,none:0};reviewReport.sheets.forEach(s=>{if(s.counts.real_change)n.real++;if(s.counts.uncertain)n.uncertain++;if(sheetKind(s)==='none')n.none++});
document.querySelectorAll('[data-sheet-count]').forEach(el=>el.textContent=n[el.dataset.sheetCount]);
document.querySelectorAll('.chip[data-count]').forEach(c=>c.classList.toggle('zero',parseInt(c.textContent,10)===0));renderHighlights();applySheetFilter()}
document.querySelectorAll('.seg button').forEach(b=>b.onclick=()=>{sheetFilter=b.dataset.sheets;applySheetFilter()});
sheetRows.forEach(r=>r.addEventListener('click',e=>{if(e.target.closest('a'))return;const a=r.querySelector('a.open');if(a)location.href=a.href}));
refreshIndex();
"""


def _revision(source: dict[str, Any], key: str, default: str) -> str:
    """The revision label, or "" when the report only knows the role name."""
    value = str(source.get(key) or "").strip()
    return "" if not value or value.upper() == default else value


def _zone_label(zone: dict[str, Any]) -> str:
    reference = str(zone.get("object_ref") or "").strip()
    if reference:
        return reference
    text = str(zone.get("description") or "").replace("**", "").strip()
    colon = text.find(":")
    return (text[:colon] if 0 < colon < 115 else text).strip()


def _highlight_items(zones: Sequence[dict[str, Any]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    items: list[tuple[str, str]] = []
    for classification, css in (("real_change", "real"), ("uncertain", "uncertain")):
        for zone in zones:
            label = _zone_label(zone)
            if zone.get("classification") == classification and label and (css, label) not in seen:
                seen.add((css, label))
                items.append((css, label))
    return items


def _highlights_html(zones: Sequence[dict[str, Any]]) -> str:
    """What changed on the sheet: object names, edits first, then items to check.

    Mirrors renderHighlights() in the page script, which redraws the list once the
    reader's manual decisions are applied; this copy is what shows without them.
    """
    items = _highlight_items(zones)
    noise = sum(zone.get("classification") == "alignment_or_rendering_noise" for zone in zones)
    if not items:
        text = f"Только оформление / шум ({noise})" if noise else "Правок не найдено"
        return f"<li class='none'>{escape(text)}</li>"
    html = "".join(
        f"<li class='{css}' title='{escape(label, quote=True)}'>{escape(label if len(label) <= 72 else label[:71] + '…')}</li>"
        for css, label in items[:4]
    )
    if len(items) > 4:
        html += f"<li class='more'>и ещё {len(items) - 4}</li>"
    return html


def vision_index_html(
    provider: str,
    model: str,
    sheets: Sequence[dict[str, Any]],
    *,
    root_filename: str = "index.html",
) -> str:
    del root_filename
    if not sheets:
        raise ValueError("At least one sheet is required")
    first = sheets[0]
    source = first.get("source") or {}

    def count(sheet: dict[str, Any], name: str) -> int:
        return int((sheet.get("counts") or {}).get(name) or 0)

    totals = {
        name: sum(count(sheet, name) for sheet in sheets)
        for name in ("real_change", "alignment_or_rendering_noise", "uncertain")
    }
    with_real = sum(1 for sheet in sheets if count(sheet, "real_change"))
    with_uncertain = sum(1 for sheet in sheets if count(sheet, "uncertain"))
    clean = sum(1 for sheet in sheets if not count(sheet, "real_change") and not count(sheet, "uncertain"))
    rows: list[str] = []
    for sheet in sheets:
        seq = int(sheet["seq"])
        chips = "".join(
            f"<span class='chip {css}{'' if count(sheet, name) else ' zero'}' data-sheet='{seq}' data-count='{name}' "
            f"data-suffix='{suffix}'>{count(sheet, name)}{suffix}</span>"
            for name, css, suffix in (
                ("real_change", "real", " правок"),
                ("uncertain", "uncertain", " проверить"),
                ("alignment_or_rendering_noise", "noise", " шум"),
            )
        )
        rows.append(
            f"<tr data-seq='{seq}'><td class='mid'><span class='sheet-no'>{seq}</span></td>"
            f"<td class='mid'><div class='counts'>{chips}</div></td>"
            f"<td><ul class='hl' data-highlights='{seq}'>{_highlights_html(sheet.get('zones') or [])}</ul></td>"
            f"<td class='mid'><div class='preview'><figure><img loading='lazy' src='sheets/sheet_{seq:03d}/old_thumb.png' alt='OLD лист {seq}'>"
            f"<figcaption>OLD</figcaption></figure><figure><img loading='lazy' src='sheets/sheet_{seq:03d}/new_thumb.png' alt='NEW лист {seq}'>"
            f"<figcaption>NEW</figcaption></figure></div></td><td class='mid'><a class='open' "
            f"href='sheets/sheet_{seq:03d}/comparison.html'>Открыть лист →</a></td></tr>"
        )
    alignments = {str(sheet.get("global_alignment") or "").strip().rstrip(". ") for sheet in sheets}
    alignments.discard("")
    method = f"{alignments.pop()}. " if len(alignments) == 1 else ""

    def document(role: str, key: str, name_key: str) -> str:
        revision = _revision(source, key, role)
        rev_html = f"<div class='doc-rev'>ревизия {escape(revision)}</div>" if revision else ""
        return (
            f"<article class='doc {role.lower()}'><span class='doc-pill'>{role}</span><div>"
            f"<div class='doc-name'>{escape(str(source.get(name_key) or role))}</div>{rev_html}</div></article>"
        )

    payload = json.dumps(dict(model=model, sheets=list(sheets)), ensure_ascii=False).replace("</", "<\\/")
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' "
        "content='width=device-width,initial-scale=1'><title>AI Compare — матрица листов</title>"
        f"<style>{_INDEX_CSS}</style></head><body><header class='hero'><div class='hero-row'><div class='hero-mark'>AI</div>"
        f"<div><h1>{escape(provider)} AI Compare — матрица проверенных листов</h1>"
        f"<p>Модель: {escape(model)} · листов: {len(sheets)} · интерфейс PDFCompare</p>"
        "</div></div></header><main class='wrap'><section class='documents'>"
        f"{document('OLD', 'old_revision', 'old_name')}<span class='doc-arrow'>→</span>"
        f"{document('NEW', 'new_revision', 'new_name')}</section><section class='kpis'>"
        f"<article class='kpi real'><span>Правки</span><strong data-count='real_change'>{totals['real_change']}</strong>"
        f"<small>на листах: <b data-sheet-count='real'>{with_real}</b></small></article>"
        f"<article class='kpi uncertain'><span>Требуют проверки</span><strong data-count='uncertain'>{totals['uncertain']}</strong>"
        f"<small>на листах: <b data-sheet-count='uncertain'>{with_uncertain}</b></small></article>"
        "<article class='kpi noise'><span>Оформление / шум</span>"
        f"<strong data-count='alignment_or_rendering_noise'>{totals['alignment_or_rendering_noise']}</strong>"
        "<small>на листах скрыты по умолчанию</small></article>"
        f"<article class='kpi'><span>Проверено листов</span><strong>{len(sheets)}</strong>"
        f"<small>без правок: <b data-sheet-count='none'>{clean}</b></small></article></section>"
        "<h2 class='matrix-title'>Матрица AI-сравнения</h2><section class='toolbar'><div class='seg' role='group' aria-label='Какие листы показать'>"
        f"<button class='active' data-sheets='all'>Все<b data-sheet-count='all'>{len(sheets)}</b></button>"
        f"<button data-sheets='real'>С правками<b data-sheet-count='real'>{with_real}</b></button>"
        f"<button data-sheets='uncertain'>Проверить<b data-sheet-count='uncertain'>{with_uncertain}</b></button>"
        f"<button data-sheets='none'>Без правок<b data-sheet-count='none'>{clean}</b></button></div>"
        "<div class='defaults'><label><input type='checkbox' id='defaultOnlyChanges'> "
        "По умолчанию показывать только правки на всех листах</label>"
        "<small id='reviewStatus'>Ручная оценка хранится в этом браузере.</small></div></section>"
        "<table class='matrix'><thead><tr><th>Лист</th><th>Найдено</th><th>Что изменилось</th><th>Превью</th><th></th>"
        f"</tr></thead><tbody>{''.join(rows)}"
        "<tr id='emptySheets' hidden><td colspan='5' class='empty'>Нет листов в этом фильтре.</td></tr></tbody></table>"
        f"<p class='footnote'>{escape(method)}Контуры объектов приблизительны. Оранжевые наблюдения AI не подтвердил — "
        "их нужно проверить. Ваши решения по зонам и поправленные контуры («Ваше решение» и «Править контур» на листе) "
        "хранятся в этом браузере и не меняют исходный вывод AI.</p></main>"
        f"<script id='reportData' type='application/json'>{payload}</script>"
        f"<script>{INDEX_REVIEW_SCRIPT}{_INDEX_UI_SCRIPT}</script></body></html>"
    )


def _pager(seq: int, sheet_numbers: Sequence[int]) -> str:
    index = sheet_numbers.index(seq)
    first = f"../sheet_{sheet_numbers[0]:03d}/comparison.html" if index else None
    previous = f"../sheet_{sheet_numbers[index - 1]:03d}/comparison.html" if index else None
    following = f"../sheet_{sheet_numbers[index + 1]:03d}/comparison.html" if index + 1 < len(sheet_numbers) else None
    last = f"../sheet_{sheet_numbers[-1]:03d}/comparison.html" if index + 1 < len(sheet_numbers) else None

    def control(label: str, href: str | None) -> str:
        return f"<a class='btn' href='{href}'>{label}</a>" if href else f"<button class='btn' disabled>{label}</button>"

    return "".join(
        (
            control("⇤", first),
            control("←", previous),
            f"<span class='page-count'>{index + 1} / {len(sheet_numbers)} · лист {seq}</span>",
            control("→", following),
            control("⇥", last),
        )
    )


def _sheet_index(sheet_numbers: Sequence[int], sheets: Sequence[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """What the sheet switcher lists: every sheet, with AI counts and main objects when known."""
    if not sheets:
        return [{"seq": int(seq)} for seq in sheet_numbers]
    return [
        {
            "seq": int(item["seq"]),
            "counts": {
                name: int((item.get("counts") or {}).get(name) or 0)
                for name in ("real_change", "uncertain", "alignment_or_rendering_noise")
            },
            "labels": [label for _, label in _highlight_items(item.get("zones") or [])[:3]],
        }
        for item in sheets
    ]


def vision_sheet_html(
    sheet: dict[str, Any],
    sheet_numbers: Sequence[int],
    *,
    root_filename: str = "index.html",
    sheets: Sequence[dict[str, Any]] | None = None,
) -> str:
    seq = int(sheet["seq"])
    source = sheet.get("source") or {}
    counts = sheet.get("counts") or {}
    width, height = (int(value) for value in sheet["size_px"])
    old_rev, new_rev = _revision(source, "old_revision", "OLD"), _revision(source, "new_revision", "NEW")
    revisions = f" · {escape(old_rev or 'OLD')} → {escape(new_rev or 'NEW')}" if old_rev or new_rev else ""
    old_corner = f"OLD · {escape(old_rev)}" if old_rev else "OLD"
    new_corner = f"NEW · {escape(new_rev)}" if new_rev else "NEW"
    payload = dict(sheet)
    payload["size_px"] = [width, height]
    report_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    index_json = json.dumps(_sheet_index(sheet_numbers, sheets), ensure_ascii=False).replace("</", "<\\/")
    position = f"{list(sheet_numbers).index(seq) + 1} / {len(sheet_numbers)}" if seq in sheet_numbers else str(seq)
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width,initial-scale=1'><title>AI-сравнение · Лист {seq}</title><style>{_SHEET_CSS}</style></head>"
        "<body><div class='app'><header class='topbar'>"
        f"<a class='btn' href='../../{escape(root_filename)}'>⌂ Обзор</a>"
        "<div class='sheet-switcher' id='sheetSwitcher'><button class='btn' id='sheetNavBtn' aria-expanded='false' "
        f"aria-controls='sheetNav' title='Все листы отчёта'>▦ Листы <span class='nav-pos'>{position}</span></button>"
        "<div class='sheet-nav' id='sheetNav' hidden><div class='sheet-nav-list' id='sheetNavList'></div>"
        "<div class='sheet-nav-preview' id='sheetNavPreview'></div></div></div>"
        "<div class='brand'><div class='brand-mark'>AI</div><div>"
        f"<div class='title'>Лист {seq}{revisions}</div><div class='subtitle'>Содержательные правки · оранжевый: требуется проверка · контуры приблизительные</div></div></div>"
        f"<button class='btn noise-toggle active' id='noiseToggle'>Скрыть шум ({int(counts.get('alignment_or_rendering_noise') or 0)})</button>"
        "<button class='btn' id='copyMarkdown'>⧉ Копировать Markdown</button></header><main class='workspace'>"
        "<aside class='panel summary'><div class='panel-head'><h2>Общая сводка</h2><p>Выберите наблюдение — лист приблизится к объекту, "
        "справа появится структурированное объяснение.</p></div><div><div class='summary-metrics'>"
        f"<div class='metric'><b data-count='real_change'>{int(counts.get('real_change') or 0)}</b><span>правки</span></div>"
        f"<div class='metric'><b data-count='alignment_or_rendering_noise'>{int(counts.get('alignment_or_rendering_noise') or 0)}</b><span>шум</span></div>"
        f"<div class='metric'><b data-count='uncertain'>{int(counts.get('uncertain') or 0)}</b><span>проверить</span></div></div>"
        "<div class='filters'><button class='filter active' data-filter='all'>Все</button><button class='filter' data-filter='real_change'>Правки</button>"
        "<button class='filter' data-filter='uncertain'>Проверить</button><button class='filter' data-filter='alignment_or_rendering_noise'>Шум</button>"
        "</div></div><div class='zone-list' id='zoneList'></div></aside><section class='panel viewer'><div class='toolbar'>"
        "<button class='btn' id='zoomOut'>−</button><span class='zoom-label' id='zoomLabel'>100%</span><button class='btn' id='zoomIn'>+</button>"
        "<button class='btn' id='fit'>Вписать</button><span class='slider-help' id='sliderHelp'>ЛКМ по листу — граница OLD / NEW</span>"
        "<span class='edit-hint' id='editHint' hidden>Правка контура: тяните контур или вершину · двойной щелчок по ребру — "
        "новая вершина · Alt+щелчок — удалить вершину · Ctrl+Z — отменить · Esc — готово</span>"
        f"<span class='quality'>PNG · {width}×{height}</span>"
        "</div><div class='stage' id='stage'><div class='surface' id='surface'><img class='sheet new' src='new.png' alt='Новая ревизия'>"
        "<img class='sheet old' src='old.png' alt='Старая ревизия'><div class='zones-layer' id='zonesLayer'></div><div class='split-line'></div>"
        f"<div class='split-knob' id='splitKnob'>50%</div><span class='corner-label old'>{old_corner}</span>"
        f"<span class='corner-label new'>{new_corner}</span></div><div class='hint'>ЛКМ — OLD/NEW · "
        "Ctrl+колесо — масштаб · ПКМ/СКМ или Space+drag — панорама · 0 — вписать</div></div></section>"
        "<aside class='panel inspector'><div class='zone-header'><div class='zone-heading'><span class='big-no real' id='bigNo'>1</span><div>"
        "<h2 id='zoneTitle'>Зона 1</h2><span class='class-badge real' id='classBadge'>Реальное изменение</span></div></div>"
        "<div class='verdict'><div class='verdict-head'><span class='verdict-label'>Ваше решение</span>"
        "<button class='link-btn' id='resetVerdict' hidden>↺ Вернуть вывод AI</button></div>"
        "<div class='verdict-seg' role='group' aria-label='Ваше решение по зоне'>"
        "<button data-verdict='real_change' class='v-real' title='Клавиша 1'><i></i>Правка</button>"
        "<button data-verdict='uncertain' class='v-uncertain' title='Клавиша 2'><i></i>Проверить</button>"
        "<button data-verdict='alignment_or_rendering_noise' class='v-noise' title='Клавиша 3'><i></i>Шум</button></div>"
        "<p class='verdict-note'><span id='aiVerdict'></span> <small id='reviewStatus'>Сохраняется в этом браузере</small></p></div></div>"
        "<div class='structured'><h3 id='observationTitle'>Наблюдение</h3><p class='lead' id='observationLead'></p>"
        "<div class='delta' id='deltaBlock' hidden><div class='delta-row old'><span>OLD</span><p id='deltaOld'></p></div><div class='delta-row new'><span>NEW</span><p id='deltaNew'></p></div><div class='delta-impact' id='deltaImpact'><b>Последствие</b><p id='deltaImpactText'></p></div></div><div id='changesSection'><h3>Что изменилось</h3><ul id='observationFacts'></ul></div><h3>Проверка</h3><div class='facts'>"
        "<div class='fact'>Уверенность<b id='confidence'>—</b></div><div class='fact'>Область, px<b id='rect'>—</b></div></div></div>"
        "<div class='detail'><div class='detail-title'><b>Детальный OLD / NEW</b><span class='quality'>без JPEG</span></div>"
        "<div class='detail-slider' id='detailSlider'><img id='detailNew' alt='NEW crop'><canvas id='detailNewCanvas' hidden></canvas>"
        "<img class='detail-old' id='detailOld' alt='OLD crop'><canvas class='detail-old' id='detailOldCanvas' hidden></canvas>"
        "<div class='detail-line' id='detailLine'></div></div><input class='detail-range' id='detailRange' type='range' min='0' max='100' value='50'>"
        "<div class='detail-empty' id='detailEmpty' hidden>Вывод относится ко всему листу; отдельная прямоугольная область не задана.</div></div>"
        "<div class='shape-tools'><button class='btn' id='editShape' title='Клавиша E'>✎ Править контур</button>"
        "<button class='link-btn' id='resetShape' hidden>↺ Вернуть контур AI</button></div>"
        "<div class='zone-nav'><button class='btn' id='prevZone'>←</button><button class='btn primary' id='focusZone'>Показать на листе</button>"
        "<button class='btn' id='nextZone'>→</button></div></aside></main><nav class='sheet-pager' aria-label='Навигация по листам'>"
        f"{_pager(seq, sheet_numbers)}</nav></div><div class='toast' id='toast'>Markdown скопирован</div>"
        f"<script id='reportData' type='application/json'>{report_json}</script>"
        f"<script id='sheetIndex' type='application/json'>{index_json}</script><script>{_SHEET_SCRIPT}</script></body></html>"
    )


__all__ = ["vision_index_html", "vision_sheet_html"]

