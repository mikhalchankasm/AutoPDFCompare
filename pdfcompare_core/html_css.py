"""Shared CSS token sheet used by the dashboard and detail views."""

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
