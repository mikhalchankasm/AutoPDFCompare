"""Offline report review state shared by the index and sheet viewers."""

REVIEW_SCRIPT = r"""
const reviewReport=JSON.parse(document.getElementById('reportData').textContent);
const reviewBase=new URL('.',location.href).pathname.replace(/\/sheets\/sheet_\d+\/$/,'/');
const reviewStorageKey='pdfcompare.review.v1:'+reviewBase+':'+reviewReport.model;
const reviewClasses=['real_change','alignment_or_rendering_noise','uncertain'];
function readReview(raw){try{const s=JSON.parse(raw);return s&&s.scope===reviewStorageKey&&typeof s.overrides==='object'&&s.overrides?s:null}catch(e){return null}}
let storedReview=null;try{storedReview=readReview(localStorage.getItem(reviewStorageKey))}catch(e){}
const linkedReview=readReview(new URLSearchParams(location.hash.slice(1)).get('review'));
let reviewState=[storedReview,linkedReview].filter(Boolean).sort((a,b)=>(b.updated||0)-(a.updated||0))[0]||
{scope:reviewStorageKey,updated:0,onlyChanges:false,overrides:{}};
function reviewZoneKey(sheet,z){const text=JSON.stringify([sheet.review_source||sheet.source,sheet.seq,z.id,z.description,z.ai_rect||z.rect]);
let h=2166136261;for(let i=0;i<text.length;i++)h=Math.imul(h^text.charCodeAt(i),16777619);return sheet.seq+':'+(h>>>0).toString(16)}
// A hand-corrected outline replaces the AI geometry for display only; the key keeps using the AI rect so a
// decision stays attached to its zone after the outline moves.
function reviewShape(value){if(!value||!Array.isArray(value.rect)||value.rect.length!==4||!Array.isArray(value.polygons))return null;
const polygons=value.polygons.filter(p=>Array.isArray(p)&&p.length>=3&&p.every(q=>Array.isArray(q)&&q.length===2&&q.every(Number.isFinite)));
return value.rect.every(Number.isFinite)&&polygons.length?{rect:{x:value.rect[0],y:value.rect[1],w:value.rect[2],h:value.rect[3]},polygons}:null}
function applyReviews(sheet){sheet.zones.forEach(z=>{z.ai_classification=z.ai_classification||z.classification;
if(!('ai_rect' in z)){z.ai_rect=z.rect||null;z.ai_polygons=z.polygons_px||[]}const key=reviewZoneKey(sheet,z);
const value=reviewState.overrides[key];z.manual_classification=reviewClasses.includes(value)?value:null;
z.classification=z.manual_classification||z.ai_classification;const shape=reviewShape((reviewState.shapes||{})[key]);
z.manual_shape=!!shape&&!!z.ai_rect;z.rect=z.manual_shape?shape.rect:z.ai_rect;z.polygons_px=z.manual_shape?shape.polygons:z.ai_polygons})}
function reviewLinks(){document.querySelectorAll('a[href]').forEach(a=>{const u=new URL(a.getAttribute('href'),location.href);
if(u.origin===location.origin&&u.pathname.startsWith(reviewBase)&&u.pathname.endsWith('.html')){
u.hash='review='+encodeURIComponent(JSON.stringify(reviewState));a.href=u.href}})}
function saveReview(){reviewState.updated=Date.now();const raw=JSON.stringify(reviewState);let saved=false;
try{localStorage.setItem(reviewStorageKey,raw);saved=true}catch(e){}
history.replaceState(null,'','#review='+encodeURIComponent(raw));reviewLinks();
const note=document.getElementById('reviewStatus');if(note)note.textContent=saved?'Ваши решения сохранены в этом браузере.':'Решения сохранены в ссылке; переходите между листами кнопками отчёта.'}
function updateReviewCounts(sheets){const totals={real_change:0,alignment_or_rendering_noise:0,uncertain:0};
sheets.forEach(s=>{applyReviews(s);const counts={real_change:0,alignment_or_rendering_noise:0,uncertain:0};
s.zones.forEach(z=>counts[z.classification]++);s.counts=counts;Object.keys(totals).forEach(k=>totals[k]+=counts[k]);
reviewState.summary=reviewState.summary||{};reviewState.summary[s.seq]=Object.assign({},counts);
document.querySelectorAll('[data-sheet="'+s.seq+'"][data-count]').forEach(el=>el.textContent=counts[el.dataset.count]+(el.dataset.suffix||''))});
document.querySelectorAll('[data-count]:not([data-sheet])').forEach(el=>el.textContent=totals[el.dataset.count]+(el.dataset.suffix||''))}
reviewLinks();
"""

INDEX_REVIEW_SCRIPT = REVIEW_SCRIPT + r"""
updateReviewCounts(reviewReport.sheets);reviewLinks();
const onlyChanges=document.getElementById('defaultOnlyChanges');onlyChanges.checked=!!reviewState.onlyChanges;
onlyChanges.onchange=()=>{reviewState.onlyChanges=onlyChanges.checked;saveReview()};
"""
