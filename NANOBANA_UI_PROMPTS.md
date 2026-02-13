# Промпты для Nano Banana — UI mockup PDFCompare Local

Каждый промпт ниже — самостоятельный. Копируй и вставляй в Nano Banana как есть.

---

## Промпт 1 — Пустое состояние (Idle)

```
A pixel-perfect UI mockup of a Windows 11 desktop application window titled "PDFCompare Local". Clean, modern, light theme. White background (#FFFFFF). Window size 900×580px. Segoe UI font throughout. NO browser chrome — this is a native desktop app window with standard Windows 11 title bar (minimize, maximize, close buttons).

Top area of the window:
- Left-aligned app title "PDFCompare Local" in dark text (#1E293B), Segoe UI Semibold 14pt
- Below it, subtitle "Локальное сравнение PDF · без облака" in muted gray (#64748B), 9pt
- Small gear icon (⚙) in the top-right corner, muted gray

Two tabs directly below the header: "Сравнение" (active, underlined with blue #3B82F6) and "История" (inactive, gray text). Tabs use Segoe UI 10pt.

Main content area (tab "Сравнение"):

Section A — Drop Zone:
- Full-width rounded rectangle (border-radius 8px), height ~100px
- Dashed 2px border in light gray (#CBD5E1), background #F0F4F8
- Centered: a 48px icon showing two overlapping document pages with a "+" symbol between them, drawn in muted blue-gray
- Below the icon, centered text line 1: "Перетащите 2 файла PDF сюда" in Segoe UI Semibold 11pt, dark text
- Centered text line 2: "или используйте кнопки ниже" in Segoe UI Regular 9pt, muted gray (#64748B)
- The drop zone looks inviting and interactive

Section B — File Inputs (below drop zone, 12px gap):
- Three horizontal rows, each with: a label (120px fixed width), a text input field (stretched, light gray border #E2E8F0, rounded 4px, empty), and a "Выбрать..." button (outline style, gray border, rounded 4px)
- Row 1: small red dot (●) + label "Старый PDF (OLD)" — input is empty, placeholder text "не выбран" in light gray
- Row 2: small green dot (●) + label "Новый PDF (NEW)" — input is empty, placeholder "не выбран"
- Row 3: small folder icon (📁) + label "Папка вывода" — input is empty, placeholder "не выбрана"

Section C — Options:
- A single clickable text line: "Параметры ▾" in Segoe UI 9pt, muted blue (#3B82F6). This is collapsed, nothing else is visible.

Section D — Action Area:
- Full-width button, 40px tall, rounded 6px, DISABLED state: light gray background (#E2E8F0), gray text (#94A3B8), text reads "Сравнить (Enter)"
- Below it, 8px gap, two small text-style links side by side: "Очистить" and "Из истории" in muted gray (#64748B), 9pt

Bottom of the window:
- A thin 3px line spanning full width, light gray (#E2E8F0) — this is the inactive progress bar
- Below it, small status text: "Перетащите файлы PDF для начала работы" in 8pt muted gray

The overall aesthetic is clean, modern, airy. Generous white space. Subtle shadows on the drop zone. The design feels professional and minimal, similar to Figma or Linear app aesthetics. The image MUST look like a real Windows 11 application screenshot, NOT a website.
```

---

## Промпт 2 — Файлы выбраны, готов к запуску (Ready)

```
A pixel-perfect UI mockup of a Windows 11 desktop application window titled "PDFCompare Local". Clean, modern, light theme. White background. Window size 900×580px. Segoe UI font. Native Windows 11 title bar.

Top area: app title "PDFCompare Local" (Segoe UI Semibold 14pt, #1E293B), subtitle "Локальное сравнение PDF · без облака" (9pt, #64748B). Gear icon top-right.

Two tabs: "Сравнение" (active, blue underline #3B82F6) and "История" (inactive gray).

Main content — tab "Сравнение":

Section A — Drop Zone (files loaded state):
- Full-width rounded rectangle (8px radius), height ~100px
- Solid thin border in light blue (#93C5FD), background #F0F7FF (slightly bluer than empty state)
- Inside: two file badges side by side, horizontally centered with 24px gap between them
- Left badge: rounded pill shape, light red background (#FEF2F2), border #FECACA. Contains: red document icon + text "ПакетРД-1_revC03.pdf" in 9pt dark text + "(42 стр.)" in muted text + a small "×" button at the right edge
- Right badge: rounded pill shape, light green background (#F0FDF4), border #BBF7D0. Contains: green document icon + text "ПакетРД-1_rev.C05.pdf" in 9pt dark text + "(38 стр.)" in muted text + a small "×" button
- Above the badges, small muted text: "Файлы загружены" in 8pt gray

Section B — File Inputs (populated):
- Row 1: red dot (●) + "Старый PDF (OLD)" + input field filled with "…/ПакетРД-1/…revC03.pdf" in dark text, a small green checkmark (✓) at the right edge of the input + "Выбрать..." button
- Row 2: green dot (●) + "Новый PDF (NEW)" + input field filled with "…/ПакетРД-1/…rev.C05.pdf", green checkmark + "Выбрать..." button
- Row 3: folder icon + "Папка вывода" + input field filled with "D:/Temp/240000-AC21", green checkmark + "Выбрать..." button

Section C — Options (collapsed):
- Text: "Параметры ▾" in muted blue. Collapsed.

Section D — Action Area:
- Full-width button, 40px tall, rounded 6px, ACTIVE state: bright blue background (#3B82F6), white bold text "Сравнить (Enter)", Segoe UI Semibold 11pt. The button looks clickable and prominent — it is THE primary action.
- Below: "Очистить" and "Из истории" text links in gray

Bottom:
- Thin inactive progress bar (3px, gray)
- Status: "Готово к сравнению. Нажмите Enter." in 8pt muted gray

Clean, modern, airy design. Looks like a real native Windows 11 app screenshot. NOT a website.
```

---

## Промпт 3 — Выполняется сравнение (Running)

```
A pixel-perfect UI mockup of a Windows 11 desktop application window titled "PDFCompare Local". Clean, modern, light theme. White background. 900×580px. Segoe UI font. Windows 11 title bar.

Top area: "PDFCompare Local" title, subtitle, gear icon — same as other states.

Tabs: "Сравнение" active (blue underline), "История" inactive.

Main content — tab "Сравнение":

Section A — Drop Zone:
- Same as "files loaded" state: two file badges (red OLD pill badge, green NEW pill badge) inside the drop zone
- The entire drop zone has a subtle pulsing blue glow border to indicate activity

Section B — File Inputs:
- All three rows populated with paths, but the entire section is visually DIMMED (reduced opacity ~50%), inputs are non-interactive during processing

Section C — Options: collapsed, also dimmed

Section D — Action Area (RUNNING state):
- The primary button has TRANSFORMED into a progress-button:
  - Full width, 40px tall, rounded 6px
  - The LEFT 67% of the button is filled with blue (#3B82F6), the RIGHT 33% is light gray (#E2E8F0)
  - White bold text centered on the blue portion: "Сравнение... 67%"
  - This creates a progress-bar-inside-a-button effect
- Below: secondary links are hidden during run

Bottom:
- The thin 3px progress bar is now ACTIVE: filled 67% with blue (#3B82F6), remaining 33% gray. Smooth rounded ends.
- Status text: "Вычисление различий страниц (25/38)..." in 8pt, dark gray (#475569) — more prominent than idle state

The overall feel is: the app is working, the user sees clear progress. The dimmed inputs communicate "please wait". The progress-button is the focal point. Clean, modern design. Real Windows 11 app screenshot.
```

---

## Промпт 4 — Завершено (Completed)

```
A pixel-perfect UI mockup of a Windows 11 desktop application window titled "PDFCompare Local". Clean, modern, light theme. White background. 900×580px. Segoe UI font. Windows 11 title bar.

Top area: "PDFCompare Local" title, subtitle, gear icon.

Tabs: "Сравнение" active (blue underline), "История" inactive.

Main content — tab "Сравнение":

Section A — Drop Zone:
- File badges visible (red OLD + green NEW pills), normal state, not dimmed

Section B — File Inputs:
- All three rows populated, normal state (not dimmed), checkmarks visible

Section C — Options: collapsed "Параметры ▾"

Section D — Result Card (replaces the action button area):
- A rounded card (8px radius), light green background (#ECFDF5), thin green border (#BBF7D0)
- Left side of the card:
  - Line 1 (bold, 10pt, #1E293B): "12 стр. без изменений · 3 изменены · 1 добавлена · 0 удалено"
  - Line 2 (regular, 9pt, #16A34A): "✓ Выполнено за 1 мин 23 сек"
- Right side of the card (vertically centered):
  - Primary button: "Открыть отчёт" — blue (#3B82F6) background, white text, rounded 6px, 32px tall
  - Below it, 6px gap: "Открыть папку" — outline button, blue border, blue text, white background, rounded 6px, 32px tall
- Below the card, centered: text link "Запустить новое сравнение →" in blue (#3B82F6), 9pt, underlined

Bottom:
- Progress bar is FULL, 3px, green (#16A34A) instead of blue — signaling completion
- Status: "Отчёт: D:/Temp/240000-AC21/run_20260213_011937/report_bundle/index.html" in 8pt muted gray

The result card is the focal point. The green tint communicates success. Clean, modern, professional. Real Windows 11 app, NOT a website.
```

---

## Промпт 5 — Вкладка «История» (History Tab)

```
A pixel-perfect UI mockup of a Windows 11 desktop application window titled "PDFCompare Local". Clean, modern, light theme. White background. 900×580px. Segoe UI font. Windows 11 title bar.

Top area: "PDFCompare Local" title, subtitle, gear icon.

Two tabs: "Сравнение" (inactive, gray) and "История" (ACTIVE, blue underline #3B82F6). The History tab is now selected.

Main content — tab "История":

Toolbar row (top of tab content):
- Three small outline buttons in a row: "Восстановить" | "Открыть папку" | "Удалить" — all with gray borders, 9pt text, rounded 4px, 28px height

Table below the toolbar (full width, fills remaining space):
- Column headers: "Дата/время" (150px) | "Результат" (80px) | "Старый PDF" (200px) | "Новый PDF" (200px) | "Папка" (remaining)
- Headers have light gray background (#F8FAFC), Segoe UI Semibold 9pt, bottom border #E2E8F0

Table rows (showing 7 rows of sample data, alternating white and #FAFBFC):
- Row 1: "2026-02-13 01:19" | green badge "OK" | "ПакетРД-1_revC03.pdf" | "ПакетРД-1_rev.C05.pdf" | "D:/Temp/240000-AC21"
- Row 2: "2026-02-12 18:45" | green badge "OK" | "Чертежи_v2.pdf" | "Чертежи_v3.pdf" | "D:/Temp/Чертежи"
- Row 3 (SELECTED — entire row has blue highlight #EFF6FF, blue left border 3px #3B82F6): "2026-02-12 15:30" | red badge "Ошибка" | "Спецификация.pdf" | "Спецификация_new.pdf" | "D:/Temp/Spec"
- Row 4: "2026-02-11 09:12" | green badge "OK" | "Plan_rev1.pdf" | "Plan_rev2.pdf" | "D:/Projects/Plans"
- Row 5: "2026-02-10 22:01" | gray badge "Снимок" | "Draft_A.pdf" | "Draft_B.pdf" | "D:/Temp/Drafts"
- Row 6: "2026-02-10 14:55" | green badge "OK" | "РД_33_revA.pdf" | "РД_33_revB.pdf" | "D:/Temp/RD33"
- Row 7: "2026-02-09 11:30" | green badge "OK" | "Схема_1.pdf" | "Схема_2.pdf" | "D:/Temp/Schemes"

Badge styles:
- "OK" badge: small rounded pill (48×20px), green background (#ECFDF5), green text (#16A34A), green border (#BBF7D0)
- "Ошибка" badge: same pill shape, red background (#FEF2F2), red text (#DC2626), red border (#FECACA)
- "Снимок" badge: same pill shape, gray background (#F1F5F9), gray text (#64748B), gray border (#E2E8F0)

Below the table:
- Small hint text: "Дважды нажмите на строку для восстановления параметров" in 8pt muted gray (#64748B)

Scrollbar: thin modern scrollbar on the right edge of the table, Windows 11 style.

Clean, modern, airy. The table is clean and scannable. The selected row is clearly highlighted. Real native Windows 11 application screenshot, NOT a website or browser.
```

---

## Промпт 6 (бонус) — Состояние ошибки (Error)

```
A pixel-perfect UI mockup of a Windows 11 desktop application window titled "PDFCompare Local". Clean, modern, light theme. White background. 900×580px. Segoe UI font. Windows 11 title bar.

Top area: "PDFCompare Local" title, subtitle, gear icon.

Tabs: "Сравнение" active, "История" inactive.

Main content — tab "Сравнение":

Drop Zone: file badges visible (OLD + NEW pills). File Inputs: populated. Options: collapsed.

Section D — Error Result Card (replaces action button):
- Rounded card (8px radius), light red background (#FEF2F2), thin red border (#FECACA)
- Left side:
  - Line 1 (bold, 10pt, #DC2626): "✕ Ошибка при сравнении"
  - Line 2 (regular, 9pt, #1E293B): "Файл повреждён или защищён паролем: ПакетРД-1_revC03.pdf"
- Right side:
  - Button: "Повторить" — red outline button (#DC2626 border, red text), rounded 6px, 32px tall
- Below the card: text link "Запустить новое сравнение →" in blue, 9pt

Progress bar: full, RED (#DC2626), 3px.

The red tint clearly communicates failure. Clean, modern, professional. Real Windows 11 app.
```

---

## Советы по генерации

1. **Генерируй по одному промпту за раз** — Nano Banana лучше работает с одним детальным описанием, чем с пакетом
2. **Если текст на русском отрендерился с ошибками** — добавь в конец промпта: `All Russian Cyrillic text MUST be spelled correctly and be legible. Double-check every Russian word.`
3. **Если окно выглядит как веб-страница** — усиль: `This MUST look like a native Windows 11 desktop application with a real Windows title bar (not a browser). No URL bar, no browser tabs.`
4. **Для итерации** — после первой генерации используй follow-up: `Make the following edits to the previous image: ...` с конкретным списком правок
