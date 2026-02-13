# PDFCompare Local — UI Redesign Brief

## 1. Current UI Assessment

### Screenshot Reference
The current interface is a standard Windows Tkinter application (880x520, `vista` theme). It has two tabs ("Сравнение" / "История"), a drop zone, path input rows, options, action buttons, and a progress bar.

### What Works
- **Functional completeness**: all controls needed for the workflow are present in one screen
- **Drag-and-drop**: supported via native Windows hook — good for power users
- **History tab**: useful for repeat comparisons of the same document pairs
- **Keyboard shortcut**: Enter key triggers comparison — efficient

### Problems

**Visual hierarchy is flat.**
Every element has equal visual weight. The primary action ("Run Compare") is the same size and style as "Clear" and "Restore Last". There is no clear reading path from top to bottom.

**Drop Zone is inert.**
The drop area is a tiny LabelFrame with one line of text. It doesn't look interactive — no icon, no dashed border, no hover state. Users unfamiliar with the app won't realize they can drag files here.

**Long paths are unreadable.**
The path entries show full filesystem paths that overflow horizontally. With deeply nested Russian-language directory names (as in the screenshot), the actual filename is cut off. No ellipsis, no tooltip, no way to see the file name at a glance.

**No visual state feedback.**
When a comparison is running, only the progress bar and status text change. The Run button is disabled but looks the same. There is no visual distinction between idle, running, and completed states.

**Options feel buried.**
DPI and Stroke tolerance are in a small LabelFrame with no explanation. A new user won't know what "Stroke tolerance (px): 2.0" means or what value to choose.

**Mixed language.**
Tab labels are in Russian ("Сравнение", "История"), all other text is English. This is disorienting for both Russian and English speakers.

**No results preview.**
After completion, the user sees a status line with a path and must click "Open Report" to see anything. There is no inline summary — how many pages matched, how many changed, etc.

**Cramped button bar.**
Five buttons in one row with inconsistent spacing. "Open Report" and "Open Run Folder" are only relevant after a run completes, but they are always visible (disabled).

**No application icon / branding.**
The window icon is the default Tkinter feather. No visual identity.

---

## 2. Design Brief for New UI Variant

### Product Context
**App name:** PDFCompare Local
**Platform:** Windows 10/11 desktop
**Framework:** Will be rendered as a Tkinter app (ttk widgets), but design the ideal layout — we will adapt
**Target user:** Engineers and document controllers comparing revision sets of technical PDFs (drawings, specs, reports)
**Language:** Primary Russian, English fallback. All labels should be in Russian with English in parentheses where helpful
**Window size:** 900×580 default, minimum 800×500, resizable

### Design Principles
1. **One clear action per screen state.** In idle state: "drop or select files". In ready state: "run comparison". In completed state: "view report".
2. **Progressive disclosure.** Show only what's relevant. Hide advanced options behind an expander. Show result actions only after completion.
3. **Visual feedback at every step.** Dropping files, running, completing, erroring — each should look distinct.

---

### Layout Specification

#### Top Bar
- App icon (two overlapping document icons with a magnifier) + title "PDFCompare Local" in Segoe UI Semibold 14pt
- Subtitle: "Локальное сравнение PDF без облака" in muted gray, 9pt
- Top-right corner: gear icon button for settings (future)

#### Main Area — Tab "Сравнение" (Compare)

**A. Drop Zone (top, prominent)**
- Height: ~100px, full width
- Dashed 2px border, rounded corners (8px), light blue-gray background (#F0F4F8)
- Center icon: large (48px) document-pair icon with a "+" between them
- Center text line 1: "Перетащите 2 файла PDF сюда" (bold, 11pt)
- Center text line 2: "или используйте кнопки ниже" (muted, 9pt)
- On hover: border color shifts to accent blue (#3B82F6), background brightens
- On drop: brief green flash (#D1FAE5), then files populate below
- On file loaded: show two mini file badges inside the drop zone:
  - Left badge: "OLD — filename.pdf (42 стр.)" with red-tinted icon
  - Right badge: "NEW — filename.pdf (38 стр.)" with green-tinted icon
  - Each badge has an "×" button to clear

**B. File Inputs (below drop zone, compact)**
- Three rows, each: label (fixed 120px) | path entry (stretch) | "Выбрать..." button
- Row 1: "Старый PDF (OLD)" — red-tinted dot indicator
- Row 2: "Новый PDF (NEW)" — green-tinted dot indicator
- Row 3: "Папка вывода" — folder icon
- Path entries: show only the filename + parent folder, full path in tooltip on hover
- If path is valid: small green checkmark at the right edge of the entry
- If path is missing/invalid: small red "!" at the right edge

**C. Options (collapsed by default)**
- Expandable section: "Параметры ▾" / "Параметры ▴"
- When expanded:
  - Row 1: "Разрешение (DPI)" — slider 120–600, current value label, default 250
  - Row 2: "Допуск штриха (px)" — slider 0.0–10.0, step 0.5, default 2.0
  - Brief tooltip text under each: "Выше = точнее, но медленнее" / "Игнорирует различия тоньше указанного размера"

**D. Action Area**
- **Primary button:** "Сравнить (Enter)" — accent blue (#3B82F6), white text, full-width or 200px centered, 40px tall, rounded 6px. Bold. This is THE action.
- **Secondary row (below, small):** "Очистить" | "Из истории" — text-style buttons, gray, 10pt
- When running: primary button transforms into a cancel-style state with spinner animation text "Сравнение... 34%" — the button itself becomes the progress indicator (fills left-to-right with accent color)
- When done: primary button area is replaced by result summary card (see below)

**E. Result Card (appears after completion, replaces action area)**
- Rounded card with light green background (#ECFDF5) for success, light red (#FEF2F2) for error
- Left side: summary stats in bold:
  - "12 стр. без изменений · 3 изменены · 1 добавлена · 0 удалено"
  - Duration: "Выполнено за 1 мин 23 сек"
- Right side: two buttons:
  - "Открыть отчёт" — primary accent button
  - "Открыть папку" — secondary outline button
- Below card: "Запустить новое сравнение" — text link to reset

**F. Progress (during run)**
- Thin (3px) progress bar directly below the drop zone (or below the primary button)
- Accent blue fill, animated
- Status text below: current operation description

#### Main Area — Tab "История" (History)

**Table view:**
- Columns: Дата/время | Результат | Старый PDF | Новый PDF | Папка
- "Результат" column uses colored badges: green "OK", red "Ошибка", gray "Снимок"
- File columns show only filenames (not full paths); full path in tooltip
- Row hover: light blue highlight
- Double-click: restores inputs (same as current)
- Selected row actions (toolbar above table):
  - "Восстановить" | "Открыть папку" | "Удалить"
- Empty state: centered illustration + text "История пуста. Запустите первое сравнение."

---

### Color Palette

| Role | Color | Usage |
|------|-------|-------|
| Background | #FFFFFF | Main window background |
| Surface | #F8FAFC | Cards, panels |
| Drop Zone BG | #F0F4F8 | Drop area idle |
| Drop Zone Hover | #E0EAFF | Drop area on hover |
| Border | #E2E8F0 | Input borders, dividers |
| Text Primary | #1E293B | Headings, labels |
| Text Secondary | #64748B | Hints, descriptions |
| Accent Blue | #3B82F6 | Primary button, links, progress |
| Accent Blue Hover | #2563EB | Button hover state |
| Success Green | #16A34A | Completion badge, valid checkmarks |
| Success BG | #ECFDF5 | Success result card |
| Error Red | #DC2626 | Error badge, invalid indicators |
| Error BG | #FEF2F2 | Error result card |
| OLD indicator | #EF4444 | Red dot/tint for "old" document |
| NEW indicator | #22C55E | Green dot/tint for "new" document |

---

### Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| App title | Segoe UI | 14pt | Semibold |
| Tab labels | Segoe UI | 10pt | Medium |
| Section headers | Segoe UI | 10pt | Semibold |
| Labels | Segoe UI | 9pt | Regular |
| Input text | Segoe UI | 9pt | Regular |
| Primary button | Segoe UI | 11pt | Semibold |
| Secondary button | Segoe UI | 9pt | Regular |
| Status/hint | Segoe UI | 8pt | Regular |
| Result stats | Segoe UI | 10pt | Semibold |

---

### States to Illustrate

Please generate **four mockup frames** for the main "Сравнение" tab:

**Frame 1 — Empty / Idle**
- No files selected
- Drop zone prominent and inviting
- Primary button disabled (grayed)
- No result card visible

**Frame 2 — Files Selected, Ready**
- Both PDF paths populated (show file badges in drop zone)
- Output folder set
- Primary button active (blue)
- Options collapsed

**Frame 3 — Running**
- Primary button shows progress fill "Сравнение... 67%"
- Thin progress bar below drop zone
- Status text: "Выравнивание страниц (12/38)..."
- Inputs are dimmed / non-interactive

**Frame 4 — Completed**
- Result card visible with summary stats
- "Открыть отчёт" and "Открыть папку" buttons
- Progress bar full, green
- "Запустить новое сравнение" link below

And **one frame** for the "История" tab:
- Several rows with mixed OK/Error/Snapshot results
- One row selected (blue highlight)
- Toolbar buttons active

---

### Interaction Notes

- **Drag-and-drop** should remain the primary file input method. The drop zone should feel like a target.
- **Enter key** triggers comparison at any time when files are loaded.
- **Escape key** could cancel a running comparison (future).
- Tooltips on all truncated paths and option controls.
- Window is resizable; the drop zone and table should stretch, input rows should stretch horizontally, buttons stay fixed size.
- Minimum viable animation: progress fill, drop zone hover color, result card slide-in.

---

### What NOT to Change (Functional Constraints)

- Two-tab structure (Compare + History) must remain
- Three file inputs (OLD, NEW, Output) must remain
- DPI and Stroke tolerance must remain as user-configurable options
- History must store up to 300 runs with same data fields
- State persistence to `~/.pdfcompare_local/state.json` is unchanged
- The app runs on Windows 10/11 only
