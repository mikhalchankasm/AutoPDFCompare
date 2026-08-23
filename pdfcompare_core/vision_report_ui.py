from __future__ import annotations

import json
from collections.abc import Sequence
from html import escape
from typing import Any


_BASE_CSS = """
:root {
  --bg:#f8fafc;--surface:#fff;--surface2:#f1f5f9;--border:#e2e8f0;
  --border-strong:#cbd5e1;--text:#0f172a;--muted:#475569;--brand:#2563eb;
  --real:#dc2626;--real-soft:#fef2f2;--noise:#0284c7;--noise-soft:#e0f2fe;
  --uncertain:#7c3aed;--uncertain-soft:#f3e8ff;--shadow:0 8px 24px #0f172a1a;
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
.chip.noise{color:#075985;background:var(--noise-soft)}.chip.uncertain{color:#5b21b6;background:var(--uncertain-soft)}
"""


_INDEX_CSS = _BASE_CSS + """
body{min-height:100%;padding-bottom:40px}.hero{padding:22px 28px 18px;border-bottom:1px solid var(--border);
background:var(--surface)}.hero-row{display:flex;align-items:center;gap:14px;max-width:1500px;margin:auto}
.hero-mark{display:grid;place-items:center;width:42px;height:42px;border-radius:10px;background:#0f172a;color:#fff;
font-weight:900}.hero h1{margin:0;font-size:22px}.hero p{margin:4px 0 0;color:var(--muted);font-size:13px}
.wrap{max-width:1500px;margin:auto;padding:18px 28px}.documents{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.doc,.kpi{border:1px solid var(--border);border-radius:10px;background:#fff;box-shadow:0 1px 2px #0f172a0f}
.doc{padding:13px 15px}.doc b{display:block;margin-bottom:4px}.doc span{color:var(--muted);font-size:12px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}.kpi{padding:14px}
.kpi span{display:block;color:var(--muted);font-size:11px;font-weight:800;text-transform:uppercase}.kpi strong{font-size:25px}
.section-title{display:flex;align-items:center;justify-content:space-between;margin:20px 0 8px}.section-title h2{font-size:16px;margin:0}
.matrix{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border:1px solid var(--border);
border-radius:10px;overflow:hidden}.matrix th,.matrix td{padding:11px 12px;border-bottom:1px solid var(--border);
text-align:left;vertical-align:middle}.matrix th{font-size:11px;text-transform:uppercase;color:var(--muted);background:var(--surface2)}
.matrix tr:last-child td{border-bottom:0}.matrix tbody tr:hover{background:#f8fafc}.sheet-no{font-size:20px;font-weight:900}
.counts{display:flex;gap:5px;flex-wrap:wrap}.preview{display:grid;grid-template-columns:1fr 1fr;gap:5px;width:290px}
.preview figure{margin:0;position:relative;border:1px solid var(--border);border-radius:6px;overflow:hidden;background:#e2e8f0}
.preview img{display:block;width:100%;height:64px;object-fit:contain;background:#fff}.preview figcaption{position:absolute;left:4px;
top:4px;padding:2px 5px;border-radius:4px;background:#0f172ad9;color:#fff;font-size:9px;font-weight:900}
.summary-text{max-width:420px;font-size:12px;color:var(--muted);line-height:1.5}
@media(max-width:900px){.documents,.kpis{grid-template-columns:1fr 1fr}.wrap{padding:14px}.matrix{display:block;
overflow-x:auto}.preview{width:230px}}@media(max-width:560px){.documents,.kpis{grid-template-columns:1fr}.hero{padding:16px}}
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
.zone-label{overflow:hidden}.zone-label b{display:block;font-size:12px}.zone-label span{display:block;overflow:hidden;text-overflow:ellipsis;
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
.inspector{display:flex;flex-direction:column;overflow:hidden}.zone-header{flex:0 0 auto;padding:12px 15px;border-bottom:1px solid var(--border)}
.zone-heading{display:flex;align-items:center;gap:9px}.big-no{display:grid;place-items:center;width:34px;height:34px;border-radius:8px;
color:#fff;font-weight:900}.zone-header h2{margin:0;font-size:16px}.class-badge{display:inline-flex;border-radius:999px;padding:4px 8px;
font-size:10px;font-weight:900;text-transform:uppercase}.class-badge.real{color:#991b1b;background:#fee2e2}.class-badge.noise{color:#075985;
background:var(--noise-soft)}.class-badge.uncertain{color:#5b21b6;background:var(--uncertain-soft)}.structured{flex:1 1 auto;min-height:150px;
overflow:auto;padding:14px 15px;border-bottom:1px solid var(--border);font-size:13px;line-height:1.55}.structured h3{margin:0 0 7px;font-size:13px}
.structured .lead{margin:0 0 13px;font-weight:750}.structured ul{margin:0 0 14px;padding-left:19px}.structured li{margin:0 0 6px}
.structured strong{color:#0f172a;background:#fef3c7;border-radius:3px;padding:0 2px}.facts{display:grid;grid-template-columns:repeat(2,1fr);gap:6px}
.fact{padding:7px 8px;border-radius:7px;background:var(--surface2);font-size:10px;color:var(--muted)}.fact b{display:block;color:var(--text);
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
@media(max-width:1200px){.workspace{grid-template-columns:245px minmax(440px,1fr) 340px}.subtitle{display:none}}
@media(max-width:900px){body{overflow:auto}.app{height:auto;min-height:100%}.workspace{display:flex;flex-direction:column}.summary{max-height:380px}
.viewer{height:68vh;min-height:520px}.inspector{overflow:visible}.topbar{position:sticky;top:0;flex-wrap:wrap}.sheet-pager{position:sticky;bottom:0}.slider-help{display:none}}
"""


_SHEET_SCRIPT = r"""
const report=JSON.parse(document.getElementById('reportData').textContent),W=report.size_px[0],H=report.size_px[1];
const stage=document.getElementById('stage'),surface=document.getElementById('surface'),zoneList=document.getElementById('zoneList');
const zonesLayer=document.getElementById('zonesLayer'),splitKnob=document.getElementById('splitKnob');
let scale=.1,selectedIndex=0,activeFilter='all',showNoise=true,spaceDown=false,panning=false,splitDragging=false,panStart=null;
const kind=z=>z.classification==='real_change'?'real':z.classification==='uncertain'?'uncertain':'noise';
const kindLabel=z=>kind(z)==='real'?'Реальное изменение':kind(z)==='uncertain'?'Требует проверки':'Шум / локальный сдвиг';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const emphasize=s=>esc(s).replace(/\b(OLD|NEW)\b|→|->|удален[а-яё]*|добавлен[а-яё]*|заменен[а-яё]*|изменен[а-яё]*/gi,'<strong>$&</strong>');
function structure(z){let text=z.description.replace(/\*\*/g,'').trim(),title=`Зона ${z.id}`,body=text;const colon=text.indexOf(':');
if(colon>0&&colon<115){title=text.slice(0,colon).trim().replace(/[«»]/g,'').replace(/\s*OLD\s*(?:->|→)\s*NEW\s*$/i,'');
body=text.slice(colon+1).trim()}let facts=body.split(/;\s*/).map(x=>x.trim()).filter(Boolean);if(facts.length===1&&body.length>180)
facts=body.split(/\.\s+(?=[А-ЯA-Z«])/).map(x=>x.trim()).filter(Boolean);return{title,facts:facts.length?facts:[body]}}
function visibleZones(){return report.zones.map((z,i)=>({z,i})).filter(({z})=>(showNoise||kind(z)!=='noise')&&
(activeFilter==='all'||z.classification===activeFilter))}function ensureSelection(){const v=visibleZones();if(!v.some(x=>x.i===selectedIndex)&&v.length)selectedIndex=v[0].i}
function renderList(){ensureSelection();zoneList.innerHTML='';visibleZones().forEach(({z,i})=>{const b=document.createElement('button');
b.className=`zone-row ${kind(z)} ${i===selectedIndex?'active':''}`;b.innerHTML=`<span class="zone-no">${z.id}</span><span class="zone-label">
<b>Зона ${z.id}</b><span>${esc(z.description.slice(0,88))}${z.description.length>88?'…':''}</span></span><span class="confidence">${z.confidence}%</span>`;
b.onclick=()=>selectZone(i,true);zoneList.appendChild(b)});if(!zoneList.children.length)zoneList.innerHTML='<div class="detail-empty">В этом фильтре зон нет.</div>'}
function renderBoxes(){zonesLayer.innerHTML='';report.zones.forEach((z,i)=>{if(!z.rect||(!showNoise&&kind(z)==='noise'))return;const r=z.rect,b=document.createElement('div');
b.className=`zone-box ${kind(z)} ${i===selectedIndex?'selected':''} ${r.y<120?'near-top':''}`;b.style.cssText=`left:${r.x/W*100}%;top:${r.y/H*100}%;
width:${r.w/W*100}%;height:${r.h/H*100}%`;b.innerHTML=`<span class="zone-tag">${z.id}</span>`;zonesLayer.appendChild(b)})}
function selectZone(i,focus=false){selectedIndex=(i+report.zones.length)%report.zones.length;const z=report.zones[selectedIndex],r=z.rect,k=kind(z),s=structure(z);
document.getElementById('bigNo').textContent=z.id;document.getElementById('bigNo').className=`big-no ${k}`;document.getElementById('zoneTitle').textContent=`Зона ${z.id}`;
const badge=document.getElementById('classBadge');badge.textContent=kindLabel(z);badge.className=`class-badge ${k}`;document.getElementById('observationTitle').textContent=s.title;
document.getElementById('observationLead').innerHTML=emphasize(s.facts[0]);const changes=document.getElementById('changesSection');changes.hidden=s.facts.length<2;
document.getElementById('observationFacts').innerHTML=s.facts.slice(1).map(x=>`<li>${emphasize(x)}</li>`).join('');document.getElementById('confidence').textContent=`${z.confidence}%`;
document.getElementById('rect').textContent=r?`${r.x}, ${r.y} · ${r.w}×${r.h}`:'весь лист';const slider=document.getElementById('detailSlider'),range=document.getElementById('detailRange');
const empty=document.getElementById('detailEmpty'),focusBtn=document.getElementById('focusZone');slider.hidden=!r;range.hidden=!r;empty.hidden=!!r;focusBtn.disabled=!r;
if(r&&z.images){document.getElementById('detailOld').src=z.images.old||'';document.getElementById('detailNew').src=z.images.new||''}renderList();renderBoxes();if(focus&&r)requestAnimationFrame(focusSelected)}
function setScale(n,a){n=Math.max(.025,Math.min(2.5,n));const old=scale,ax=a?.x??(stage.scrollLeft+stage.clientWidth/2)/old,ay=a?.y??(stage.scrollTop+stage.clientHeight/2)/old;
scale=n;surface.style.width=`${W*scale}px`;surface.style.height=`${H*scale}px`;document.getElementById('zoomLabel').textContent=`${Math.round(scale*100)}%`;
requestAnimationFrame(()=>{stage.scrollLeft=ax*scale-(a?.clientX??stage.clientWidth/2);stage.scrollTop=ay*scale-(a?.clientY??stage.clientHeight/2)})}
function fit(){const p=52;setScale(Math.min((stage.clientWidth-p)/W,(stage.clientHeight-p)/H));requestAnimationFrame(()=>{stage.scrollLeft=0;stage.scrollTop=0})}
function focusSelected(){const r=report.zones[selectedIndex].rect;if(!r)return;const p=Math.max(100,Math.min(350,Math.max(r.w,r.h)*.18));
const target=Math.min((stage.clientWidth*.76)/(r.w+p*2),(stage.clientHeight*.76)/(r.h+p*2),1.35);setScale(Math.max(target,.08),{x:r.x+r.w/2,y:r.y+r.h/2,
clientX:stage.clientWidth/2,clientY:stage.clientHeight/2})}function setSplit(v){v=Math.max(0,Math.min(100,v));surface.style.setProperty('--split',`${v}%`);splitKnob.textContent=`${Math.round(v)}%`}
function splitAt(e){const r=surface.getBoundingClientRect();setSplit((e.clientX-r.left)/r.width*100)}function toggleNoise(){showNoise=!showNoise;const b=document.getElementById('noiseToggle');
b.classList.toggle('active',showNoise);b.textContent=showNoise?`Скрыть шум (${report.counts.alignment_or_rendering_noise})`:`Показать шум (${report.counts.alignment_or_rendering_noise})`;
if(!showNoise&&activeFilter==='alignment_or_rendering_noise'){activeFilter='all';document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x.dataset.filter==='all'))}
renderList();renderBoxes();ensureSelection();selectZone(selectedIndex,false)}function markdown(){const z=report.zones[selectedIndex],s=structure(z),r=z.rect;
const lines=[`### Лист ${report.seq} — зона ${z.id}`,`**Тип:** ${kindLabel(z)}`,`**Уверенность:** ${z.confidence}%`,`**Область:** ${r?`${r.x}, ${r.y}; ${r.w}×${r.h} px`:'весь лист'}`,
'',`#### ${s.title}`,...s.facts.map(x=>`- ${x}`)];return lines.join('\n')}async function copyMarkdown(){const text=markdown();let copied=false;
const onCopy=e=>{e.clipboardData.setData('text/plain',text);e.preventDefault()};document.addEventListener('copy',onCopy);try{copied=document.execCommand('copy')}finally{
document.removeEventListener('copy',onCopy)}if(!copied&&navigator.clipboard){try{await navigator.clipboard.writeText(text);copied=true}catch(e){copied=false}}
const toast=document.getElementById('toast');toast.textContent=copied?'Markdown скопирован':'Не удалось скопировать — повторите';toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),1800)}
document.getElementById('noiseToggle').onclick=toggleNoise;document.getElementById('copyMarkdown').onclick=copyMarkdown;document.getElementById('zoomIn').onclick=()=>setScale(scale*1.18);
document.getElementById('zoomOut').onclick=()=>setScale(scale/1.18);document.getElementById('fit').onclick=fit;document.getElementById('focusZone').onclick=focusSelected;
function adjacent(d){const v=visibleZones();let p=v.findIndex(x=>x.i===selectedIndex);p=(p+d+v.length)%v.length;if(v.length)selectZone(v[p].i,true)}
document.getElementById('prevZone').onclick=()=>adjacent(-1);document.getElementById('nextZone').onclick=()=>adjacent(1);document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{
activeFilter=b.dataset.filter;if(activeFilter==='alignment_or_rendering_noise'&&!showNoise)toggleNoise();document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x===b));
renderList();ensureSelection();selectZone(selectedIndex,false)});const dr=document.getElementById('detailRange');dr.oninput=()=>{document.getElementById('detailOld').style.clipPath=
`inset(0 ${100-dr.value}% 0 0)`;document.getElementById('detailLine').style.left=`${dr.value}%`};stage.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();
const r=stage.getBoundingClientRect(),cx=e.clientX-r.left,cy=e.clientY-r.top;setScale(scale*(e.deltaY<0?1.12:1/1.12),{x:(stage.scrollLeft+cx)/scale,y:(stage.scrollTop+cy)/scale,
clientX:cx,clientY:cy})},{passive:false});stage.oncontextmenu=e=>e.preventDefault();stage.onpointerdown=e=>{if(e.button===0&&!spaceDown&&surface.contains(e.target)){
splitDragging=true;stage.setPointerCapture(e.pointerId);splitAt(e);e.preventDefault();return}if(e.button===1||e.button===2||(e.button===0&&spaceDown)){panning=true;
stage.classList.add('panning');panStart={x:e.clientX,y:e.clientY,left:stage.scrollLeft,top:stage.scrollTop};stage.setPointerCapture(e.pointerId);e.preventDefault()}};
stage.onpointermove=e=>{if(splitDragging){splitAt(e);return}if(panning){stage.scrollLeft=panStart.left-(e.clientX-panStart.x);stage.scrollTop=panStart.top-(e.clientY-panStart.y)}};
stage.onpointerup=stage.onpointercancel=()=>{splitDragging=false;panning=false;stage.classList.remove('panning')};window.onkeydown=e=>{if(e.code==='Space')spaceDown=true;
if(e.key==='0')fit();if(e.key===']')adjacent(1);if(e.key==='[')adjacent(-1)};window.onkeyup=e=>{if(e.code==='Space')spaceDown=false};document.querySelector('.sheet.new').onload=()=>{fit();selectZone(0,false)};
setSplit(50);renderList();renderBoxes();selectZone(0,false);
"""


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
    totals = {
        name: sum(int((sheet.get("counts") or {}).get(name) or 0) for sheet in sheets)
        for name in ("real_change", "alignment_or_rendering_noise", "uncertain")
    }
    rows: list[str] = []
    for sheet in sheets:
        seq = int(sheet["seq"])
        counts = sheet.get("counts") or {}
        summary = str(sheet.get("global_alignment") or "Совмещение не определено").rstrip(". ") + "."
        rows.append(
            f"<tr><td><span class='sheet-no'>{seq}</span></td><td><div class='counts'>"
            f"<span class='chip real'>{int(counts.get('real_change') or 0)} правок</span>"
            f"<span class='chip noise'>{int(counts.get('alignment_or_rendering_noise') or 0)} шум</span>"
            f"<span class='chip uncertain'>{int(counts.get('uncertain') or 0)} проверить</span></div></td>"
            f"<td><div class='summary-text'>{escape(summary)} Все зоны показаны при открытии листа.</div></td>"
            f"<td><div class='preview'><figure><img src='sheets/sheet_{seq:03d}/old_thumb.png' alt='OLD лист {seq}'>"
            f"<figcaption>OLD</figcaption></figure><figure><img src='sheets/sheet_{seq:03d}/new_thumb.png' alt='NEW лист {seq}'>"
            f"<figcaption>NEW</figcaption></figure></div></td><td><a class='btn primary' "
            f"href='sheets/sheet_{seq:03d}/comparison.html'>Открыть лист</a></td></tr>"
        )
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' "
        "content='width=device-width,initial-scale=1'><title>AI Compare — матрица листов</title>"
        f"<style>{_INDEX_CSS}</style></head><body><header class='hero'><div class='hero-row'><div class='hero-mark'>AI</div>"
        f"<div><h1>{escape(provider)} AI Compare — матрица проверенных листов</h1><p>Модель: {escape(model)} · интерфейс PDFCompare</p>"
        "</div></div></header><main class='wrap'><section class='documents'>"
        f"<article class='doc'><b>OLD · {escape(str(source.get('old_revision') or 'OLD'))}</b>"
        f"<span>{escape(str(source.get('old_name') or 'OLD'))}</span></article>"
        f"<article class='doc'><b>NEW · {escape(str(source.get('new_revision') or 'NEW'))}</b>"
        f"<span>{escape(str(source.get('new_name') or 'NEW'))}</span></article></section><section class='kpis'>"
        f"<article class='kpi'><span>Проверено листов</span><strong>{len(sheets)}</strong></article>"
        f"<article class='kpi'><span>Реальные изменения</span><strong>{totals['real_change']}</strong></article>"
        f"<article class='kpi'><span>Шумовые зоны</span><strong>{totals['alignment_or_rendering_noise']}</strong></article>"
        f"<article class='kpi'><span>Требуют проверки</span><strong>{totals['uncertain']}</strong></article></section>"
        "<div class='section-title'><h2>Матрица AI-сравнения</h2><span class='chip'>Шум показан по умолчанию</span></div>"
        "<table class='matrix'><thead><tr><th>Лист</th><th>Классификация</th><th>Сводка</th><th>Превью</th><th>Открыть</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></main></body></html>"
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


def vision_sheet_html(
    sheet: dict[str, Any],
    sheet_numbers: Sequence[int],
    *,
    root_filename: str = "index.html",
) -> str:
    seq = int(sheet["seq"])
    source = sheet.get("source") or {}
    counts = sheet.get("counts") or {}
    width, height = (int(value) for value in sheet["size_px"])
    payload = dict(sheet)
    payload["size_px"] = [width, height]
    report_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width,initial-scale=1'><title>AI-сравнение · Лист {seq}</title><style>{_SHEET_CSS}</style></head>"
        "<body><div class='app'><header class='topbar'>"
        f"<a class='btn' href='../../{escape(root_filename)}'>⌂ Обзор</a><div class='brand'><div class='brand-mark'>AI</div><div>"
        f"<div class='title'>Лист {seq} · {escape(str(source.get('old_revision') or 'OLD'))} → "
        f"{escape(str(source.get('new_revision') or 'NEW'))}</div><div class='subtitle'>AI-проверка поверх исходных PNG PDFCompare</div></div></div>"
        f"<button class='btn noise-toggle active' id='noiseToggle'>Скрыть шум ({int(counts.get('alignment_or_rendering_noise') or 0)})</button>"
        "<button class='btn' id='copyMarkdown'>⧉ Копировать Markdown</button></header><main class='workspace'>"
        "<aside class='panel summary'><div class='panel-head'><h2>Общая сводка</h2><p>Все зоны показаны. Выберите зону — лист приблизится к ней, "
        "справа появится структурированное объяснение.</p></div><div><div class='summary-metrics'>"
        f"<div class='metric'><b>{int(counts.get('real_change') or 0)}</b><span>правки</span></div>"
        f"<div class='metric'><b>{int(counts.get('alignment_or_rendering_noise') or 0)}</b><span>шум</span></div>"
        f"<div class='metric'><b>{int(counts.get('uncertain') or 0)}</b><span>проверить</span></div></div>"
        "<div class='filters'><button class='filter active' data-filter='all'>Все</button><button class='filter' data-filter='real_change'>Правки</button>"
        "<button class='filter' data-filter='uncertain'>Проверить</button><button class='filter' data-filter='alignment_or_rendering_noise'>Шум</button>"
        "</div></div><div class='zone-list' id='zoneList'></div></aside><section class='panel viewer'><div class='toolbar'>"
        "<button class='btn' id='zoomOut'>−</button><span class='zoom-label' id='zoomLabel'>100%</span><button class='btn' id='zoomIn'>+</button>"
        f"<button class='btn' id='fit'>Вписать</button><span class='slider-help'>ЛКМ по листу — граница OLD / NEW</span><span class='quality'>PNG · {width}×{height}</span>"
        "</div><div class='stage' id='stage'><div class='surface' id='surface'><img class='sheet new' src='new.png' alt='Новая ревизия'>"
        "<img class='sheet old' src='old.png' alt='Старая ревизия'><div class='zones-layer' id='zonesLayer'></div><div class='split-line'></div>"
        f"<div class='split-knob' id='splitKnob'>50%</div><span class='corner-label old'>OLD · {escape(str(source.get('old_revision') or 'OLD'))}</span>"
        f"<span class='corner-label new'>NEW · {escape(str(source.get('new_revision') or 'NEW'))}</span></div><div class='hint'>ЛКМ — OLD/NEW · "
        "Ctrl+колесо — масштаб · ПКМ/СКМ или Space+drag — панорама · 0 — вписать</div></div></section>"
        "<aside class='panel inspector'><div class='zone-header'><div class='zone-heading'><span class='big-no real' id='bigNo'>1</span><div>"
        "<h2 id='zoneTitle'>Зона 1</h2><span class='class-badge real' id='classBadge'>Реальное изменение</span></div></div></div>"
        "<div class='structured'><h3 id='observationTitle'>Наблюдение</h3><p class='lead' id='observationLead'></p>"
        "<div id='changesSection'><h3>Что изменилось</h3><ul id='observationFacts'></ul></div><h3>Проверка</h3><div class='facts'>"
        "<div class='fact'>Уверенность<b id='confidence'>—</b></div><div class='fact'>Область, px<b id='rect'>—</b></div></div></div>"
        "<div class='detail'><div class='detail-title'><b>Детальный OLD / NEW</b><span class='quality'>без JPEG</span></div>"
        "<div class='detail-slider' id='detailSlider'><img id='detailNew' alt='NEW crop'><img class='detail-old' id='detailOld' alt='OLD crop'>"
        "<div class='detail-line' id='detailLine'></div></div><input class='detail-range' id='detailRange' type='range' min='0' max='100' value='50'>"
        "<div class='detail-empty' id='detailEmpty' hidden>Вывод относится ко всему листу; отдельная прямоугольная область не задана.</div></div>"
        "<div class='zone-nav'><button class='btn' id='prevZone'>←</button><button class='btn primary' id='focusZone'>Показать на листе</button>"
        "<button class='btn' id='nextZone'>→</button></div></aside></main><nav class='sheet-pager' aria-label='Навигация по листам'>"
        f"{_pager(seq, sheet_numbers)}</nav></div><div class='toast' id='toast'>Markdown скопирован</div>"
        f"<script id='reportData' type='application/json'>{report_json}</script><script>{_SHEET_SCRIPT}</script></body></html>"
    )


__all__ = ["vision_index_html", "vision_sheet_html"]
