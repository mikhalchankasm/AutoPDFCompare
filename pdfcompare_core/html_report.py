"""Final HTML report builder (dashboard, slider views, detail pages)."""

from __future__ import annotations

import html
import json
import os
import shutil
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import fitz


from .classification import level_to_report_tags, status_and_confidence
from .constants import (
    FG_MINOR_PERCENT,
    FG_MODERATE_PERCENT,
    PAGE_INFO_THUMB_DPI,
    START_REPORT_FILE,
    UNCHANGED_DIFF_PERCENT,
)
from .pdf_io import (
    copy_thumb,
    find_pages_dir,
    internal_dir,
    page_map_csv_path,
    report_dir,
    write_start_page,
)



from .html_css import REPORT_CSS_TOKENS
from .html_i18n import HTML_REPORT_I18N
from .html_icons import report_icon



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
  grid-template-columns: minmax(140px,1fr) minmax(0,auto) minmax(auto,1fr);
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
  justify-content: center;
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
}
.cmp-nav { display: flex; align-items: center; gap: 6px; }
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
  grid-template-rows: 48px minmax(0,1fr) auto;
  container-type: inline-size;
}
.cmp-page.pinned .cmp-main { grid-column: 2; }
/* Header adapts to the content column width (matters when the sidebar is pinned). */
@container (max-width: 1240px) {
  .cmp-nav .btn { width: 32px; min-width: 32px; padding: 0; }
  .cmp-nav .btn span { display: none; }
}
@container (max-width: 1040px) {
  .segmented .seg-btn > span[data-i18n-ru] { display: none; }
}
.cmp-count {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 10px;
  color: var(--text-muted);
  background: var(--surface);
  font-size: 12px;
  font-weight: 800;
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
.segmented .dropdown { display: inline-flex; }
.segmented .dropdown .seg-btn { border-left: 1px solid var(--border); }
.caret { color: var(--text-faint); font-size: 10px; }
.bbox-panel { width: 280px; padding: 10px; gap: 10px; }
.bbox-row { display: grid; grid-template-columns: 110px 1fr auto; gap: 8px; align-items: center; }
.bbox-row-label {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .5px;
  text-transform: uppercase;
}
.bbox-colors { display: inline-flex; gap: 6px; }
.bbox-panel .swatch-option {
  width: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 5px;
  background: var(--surface);
  cursor: pointer;
}
.bbox-panel .swatch-option.active { border-color: var(--brand); box-shadow: 0 0 0 2px var(--brand-soft); }
.swatch { display: inline-block; width: 18px; height: 18px; border-radius: 4px; border: 2px solid currentColor; box-sizing: border-box; }
.bbox-opacity { width: 100%; }
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




def _prepare_pages_records(
    details: Sequence[dict],
    file_a: Path,
    file_b: Path,
    pages_root: Path,
    bundle_dir: Path,
    thumbs_dir: Path,
    t: dict[str, str],
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Copy thumbnails and assemble the per-page display records.

    progress_cb(done, total) is called once per processed row, so the caller
    can map row indices into its global progress percent space.
    """
    pages_records: list[dict] = []
    total_details = max(1, len(details))
    for row_idx, row in enumerate(details, start=1):
        seq = int(row["seq"])
        a_page = row.get("a_page")
        b_page = row.get("b_page")
        pair_name = row.get("pair_dir", f"{seq:03d}__A_{a_page or 'NA'}__B_{b_page or 'NA'}")
        pair_abs = pages_root / pair_name
        pair_rel = Path(os.path.relpath(pair_abs, bundle_dir))

        old_img = pair_rel / "a.png"
        new_img = pair_rel / "b.png"
        diff_img = pair_rel / "overlay.png"
        if not (pair_abs / "a.png").exists():
            old_img = pair_rel / "a_preview.png"
        if not (pair_abs / "b.png").exists():
            new_img = pair_rel / "b_preview.png"
        if not (pair_abs / "overlay.png").exists():
            diff_img = Path()

        thumb_old = Path("assets") / "thumbs" / f"{seq:03d}_old.jpg"
        thumb_new = Path("assets") / "thumbs" / f"{seq:03d}_new.jpg"
        thumb_diff = Path("assets") / "thumbs" / f"{seq:03d}_diff.jpg"
        old_src = pair_abs / old_img.name if old_img and old_img.name else None
        new_src = pair_abs / new_img.name if new_img and new_img.name else None
        diff_src = pair_abs / diff_img.name if diff_img and diff_img.name else None
        old_preview_src = pair_abs / "a_preview.png"
        new_preview_src = pair_abs / "b_preview.png"
        old_thumb_src = old_preview_src if old_preview_src.is_file() else old_src
        new_thumb_src = new_preview_src if new_preview_src.is_file() else new_src
        copy_thumb(old_thumb_src if old_thumb_src and old_thumb_src.is_file() else None, thumbs_dir / thumb_old.name)
        copy_thumb(new_thumb_src if new_thumb_src and new_thumb_src.is_file() else None, thumbs_dir / thumb_new.name)
        copy_thumb(diff_src if diff_src and diff_src.is_file() else None, thumbs_dir / thumb_diff.name)

        status, conf, content_status, moved = status_and_confidence(row)
        if row["status"] == "added":
            status_simple = "NEW"
            status_ru = t["status_new_sheet"]
            note = t["note_new_only"]
        elif row["status"] == "removed":
            status_simple = "CHANGED"
            status_ru = t["status_changed_short"]
            note = t["note_removed_in_b"]
        elif content_status == "UNCHANGED":
            status_simple = "UNCHANGED"
            status_ru = t["status_unchanged_short"]
            note = t["note_no_significant"]
        else:
            status_simple = "CHANGED"
            status_ru = t["status_changed_short"]
            fg = row.get("diff_foreground_percent")
            area = row.get("diff_area_mm2")
            n_zones = row.get("bboxes_count")
            max_region = row.get("max_region_area_mm2")
            sparse = bool(row.get("foreground_sparse") or False)
            if sparse or fg is None:
                note = t["note_visual_changes_sparse"].format(
                    area=float(area or 0),
                    n=int(n_zones or 0),
                    max=float(max_region or 0),
                )
            else:
                note = t["note_visual_changes"].format(
                    fg=float(fg),
                    area=float(area or 0),
                    n=int(n_zones or 0),
                    max=float(max_region or 0),
                )
        if row.get("ecc_failed"):
            note = f"{note} {t['note_ecc_failed']}"

        a_label = "-" if a_page is None else str(a_page)
        b_label = "-" if b_page is None else str(b_page)
        nav_label = f"({file_a.name} {t['nav_sheet_word']} {a_label}) - ({file_b.name} {t['nav_sheet_word']} {b_label})"
        pages_records.append(
            {
                "seq": seq,
                "b_index": b_page,
                "a_index": a_page,
                "status_raw": status,
                "status": status_simple,
                "status_ru": status_ru,
                "content_status": content_status,
                "match_confidence": conf,
                "moved": moved,
                "diff_metric": row.get("diff_percent"),
                "diff_area_px": row.get("diff_area_px"),
                "diff_area_mm2": row.get("diff_area_mm2"),
                "diff_foreground_metric": row.get("diff_foreground_percent"),
                "foreground_sparse": bool(row.get("foreground_sparse") or False),
                "added_area_mm2": row.get("added_area_mm2"),
                "removed_area_mm2": row.get("removed_area_mm2"),
                "max_region_area_mm2": row.get("max_region_area_mm2"),
                "change_level": row.get("change_level"),
                "bboxes_count": row.get("bboxes_count"),
                "page_settings": {
                    "high_dpi": row.get("high_dpi"),
                    "stroke_tol_px": row.get("stroke_tol_px"),
                    "diff_strictness": row.get("diff_strictness"),
                    "bbox_merge_gap_mm": row.get("bbox_merge_gap_mm"),
                    "bbox_merge_max_area_ratio": row.get("bbox_merge_max_area_ratio"),
                    "mixed_settings": row.get("mixed_settings"),
                },
                "score": row.get("score"),
                "notes": note,
                "nav_label": nav_label,
                "view_file": f"{seq:03d}.html",
                "assets": {
                    "thumb_old": str(thumb_old).replace("\\", "/") if (thumbs_dir / thumb_old.name).exists() else None,
                    "thumb_new": str(thumb_new).replace("\\", "/") if (thumbs_dir / thumb_new.name).exists() else None,
                    "thumb_diff": str(thumb_diff).replace("\\", "/") if (thumbs_dir / thumb_diff.name).exists() else None,
                    "hires_old": str(old_img).replace("\\", "/") if old_img and (pair_abs / old_img.name).exists() else None,
                    "hires_new": str(new_img).replace("\\", "/") if new_img and (pair_abs / new_img.name).exists() else None,
                    "hires_diff": str(diff_img).replace("\\", "/") if diff_img and (pair_abs / diff_img.name).exists() else None,
                },
            }
        )
        if progress_cb is not None:
            progress_cb(row_idx, total_details)
    return pages_records



def generate_html_report(
    run_dir: Path,
    file_a: Path,
    file_b: Path,
    details: Sequence[dict],
    high_dpi: int,
    stroke_tol_px: float,
    report_lang: str = "ru",
    progress_cb: Callable[[float, str], None] | None = None,
) -> Path:
    def emit(pct: float, msg: str) -> None:
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    lang = "en" if str(report_lang).lower().startswith("en") else "ru"
    i18n = HTML_REPORT_I18N
    t = i18n[lang]

    def tr(key: str) -> str:
        return html.escape(str(t.get(key, key)))

    def tr_attr(key: str) -> str:
        return html.escape(str(t.get(key, key)), quote=True)

    def i18n_span(key: str, cls: str | None = None) -> str:
        ru = html.escape(str(i18n["ru"].get(key, key)), quote=True)
        en = html.escape(str(i18n["en"].get(key, key)), quote=True)
        text = html.escape(str(i18n[lang].get(key, key)))
        cls_attr = f' class="{html.escape(cls, quote=True)}"' if cls else ""
        return f'<span{cls_attr} data-i18n-ru="{ru}" data-i18n-en="{en}">{text}</span>'

    def i18n_span_text(ru_text: str, en_text: str, cls: str | None = None) -> str:
        ru_attr = html.escape(ru_text, quote=True)
        en_attr = html.escape(en_text, quote=True)
        text = html.escape(en_text if lang == "en" else ru_text)
        cls_attr = f' class="{html.escape(cls, quote=True)}"' if cls else ""
        return f'<span{cls_attr} data-i18n-ru="{ru_attr}" data-i18n-en="{en_attr}">{text}</span>'

    def i18n_aria(ru_text: str, en_text: str, attr_name: str = "aria-label") -> str:
        ru_attr = html.escape(ru_text, quote=True)
        en_attr = html.escape(en_text, quote=True)
        current = html.escape(en_text if lang == "en" else ru_text, quote=True)
        return f'{attr_name}="{current}" data-i18n-aria-ru="{ru_attr}" data-i18n-aria-en="{en_attr}"'

    def i18n_attr(key: str, attr_name: str) -> str:
        ru = html.escape(str(i18n["ru"].get(key, key)), quote=True)
        en = html.escape(str(i18n["en"].get(key, key)), quote=True)
        return f'data-i18n-{attr_name}-ru="{ru}" data-i18n-{attr_name}-en="{en}"'

    def i18n_placeholder_text(ru_text: str, en_text: str) -> str:
        current = html.escape(en_text if lang == "en" else ru_text, quote=True)
        return (
            f'placeholder="{current}" data-i18n-placeholder-ru="{html.escape(ru_text, quote=True)}" '
            f'data-i18n-placeholder-en="{html.escape(en_text, quote=True)}"'
        )

    def title_attrs(ru_text: str, en_text: str) -> str:
        return f'data-title-ru="{html.escape(ru_text, quote=True)}" data-title-en="{html.escape(en_text, quote=True)}"'

    def title_text(ru_text: str, en_text: str) -> str:
        return html.escape(en_text if lang == "en" else ru_text)

    def format_duration_pair(seconds: float | None) -> tuple[str, str]:
        if seconds is None or seconds < 0:
            return "-", "-"
        total = int(round(seconds))
        minutes, secs = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}ч {minutes:02d}м {secs:02d}с", f"{hours}h {minutes:02d}m {secs:02d}s"
        if minutes:
            return f"{minutes}м {secs:02d}с", f"{minutes}m {secs:02d}s"
        return f"{secs}с", f"{secs}s"

    emit(2, t["progress_prepare_bundle"])
    final_bundle_dir = report_dir(run_dir)
    bundle_dir = internal_dir(run_dir) / f".report_{uuid4().hex}"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    pages_root = find_pages_dir(run_dir)
    if not pages_root.exists():
        raise RuntimeError(f"Не найдена папка страниц: {pages_root}")
    thumbs_dir = bundle_dir / "assets" / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(file_a) as da, fitz.open(file_b) as db:
        page_count_a = len(da)
        page_count_b = len(db)

    pages_records = _prepare_pages_records(
        details,
        file_a,
        file_b,
        pages_root,
        bundle_dir,
        thumbs_dir,
        t,
        progress_cb=lambda done, total: emit(6 + 58 * (done / total), t["progress_prepare_pages"].format(idx=done, total=total)),
    )

    pages_records.sort(key=lambda x: (x["b_index"] is None, x["b_index"] or 0, x["seq"]))
    for idx, p in enumerate(pages_records):
        p["view_ord"] = idx + 1
        p["prev_view_file"] = pages_records[idx - 1]["view_file"] if idx > 0 else None
        p["next_view_file"] = pages_records[idx + 1]["view_file"] if idx + 1 < len(pages_records) else None
        p["slider_file"] = f"cmp_{p['view_file']}" if p["assets"]["hires_old"] and p["assets"]["hires_new"] else None

    slider_records = [p for p in pages_records if p["slider_file"]]
    for idx, p in enumerate(slider_records):
        p["prev_slider_file"] = slider_records[idx - 1]["slider_file"] if idx > 0 else None
        p["next_slider_file"] = slider_records[idx + 1]["slider_file"] if idx + 1 < len(slider_records) else None
    slider_record_by_file = {p["slider_file"]: p for p in slider_records if p.get("slider_file")}
    first_slider_file = slider_records[0]["slider_file"] if slider_records else None
    last_slider_file = slider_records[-1]["slider_file"] if slider_records else None

    counts = {
        "unchanged": sum(1 for p in pages_records if p["status"] == "UNCHANGED"),
        "changed": sum(1 for p in pages_records if p["status"] == "CHANGED"),
        "new": sum(1 for p in pages_records if p["status"] == "NEW"),
        "removed": sum(1 for p in pages_records if p["status_raw"] == "REMOVED"),
        "moved": sum(1 for p in pages_records if p["moved"]),
    }
    mixed_precision_pages = [
        p for p in pages_records if (p.get("page_settings") or {}).get("mixed_settings")
    ]
    mixed_precision_seqs = [int(p["seq"]) for p in mixed_precision_pages]

    report_model = {
        "documents": {
            "a": {
                "name": file_a.name,
                "size_bytes": file_a.stat().st_size,
                "page_count": page_count_a,
            },
            "b": {
                "name": file_b.name,
                "size_bytes": file_b.stat().st_size,
                "page_count": page_count_b,
            },
        },
        "settings": {
            "dpi_thumb": PAGE_INFO_THUMB_DPI,
            "dpi_diff": high_dpi,
            "stroke_tolerance_px": stroke_tol_px,
            "threshold_unchanged_percent": UNCHANGED_DIFF_PERCENT,
            "bbox_detected_means_changed": True,
            "align_mode": "ECC_AFFINE",
            "report_lang": lang,
            "is_mixed_precision": bool(mixed_precision_pages),
            "mixed_precision_seqs": mixed_precision_seqs,
        },
        "summary": {"counts": counts},
        "pages": pages_records,
    }
    (bundle_dir / "report.json").write_text(json.dumps(report_model, ensure_ascii=False, indent=2), encoding="utf-8")

    status_label_keys = {
        "CHANGED": "status_col_changed",
        "UNCHANGED": "status_col_unchanged",
        "ADDED": "status_col_added",
        "REMOVED": "status_col_removed",
    }
    level_label_keys = {
        "MAJOR": "level_major",
        "MODERATE": "level_moderate",
        "MINOR": "level_minor",
        "UNCHANGED": "level_unchanged",
    }
    status_badge_classes = {
        "CHANGED": "st-changed",
        "UNCHANGED": "st-unchanged",
        "ADDED": "st-added",
        "REMOVED": "st-removed",
    }
    level_badge_classes = {
        "MAJOR": "lv-major",
        "MODERATE": "lv-moderate",
        "MINOR": "lv-minor",
        "UNCHANGED": "lv-unchanged",
    }

    def report_tags_for_page(page: dict) -> tuple[str, str]:
        status_raw = str(page.get("status_raw") or "")
        if status_raw == "ADDED":
            return "ADDED", ""
        elif status_raw == "REMOVED":
            return "REMOVED", ""
        return level_to_report_tags(page.get("change_level"))

    def status_badge_html(status_tag: str) -> str:
        cls = status_badge_classes.get(status_tag, "st-changed")
        key = status_label_keys.get(status_tag)
        label = i18n_span(key) if key else html.escape(status_tag)
        return f'<span class="badge {cls}">{label}</span>'

    def level_badge_html(level_tag: str) -> str:
        if not level_tag:
            return "—"
        cls = level_badge_classes.get(level_tag, "lv-major")
        key = level_label_keys.get(level_tag)
        label = i18n_span(key) if key else html.escape(level_tag)
        return f'<span class="badge {cls}">{label}</span>'

    def is_mixed_precision_page(page: dict) -> bool:
        return bool((page.get("page_settings") or {}).get("mixed_settings"))

    def page_precision_text(page: dict) -> tuple[str, str]:
        settings = page.get("page_settings") or {}
        mixed = settings.get("mixed_settings") or {}
        dpi = settings.get("high_dpi") or mixed.get("dpi") or high_dpi
        tol = settings.get("stroke_tol_px") if settings.get("stroke_tol_px") is not None else mixed.get("stroke_tol_px")
        strictness = settings.get("diff_strictness") or mixed.get("diff_strictness") or "-"
        merge_gap = settings.get("bbox_merge_gap_mm")
        if merge_gap is None:
            merge_gap = mixed.get("bbox_merge_gap_mm")
        try:
            merge_gap_num = float(merge_gap or 0.0)
        except (TypeError, ValueError):
            merge_gap_num = 0.0
        tol_txt = "-" if tol is None else f"{float(tol):g}px"
        merge_ru = "merge выкл." if merge_gap_num <= 0 else f"merge {merge_gap_num:g} мм"
        merge_en = "merge off" if merge_gap_num <= 0 else f"merge {merge_gap_num:g} mm"
        return (
            f"DPI {dpi} · {strictness} · tol {tol_txt} · {merge_ru}",
            f"DPI {dpi} · {strictness} · tol {tol_txt} · {merge_en}",
        )

    def precision_badge_html(page: dict) -> str:
        if not is_mixed_precision_page(page):
            return ""
        ru_text, en_text = page_precision_text(page)
        title = title_text(ru_text, en_text)
        return (
            f'<span class="badge precision-badge" title="{html.escape(title, quote=True)}">'
            f'{i18n_span_text("Пересчитан", "Custom precision")}</span>'
        )

    def badge_class(status: str) -> str:
        return {
            "UNCHANGED": "ok",
            "CHANGED": "warn",
            "NEW": "add",
            "ADDED": "add",
            "REMOVED": "warn",
        }.get(status, "warn")

    def heat_class(fg: float | None) -> str:
        if fg is None or fg < FG_MINOR_PERCENT:
            return "heat-ok"
        if fg < FG_MODERATE_PERCENT:
            return "heat-warn"
        return "heat-bad"

    def fg_meter_html(fg: float | None, sparse: bool = False) -> str:
        if fg is None:
            return '<span class="faint">—</span>'
        if sparse:
            return '<span class="faint">—</span>'
        # Scale: 20% FG saturates the bar (20 * 5 = 100).
        width = fg * 5.0
        return (
            '<div class="diff-wrap">'
            '<div class="diff-bar">'
            f'<div class="diff-fill {heat_class(fg)}" style="width:clamp(2%, {width:.3f}%, 100%);"></div>'
            "</div>"
            f'<span class="diff-num">{fg:.2f}%</span>'
            "</div>"
        )

    def metric_percent_html(value: float | None) -> str:
        if value is None:
            return '<span class="faint">—</span>'
        return f'<span class="diff-num">{float(value):.2f}%</span>'

    def metric_area_html(value: float | None) -> str:
        if value is None:
            return '<span class="faint">—</span>'
        return f'<span class="diff-num">{float(value):.1f}</span>'

    def preview_tile(src: str | None, label: str, alt: str) -> str:
        label_html = i18n_span_text(label, label, "pv-label")
        if src:
            media = f'<img loading="lazy" src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}"/>'
        else:
            media = '<div class="ph">—</div>'
        return f'<div class="pv-tile">{label_html}{media}</div>'

    matrix_rows: list[str] = []
    changed_cnt = 0
    added_cnt = 0
    removed_cnt = 0
    unchanged_cnt = 0

    for p in pages_records:
        status_tag, level_tag = report_tags_for_page(p)
        p["_status_tag"] = status_tag
        p["_level_tag"] = level_tag
        if status_tag == "CHANGED":
            changed_cnt += 1
        elif status_tag == "ADDED":
            added_cnt += 1
        elif status_tag == "REMOVED":
            removed_cnt += 1
        elif status_tag == "UNCHANGED":
            unchanged_cnt += 1

        a_idx = "—" if p["a_index"] is None else f"A{p['a_index']}"
        b_idx = "—" if p["b_index"] is None else f"B{p['b_index']}"
        seq_txt = str(p["seq"])
        diff_val = None if p.get("diff_metric") is None else float(p["diff_metric"])
        fg_diff_val = None if p.get("diff_foreground_metric") is None else float(p["diff_foreground_metric"])
        area_mm2_val = None if p.get("diff_area_mm2") is None else float(p["diff_area_mm2"])
        boxes_txt = "—" if p.get("bboxes_count") is None else str(int(p["bboxes_count"]))
        fg_sparse = bool(p.get("foreground_sparse") or False)
        href = f"views/{p['view_file']}"

        thumb_old = p["assets"].get("thumb_old")
        thumb_new = p["assets"].get("thumb_new")
        thumb_diff = p["assets"].get("thumb_diff")
        preview_html = (
            "<div class='pv'>"
            f"{preview_tile(thumb_old, 'OLD', 'old preview')}"
            f"{preview_tile(thumb_new, 'NEW', 'new preview')}"
            f"{preview_tile(thumb_diff, 'DIFF', 'diff preview')}"
            "</div>"
        )
        status_search = str(i18n[lang].get(status_label_keys.get(status_tag, ""), status_tag))
        level_search = str(i18n[lang].get(level_label_keys.get(level_tag, ""), level_tag))
        precision_badge = precision_badge_html(p)
        _precision_ru, precision_en = page_precision_text(p)
        precision_search = "custom precision пересчитан " + (precision_en if is_mixed_precision_page(p) else "")
        row_search = f"{seq_txt} {a_idx} {b_idx} {status_tag} {level_tag} {status_search} {level_search} {precision_search}".lower()
        matrix_rows.append(
            f"<tr class='mx-row' data-status='{status_tag}' data-level='{level_tag or 'NONE'}' "
            f"data-search='{html.escape(row_search, quote=True)}' data-href='{html.escape(href, quote=True)}'>"
            f"<td class='td-seq seq-col'>{html.escape(seq_txt)}</td>"
            f"<td class='td-map map-cell'>{html.escape(a_idx)}{report_icon('arrow-right', 'ic map-icon', 14)}{html.escape(b_idx)}</td>"
            f"<td class='td-status'>{status_badge_html(status_tag)}{precision_badge}</td>"
            f"<td class='td-level'>{level_badge_html(level_tag)}</td>"
            f"<td class='td-fg diff-cell'>{fg_meter_html(fg_diff_val, sparse=fg_sparse)}</td>"
            f"<td class='td-diff'>{metric_percent_html(diff_val)}</td>"
            f"<td class='td-area'>{metric_area_html(area_mm2_val)}</td>"
            f"<td class='td-boxes'>{html.escape(boxes_txt)}</td>"
            f"<td class='td-preview'>{preview_html}</td>"
            f"<td class='td-open'><a class='open-link' href='{html.escape(href, quote=True)}' "
            f"{i18n_aria('Открыть сравнение листа', 'Open sheet compare')} title='{tr_attr('open_sheet_title')}'>{report_icon('arrow-up-right', size=16)}</a></td>"
            "</tr>"
        )

    total_pages = len(pages_records)
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elapsed_sum = sum(float(row.get("elapsed_sec") or 0.0) for row in details)
    duration_ru, duration_en = format_duration_pair(elapsed_sum if elapsed_sum > 0 else None)
    if mixed_precision_seqs:
        seqs_txt = ", ".join(map(str, mixed_precision_seqs))
        dpi_meta_ru = f"DPI: {high_dpi} базовый · смешанная точность: листы {seqs_txt}"
        dpi_meta_en = f"DPI: {high_dpi} base · mixed precision: sheets {seqs_txt}"
    else:
        dpi_meta_ru = f"DPI: {high_dpi}"
        dpi_meta_en = f"DPI: {high_dpi}"
    run_meta = i18n_span_text(
        f"Дата: {run_timestamp} · длительность: {duration_ru} · {dpi_meta_ru} · stroke tol: {stroke_tol_px:g}px",
        f"Date: {run_timestamp} · duration: {duration_en} · {dpi_meta_en} · stroke tol: {stroke_tol_px:g}px",
    )
    old_doc_meta = i18n_span_text(f"Doc A · {page_count_a} листов · ред. ?", f"Doc A · {page_count_a} sheets · rev. ?")
    new_doc_meta = i18n_span_text(f"Doc B · {page_count_b} листов · ред. ?", f"Doc B · {page_count_b} sheets · rev. ?")
    footer_text = i18n_span_text(
        f"Создано PDFCompare Local · собрано локально · {run_timestamp}",
        f"Created by PDFCompare Local · built locally · {run_timestamp}",
    )
    csv_link = None
    if page_map_csv_path(run_dir).exists():
        csv_link = str(Path(os.path.relpath(page_map_csv_path(run_dir), bundle_dir))).replace("\\", "/")
    zip_link = None
    for candidate in (internal_dir(run_dir) / "report_bundle.zip", run_dir / "report_bundle.zip"):
        if candidate.exists():
            zip_link = str(Path(os.path.relpath(candidate, bundle_dir))).replace("\\", "/")
            break
    export_items = [
        f'<a href="report.json" download>{i18n_span_text("Скачать report.json", "Download report.json")}</a>'
    ]
    if csv_link:
        export_items.append(
            f'<a href="{html.escape(csv_link, quote=True)}" download>{i18n_span_text("Скачать CSV", "Download CSV")}</a>'
        )
    if zip_link:
        export_items.append(
            f'<a href="{html.escape(zip_link, quote=True)}" download>{i18n_span_text("Скачать ZIP-бандл", "Download ZIP bundle")}</a>'
        )
    export_menu_html = "".join(export_items)
    sun_icon_js = json.dumps(report_icon("sun", size=18))
    moon_icon_js = json.dumps(report_icon("moon", size=18))
    index_title_ru = "Сводка сравнения PDF — матрица изменений"
    index_title_en = "PDF compare summary — change matrix"

    summary_html = f"""<!doctype html>
<html lang="{lang}" {title_attrs(index_title_ru, index_title_en)}>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title_text(index_title_ru, index_title_en)}</title>
  <script>
    try {{
      const savedTheme = localStorage.getItem('pdfcompare.theme');
      if (savedTheme === 'dark') document.documentElement.dataset.theme = 'dark';
      const savedLang = localStorage.getItem('pdfcompare.lang');
      if (savedLang === 'en' || savedLang === 'ru') document.documentElement.lang = savedLang;
    }} catch (e) {{}}
  </script>
  <style>
{REPORT_CSS_TOKENS}
{CSS_INDEX}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">{report_icon("git-compare", size=20)}</div>
        <div>
          <h1>{i18n_span_text("PDF Compare — матрица изменений", "PDF Compare — Change Matrix")}</h1>
          <div class="subtitle">{i18n_span_text("Локальное сравнение PDF без облака", "Local PDF comparison without cloud processing")}</div>
        </div>
      </div>
      <div class="top-actions">
        <div class="lang-switch" {i18n_aria("Язык", "Language")}>
          <button type="button" data-lang="ru">RU</button>
          <button type="button" data-lang="en">EN</button>
        </div>
        <button id="themeToggle" class="btn icon-only" type="button" {i18n_aria("Переключить тему", "Toggle theme")}>{report_icon("moon", size=18)}</button>
      </div>
    </header>

    <section class="docs" {i18n_aria("Документы", "Documents")}>
      <article class="doc-card old">
        {i18n_span_text("OLD", "OLD", "doc-pill")}
        <div>
          <div class="doc-name">{html.escape(file_a.name)}</div>
          <div class="doc-meta">{old_doc_meta}</div>
        </div>
      </article>
      <div class="doc-arrow">{report_icon("arrow-right", size=20)}</div>
      <article class="doc-card new">
        {i18n_span_text("NEW", "NEW", "doc-pill")}
        <div>
          <div class="doc-name">{html.escape(file_b.name)}</div>
          <div class="doc-meta">{new_doc_meta}</div>
        </div>
      </article>
    </section>
    <p class="run-meta">{run_meta}</p>

    <section class="kpi" {i18n_aria("Сводка", "Summary")}>
      <button type="button" class="kpi-card" data-kind="status" data-value="CHANGED" aria-pressed="false">
        <span class="kpi-ico">{report_icon("alert-circle", size=20)}</span>
        <span><span class="kpi-label">{i18n_span_text("ИЗМЕНЕНЫ", "CHANGED")}</span><span class="kpi-value"><strong>{changed_cnt}</strong><span class="kpi-context">{i18n_span_text(f"из {total_pages}", f"of {total_pages}")}</span></span></span>
      </button>
      <button type="button" class="kpi-card" data-kind="status" data-value="ADDED" aria-pressed="false">
        <span class="kpi-ico">{report_icon("plus-circle", size=20)}</span>
        <span><span class="kpi-label">{i18n_span_text("ДОБАВЛЕНЫ", "ADDED")}</span><span class="kpi-value"><strong>{added_cnt}</strong><span class="kpi-context">{i18n_span_text(f"из {total_pages}", f"of {total_pages}")}</span></span></span>
      </button>
      <button type="button" class="kpi-card" data-kind="status" data-value="REMOVED" aria-pressed="false">
        <span class="kpi-ico">{report_icon("minus-circle", size=20)}</span>
        <span><span class="kpi-label">{i18n_span_text("УДАЛЕНЫ", "REMOVED")}</span><span class="kpi-value"><strong>{removed_cnt}</strong><span class="kpi-context">{i18n_span_text(f"из {total_pages}", f"of {total_pages}")}</span></span></span>
      </button>
      <button type="button" class="kpi-card" data-kind="status" data-value="UNCHANGED" aria-pressed="false">
        <span class="kpi-ico">{report_icon("check-circle", size=20)}</span>
        <span><span class="kpi-label">{i18n_span_text("БЕЗ ИЗМЕНЕНИЙ", "UNCHANGED")}</span><span class="kpi-value"><strong>{unchanged_cnt}</strong><span class="kpi-context">{i18n_span_text(f"из {total_pages}", f"of {total_pages}")}</span></span></span>
      </button>
    </section>

    <section class="matrix-tools">
      <label class="search-wrap">
        {i18n_span("search_sheet", "sr-only")}
        {report_icon("search", size=16)}
        <input id="sheetSearch" class="search" {i18n_attr("search_sheet", "placeholder")} placeholder="{tr_attr("search_sheet")}"/>
      </label>
      <div class="dropdown" data-dropdown>
        <button id="exportBtn" class="btn" type="button" aria-haspopup="menu" aria-expanded="false">{report_icon("download", size=16)}{i18n_span_text("Экспорт", "Export")}<span class="caret">▾</span></button>
        <div class="dropdown-menu" role="menu">{export_menu_html}</div>
      </div>
    </section>

    <section class="matrix" {i18n_aria("Матрица изменений", "Change matrix")}>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>A {report_icon("arrow-right", "ic map-icon", 14)} B</th>
            <th>{i18n_span_text("Статус", "Status")}</th>
            <th>{i18n_span_text("Уровень", "Level")}</th>
            <th>{i18n_span_text("Заполнено %", "Drawn %")}</th>
            <th>{i18n_span_text("Лист %", "Sheet %")}</th>
            <th>mm²</th>
            <th>Δ</th>
            <th>{i18n_span_text("Превью", "Preview")}</th>
            <th>{i18n_span_text("Открыть", "Open")}</th>
          </tr>
        </thead>
        <tbody id="mxBody">
          {''.join(matrix_rows)}
        </tbody>
      </table>
      <div id="emptyMsg" class="empty" style="display:none;">{i18n_span("empty_filter")}</div>
    </section>

    <details class="legend">
      <summary>{i18n_span_text("Легенда и пороги", "Legend and thresholds")}</summary>
      <div class="legend-body">
        <div class="legend-row">{status_badge_html("CHANGED")}<span>{i18n_span_text("лист содержит визуальные изменения", "sheet has visual changes")}</span></div>
        <div class="legend-row">{status_badge_html("ADDED")}<span>{i18n_span("legend_added_desc")}</span></div>
        <div class="legend-row">{status_badge_html("REMOVED")}<span>{i18n_span("legend_removed_desc")}</span></div>
        <div class="legend-row">{status_badge_html("UNCHANGED")}<span>{i18n_span_text("существенные изменения не обнаружены", "no significant changes detected")}</span></div>
        <div class="legend-row">{level_badge_html("MAJOR")}<span>{i18n_span_text("≥ 20% заполненного - MAJOR", "≥ 20% drawn - MAJOR")}</span></div>
        <div class="legend-row">{level_badge_html("MODERATE")}<span>{i18n_span_text("≥ 8% заполненного - MODERATE", "≥ 8% drawn - MODERATE")}</span></div>
        <div class="legend-row">{level_badge_html("MINOR")}<span>{i18n_span_text("≥ 1% заполненного - MINOR", "≥ 1% drawn - MINOR")}</span></div>
        <div class="legend-row">{level_badge_html("UNCHANGED")}<span>{i18n_span_text("без зон изменений - UNCHANGED", "no change zones - UNCHANGED")}</span></div>
      </div>
    </details>

    <footer class="footer">{footer_text}</footer>
  </div>

  <script>
    const kpis = [...document.querySelectorAll('.kpi-card')];
    const rows = [...document.querySelectorAll('#mxBody tr.mx-row')];
    const searchInput = document.getElementById('sheetSearch');
    const emptyMsg = document.getElementById('emptyMsg');
    const langButtons = [...document.querySelectorAll('[data-lang]')];
    const themeBtn = document.getElementById('themeToggle');
    const sunIcon = {sun_icon_js};
    const moonIcon = {moon_icon_js};
    let statusFilter = 'ALL';

    function applyTheme(theme) {{
      const next = theme === 'dark' ? 'dark' : 'light';
      if (next === 'dark') {{
        document.documentElement.dataset.theme = 'dark';
        themeBtn.innerHTML = sunIcon;
      }} else {{
        delete document.documentElement.dataset.theme;
        themeBtn.innerHTML = moonIcon;
      }}
      try {{ localStorage.setItem('pdfcompare.theme', next); }} catch (e) {{}}
    }}

    function applyLang(nextLang, persist = true) {{
      const next = nextLang === 'en' ? 'en' : 'ru';
      const root = document.documentElement;
      document.documentElement.lang = next;
      if (root.dataset.titleRu && root.dataset.titleEn) {{
        document.title = next === 'en' ? root.dataset.titleEn : root.dataset.titleRu;
      }}
      document.querySelectorAll('[data-i18n-ru]').forEach(el => {{
        el.textContent = next === 'en' ? el.dataset.i18nEn : el.dataset.i18nRu;
      }});
      document.querySelectorAll('[data-i18n-placeholder-ru]').forEach(el => {{
        el.setAttribute('placeholder', next === 'en' ? el.dataset.i18nPlaceholderEn : el.dataset.i18nPlaceholderRu);
      }});
      document.querySelectorAll('[data-i18n-aria-ru]').forEach(el => {{
        el.setAttribute('aria-label', next === 'en' ? el.dataset.i18nAriaEn : el.dataset.i18nAriaRu);
      }});
      langButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.lang === next));
      if (persist) {{
        try {{ localStorage.setItem('pdfcompare.lang', next); }} catch (e) {{}}
      }}
    }}

    function updateFilterUi() {{
      kpis.forEach(kpi => {{
        const active = statusFilter === kpi.dataset.value;
        kpi.classList.toggle('active', active);
        kpi.setAttribute('aria-pressed', active ? 'true' : 'false');
      }});
    }}

    function applyFilters() {{
      const q = searchInput.value.trim().toLowerCase();
      let visible = 0;
      rows.forEach(row => {{
        const st = row.dataset.status;
        const text = row.dataset.search || '';
        let ok = true;
        if (statusFilter !== 'ALL') ok = st === statusFilter;
        if (ok && q) ok = text.includes(q);
        row.style.display = ok ? '' : 'none';
        if (ok) visible += 1;
      }});
      emptyMsg.style.display = visible ? 'none' : 'block';
      updateFilterUi();
    }}

    function handleKpiFilter(control) {{
      const value = control.dataset.value || '';
      statusFilter = statusFilter === value ? 'ALL' : value;
      applyFilters();
    }}

    kpis.forEach(control => {{
      control.addEventListener('click', () => handleKpiFilter(control));
    }});
    searchInput.addEventListener('input', applyFilters);
    rows.forEach(row => {{
      row.addEventListener('click', (e) => {{
        const target = e.target;
        if (target && target.closest('a')) return;
        const href = row.dataset.href;
        if (href) window.location.href = href;
      }});
    }});
    document.querySelectorAll('[data-dropdown]').forEach(dropdown => {{
      const btn = dropdown.querySelector('button');
      btn.addEventListener('click', (e) => {{
        e.stopPropagation();
        const open = dropdown.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      }});
    }});
    document.addEventListener('click', () => {{
      document.querySelectorAll('[data-dropdown].open').forEach(dropdown => {{
        dropdown.classList.remove('open');
        const btn = dropdown.querySelector('button');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      }});
    }});
    langButtons.forEach(btn => btn.addEventListener('click', () => applyLang(btn.dataset.lang)));
    themeBtn.addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
    let savedTheme = 'light';
    try {{ savedTheme = localStorage.getItem('pdfcompare.theme') || (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'); }} catch (e) {{}}
    applyTheme(savedTheme);
    let savedLang = document.documentElement.lang === 'en' ? 'en' : 'ru';
    try {{ savedLang = localStorage.getItem('pdfcompare.lang') || savedLang; }} catch (e) {{}}
    applyLang(savedLang, false);
    applyFilters();
  </script>
</body>
</html>
"""
    (bundle_dir / "index.html").write_text(summary_html, encoding="utf-8")

    views_dir = bundle_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)

    nav_items = []
    for p in pages_records:
        nav_a = "—" if p["a_index"] is None else f"A{p['a_index']}"
        nav_b = "—" if p["b_index"] is None else f"B{p['b_index']}"
        nav_short = f"{p['seq']} · {nav_a} -> {nav_b}"
        search_label = (
            f"{nav_short} {p['nav_label']} {p['status_ru']} {p.get('_status_tag', '')} "
            f"{p.get('_level_tag', '')} {p['b_index'] or ''} {p['a_index'] or ''}"
        ).lower()
        nav_status = (
            report_icon("check-circle", "ic nav-ok", 16)
            if p.get("_status_tag") == "UNCHANGED"
            else status_badge_html(str(p.get("_status_tag") or "CHANGED"))
        )
        nav_items.append(
            f"<a class='nav-item' data-label='{html.escape(search_label, quote=True)}' "
            f"title='{html.escape(p['nav_label'], quote=True)}' href='{html.escape(p['view_file'], quote=True)}'>"
            f"<span class='nav-main'>{html.escape(nav_short)}</span>{nav_status}</a>"
        )
    nav_html = "".join(nav_items)

    total_views = max(1, len(pages_records))
    for view_idx, p in enumerate(pages_records, start=1):
        a_idx = "-" if p["a_index"] is None else str(p["a_index"])
        b_idx = "-" if p["b_index"] is None else str(p["b_index"])
        diff_txt = "-" if p["diff_metric"] is None else f'{p["diff_metric"]:.3f}%'
        fg_diff_txt = "-" if p.get("diff_foreground_metric") is None else f'{float(p["diff_foreground_metric"]):.2f}%'
        area_txt = "-" if p.get("diff_area_mm2") is None else f'{float(p["diff_area_mm2"]):.1f} mm²'
        old_src = f"../{p['assets']['hires_old']}" if p["assets"]["hires_old"] else None
        new_src = f"../{p['assets']['hires_new']}" if p["assets"]["hires_new"] else None
        diff_src = f"../{p['assets']['hires_diff']}" if p["assets"]["hires_diff"] else None
        prev_link = p["prev_view_file"]
        next_link = p["next_view_file"]
        slider_file = p["slider_file"]
        pair_rel = None
        bboxes_data: list[dict] = []
        if p["assets"]["hires_old"]:
            pair_rel = Path(p["assets"]["hires_old"]).parent
        elif p["assets"]["hires_new"]:
            pair_rel = Path(p["assets"]["hires_new"]).parent
        if pair_rel is not None and (bundle_dir / pair_rel / "bboxes.json").exists():
            try:
                bboxes_data = json.loads((bundle_dir / pair_rel / "bboxes.json").read_text(encoding="utf-8"))
            except Exception:
                bboxes_data = []

        status_tag = str(p.get("_status_tag") or "CHANGED")
        level_tag = str(p.get("_level_tag") or "")
        boxes_text = "—" if p.get("bboxes_count") is None else str(int(p["bboxes_count"]))
        detail_precision_badge = precision_badge_html(p)
        precision_ru, precision_en = page_precision_text(p)
        detail_precision_text = (
            f'<span class="muted">{i18n_span_text(precision_ru, precision_en)}</span>'
            if is_mixed_precision_page(p)
            else ""
        )

        def figure_html(src: str | None, label: str, cls: str = "", bbox_off_src: str | None = None) -> str:
            data_attrs = ""
            if bbox_off_src and src:
                data_attrs = (
                    f' data-bbox-on-src="{html.escape(src, quote=True)}"'
                    f' data-bbox-off-src="{html.escape(bbox_off_src, quote=True)}"'
                )
            media = (
                f'<img loading="lazy" src="{html.escape(src, quote=True)}" alt="{html.escape(label.lower(), quote=True)} sheet"{data_attrs}/>'
                if src
                else f'<div class="noimg">{i18n_span("no_data")}</div>'
            )
            label_attr = html.escape(label, quote=True)
            return (
                f'<figure class="{html.escape(cls, quote=True)}">'
                f'<span class="cap-pill" data-i18n-ru="{label_attr}" data-i18n-en="{label_attr}">{html.escape(label)}</span>'
                f"{media}</figure>"
            )

        external_items: list[str] = []
        for label, ru_label, en_label, src in (
            ("OLD", "Старый", "Old", old_src),
            ("NEW", "Новый", "New", new_src),
            ("DIFF", "Отличия", "Diff", diff_src),
        ):
            if src:
                external_items.append(
                    f'<button type="button" class="open-ext" data-src="{html.escape(src, quote=True)}">'
                    f'<span>{i18n_span_text(ru_label, en_label)}</span><span class="badge lv-empty">{label}</span></button>'
                )
        external_menu = "".join(external_items) if external_items else f'<button type="button" disabled>{i18n_span("no_data")}</button>'
        prev_top = (
            f'<a class="btn" href="{html.escape(prev_link, quote=True)}">{report_icon("chevron-left", size=16)}{i18n_span_text("Назад", "Previous")}</a>'
            if prev_link
            else f'<button class="btn" type="button" disabled>{report_icon("chevron-left", size=16)}{i18n_span_text("Назад", "Previous")}</button>'
        )
        next_top = (
            f'<a class="btn primary" href="{html.escape(next_link, quote=True)}">{i18n_span_text("Вперёд", "Next")}{report_icon("chevron-right", size=16)}</a>'
            if next_link
            else f'<button class="btn primary" type="button" disabled>{i18n_span_text("Вперёд", "Next")}{report_icon("chevron-right", size=16)}</button>'
        )
        primary_slider_action = (
            f'<a class="btn primary btn-xl btn-slider" id="primarySliderLink" href="{html.escape(slider_file, quote=True)}">'
            f'{report_icon("arrow-left-right", size=20)}'
            f'{i18n_span_text("Открыть в слайдере", "Open in slider")}'
            f'<span class="kbd">{i18n_span_text("Enter", "Enter")}</span></a>'
            if slider_file
            else f'<button class="btn primary btn-xl btn-slider" type="button" disabled>'
            f'{report_icon("arrow-left-right", size=20)}'
            f'{i18n_span_text("Слайдер недоступен", "Slider unavailable")}</button>'
        )
        view_title_ru = f"Лист {view_idx} / {len(pages_records)} — PDFCompare"
        view_title_en = f"Sheet {view_idx} / {len(pages_records)} — PDFCompare"
        detail_html = f"""<!doctype html>
<html lang="{lang}" {title_attrs(view_title_ru, view_title_en)}>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title_text(view_title_ru, view_title_en)}</title>
  <script>
    try {{
      const savedTheme = localStorage.getItem('pdfcompare.theme');
      if (savedTheme === 'dark') document.documentElement.dataset.theme = 'dark';
      const savedLang = localStorage.getItem('pdfcompare.lang');
      if (savedLang === 'en' || savedLang === 'ru') document.documentElement.lang = savedLang;
    }} catch (e) {{}}
  </script>
  <style>
{REPORT_CSS_TOKENS}
{CSS_VIEW}
  </style>
</head>
<body>
  <header class="toolbar" {i18n_aria("Навигация по листу", "Sheet navigation")}>
    <div><a class="btn ghost" href="../index.html">{report_icon("arrow-left", size=16)}{i18n_span_text("К матрице изменений", "Back to change matrix")}</a></div>
    <div class="toolbar-center">
      <span class="sheet-title">{i18n_span_text(f"Лист {view_idx} из {len(pages_records)}", f"Sheet {view_idx} of {len(pages_records)}")}</span>
      {status_badge_html(status_tag)}
      {level_badge_html(level_tag) if level_tag else ""}
      {detail_precision_badge}
      <span class="muted">{i18n_span_text(f"· заполнено {fg_diff_txt} · лист {diff_txt} · {area_txt} · {boxes_text} областей", f"· drawn {fg_diff_txt} · sheet {diff_txt} · {area_txt} · {boxes_text} areas")}</span>
      {detail_precision_text}
    </div>
    <div class="toolbar-right">
      {prev_top}
      {next_top}
      <span class="muted">{i18n_span_text(f"Лист {view_idx}/{len(pages_records)}", f"Sheet {view_idx}/{len(pages_records)}")}</span>
    </div>
  </header>

  <div class="body-grid">
    <aside class="side">
      <div class="side-summary">
        <div class="side-summary-title">{i18n_span_text("Сводка", "Summary")}</div>
        <ul class="side-summary-list">
          <li><span class="dot dot-changed"></span><span>{i18n_span_text("Изменены", "Changed")}</span><b>{changed_cnt}</b></li>
          <li><span class="dot dot-added"></span><span>{i18n_span_text("Добавлены", "Added")}</span><b>{added_cnt}</b></li>
          <li><span class="dot dot-removed"></span><span>{i18n_span_text("Удалены", "Removed")}</span><b>{removed_cnt}</b></li>
          <li><span class="dot dot-unchanged"></span><span>{i18n_span_text("Без изменений", "Unchanged")}</span><b>{unchanged_cnt}</b></li>
        </ul>
      </div>
      <div class="section-title">{i18n_span_text("НАВИГАЦИЯ ПО ЛИСТАМ", "SHEET NAVIGATION")}</div>
      <label class="search-wrap">
        {i18n_span("search_sheet", "sr-only")}
        {report_icon("search", size=16)}
        <input id="search" class="search" {i18n_attr("search_sheet", "placeholder")} placeholder="{tr_attr("search_sheet")}"/>
      </label>
      <div id="navList" class="nav-list">{nav_html}</div>
    </aside>

    <main class="view-area">
      <div class="view-tools">
        <div class="view-primary">
          {primary_slider_action}
          <div class="primary-hint">{i18n_span_text("Главный режим просмотра — split-view с движком сравнения", "Primary view — side-by-side compare slider")}</div>
        </div>
        <div class="view-modes">
          <span class="view-modes-label">{i18n_span_text("Другой режим:", "Other mode:")}</span>
          <div class="tabs" role="tablist" {i18n_aria("Режим просмотра", "View mode")}>
            <button type="button" class="tab active" data-mode="split">{i18n_span_text("Сравнение", "Split")}</button>
            <button type="button" class="tab" data-mode="old">{i18n_span_text("OLD", "OLD")}</button>
            <button type="button" class="tab" data-mode="new">{i18n_span_text("NEW", "NEW")}</button>
            <button type="button" class="tab" data-mode="diff">{i18n_span_text("DIFF", "DIFF")}</button>
          </div>
          <div class="dropdown" data-dropdown>
            <button class="btn" type="button" aria-haspopup="menu" aria-expanded="false">{report_icon("external-link", size=16)}{i18n_span_text("Открыть внешне", "Open externally")}</button>
            <div class="dropdown-menu" role="menu">{external_menu}</div>
          </div>
        </div>
      </div>

      <section class="preview-mode active" data-panel="split">
        <div class="split-grid">
          <div class="left-stack">
            {figure_html(old_src, "OLD")}
            {figure_html(new_src, "NEW")}
          </div>
          <div class="diff-view">{figure_html(diff_src, "DIFF", "diff-figure", new_src)}</div>
        </div>
      </section>
      <section class="preview-mode" data-panel="old"><div class="single-view">{figure_html(old_src, "OLD")}</div></section>
      <section class="preview-mode" data-panel="new"><div class="single-view">{figure_html(new_src, "NEW")}</div></section>
      <section class="preview-mode" data-panel="diff"><div class="single-view">{figure_html(diff_src, "DIFF", "", new_src)}</div></section>
    </main>
  </div>

  <script>
    const current = "{html.escape(p['view_file'], quote=True)}";
    const primarySliderHref = {json.dumps(slider_file or "")};
    document.querySelectorAll('.nav-item').forEach(a => {{
      const href = a.getAttribute('href');
      if (href === current) a.classList.add('current');
    }});
    const inp = document.getElementById('search');
    const items = [...document.querySelectorAll('.nav-item')];
    inp.addEventListener('input', () => {{
      const q = inp.value.trim().toLowerCase();
      items.forEach(it => {{
        it.style.display = !q || it.dataset.label.includes(q) ? '' : 'none';
      }});
    }});
    function applyLang(nextLang) {{
      const next = nextLang === 'en' ? 'en' : 'ru';
      const root = document.documentElement;
      document.documentElement.lang = next;
      if (root.dataset.titleRu && root.dataset.titleEn) {{
        document.title = next === 'en' ? root.dataset.titleEn : root.dataset.titleRu;
      }}
      document.querySelectorAll('[data-i18n-ru]').forEach(el => {{
        el.textContent = next === 'en' ? el.dataset.i18nEn : el.dataset.i18nRu;
      }});
      document.querySelectorAll('[data-i18n-placeholder-ru]').forEach(el => {{
        el.setAttribute('placeholder', next === 'en' ? el.dataset.i18nPlaceholderEn : el.dataset.i18nPlaceholderRu);
      }});
      document.querySelectorAll('[data-i18n-aria-ru]').forEach(el => {{
        el.setAttribute('aria-label', next === 'en' ? el.dataset.i18nAriaEn : el.dataset.i18nAriaRu);
      }});
    }}
    try {{ applyLang(localStorage.getItem('pdfcompare.lang') || document.documentElement.lang); }} catch (e) {{}}
    let currentMode = 'split';
    document.querySelectorAll('.tab').forEach(tab => {{
      tab.addEventListener('click', () => {{
        if (tab.disabled) return;
        const mode = tab.dataset.mode;
        currentMode = mode;
        document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
        document.querySelectorAll('.preview-mode').forEach(panel => {{
          panel.classList.toggle('active', panel.dataset.panel === mode);
        }});
      }});
    }});
    document.querySelectorAll('[data-dropdown]').forEach(dropdown => {{
      const btn = dropdown.querySelector('button');
      btn.addEventListener('click', (e) => {{
        e.stopPropagation();
        const open = dropdown.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      }});
    }});
    document.addEventListener('click', () => {{
      document.querySelectorAll('[data-dropdown].open').forEach(dropdown => {{
        dropdown.classList.remove('open');
        const btn = dropdown.querySelector('button');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      }});
    }});
    function toWinPath(rel) {{
      try {{
        const u = new URL(rel, window.location.href);
        if (u.protocol !== 'file:') return null;
        let p = decodeURIComponent(u.pathname);
        if (/^\\/[A-Za-z]:/.test(p)) p = p.slice(1);
        return p.replace(/\\//g, '\\\\');
      }} catch (e) {{
        return null;
      }}
    }}
    document.querySelectorAll('.open-ext').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const rel = btn.dataset.src;
        const wp = toWinPath(rel);
        if (!wp) {{
          window.open(rel, '_blank');
          return;
        }}
        const uri = 'ms-photos:viewer?fileName=' + encodeURIComponent(wp);
        window.location.href = uri;
      }});
    }});
    document.addEventListener('keydown', (e) => {{
      const tag = (e.target && e.target.tagName || '').toLowerCase();
      if (!primarySliderHref || tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if (e.key === 'Enter') {{
        window.location.href = primarySliderHref;
      }}
    }});
  </script>
</body>
</html>
"""
        (views_dir / p["view_file"]).write_text(detail_html, encoding="utf-8")

        if slider_file and old_src and new_src:
            prev_slider_file = p.get("prev_slider_file")
            next_slider_file = p.get("next_slider_file")
            prev_slider_rec = slider_record_by_file.get(prev_slider_file)
            next_slider_rec = slider_record_by_file.get(next_slider_file)
            prev_slider_ord = prev_slider_rec["view_ord"] if prev_slider_rec else ""
            next_slider_ord = next_slider_rec["view_ord"] if next_slider_rec else ""
            prev_cmp_btn = (
                f'<a class="btn" href="{html.escape(str(prev_slider_file), quote=True)}">'
                f'{report_icon("chevron-left", size=16)}{i18n_span_text(f"Лист {prev_slider_ord}", f"Sheet {prev_slider_ord}")}</a>'
                if prev_slider_file and prev_slider_rec
                else f'<span class="btn disabled">{report_icon("chevron-left", size=16)}{i18n_span_text("Первый лист", "First sheet")}</span>'
            )
            next_cmp_btn = (
                f'<a class="btn primary" href="{html.escape(str(next_slider_file), quote=True)}">'
                f'{i18n_span_text(f"Лист {next_slider_ord}", f"Sheet {next_slider_ord}")}{report_icon("chevron-right", size=16)}</a>'
                if next_slider_file and next_slider_rec
                else f'<span class="btn primary disabled">{i18n_span_text("Последний лист", "Last sheet")}{report_icon("chevron-right", size=16)}</span>'
            )
            slider_nav_items: list[str] = []
            all_sheets_data: list[dict] = []
            for nav_p in pages_records:
                nav_a = "—" if nav_p["a_index"] is None else f"A{nav_p['a_index']}"
                nav_b = "—" if nav_p["b_index"] is None else f"B{nav_p['b_index']}"
                nav_diff = "—" if nav_p["diff_metric"] is None else f'{nav_p["diff_metric"]:.3f}%'
                nav_fg = "—" if nav_p.get("diff_foreground_metric") is None else f'{float(nav_p["diff_foreground_metric"]):.2f}%'
                nav_boxes = "—" if nav_p["bboxes_count"] is None else str(nav_p["bboxes_count"])
                nav_has_slider = bool(nav_p.get("slider_file"))
                nav_href = str(nav_p["slider_file"] if nav_has_slider else nav_p["view_file"])
                nav_current = " current" if nav_p.get("slider_file") == slider_file else ""
                nav_disabled = "" if nav_has_slider else " disabled-slider"
                nav_status_tag = str(nav_p.get("_status_tag") or "CHANGED")
                nav_level_tag = str(nav_p.get("_level_tag") or "")
                status_key = status_label_keys.get(nav_status_tag, "")
                nav_status_ru = str(i18n["ru"].get(status_key, nav_status_tag))
                nav_status_en = str(i18n["en"].get(status_key, nav_status_tag))
                nav_search = (
                    f"{nav_p['view_ord']} {nav_a} {nav_b} {nav_p['status_ru']} {nav_status_tag} "
                    f"{nav_level_tag} {nav_fg} {nav_diff} {nav_boxes} {nav_p['notes']}"
                ).lower()
                nav_title_ru = (
                    "Слайдер недоступен для добавленных/удалённых листов"
                    if not nav_has_slider
                    else nav_p["nav_label"]
                )
                nav_title_en = (
                    "Slider not available for added/removed sheets"
                    if not nav_has_slider
                    else nav_p["nav_label"]
                )
                nav_aria_ru = (
                    "Слайдер недоступен для добавленных/удалённых листов"
                    if not nav_has_slider
                    else "Открыть лист в слайдере"
                )
                nav_aria_en = (
                    "Slider not available for added/removed sheets"
                    if not nav_has_slider
                    else "Open sheet in slider"
                )
                nav_meta_ru = (
                    "Слайдер недоступен · открыть страницу листа"
                    if not nav_has_slider
                    else f"заполнено {nav_fg} · {nav_boxes} областей"
                )
                nav_meta_en = (
                    "Slider unavailable · open sheet page"
                    if not nav_has_slider
                    else f"drawn {nav_fg} · {nav_boxes} boxes"
                )
                nav_title = title_text(nav_title_ru, nav_title_en)
                nav_aria = i18n_aria(nav_aria_ru, nav_aria_en)
                nav_meta = i18n_span_text(nav_meta_ru, nav_meta_en)
                all_sheets_data.append(
                    {
                        "seq": nav_p["view_ord"],
                        "label": f"{nav_a} -> {nav_b}",
                        "status": nav_status_tag,
                        "statusRu": nav_status_ru,
                        "statusEn": nav_status_en,
                        "level": nav_level_tag,
                        "hasSlider": nav_has_slider,
                        "href": nav_href,
                        "diff": nav_diff,
                        "boxes": nav_boxes,
                        "metaRu": nav_meta_ru,
                        "metaEn": nav_meta_en,
                        "titleRu": nav_title_ru,
                        "titleEn": nav_title_en,
                        "ariaRu": nav_aria_ru,
                        "ariaEn": nav_aria_en,
                        "search": nav_search,
                    }
                )
                slider_nav_items.append(
                    f"<a class='slider-nav-item{nav_current}{nav_disabled}' data-label='{html.escape(nav_search, quote=True)}' "
                    f"href='{html.escape(nav_href, quote=True)}' role='menuitem' title='{nav_title}' {nav_aria}>"
                    f"<span class='slider-nav-main'><b>{html.escape(str(nav_p['view_ord']))} · {html.escape(nav_a)} -> {html.escape(nav_b)}</b>"
                    f"{status_badge_html(nav_status_tag)}</span>"
                    f"<span class='slider-nav-meta'>{nav_meta}</span></a>"
                )
            slider_nav_html = "".join(slider_nav_items)
            all_sheets_js = json.dumps(all_sheets_data, ensure_ascii=False)
            slider_title_ru = f"Слайдер — лист {view_idx} / {len(pages_records)}"
            slider_title_en = f"Slider — sheet {view_idx} / {len(pages_records)}"
            slider_html = f"""<!doctype html>
<html lang="{lang}" {title_attrs(slider_title_ru, slider_title_en)}>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title_text(slider_title_ru, slider_title_en)}</title>
  <script>
    try {{
      if (new URLSearchParams(location.search).get('embed') === '1') {{
        document.documentElement.classList.add('embed');
      }}
      const savedTheme = localStorage.getItem('pdfcompare.theme');
      if (savedTheme === 'dark') document.documentElement.dataset.theme = 'dark';
      const savedLang = localStorage.getItem('pdfcompare.lang');
      if (savedLang === 'en' || savedLang === 'ru') document.documentElement.lang = savedLang;
      const savedBbox = JSON.parse(localStorage.getItem('pdfcompare.bbox') || '{{}}');
      const palettes = {{
        yellow: {{ border: [255, 180, 0], fill: [255, 235, 120] }},
        pink: {{ border: [236, 72, 153], fill: [244, 114, 182] }},
        green: {{ border: [22, 163, 74], fill: [134, 239, 172] }},
      }};
      const palette = palettes[savedBbox.color] || palettes.yellow;
      const opacity = Math.max(0, Math.min(100, Number(savedBbox.opacity) || 74));
      document.documentElement.style.setProperty('--bbox-border', `rgba(${{palette.border.join(',')}},${{(opacity / 100).toFixed(2)}})`);
      document.documentElement.style.setProperty('--bbox-fill', `rgba(${{palette.fill.join(',')}},${{(opacity / 100 * 0.18).toFixed(2)}})`);
      document.documentElement.dataset.bboxEnabled = savedBbox.enabled === false ? 'false' : 'true';
    }} catch (e) {{}}
  </script>
  <style>
    html, body {{ width:100%; height:100%; }}
    body {{ margin:0; font-family:Segoe UI,Arial,sans-serif; background:#f3f6fb; color:#1d2433; overflow:hidden; }}
    .wrap {{ width:100vw; height:100vh; margin:0; padding:0; }}
    .panel {{ width:100%; height:100%; background:#fff; border:0; border-radius:0; padding:10px; box-sizing:border-box; display:flex; flex-direction:column; }}
    .top {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; margin-bottom:10px; }}
    .top-actions {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; justify-content:flex-end; }}
    .btn {{ border:1px solid #d7deea; border-radius:8px; padding:6px 10px; text-decoration:none; color:#0f4fa8; background:#fff; }}
    .btn.disabled {{ color:#7b8496; background:#f4f6fa; cursor:default; }}
    .btn-save {{ background:#eaf8ef; border-color:#88d4a2; color:#176235; font-weight:800; }}
    .slider-nav-search {{ width:100%; box-sizing:border-box; border:1px solid #d7deea; border-radius:8px; padding:8px; margin:0 0 8px 0; }}
    .slider-nav-list {{ display:grid; gap:6px; }}
    .slider-nav-item {{ display:grid; gap:4px; border:1px solid #d7deea; border-radius:8px; padding:8px; text-decoration:none; color:inherit; background:#fbfdff; }}
    .slider-nav-item:hover {{ border-color:#0f4fa8; background:#eef5ff; }}
    .slider-nav-item.current {{ border-color:#1fa463; background:#e8f8ee; box-shadow:inset 4px 0 0 #1fa463; font-weight:800; }}
    .slider-nav-main {{ display:flex; justify-content:space-between; gap:8px; align-items:center; }}
    .slider-nav-meta {{ color:#5f6b84; font-size:12px; }}
    .s {{ font-size:11px; border-radius:999px; padding:2px 8px; color:#fff; white-space:nowrap; }}
    .s.ok {{ background:#1f8c4f; }} .s.warn {{ background:#cc3d17; }} .s.add {{ background:#0569d0; }}
    .stage {{ flex:1; width:100%; background:#fff; box-sizing:border-box; overflow:auto; min-height:0; position:relative; }}
    .stage.dragging {{ cursor:ew-resize; }}
    .stage.panning {{ cursor:grabbing; }}
    .compare-surface {{ position:relative; display:none; background:#fff; overflow:hidden; cursor:ew-resize; transform-origin:0 0; }}
    .layer {{ position:absolute; inset:0; width:100%; height:100%; object-fit:fill; user-select:none; -webkit-user-drag:none; }}
    .old-layer {{ position:absolute; inset:0; overflow:hidden; clip-path:inset(0 50% 0 0); }}
    .bbox-layer {{ position:absolute; inset:0; pointer-events:none; }}
    .bbox {{ position:absolute; border:2px solid var(--bbox-border); background:var(--bbox-fill); box-sizing:border-box; }}
    .divider {{ position:absolute; top:0; bottom:0; left:50%; width:2px; background:rgba(20,120,255,.95); pointer-events:none; }}
    .load-msg {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#5f6b84; }}
    .stage.panning .compare-surface {{ cursor:grabbing; }}
    .slider-wrap {{ margin:10px 0 0 0; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    input[type=range] {{ width:100%; }}
    .muted {{ color:#5f6b84; font-size:12px; }}
    .small {{ width:150px; }}
    .bbox-controls {{ display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-left:auto; }}
    .swatch-option {{ display:inline-flex; align-items:center; gap:5px; border:1px solid #d7deea; border-radius:8px; padding:5px 8px; background:#fff; cursor:pointer; user-select:none; }}
    .swatch-option input {{ margin:0; }}
    .swatch {{ width:14px; height:14px; border-radius:4px; border:2px solid currentColor; box-sizing:border-box; }}
    .swatch-yellow {{ color:rgb(255,180,0); background:rgba(255,235,120,.45); }}
    .swatch-pink {{ color:rgb(236,72,153); background:rgba(244,114,182,.45); }}
    .swatch-green {{ color:rgb(22,163,74); background:rgba(134,239,172,.45); }}
    .bbox-opacity {{ width:110px; }}
    .zoom-rect {{ position:absolute; border:2px dashed rgba(20,120,255,.95); background:rgba(20,120,255,.12); box-sizing:border-box; pointer-events:none; z-index:5; display:none; }}
{REPORT_CSS_TOKENS}
{CSS_CMP}
  </style>
</head>
<body>
  <div class="cmp-page pinned" id="cmpPage">
  <aside class="sheet-drawer" id="sheetDrawer" {i18n_aria("Навигация по листам", "Sheet navigation")}>
    <button class="sheet-drawer-handle" type="button" aria-controls="sheetDrawerPanel" aria-expanded="false" {i18n_aria("Открыть список листов", "Open sheet list")}>
      {report_icon("list", size=16)}
      {i18n_span_text("Открыть список листов", "Open sheet list", "sr-only")}
    </button>
    <div class="sheet-drawer-panel" id="sheetDrawerPanel">
      <div class="sheet-drawer-head">
        <strong>{i18n_span_text("Листы", "Sheets")}</strong>
        <span class="muted">{view_idx} / {len(pages_records)}</span>
        <button class="sheet-drawer-pin" id="drawerPin" type="button" {i18n_aria("Открепить панель", "Unpin panel")}>📌</button>
      </div>
      <input id="sliderNavSearch" class="slider-nav-search" type="search" {i18n_placeholder_text("Поиск…", "Search…")}/>
      <div id="sliderNavList" class="slider-nav-list">{slider_nav_html}</div>
      <div class="sheet-drawer-hint muted">{i18n_span_text("📌 — открепить · ←/→ — соседний лист", "📌 — unpin · ←/→ — adjacent sheet")}</div>
    </div>
  </aside>
  <div class="cmp-main">
    <header class="cmp-header">
      <div class="cmp-left">
        <a class="btn ghost" href="{html.escape(p['view_file'], quote=True)}">{report_icon("arrow-left", size=16)}{i18n_span_text("К листу", "Back to sheet")}</a>
      </div>
      <div class="cmp-title">
        <span>{i18n_span_text(f"Лист {view_idx} / {len(pages_records)}", f"Sheet {view_idx} / {len(pages_records)}")}</span>
        {status_badge_html(status_tag)}
        {level_badge_html(level_tag) if level_tag else ""}
        <span class="muted">· {html.escape(fg_diff_txt)} FG · {html.escape(diff_txt)}</span>
      </div>
      <div class="cmp-right">
        <div class="cmp-nav">
          {prev_cmp_btn}
          <span class="cmp-count">{i18n_span_text(f"Лист {view_idx} / {len(pages_records)}", f"Sheet {view_idx} / {len(pages_records)}")}</span>
          {next_cmp_btn}
        </div>
        <div class="segmented" {i18n_aria("Управление слайдером", "Slider controls")}>
          <button class="seg-btn" id="fitBtn" type="button">{report_icon("maximize-2", size=16)}{i18n_span_text("Вписать", "Fit")}</button>
          <button class="seg-btn" id="oneBtn" type="button">{report_icon("square", size=16)}{i18n_span_text("1:1", "1:1")}</button>
          <div class="dropdown" data-dropdown>
            <button class="seg-btn" id="bboxMenuBtn" type="button" aria-haspopup="menu" aria-expanded="false" {i18n_aria("Настройки выделения", "Bbox settings")}>
              <span class="bbox-swatch swatch-yellow" id="bboxSwatch" aria-hidden="true"></span>
              {i18n_span_text("Bbox", "Bbox")}
              <span class="caret">▾</span>
            </button>
            <div class="dropdown-menu bbox-panel" role="menu">
              <div class="bbox-row">
                <span class="bbox-row-label">{i18n_span_text("Показывать", "Show")}</span>
                <div class="seg-toggle" id="bboxToggle" role="group" {i18n_aria("Показывать Bbox", "Show Bbox")}>
                  <button type="button" class="seg-toggle-opt active" data-bbox="on">{i18n_span_text("ON", "ON")}</button>
                  <button type="button" class="seg-toggle-opt" data-bbox="off">{i18n_span_text("OFF", "OFF")}</button>
                </div>
              </div>
              <div class="bbox-row">
                <span class="bbox-row-label">{i18n_span_text("Цвет", "Color")}</span>
                <div class="bbox-colors">
                  <button type="button" class="swatch-option active" data-color="yellow" {i18n_aria("Жёлтый", "Yellow")}><span class="swatch swatch-yellow"></span></button>
                  <button type="button" class="swatch-option" data-color="pink" {i18n_aria("Розовый", "Pink")}><span class="swatch swatch-pink"></span></button>
                  <button type="button" class="swatch-option" data-color="green" {i18n_aria("Зелёный", "Green")}><span class="swatch swatch-green"></span></button>
                </div>
              </div>
              <div class="bbox-row">
                <span class="bbox-row-label">{i18n_span_text("Прозрачность", "Opacity")}</span>
                <input class="bbox-opacity" id="bboxOpacity" type="range" min="0" max="100" value="74"/>
                <span class="bbox-opacity-value" id="bboxOpacityValue">74%</span>
              </div>
            </div>
          </div>
          <span class="seg-btn">{report_icon("zoom-in", size=16)}<span>{i18n_span_text("Масштаб", "Zoom")}</span><span id="zoomVal">100%</span></span>
        </div>
      </div>
    </header>
      <div class="stage" id="stage" tabindex="0">
        <div class="compare-surface" id="surface">
          <img id="imgNew" class="layer new-layer" alt="{html.escape(t["slider_new"])}" draggable="false"/>
          <div id="oldLayer" class="old-layer"><img id="imgOld" class="layer" alt="{html.escape(t["slider_old"])}" draggable="false"/></div>
          <div id="bboxLayer" class="bbox-layer"></div>
          <div id="zoomRect" class="zoom-rect"></div>
          <div id="divider" class="divider"></div>
        </div>
        <div id="loadMsg" class="load-msg">{html.escape(t["no_data"])}</div>
      </div>
      <div class="slider-panel">
        <div class="split-line">
          {i18n_span_text("OLD", "OLD", "split-label old")}
          <input id="split" type="range" min="0" max="100" step="0.1" value="50"/>
          {i18n_span_text("NEW", "NEW", "split-label new")}
        </div>
        <input id="zoom" class="sr-only" type="range" min="1" max="500" value="100"/>
        <div class="hint">{i18n_span_text("ЛКМ - сплит · ПКМ-drag - pan · СКМ-выделение - zoom · Ctrl+Wheel - zoom", "Left click - split · Right drag - pan · Middle drag - zoom to rect · Ctrl+Wheel - zoom")}</div>
      </div>
  </div>
  </div>
  <script>
    const oldSrc = {json.dumps(old_src)};
    const newSrc = {json.dumps(new_src)};
    const bboxData = {json.dumps(bboxes_data, ensure_ascii=False)};
    const prevSliderHref = {json.dumps(prev_slider_file)};
    const nextSliderHref = {json.dumps(next_slider_file)};
    const firstSliderHref = {json.dumps(first_slider_file)};
    const lastSliderHref = {json.dumps(last_slider_file)};
    const slider = document.getElementById('split');
    const zoom = document.getElementById('zoom');
    const zoomVal = document.getElementById('zoomVal');
    const fitBtn = document.getElementById('fitBtn');
    const oneBtn = document.getElementById('oneBtn');
    const stage = document.getElementById('stage');
    const surface = document.getElementById('surface');
    const oldLayer = document.getElementById('oldLayer');
    const divider = document.getElementById('divider');
    const bboxLayer = document.getElementById('bboxLayer');
    const loadMsg = document.getElementById('loadMsg');
    const oldImg = document.getElementById('imgOld');
    const newImg = document.getElementById('imgNew');
    const bboxToggle = document.getElementById('bboxToggle');
    const bboxOpacity = document.getElementById('bboxOpacity');
    const bboxOpacityValue = document.getElementById('bboxOpacityValue');
    const bboxSwatch = document.getElementById('bboxSwatch');
    const allSheets = {all_sheets_js};
    const currentSeq = {view_idx};
    const drawer = document.getElementById('sheetDrawer');
    const drawerHandle = drawer ? drawer.querySelector('.sheet-drawer-handle') : null;
    const sliderNavSearch = document.getElementById('sliderNavSearch');
    const sliderNavList = document.getElementById('sliderNavList');
    let sliderNavItems = [];
    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      }}[ch]));
    }}
    function badgeClass(status) {{
      if (status === 'ADDED') return 'st-added';
      if (status === 'REMOVED') return 'st-removed';
      if (status === 'UNCHANGED') return 'st-unchanged';
      return 'st-changed';
    }}
    function renderDrawerItems() {{
      if (!sliderNavList) return;
      const lang = document.documentElement.lang === 'en' ? 'en' : 'ru';
      sliderNavList.innerHTML = allSheets.map(sheet => {{
        const classes = 'slider-nav-item' + (sheet.seq === currentSeq ? ' current' : '') + (sheet.hasSlider ? '' : ' disabled-slider');
        const label = escapeHtml(sheet.label || '');
        const statusRu = escapeHtml(sheet.statusRu || sheet.status || '');
        const statusEn = escapeHtml(sheet.statusEn || sheet.status || '');
        const statusLabel = lang === 'en' ? statusEn : statusRu;
        const metaRu = escapeHtml(sheet.metaRu || '');
        const metaEn = escapeHtml(sheet.metaEn || '');
        const meta = lang === 'en' ? metaEn : metaRu;
        const title = escapeHtml(lang === 'en' ? sheet.titleEn : sheet.titleRu);
        const ariaRu = escapeHtml(sheet.ariaRu || '');
        const ariaEn = escapeHtml(sheet.ariaEn || '');
        const aria = lang === 'en' ? ariaEn : ariaRu;
        return '<a class="' + classes + '" data-label="' + escapeHtml(sheet.search || '') + '" href="' + escapeHtml(sheet.href || '#') + '" role="menuitem" title="' + title + '" aria-label="' + aria + '" data-i18n-aria-ru="' + ariaRu + '" data-i18n-aria-en="' + ariaEn + '">'
          + '<span class="slider-nav-main"><b>' + escapeHtml(String(sheet.seq || '')) + ' · ' + label + '</b>'
          + '<span class="badge ' + badgeClass(sheet.status) + '" data-i18n-ru="' + statusRu + '" data-i18n-en="' + statusEn + '">' + statusLabel + '</span></span>'
          + '<span class="slider-nav-meta" data-i18n-ru="' + metaRu + '" data-i18n-en="' + metaEn + '">' + meta + '</span></a>';
      }}).join('');
      sliderNavItems = [...document.querySelectorAll('.slider-nav-item')];
    }}
    renderDrawerItems();
    function applyLang(nextLang) {{
      const next = nextLang === 'en' ? 'en' : 'ru';
      const root = document.documentElement;
      document.documentElement.lang = next;
      if (root.dataset.titleRu && root.dataset.titleEn) {{
        document.title = next === 'en' ? root.dataset.titleEn : root.dataset.titleRu;
      }}
      document.querySelectorAll('[data-i18n-ru]').forEach(el => {{
        el.textContent = next === 'en' ? el.dataset.i18nEn : el.dataset.i18nRu;
      }});
      document.querySelectorAll('[data-i18n-placeholder-ru]').forEach(el => {{
        el.setAttribute('placeholder', next === 'en' ? el.dataset.i18nPlaceholderEn : el.dataset.i18nPlaceholderRu);
      }});
      document.querySelectorAll('[data-i18n-aria-ru]').forEach(el => {{
        el.setAttribute('aria-label', next === 'en' ? el.dataset.i18nAriaEn : el.dataset.i18nAriaRu);
      }});
    }}
    try {{ applyLang(localStorage.getItem('pdfcompare.lang') || document.documentElement.lang); }} catch (e) {{}}
    function openDrawer() {{
      if (!drawer || isPinned()) return;
      drawer.classList.add('open');
      if (drawerHandle) drawerHandle.setAttribute('aria-expanded', 'true');
    }}
    function closeDrawer() {{
      if (!drawer || isPinned()) return;
      drawer.classList.remove('open');
      if (drawerHandle) drawerHandle.setAttribute('aria-expanded', 'false');
    }}
    const cmpPage = document.getElementById('cmpPage');
    const drawerPin = document.getElementById('drawerPin');
    function isPinned() {{ return cmpPage && cmpPage.classList.contains('pinned'); }}
    function applyPinned(pinned) {{
      if (!cmpPage) return;
      const en = document.documentElement.lang === 'en';
      cmpPage.classList.toggle('pinned', pinned);
      if (drawerPin) {{
        drawerPin.textContent = pinned ? '📌' : '📍';
        drawerPin.setAttribute('aria-label', pinned ? (en ? 'Unpin panel' : 'Открепить панель') : (en ? 'Pin panel' : 'Прикрепить панель'));
      }}
      if (!pinned && drawer) drawer.classList.remove('open');
      try {{ localStorage.setItem('pdfcompare.drawer', pinned ? 'pinned' : 'floating'); }} catch (e) {{}}
    }}
    function togglePin() {{
      applyPinned(!isPinned());
      // The stage width changes by the panel width; re-fit once the
      // grid-template-columns transition (~180ms) settles.
      window.setTimeout(() => fitToWindow(), 220);
    }}
    // Restore persisted pin state (default: pinned).
    try {{
      const stored = localStorage.getItem('pdfcompare.drawer');
      applyPinned(stored ? stored === 'pinned' : true);
    }} catch (e) {{}}
    if (drawerPin) {{ drawerPin.addEventListener('click', togglePin); }}
    if (drawer) {{
      drawer.addEventListener('mouseenter', openDrawer);
      drawer.addEventListener('mouseleave', closeDrawer);
    }}
    if (drawerHandle) {{
      drawerHandle.addEventListener('click', (e) => {{
        e.stopPropagation();
        if (drawer.classList.contains('open')) closeDrawer();
        else {{
          openDrawer();
          if (sliderNavSearch) sliderNavSearch.focus();
        }}
      }});
    }}
    if (sliderNavSearch) {{
      sliderNavSearch.addEventListener('input', () => {{
        const q = sliderNavSearch.value.trim().toLowerCase();
        sliderNavItems.forEach(item => {{
          item.style.display = !q || (item.dataset.label || '').includes(q) ? '' : 'none';
        }});
      }});
    }}
    document.addEventListener('click', (e) => {{
      document.querySelectorAll('[data-dropdown].open').forEach(dropdown => {{
        if (dropdown.contains(e.target)) return;
        dropdown.classList.remove('open');
        const btn = dropdown.querySelector('button');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      }});
    }});
    document.querySelectorAll('[data-dropdown]').forEach(dropdown => {{
      const btn = dropdown.querySelector('button');
      btn.addEventListener('click', (e) => {{
        e.stopPropagation();
        const open = dropdown.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      }});
    }});
    window.addEventListener('keydown', (e) => {{
      const tag = (e.target && e.target.tagName || '').toLowerCase();
      if (e.key === 'Escape') {{
        closeDrawer();
        document.querySelectorAll('[data-dropdown].open').forEach(dropdown => {{
          dropdown.classList.remove('open');
          const btn = dropdown.querySelector('button');
          if (btn) btn.setAttribute('aria-expanded', 'false');
        }});
        return;
      }}
      if (tag === 'input' || tag === 'button') return;
      if ((e.key === 'ArrowLeft' || e.key === 'PageUp') && prevSliderHref) {{
        window.location.href = prevSliderHref;
      }} else if ((e.key === 'ArrowRight' || e.key === 'PageDown') && nextSliderHref) {{
        window.location.href = nextSliderHref;
      }} else if (e.key === 'Home' && firstSliderHref) {{
        window.location.href = firstSliderHref;
      }} else if (e.key === 'End' && lastSliderHref) {{
        window.location.href = lastSliderHref;
      }}
    }});
    const bboxColors = {{
      yellow: {{ border: 'rgba(255,180,0,A)', fill: 'rgba(255,235,120,B)' }},
      pink: {{ border: 'rgba(236,72,153,A)', fill: 'rgba(244,114,182,B)' }},
      green: {{ border: 'rgba(22,163,74,A)', fill: 'rgba(134,239,172,B)' }},
    }};
    let bboxState = {{ enabled: true, color: 'yellow', opacity: 74 }};
    function saveBboxState() {{
      try {{ localStorage.setItem('pdfcompare.bbox', JSON.stringify(bboxState)); }} catch (e) {{}}
    }}
    function applyBboxStyle() {{
      const c = bboxColors[bboxState.color] || bboxColors.yellow;
      const opacityPct = Math.max(0, Math.min(100, Number(bboxState.opacity) || 0));
      const aBorder = Math.min(1, opacityPct / 100);
      const aFill = Math.min(1, opacityPct / 100 * 0.18);
      document.documentElement.style.setProperty('--bbox-border', c.border.replace('A', aBorder.toFixed(2)));
      document.documentElement.style.setProperty('--bbox-fill', c.fill.replace('B', aFill.toFixed(2)));
      document.documentElement.dataset.bboxEnabled = bboxState.enabled ? 'true' : 'false';
      surface.style.setProperty('--bbox-border', c.border.replace('A', aBorder.toFixed(2)));
      surface.style.setProperty('--bbox-fill', c.fill.replace('B', aFill.toFixed(2)));
      bboxLayer.style.display = bboxState.enabled ? '' : 'none';
      document.querySelectorAll('#bboxToggle .seg-toggle-opt').forEach(opt => {{
        opt.classList.toggle('active', (opt.dataset.bbox === 'on') === bboxState.enabled);
      }});
      document.querySelectorAll('.swatch-option').forEach(opt => {{
        opt.classList.toggle('active', opt.dataset.color === bboxState.color);
      }});
      if (bboxOpacity) bboxOpacity.value = String(opacityPct);
      if (bboxOpacityValue) bboxOpacityValue.textContent = opacityPct + '%';
      if (bboxSwatch) bboxSwatch.className = 'bbox-swatch swatch-' + (bboxColors[bboxState.color] ? bboxState.color : 'yellow') + (bboxState.enabled ? '' : ' off');
    }}
    function setBboxState(patch, persist = true) {{
      bboxState = {{ ...bboxState, ...patch }};
      applyBboxStyle();
      if (persist) saveBboxState();
    }}
    document.querySelectorAll('#bboxToggle .seg-toggle-opt').forEach(opt => {{
      opt.addEventListener('click', () => setBboxState({{ enabled: opt.dataset.bbox === 'on' }}));
    }});
    document.querySelectorAll('.swatch-option[data-color]').forEach(opt => {{
      opt.addEventListener('click', () => setBboxState({{ color: opt.dataset.color || 'yellow' }}));
    }});
    if (bboxOpacity) {{
      bboxOpacity.addEventListener('input', () => setBboxState({{ opacity: Number(bboxOpacity.value) || 0 }}));
    }}
    try {{
      const savedBbox = JSON.parse(localStorage.getItem('pdfcompare.bbox') || '{{}}');
      setBboxState({{
        enabled: savedBbox.enabled !== false,
        color: bboxColors[savedBbox.color] ? savedBbox.color : 'yellow',
        opacity: Number.isFinite(Number(savedBbox.opacity)) ? Number(savedBbox.opacity) : 74,
      }}, false);
    }} catch (e) {{
      applyBboxStyle();
    }}
    window.addEventListener('message', (e) => {{
      const data = e.data || {{}};
      if (data.type === 'pdfcompare:bbox') {{
        setBboxState({{ enabled: data.enabled !== false }});
      }}
    }});
    let loaded = 0;
    let naturalW = 0;
    let naturalH = 0;
    function ready() {{ loaded += 1; if (loaded >= 2) initialize(); }}
    function fail() {{ loadMsg.textContent = 'Не удалось загрузить изображение'; }}
    oldImg.onload = ready;
    newImg.onload = ready;
    oldImg.onerror = fail;
    newImg.onerror = fail;
    oldImg.src = oldSrc;
    newImg.src = newSrc;
    function initialize() {{
      naturalW = Math.max(oldImg.naturalWidth || 1, newImg.naturalWidth || 1);
      naturalH = Math.max(oldImg.naturalHeight || 1, newImg.naturalHeight || 1);
      surface.style.display = 'block';
      loadMsg.style.display = 'none';
      buildBboxes();
      applyBboxStyle();
      applySplit();
      fitToWindow();
    }}
    function buildBboxes() {{
      bboxLayer.innerHTML = '';
      bboxData.forEach(b => {{
        const x = Number(b.x || 0);
        const y = Number(b.y || 0);
        const bw = Number(b.w || 0);
        const bh = Number(b.h || 0);
        if (bw <= 1 || bh <= 1) return;
        const box = document.createElement('div');
        box.className = 'bbox';
        box.style.left = (100 * x / naturalW) + '%';
        box.style.top = (100 * y / naturalH) + '%';
        box.style.width = (100 * bw / naturalW) + '%';
        box.style.height = (100 * bh / naturalH) + '%';
        bboxLayer.appendChild(box);
      }});
    }}
    function setZoomPercent(v) {{
      const clamped = Math.max(1, Math.min(500, Math.round(v)));
      zoom.value = String(clamped);
      applyZoom();
    }}
    function applyZoom() {{
      if (!naturalW || !naturalH) return;
      const z = Number(zoom.value) / 100;
      zoomVal.textContent = Math.round(z * 100) + '%';
      surface.style.width = Math.max(1, Math.round(naturalW * z)) + 'px';
      surface.style.height = Math.max(1, Math.round(naturalH * z)) + 'px';
    }}
    function fitToWindow() {{
      if (!naturalW || !naturalH) return;
      const pad = 16;
      const sx = Math.max(0.01, (stage.clientWidth - pad) / naturalW);
      const sy = Math.max(0.01, (stage.clientHeight - pad) / naturalH);
      const s = Math.max(0.01, Math.min(sx, sy));
      setZoomPercent(s * 100);
    }}
    function setSplitFromClientX(clientX) {{
      const rect = surface.getBoundingClientRect();
      if (!rect.width) return;
      const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
      const pct = (x / rect.width) * 100;
      slider.value = String(pct);
      applySplit();
    }}
    function applySplit() {{
      const pct = Math.max(0, Math.min(100, Number(slider.value) || 0));
      oldLayer.style.clipPath = `inset(0 ${{100 - pct}}% 0 0)`;
      divider.style.left = pct + '%';
      slider.style.setProperty('--split-pct', pct + '%');
    }}
    let draggingSplit = false;
    let panning = false;
    let panStartX = 0;
    let panStartY = 0;
    let panStartScrollLeft = 0;
    let panStartScrollTop = 0;
    let selecting = false;
    const zoomRect = document.getElementById('zoomRect');
    let selStartClientX = 0;
    let selStartClientY = 0;
    function clientToSurfaceXY(clientX, clientY) {{
      const rect = surface.getBoundingClientRect();
      return {{ x: clientX - rect.left, y: clientY - rect.top, rect: rect }};
    }}
    function zoomToClientRect(startX, startY, endX, endY) {{
      // Convert a screen-space drag rectangle (relative to the surface) into
      // an image-pixel rectangle, then fit it into the viewport.
      const left = Math.min(startX, endX);
      const top = Math.min(startY, endY);
      const w = Math.abs(endX - startX);
      const h = Math.abs(endY - startY);
      if (w < 4 || h < 4) return;  // ignore accidental clicks
      const rect = surface.getBoundingClientRect();
      if (!rect.width || !rect.height || !naturalW || !naturalH) return;
      // Image-pixel rectangle captured by this drag.
      const imgX = (left / rect.width) * naturalW;
      const imgY = (top / rect.height) * naturalH;
      const imgW = (w / rect.width) * naturalW;
      const imgH = (h / rect.height) * naturalH;
      // Fit the selected image rect into the stage viewport (with padding).
      const pad = 16;
      const sx = Math.max(0.01, (stage.clientWidth - pad) / imgW);
      const sy = Math.max(0.01, (stage.clientHeight - pad) / imgH);
      const s = Math.max(0.01, Math.min(5.0, Math.min(sx, sy)));
      setZoomPercent(s * 100);
      // After resize, center the selected rect in the viewport.
      const z = s;
      stage.scrollLeft = Math.max(0, imgX * z - (stage.clientWidth - imgW * z) / 2);
      stage.scrollTop = Math.max(0, imgY * z - (stage.clientHeight - imgH * z) / 2);
    }}
    surface.addEventListener('mousedown', (e) => {{
      if (e.button === 2) {{
        panning = true;
        stage.classList.add('panning');
        panStartX = e.clientX;
        panStartY = e.clientY;
        panStartScrollLeft = stage.scrollLeft;
        panStartScrollTop = stage.scrollTop;
        e.preventDefault();
        return;
      }}
      if (e.button === 1) {{
        // Middle button: start a zoom-by-rectangle selection.
        // preventDefault is essential to suppress the browser autoscroll cursor.
        e.preventDefault();
        selecting = true;
        selStartClientX = e.clientX;
        selStartClientY = e.clientY;
        zoomRect.style.display = 'block';
        const p = clientToSurfaceXY(e.clientX, e.clientY);
        zoomRect.style.left = p.x + 'px';
        zoomRect.style.top = p.y + 'px';
        zoomRect.style.width = '0px';
        zoomRect.style.height = '0px';
        return;
      }}
      if (e.button !== 0) return;
      draggingSplit = true;
      stage.classList.add('dragging');
      setSplitFromClientX(e.clientX);
    }});
    window.addEventListener('mousemove', (e) => {{
      if (selecting) {{
        const start = clientToSurfaceXY(selStartClientX, selStartClientY);
        const cur = clientToSurfaceXY(e.clientX, e.clientY);
        const left = Math.min(start.x, cur.x);
        const top = Math.min(start.y, cur.y);
        const w = Math.abs(cur.x - start.x);
        const h = Math.abs(cur.y - start.y);
        zoomRect.style.left = left + 'px';
        zoomRect.style.top = top + 'px';
        zoomRect.style.width = w + 'px';
        zoomRect.style.height = h + 'px';
        return;
      }}
      if (panning) {{
        stage.scrollLeft = panStartScrollLeft - (e.clientX - panStartX);
        stage.scrollTop = panStartScrollTop - (e.clientY - panStartY);
        return;
      }}
      if (!draggingSplit) return;
      setSplitFromClientX(e.clientX);
    }});
    window.addEventListener('mouseup', (e) => {{
      if (selecting) {{
        selecting = false;
        zoomRect.style.display = 'none';
        const start = clientToSurfaceXY(selStartClientX, selStartClientY);
        const cur = clientToSurfaceXY(e.clientX, e.clientY);
        zoomToClientRect(start.x, start.y, cur.x, cur.y);
        return;
      }}
      if (draggingSplit) {{
        draggingSplit = false;
        stage.classList.remove('dragging');
      }}
      if (panning) {{
        panning = false;
        stage.classList.remove('panning');
      }}
    }});
    stage.addEventListener('contextmenu', (e) => {{
      e.preventDefault();
    }});
    surface.addEventListener('touchstart', (e) => {{
      if (!e.touches || !e.touches.length) return;
      draggingSplit = true;
      stage.classList.add('dragging');
      setSplitFromClientX(e.touches[0].clientX);
      e.preventDefault();
    }}, {{ passive: false }});
    window.addEventListener('touchmove', (e) => {{
      if (!draggingSplit || !e.touches || !e.touches.length) return;
      setSplitFromClientX(e.touches[0].clientX);
      e.preventDefault();
    }}, {{ passive: false }});
    window.addEventListener('touchend', () => {{
      draggingSplit = false;
      stage.classList.remove('dragging');
    }});
    stage.addEventListener('wheel', (e) => {{
      if (!e.ctrlKey) return;
      e.preventDefault();
      const delta = e.deltaY < 0 ? 6 : -6;
      setZoomPercent(Number(zoom.value) + delta);
    }}, {{ passive: false }});
    slider.addEventListener('input', applySplit);
    zoom.addEventListener('input', () => setZoomPercent(Number(zoom.value)));
    fitBtn.addEventListener('click', fitToWindow);
    oneBtn.addEventListener('click', () => setZoomPercent(100));
    window.addEventListener('resize', () => {{
      if (Number(zoom.value) <= 5) fitToWindow();
    }});
  </script>
</body>
</html>"""
            (views_dir / slider_file).write_text(slider_html, encoding="utf-8")
        emit(66 + 32 * (view_idx / total_views), t["progress_generate_view"].format(idx=view_idx, total=total_views))

    backup_bundle_dir = internal_dir(run_dir) / f".report_backup_{uuid4().hex}"
    try:
        if final_bundle_dir.exists():
            final_bundle_dir.rename(backup_bundle_dir)
        bundle_dir.rename(final_bundle_dir)
        if backup_bundle_dir.exists():
            shutil.rmtree(backup_bundle_dir)
    except Exception:
        if final_bundle_dir.exists():
            shutil.rmtree(final_bundle_dir)
        if backup_bundle_dir.exists() and not final_bundle_dir.exists():
            backup_bundle_dir.rename(final_bundle_dir)
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        raise

    write_start_page(run_dir, report_lang)
    emit(100, t["progress_ready"])
    return run_dir / START_REPORT_FILE
