"""The report's stylesheets.

``REPORT_CSS_TOKENS`` holds the design tokens shared by every page; the three
sheets below are the per-page styles, inlined into the generated HTML:
``CSS_INDEX`` for the dashboard, ``CSS_VIEW`` for the detail view, ``CSS_CMP``
for the slider compare view.
"""

from __future__ import annotations

REPORT_CSS_TOKENS = """
:root {
  --bg: #F8FAFC;
  --surface: #FFFFFF;
  --surface-2: #F1F5F9;
  --border: #E2E8F0;
  --border-strong: #CBD5E1;
  --text: #0F172A;
  --text-muted: #475569;
  --text-faint: #94A3B8;
  --brand: #2563EB;
  --brand-hover: #1D4ED8;
  --brand-soft: #EFF6FF;
  --ok: #16A34A;
  --ok-bg: #DCFCE7;
  --ok-text: #166534;
  --danger: #DC2626;
  --danger-bg: #FEE2E2;
  --danger-text: #991B1B;
  --warn: #EA580C;
  --warn-bg: #FED7AA;
  --warn-text: #9A3412;
  --minor-bg: #FEF3C7;
  --minor-text: #92400E;
  --info: #7C3AED;
  --info-bg: #EDE9FE;
  --info-text: #5B21B6;
  --removed-bg: #FFEDD5;
  --removed-text: #9A3412;
  --removed-border: #FDBA74;
  --heat-ok: linear-gradient(90deg, #16A34A 0%, #86EFAC 100%);
  --heat-warn: linear-gradient(90deg, #D97706 0%, #FCD34D 100%);
  --heat-bad: linear-gradient(90deg, #DC2626 0%, #FCA5A5 100%);
  --shadow-sm: 0 1px 2px rgba(15,23,42,.05);
  --shadow-md: 0 4px 12px rgba(15,23,42,.08);
  --radius-sm: 6px;
  --radius: 10px;
  --radius-lg: 14px;
}
[data-theme="dark"] {
  --bg: #0B1220;
  --surface: #111827;
  --surface-2: #1F2937;
  --border: #1F2937;
  --border-strong: #334155;
  --text: #E5E7EB;
  --text-muted: #94A3B8;
  --text-faint: #64748B;
  --brand-soft: #1E3A8A33;
  --ok-bg: #052E1633;
  --ok-text: #4ADE80;
  --danger-bg: #3F121233;
  --danger-text: #F87171;
  --warn-bg: #3F1B0A33;
  --warn-text: #FB923C;
  --minor-bg: #3A2E0E33;
  --minor-text: #FCD34D;
  --info-bg: #23184A33;
  --info-text: #C4B5FD;
  --removed-bg: #3F1B0A33;
  --removed-text: #FB923C;
}
* { box-sizing: border-box; }
html { color-scheme: light; }
html[data-theme="dark"] { color-scheme: dark; }
body {
  margin: 0;
  font-family: Inter, "Segoe UI", system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
  background: var(--bg);
}
a { color: inherit; }
button, input, a, summary { font: inherit; }
button { cursor: pointer; }
button:focus-visible, a:focus-visible, input:focus-visible, summary:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
.ic { flex: 0 0 auto; }
.muted { color: var(--text-muted); }
.faint { color: var(--text-faint); }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0,0,0,0);
  white-space: nowrap;
  border: 0;
}
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: .5px;
  text-transform: uppercase;
  white-space: nowrap;
}
.st-changed, .lv-major { background: var(--danger-bg); color: var(--danger-text); }
.st-unchanged, .lv-unchanged { background: var(--ok-bg); color: var(--ok-text); }
.st-added { background: var(--info-bg); color: var(--info-text); }
.st-removed {
  background: var(--removed-bg);
  color: var(--removed-text);
  border-style: dashed;
  border-color: var(--removed-border);
}
.lv-moderate { background: var(--warn-bg); color: var(--warn-text); }
.lv-minor { background: var(--minor-bg); color: var(--minor-text); }
.lv-empty { background: var(--surface-2); color: var(--text-faint); }
.precision-badge { background: var(--brand-soft); color: var(--brand); border-color: var(--brand); }
.btn {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 12px;
  color: var(--text);
  background: var(--surface);
  text-decoration: none;
  box-shadow: var(--shadow-sm);
}
.btn:hover { border-color: var(--border-strong); background: var(--surface-2); }
.btn.primary {
  border-color: var(--brand);
  background: var(--brand);
  color: #FFFFFF;
}
.btn.primary:hover { background: var(--brand-hover); }
.btn.ghost {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
}
.btn.icon-only {
  width: 32px;
  padding: 0;
  border-radius: 999px;
}
/* "Home" button: jumps to the change matrix from any page. A steady neon outline
   so it reads as the one way back to the start, distinct from the ghost nav
   links. Static glow (not a perpetual pulse) — it must not nag while reading a
   drawing; the hover brightens it. */
.btn.home-neon {
  border: 1.5px solid #22d3ee;
  color: var(--text);
  background: rgba(34, 211, 238, 0.08);
  box-shadow: 0 0 6px rgba(34, 211, 238, 0.55), inset 0 0 4px rgba(34, 211, 238, 0.22);
  transition: box-shadow .18s ease, background .18s ease, border-color .18s ease;
}
.btn.home-neon .ic { color: #06b6d4; }
.btn.home-neon:hover {
  border-color: #06b6d4;
  background: rgba(34, 211, 238, 0.16);
  box-shadow: 0 0 11px rgba(34, 211, 238, 0.9), 0 0 20px rgba(34, 211, 238, 0.5);
}
.btn[disabled], .btn.disabled {
  opacity: .45;
  cursor: not-allowed;
  box-shadow: none;
  pointer-events: none;
}
.btn[disabled]:hover, .btn.disabled:hover { background: var(--surface); border-color: var(--border); }
.dropdown { position: relative; display: inline-flex; }
.dropdown-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  min-width: 210px;
  display: none;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow-md);
  z-index: 60;
}
.dropdown.open .dropdown-menu, .dropdown:focus-within .dropdown-menu { display: grid; gap: 4px; }
.dropdown-menu a, .dropdown-menu button {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 0;
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  color: var(--text);
  background: transparent;
  text-align: left;
  text-decoration: none;
}
.dropdown-menu a:hover, .dropdown-menu button:hover { background: var(--brand-soft); }
.seg-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 3px;
  background: var(--surface);
  min-height: 32px;
}
.seg-toggle[aria-disabled="true"] { opacity: .55; }
.seg-toggle-label {
  padding: 0 6px 0 8px;
  color: var(--text-muted);
  font-weight: 700;
  font-size: 12px;
  letter-spacing: .5px;
  text-transform: uppercase;
}
.seg-toggle-opt {
  min-height: 26px;
  padding: 3px 10px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  font-weight: 700;
  font-size: 12px;
}
.seg-toggle-opt.active {
  background: var(--brand);
  color: #FFFFFF;
}
.seg-toggle-opt[data-bbox="off"].active {
  background: var(--surface-2);
  color: var(--text);
  outline: 1px solid var(--border-strong);
}
.seg-toggle-opt[disabled] { cursor: not-allowed; }
"""


CSS_INDEX = """
.wrap { max-width: 1360px; margin: 0 auto; padding: 24px; }
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.brand-mark {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: var(--radius);
  color: var(--brand);
  background: var(--brand-soft);
}
h1 { margin: 0; font-size: 22px; line-height: 1.2; font-weight: 700; letter-spacing: 0; }
.subtitle { margin-top: 2px; color: var(--text-muted); font-size: 12px; }
.top-actions { display: flex; align-items: center; gap: 8px; }
.lang-switch {
  display: inline-grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px;
  background: var(--surface);
}
.lang-switch button {
  border: 0;
  border-radius: 999px;
  padding: 5px 9px;
  color: var(--text-muted);
  background: transparent;
  font-size: 12px;
  font-weight: 700;
}
.lang-switch button.active { color: #FFFFFF; background: var(--brand); }
.docs {
  display: grid;
  grid-template-columns: minmax(0,1fr) 36px minmax(0,1fr);
  gap: 12px;
  align-items: stretch;
  margin-bottom: 8px;
}
.doc-card {
  min-height: 104px;
  display: grid;
  align-content: space-between;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: var(--shadow-md);
}
.doc-card.old { background: var(--danger-bg); }
.doc-card.new { background: var(--ok-bg); }
.doc-pill {
  justify-self: start;
  border-radius: 999px;
  padding: 3px 9px;
  background: var(--surface);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .8px;
}
.old .doc-pill { color: var(--danger-text); }
.new .doc-pill { color: var(--ok-text); }
.doc-name { margin-top: 12px; font-weight: 700; overflow-wrap: anywhere; }
.doc-meta { margin-top: 2px; color: var(--text-muted); font-size: 12px; }
.doc-arrow { display: grid; place-items: center; color: var(--text-faint); }
.run-meta { margin: 0 0 18px 0; color: var(--text-faint); font-size: 12px; }
.kpi {
  display: grid;
  grid-template-columns: repeat(4, minmax(0,1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.kpi-card {
  display: grid;
  grid-template-columns: 40px minmax(0,1fr);
  gap: 12px;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
  background: var(--surface);
  color: var(--text);
  text-align: left;
  box-shadow: var(--shadow-md);
}
.kpi-card.active { border-color: var(--brand); box-shadow: 0 0 0 2px var(--brand-soft), var(--shadow-md); }
.kpi-ico {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 999px;
}
.kpi-card[data-value="CHANGED"] .kpi-ico { color: var(--danger-text); background: var(--danger-bg); }
.kpi-card[data-value="ADDED"] .kpi-ico { color: var(--info-text); background: var(--info-bg); }
.kpi-card[data-value="REMOVED"] .kpi-ico { color: var(--removed-text); background: var(--removed-bg); }
.kpi-card[data-value="UNCHANGED"] .kpi-ico { color: var(--ok-text); background: var(--ok-bg); }
.kpi-label {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.kpi-value { display: flex; align-items: baseline; gap: 6px; }
.kpi-value strong { font-size: 28px; line-height: 1; font-weight: 800; }
.kpi-context { color: var(--text-muted); font-size: 12px; }
.matrix-tools {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin: 14px 0;
}
.search-wrap {
  width: 240px;
  position: relative;
}
.search-wrap .ic {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-faint);
}
.search {
  width: 100%;
  min-height: 34px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 10px 7px 34px;
  color: var(--text);
  background: var(--surface);
}
.matrix {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-md);
  overflow: auto;
}
table {
  width: 100%;
  min-width: 1160px;
  border-collapse: separate;
  border-spacing: 0;
}
thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-muted);
  background: var(--surface);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .8px;
  text-transform: uppercase;
  text-align: left;
}
tbody td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--surface-2);
  vertical-align: middle;
}
tbody tr { cursor: pointer; }
tbody tr:hover td { background: var(--brand-soft); }
.seq-col { font-weight: 800; color: var(--text-muted); }
.map-cell { font-weight: 700; white-space: nowrap; }
.map-icon { margin: 0 5px; color: var(--text-faint); vertical-align: -3px; }
.diff-cell { min-width: 230px; }
.diff-wrap { display: grid; grid-template-columns: 180px 52px; align-items: center; gap: 8px; }
.diff-bar { height: 8px; border-radius: 4px; background: var(--surface-2); overflow: hidden; }
.diff-fill { height: 100%; min-width: 2%; border-radius: inherit; }
.heat-ok { background: var(--heat-ok); }
.heat-warn { background: var(--heat-warn); }
.heat-bad { background: var(--heat-bad); }
.diff-num { color: var(--text-muted); font-variant-numeric: tabular-nums; text-align: right; }
.pv {
  display: grid;
  grid-template-columns: repeat(3, 86px);
  gap: 5px;
}
.pv-tile {
  position: relative;
  width: 86px;
  height: 32px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--surface-2);
}
.pv-tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
.pv-label {
  position: absolute;
  left: 3px;
  top: 3px;
  border-radius: 999px;
  padding: 1px 5px;
  color: var(--text-muted);
  background: color-mix(in srgb, var(--surface) 82%, transparent);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .4px;
}
.ph {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--text-faint);
}
.open-link {
  width: 28px;
  height: 28px;
  display: inline-grid;
  place-items: center;
  border-radius: 999px;
  color: var(--brand);
  background: var(--brand-soft);
  text-decoration: none;
}
.legend {
  margin-top: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.legend summary {
  padding: 12px 16px;
  color: var(--text-muted);
  font-weight: 800;
  cursor: pointer;
}
.legend-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0,1fr));
  gap: 12px;
  padding: 0 16px 16px;
}
.legend-row { display: flex; align-items: center; gap: 10px; }
.footer {
  margin: 18px 0 4px;
  color: var(--text-muted);
  font-size: 12px;
}
.empty { padding: 24px; color: var(--text-muted); text-align: center; }
@media (max-width: 1199px) {
  .kpi { grid-template-columns: repeat(2, minmax(0,1fr)); }
}
@media (max-width: 899px) {
  .wrap { padding: 14px; }
  .topbar { align-items: stretch; }
  .topbar { flex-direction: column; }
  .top-actions { align-self: flex-end; }
  .docs { grid-template-columns: 1fr; }
  .doc-arrow { height: 28px; }
  .kpi { grid-template-columns: 1fr; }
  .matrix-tools { align-items: stretch; flex-direction: column; }
  .matrix-tools .dropdown { align-self: flex-start; }
  .search-wrap { width: 100%; }
  .matrix { border: 0; background: transparent; box-shadow: none; overflow: visible; }
  table, thead, tbody, tr, th, td { display: block; min-width: 0; }
  thead { display: none; }
  tbody { display: grid; gap: 10px; }
  tbody td { border: 0; padding: 0; }
  tbody tr {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 8px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 12px;
    background: var(--surface);
    box-shadow: var(--shadow-sm);
  }
  tbody tr:hover td { background: transparent; }
  .td-seq { grid-column: 1; }
  .td-map { grid-column: 1; }
  .td-status, .td-level { grid-column: 1 / -1; display: inline-flex; gap: 6px; }
  .td-diff, .td-boxes { grid-column: 1; }
  .td-preview { grid-column: 1 / -1; }
  .td-open { grid-column: 2; grid-row: 1 / span 2; align-self: start; }
  .diff-wrap { grid-template-columns: minmax(120px, 1fr) 52px; }
  .pv { grid-template-columns: repeat(3, minmax(0, 86px)); }
  .legend-body { grid-template-columns: 1fr; }
}
"""


CSS_VIEW = """
body { min-height: 100vh; }
.toolbar {
  position: sticky;
  top: 0;
  z-index: 30;
  min-height: 56px;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(220px, 1fr);
  gap: 12px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.toolbar-center {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  text-align: center;
}
.sheet-title { font-weight: 800; }
.toolbar-right { display: flex; justify-content: flex-end; align-items: center; gap: 8px; }
.body-grid {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 16px;
  padding: 16px;
}
.side {
  position: sticky;
  top: 72px;
  align-self: start;
  max-height: calc(100vh - 88px);
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px;
  background: var(--surface);
  box-shadow: var(--shadow-md);
}
.side-summary { margin-bottom: 14px; }
.side-summary-title {
  margin-bottom: 6px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.side-summary-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
}
.side-summary-list li {
  display: grid;
  grid-template-columns: 14px 1fr auto;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}
.side-summary-list b { font-variant-numeric: tabular-nums; font-weight: 800; }
.dot { width: 10px; height: 10px; border-radius: 50%; }
.dot-changed { background: var(--danger); }
.dot-added { background: var(--info); }
.dot-removed { background: var(--warn); border: 1px dashed var(--removed-border); }
.dot-unchanged { background: var(--ok); }
.section-title {
  margin-bottom: 10px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.search-wrap { position: relative; margin-bottom: 10px; }
.search-wrap .ic {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-faint);
}
.search {
  width: 100%;
  min-height: 34px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 10px 7px 34px;
  color: var(--text);
  background: var(--surface);
}
.nav-list { display: grid; gap: 6px; }
.nav-item {
  display: grid;
  grid-template-columns: minmax(0,1fr) auto;
  gap: 8px;
  align-items: center;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  padding: 8px 9px;
  color: var(--text);
  background: var(--surface);
  text-decoration: none;
}
.nav-item:hover { background: var(--surface-2); }
.nav-item.current {
  border-color: var(--brand);
  background: var(--brand-soft);
  box-shadow: inset 4px 0 0 var(--brand), var(--shadow-sm);
  font-weight: 800;
}
.nav-item.current:hover { background: var(--brand-soft); }
.nav-main { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nav-ok { color: var(--ok-text); }
.view-area {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
  background: var(--surface);
  box-shadow: var(--shadow-md);
}
.view-tools {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}
.view-primary {
  display: grid;
  gap: 6px;
  min-width: min(420px, 50%);
}
.btn-xl {
  min-height: 48px;
  padding: 10px 18px;
  font-size: 15px;
  font-weight: 800;
}
.btn-slider {
  min-width: 240px;
  justify-content: flex-start;
  box-shadow: 0 6px 18px color-mix(in srgb, var(--brand) 35%, transparent);
  transition: transform .12s ease, box-shadow .12s ease;
}
.btn-slider:hover { transform: translateY(-1px); }
.btn-slider .kbd {
  margin-left: auto;
  padding: 2px 6px;
  border: 1px solid color-mix(in srgb, #FFFFFF 40%, transparent);
  border-radius: 4px;
  font-size: 11px;
  opacity: .8;
}
.primary-hint {
  color: var(--text-muted);
  font-size: 12px;
  font-style: italic;
}
.view-modes { display: inline-flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.view-modes-label {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.tabs {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}
.tab {
  min-height: 30px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  padding: 5px 11px;
  color: var(--text-muted);
  background: transparent;
  font-weight: 700;
}
.tab:hover { background: var(--brand-soft); color: var(--text); }
.tab.active {
  border-color: var(--brand);
  color: #FFFFFF;
  background: var(--brand);
  box-shadow: 0 0 0 2px var(--brand-soft);
}
.tab[data-mode="diff"].active { background: var(--danger); border-color: var(--danger); }
.tab[data-mode="old"].active { background: var(--danger-text); border-color: var(--danger-text); }
.tab[data-mode="new"].active { background: var(--ok); border-color: var(--ok); }
.tool-right { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.toggle {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  color: var(--text-muted);
  background: var(--surface);
  font-weight: 700;
}
.toggle input { margin: 0; accent-color: var(--brand); }
.preview-mode { display: none; }
.preview-mode.active { display: block; }
.split-grid {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) minmax(0, 3fr);
  gap: 12px;
}
.left-stack {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 12px;
  min-height: 70vh;
}
.single-view, .diff-view { min-height: 70vh; }
figure {
  position: relative;
  margin: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-2);
}
figure img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  background: var(--surface);
}
.left-stack figure { min-height: 260px; }
.diff-view img, .single-view img { height: 70vh; min-height: 460px; }
.cap-pill {
  position: absolute;
  left: 10px;
  top: 10px;
  z-index: 2;
  border-radius: 999px;
  padding: 3px 8px;
  color: var(--text-muted);
  background: color-mix(in srgb, var(--surface) 88%, transparent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .8px;
}
.noimg {
  min-height: 240px;
  display: grid;
  place-items: center;
  color: var(--text-faint);
}
@media (max-width: 1199px) {
  .body-grid { grid-template-columns: 200px minmax(0,1fr); }
}
@media (max-width: 899px) {
  .toolbar { grid-template-columns: 1fr; }
  .toolbar-center { justify-content: flex-start; text-align: left; }
  .toolbar-right { justify-content: flex-start; flex-wrap: wrap; }
  .body-grid { grid-template-columns: 1fr; padding: 12px; }
  .side { position: relative; top: auto; max-height: 280px; }
  .view-tools { align-items: stretch; flex-direction: column; }
  .view-primary { min-width: 0; }
  .btn-slider { width: 100%; }
  .view-modes { align-items: stretch; flex-direction: column; }
  .tool-right { justify-content: flex-start; }
  .split-grid { grid-template-columns: 1fr; }
  .left-stack { min-height: 0; }
  .left-stack figure, .diff-view img, .single-view img { min-height: 280px; height: 48vh; }
}
"""


CSS_CMP = """
html, body { width: 100%; height: 100%; overflow: hidden; }
:root {
  --bbox-border: rgba(255,180,0,.74);
  --bbox-fill: rgba(255,235,120,.13);
}
.cmp-page {
  height: 100vh;
  display: grid;
  grid-template-rows: minmax(0,1fr);
  grid-template-columns: 0 minmax(0,1fr);
  transition: grid-template-columns .18s ease;
}
.cmp-page.pinned { grid-template-columns: 300px minmax(0,1fr); }
html.embed .cmp-header { display: none; }
html.embed .cmp-main { grid-template-rows: 0 minmax(0,1fr) auto; }
/* Embed (iframe on the view page): no drawer, no pinned column. */
html.embed .sheet-drawer { display: none; }
html.embed .cmp-page, html.embed .cmp-page.pinned { grid-template-columns: 0 minmax(0,1fr); }
html.embed .cmp-page.pinned .cmp-main { grid-column: 1 / -1; }
.cmp-header {
  display: grid;
  /* The controls column is sized by its content: the title is what gives way when
     the header gets tight (it clips its metrics tail), not the buttons. */
  grid-template-columns: auto minmax(0,1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  z-index: 10;
}
.cmp-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.cmp-title {
  display: flex;
  align-items: center;
  /* Left-aligned, not centred: a centred title that outgrows its column is cut on
     both sides, and "Лист 5 / 12" loses the half that names the sheet. */
  justify-content: flex-start;
  gap: 8px;
  min-width: 0;
  font-weight: 800;
  white-space: nowrap;
  overflow: hidden;
}
/* Metrics tail is the least critical part of the title: clip it first. */
.cmp-title > .muted {
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.cmp-right {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cmp-nav { display: flex; align-items: center; gap: 6px; }
/* "Лист 9" must stay on one line: a flex item may shrink below its content width,
   and the label then wraps to two lines and pushes the button out of the header row. */
.cmp-nav .btn {
  flex: 0 0 auto;
  justify-content: center;
  white-space: nowrap;
}
.sheet-drawer {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 50;
  pointer-events: none;
}
/* Pinned: drawer is a real grid column (pushes content), not an overlay. */
.cmp-page.pinned .sheet-drawer {
  position: relative;
  z-index: auto;
  pointer-events: auto;
  grid-column: 1;
  grid-row: 1 / -1;
  min-height: 0;
  overflow: hidden;
}
.sheet-drawer-handle {
  pointer-events: auto;
  position: absolute;
  top: 50%;
  left: 0;
  transform: translateY(-50%);
  width: 16px;
  height: 80px;
  border: 0;
  border-radius: 0 8px 8px 0;
  color: #FFFFFF;
  background: var(--brand);
  display: grid;
  place-items: center;
  box-shadow: 0 6px 18px rgba(15,23,42,.18);
}
.sheet-drawer-handle::after {
  content: "";
  position: absolute;
  inset: 0 -8px 0 0;
}
.cmp-page.pinned .sheet-drawer-handle { display: none; }
.sheet-drawer-panel {
  pointer-events: auto;
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 300px;
  padding: 14px;
  border: 1px solid var(--border);
  border-width: 0 1px 0 0;
  background: var(--surface);
  box-shadow: 8px 0 24px rgba(15,23,42,.10);
  transform: translateX(-100%);
  transition: transform .18s ease;
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  gap: 10px;
}
/* Pinned: panel is always visible as part of the grid, no transform. */
.cmp-page.pinned .sheet-drawer-panel {
  position: relative;
  height: 100%;
  transform: none;
  box-shadow: none;
  border-width: 0 1px 0 0;
}
/* Hover reveal only in floating (unpinned) mode. */
.sheet-drawer:hover .sheet-drawer-panel,
.sheet-drawer.open .sheet-drawer-panel,
.sheet-drawer:focus-within .sheet-drawer-panel {
  transform: translateX(0);
}
.sheet-drawer:hover .sheet-drawer-handle,
.sheet-drawer.open .sheet-drawer-handle,
.sheet-drawer:focus-within .sheet-drawer-handle {
  opacity: 0;
  pointer-events: none;
}
.sheet-drawer-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;
}
.slider-nav-search {
  width: 100%;
  min-height: 34px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 9px;
  color: var(--text);
  background: var(--surface);
}
.slider-nav-list { overflow: auto; display: grid; gap: 6px; align-content: start; }
.slider-nav-item {
  display: grid;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  color: var(--text);
  background: var(--surface);
  text-decoration: none;
}
.slider-nav-item:hover { border-color: var(--brand); background: var(--brand-soft); }
.slider-nav-item.current {
  border-color: var(--brand);
  background: var(--brand-soft);
  box-shadow: inset 4px 0 0 var(--brand), var(--shadow-sm);
  font-weight: 800;
}
.slider-nav-item.disabled-slider {
  opacity: .7;
  border-style: dashed;
}
.slider-nav-main {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.slider-nav-meta { color: var(--text-muted); font-size: 12px; }
.sheet-drawer-hint { font-size: 11px; }
.sheet-drawer-pin {
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
}
.sheet-drawer-pin:hover { color: var(--brand); background: var(--brand-soft); }
/* cmp-main owns the header/stage/controls rows; cmp-page only splits columns. */
.cmp-main {
  grid-column: 1 / -1;
  grid-row: 1;
  min-width: 0;
  min-height: 0;
  display: grid;
  /* auto, not a fixed 48px: the header shrinks its labels first, but if it still
     needs a second line the row grows instead of the buttons spilling out of it. */
  grid-template-rows: minmax(48px, auto) minmax(0,1fr) auto;
  container-type: inline-size;
}
.cmp-page.pinned .cmp-main { grid-column: 2; }
/* Header adapts to the content column width (matters when the sidebar is pinned).
   Order of what gives way: the metrics tail, then the control labels, then the
   sheet buttons become icons — the controls themselves never wrap or shrink. */
@container (max-width: 1400px) {
  .cmp-title > .muted { display: none; }
}
@container (max-width: 1340px) {
  .bbox-bar-label, .bbox-opacity-value { display: none; }
  .nav-edge span { display: none; }
  .nav-edge { width: 32px; min-width: 32px; padding: 0; }
}
/* Too narrow for one row: the controls take a row of their own instead of
   squeezing the title down to nothing (a 0-width title column shows no sheet
   number at all, which is the one thing the header must never lose). */
@container (max-width: 1100px) {
  .cmp-header { grid-template-columns: auto minmax(0,1fr); }
  .cmp-right { grid-column: 1 / -1; justify-content: flex-start; }
  .cmp-nav .btn { width: 32px; min-width: 32px; padding: 0; }
  .cmp-nav .btn span { display: none; }
  .segmented .seg-btn > span[data-i18n-ru] { display: none; }
  .bbox-bar { gap: 4px; padding: 2px 5px; }
  .bbox-bar .bbox-opacity { width: 72px; }
}
.segmented {
  display: inline-flex;
  justify-content: flex-end;
  gap: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
}
.segmented .seg-btn {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  border-left: 1px solid var(--border);
  padding: 5px 10px;
  color: var(--text);
  background: var(--surface);
  white-space: nowrap;
}
.segmented .seg-btn:first-child { border-left: 0; }
.segmented .seg-btn:first-child { border-top-left-radius: var(--radius-sm); border-bottom-left-radius: var(--radius-sm); }
.segmented .seg-btn:last-child,
.segmented > .dropdown:last-child > .seg-btn { border-top-right-radius: var(--radius-sm); border-bottom-right-radius: var(--radius-sm); }
.segmented .seg-btn:hover { background: var(--brand-soft); }
.segmented .seg-btn:disabled:hover { background: var(--surface); }
.segmented .dropdown { display: inline-flex; }
.segmented .dropdown .seg-btn { border-left: 1px solid var(--border); }
.caret { color: var(--text-faint); font-size: 10px; }
/* Bbox controls live open in the header — colour and opacity are adjusted while
   looking at the sheet, so they must not cost a click to reach. */
.bbox-bar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  background: var(--surface);
  white-space: nowrap;
}
.bbox-bar-label {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .5px;
  text-transform: uppercase;
}
.bbox-colors { display: inline-flex; gap: 4px; }
.bbox-bar .swatch-option {
  width: auto;
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 3px;
  background: var(--surface);
  cursor: pointer;
}
.bbox-bar .swatch-option.active { border-color: var(--brand); box-shadow: 0 0 0 2px var(--brand-soft); }
.swatch { display: inline-block; width: 16px; height: 16px; border-radius: 4px; border: 2px solid currentColor; box-sizing: border-box; }
.bbox-bar .bbox-opacity { width: 92px; }
.bbox-opacity-value { color: var(--text-muted); font-variant-numeric: tabular-nums; min-width: 36px; text-align: right; }
.bbox-swatch {
  position: relative;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  display: inline-block;
  order: -1;
}
.bbox-swatch.off {
  color: var(--text-faint);
  background: var(--surface-2);
}
.bbox-swatch.off::after {
  content: "";
  position: absolute;
  left: -2px;
  right: -2px;
  top: 50%;
  height: 2px;
  background: currentColor;
  transform: rotate(-38deg);
}
.stage {
  width: 100%;
  height: 100%;
  overflow: auto;
  min-height: 0;
  position: relative;
  background: var(--surface-2);
}
.stage.dragging { cursor: ew-resize; }
.stage.panning { cursor: grabbing; }
.compare-surface {
  position: relative;
  display: none;
  background: var(--surface);
  overflow: hidden;
  cursor: ew-resize;
  transform-origin: 0 0;
}
.layer { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: fill; user-select: none; -webkit-user-drag: none; }
.old-layer { position: absolute; inset: 0; overflow: hidden; clip-path: inset(0 50% 0 0); }
.bbox-layer { position: absolute; inset: 0; pointer-events: none; }
html[data-bbox-enabled="false"] .bbox-layer { display: none; }
.bbox { position: absolute; border: 2px solid var(--bbox-border); background: var(--bbox-fill); box-sizing: border-box; }
.divider { position: absolute; top: 0; bottom: 0; left: 50%; width: 2px; background: var(--brand); pointer-events: none; }
.load-msg { position: absolute; inset: 0; display: grid; place-items: center; color: var(--text-muted); }
.stage.panning .compare-surface { cursor: grabbing; }
/* "Показать зоны": transient rings pulsing where the changes cluster. The layer
   lives inside the surface, so rings scale and pan with the sheet. */
.zone-layer { position: absolute; inset: 0; pointer-events: none; display: none; z-index: 5; }
.zone-layer.active { display: block; }
.zone-ring {
  position: absolute;
  border-radius: 5px;
  border: 3px solid #ff5a1f;
  background: rgba(255, 90, 31, 0.10);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35);
  animation: zoneFade 3.2s ease forwards;
}
.zone-ring::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 6px;
  box-shadow: 0 0 0 0 rgba(255, 90, 31, 0.6);
  animation: zonePing 1s ease-out 3;
}
/* An expanding glow of constant on-screen thickness, so a wide box does not get
   a proportionally huge halo (that was the whole problem with the circle). */
@keyframes zonePing {
  0%   { box-shadow: 0 0 0 0 rgba(255, 90, 31, 0.60); }
  100% { box-shadow: 0 0 0 14px rgba(255, 90, 31, 0); }
}
@keyframes zoneFade {
  0%   { opacity: 0; }
  10%  { opacity: 1; }
  82%  { opacity: 1; }
  100% { opacity: 0; }
}
.zone-counter {
  position: absolute;
  left: 50%;
  bottom: 16px;
  transform: translateX(-50%) translateY(8px);
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(20, 20, 24, 0.86);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .2px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
  opacity: 0;
  pointer-events: none;
  transition: opacity .2s ease, transform .2s ease;
  z-index: 6;
}
.zone-counter.show { opacity: 1; transform: translateX(-50%) translateY(0); }
.seg-btn-accent { color: #d1490f; font-weight: 700; }
.seg-btn-accent:hover:not(:disabled) { background: rgba(255, 90, 31, 0.12); }
.seg-btn-accent:disabled { color: var(--text-muted); opacity: .55; cursor: default; }
@media (prefers-reduced-motion: reduce) {
  .zone-ring::after { display: none; }
  .zone-ring { animation: zoneFade 3.2s ease forwards; }
}
.slider-panel {
  border-top: 1px solid var(--border);
  padding: 10px 18px 12px;
  background: var(--surface);
}
.split-line {
  display: grid;
  grid-template-columns: auto minmax(120px,1fr) auto;
  gap: 12px;
  align-items: center;
}
.split-label {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .8px;
}
.split-label.old { color: var(--danger-text); }
.split-label.new { color: var(--ok-text); }
input[type=range] {
  width: 100%;
  height: 18px;
  accent-color: var(--brand);
}
#split {
  appearance: none;
  background: transparent;
}
#split::-webkit-slider-runnable-track {
  height: 6px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--brand) var(--split-pct, 50%), var(--surface-2) var(--split-pct, 50%));
}
#split::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  margin-top: -6px;
  border: 2.4px solid var(--brand);
  border-radius: 999px;
  background: #FFFFFF;
}
#split::-moz-range-track {
  height: 6px;
  border-radius: 999px;
  background: var(--surface-2);
}
#split::-moz-range-progress {
  height: 6px;
  border-radius: 999px;
  background: var(--brand);
}
#split::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border: 2.4px solid var(--brand);
  border-radius: 999px;
  background: #FFFFFF;
}
.hint {
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 10px;
  text-align: center;
}
@media (max-width: 899px) {
  .cmp-header {
    min-height: 104px;
    grid-template-columns: 1fr;
    align-items: start;
  }
  .cmp-main { grid-template-rows: auto minmax(0,1fr) auto; }
  .cmp-title { justify-content: flex-start; flex-wrap: wrap; white-space: normal; }
  .cmp-right { justify-content: flex-start; flex-wrap: wrap; }
  .segmented { justify-self: start; flex-wrap: wrap; }
}
@media (max-width: 1100px) {
  .cmp-nav .btn {
    width: 32px;
    min-width: 32px;
    padding: 0;
  }
  .cmp-nav .btn span { display: none; }
}
"""
