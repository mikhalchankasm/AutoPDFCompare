"""Shared, structured help content and client-side shell for static reports."""

from __future__ import annotations

from .constants import FG_MAJOR_PERCENT, FG_MINOR_PERCENT, FG_MODERATE_PERCENT


def build_help_data() -> dict[str, list[dict[str, object]]]:
    """Return compact help sections.  The browser renders this data without HTML."""
    return {
        "ru": [
            {"id": "about", "title": "Что это за отчёт", "blocks": [{"type": "text", "text": "Сравнение двух ревизий PDF: OLD → NEW. Отчёт статический, работает локально из папки и не отправляет чертежи в облако."}]},
            {"id": "matrix", "title": "Матрица изменений", "blocks": [{"type": "text", "text": "Титульная таблица показывает пары листов, статус, уровень, «Заполнено %», «Лист %», площадь mm² и Δ. KPI-карточки фильтруют статусы, поиск фильтрует строки, меню «Экспорт» сохраняет результат."}, {"type": "note", "text": f"Уровни: MAJOR ≥{FG_MAJOR_PERCENT:g}%, MODERATE ≥{FG_MODERATE_PERCENT:g}%, MINOR ≥{FG_MINOR_PERCENT:g}% заполненной области. «Заполнено %» относится к линиям чертежа, «Лист %» — ко всей площади листа."}]},
            {"id": "sheets", "title": "Панель листов", "blocks": [{"type": "list", "items": ["Поиск находит лист по номеру, паре и статусу.", "📌 закрепляет или открепляет панель.", "🏠 возвращает к матрице изменений.", "«К листу» открывает страницу с превью OLD, NEW и DIFF."]}]},
            {"id": "controls", "title": "Верхняя панель", "blocks": [{"type": "list", "items": ["Метка пары и метрики описывают текущий лист.", "−, + и «Вписать» управляют масштабом.", "«Подсветить изменения» кратко обводит кластеры изменений на текущем масштабе.", "«Зоны изменений» включает рамки; их цвет и прозрачность общие для отчёта и сохраняются браузером."]}]},
            {"id": "canvas", "title": "Полотно и сплит", "blocks": [{"type": "keys", "items": [["ЛКМ", "двигает границу OLD / NEW"], ["ПКМ + drag", "панорамирует"], ["СКМ + выделение", "приближает прямоугольник"], ["Ctrl + колесо", "масштабирует"]]}]},
            {"id": "pager", "title": "Листалка", "blocks": [{"type": "text", "text": "« ведёт к первому листу, ‹ и › — к соседним, » — к последнему. Счётчик показывает позицию; стрелки клавиатуры тоже перелистывают."}]},
            {"id": "notes", "title": "Заметки", "blocks": [{"type": "list", "items": ["Включите «Заметка», выберите зелёный (нет изменений), жёлтый (спорное) или красный (изменение), затем выделите область.", "Тяните рамку для перемещения, её углы — для размера; двойной клик редактирует текст, × удаляет.", "«Скрыть заметки» временно прячет все рамки."]}, {"type": "note", "text": "Заметки хранятся только в localStorage браузера, привязаны к папке прогона и номеру листа. Они не попадают в отчёт, не переживают его перегенерацию и не видны коллеге, которому вы отправите папку."}]},
            {"id": "keys", "title": "Клавиатура", "blocks": [{"type": "keys", "items": [["← / →, PageUp / PageDown", "соседний лист"], ["Home / End", "первый / последний лист"], ["Z / H, Я / Р", "подсветить зоны"], ["Esc", "закрыть справку и активные режимы"], ["?", "открыть справку"], ["Ctrl + колесо", "масштаб"]]}]},
            {"id": "prefs", "title": "Темы и язык", "blocks": [{"type": "text", "text": "Переключатели на титульной странице меняют язык и тему для всего отчёта; выбор сохраняется в браузере."}]},
        ],
        "en": [
            {"id": "about", "title": "About this report", "blocks": [{"type": "text", "text": "A comparison of two PDF revisions: OLD → NEW. The report is static, works locally from its folder, and does not upload drawings to the cloud."}]},
            {"id": "matrix", "title": "Change matrix", "blocks": [{"type": "text", "text": "The summary table shows sheet pairs, status, level, Drawn %, Sheet %, mm² area and Δ. KPI cards filter statuses, search filters rows, and Export saves a result."}, {"type": "note", "text": f"Levels: MAJOR ≥{FG_MAJOR_PERCENT:g}%, MODERATE ≥{FG_MODERATE_PERCENT:g}%, MINOR ≥{FG_MINOR_PERCENT:g}% of the drawn area. Drawn % measures drawing content; Sheet % measures the entire sheet."}]},
            {"id": "sheets", "title": "Sheet panel", "blocks": [{"type": "list", "items": ["Search finds a sheet by number, pair, or status.", "📌 pins or unpins the panel.", "🏠 returns to the change matrix.", "Back to sheet opens OLD, NEW, and DIFF previews."]}]},
            {"id": "controls", "title": "Top bar", "blocks": [{"type": "list", "items": ["The pair label and metrics describe the current sheet.", "−, +, and Fit control zoom.", "Flash changes briefly outlines change clusters at the current zoom.", "Change zones toggles frames; their color and opacity apply to the report and are stored by the browser."]}]},
            {"id": "canvas", "title": "Canvas and split", "blocks": [{"type": "keys", "items": [["Left click", "moves the OLD / NEW split"], ["Right drag", "pans"], ["Middle drag", "zooms to a rectangle"], ["Ctrl + wheel", "zooms"]]}]},
            {"id": "pager", "title": "Pager", "blocks": [{"type": "text", "text": "« goes to the first sheet, ‹ and › to adjacent sheets, and » to the last. The counter shows position; keyboard arrows also move between sheets."}]},
            {"id": "notes", "title": "Notes", "blocks": [{"type": "list", "items": ["Enable Note, choose green (no change), yellow (uncertain), or red (change), then drag an area.", "Drag a box to move it; use corners to resize; double-click edits text; × deletes.", "Hide notes temporarily hides all boxes."]}, {"type": "note", "text": "Notes live only in browser localStorage and are tied to the run folder and sheet number. They are not saved in report files, do not survive report regeneration, and are not visible to colleagues who receive the folder."}]},
            {"id": "keys", "title": "Keyboard", "blocks": [{"type": "keys", "items": [["← / →, PageUp / PageDown", "adjacent sheet"], ["Home / End", "first / last sheet"], ["Z / H, Я / Р", "flash zones"], ["Esc", "close help and active modes"], ["?", "open help"], ["Ctrl + wheel", "zoom"]]}]},
            {"id": "prefs", "title": "Theme and language", "blocks": [{"type": "text", "text": "The summary-page switches set the language and theme for the whole report; the browser remembers the choice."}]},
        ],
    }


def help_shell_html() -> str:
    """Return the shared help panel host; content is filled by the common script."""
    return '<div class="help-scrim" id="helpScrim" hidden></div><aside class="help-panel" id="helpPanel" aria-hidden="true"><header class="help-header"><strong id="helpTitle">Help</strong><button class="btn icon-only" id="helpClose" type="button" aria-label="Close help">×</button></header><nav class="help-toc" id="helpToc"></nav><div class="help-body" id="helpBody"></div></aside>'


def help_script() -> str:
    """Return a dependency-free renderer shared by summary, detail, and slider pages."""
    return """
    (() => {
      const panel = document.getElementById('helpPanel');
      const scrim = document.getElementById('helpScrim');
      const body = document.getElementById('helpBody');
      const toc = document.getElementById('helpToc');
      const title = document.getElementById('helpTitle');
      const close = document.getElementById('helpClose');
      function lang() { return document.documentElement.lang === 'en' ? 'en' : 'ru'; }
      function render(next) {
        if (!body || !toc) return;
        const en = next === 'en'; const sections = (window.PDFCOMPARE_HELP || {})[en ? 'en' : 'ru'] || [];
        body.replaceChildren(); toc.replaceChildren(); title.textContent = en ? 'Help' : 'Справка'; close.setAttribute('aria-label', en ? 'Close help' : 'Закрыть справку');
        sections.forEach(section => {
          const a = document.createElement('a'); a.href = '#' + section.id; a.textContent = section.title; toc.append(a);
          const sectionEl = document.createElement('section'); sectionEl.id = section.id; const h = document.createElement('h2'); h.textContent = section.title; sectionEl.append(h);
          section.blocks.forEach(block => {
            if (block.type === 'list') { const ul = document.createElement('ul'); block.items.forEach(item => { const li = document.createElement('li'); li.textContent = item; ul.append(li); }); sectionEl.append(ul); return; }
            if (block.type === 'keys') { const table = document.createElement('table'); block.items.forEach(pair => { const row = table.insertRow(); const key = row.insertCell(); const action = row.insertCell(); key.textContent = pair[0]; action.textContent = pair[1]; }); sectionEl.append(table); return; }
            const p = document.createElement('p'); p.className = block.type === 'note' ? 'help-note' : ''; p.textContent = block.text; sectionEl.append(p);
          }); body.append(sectionEl);
        });
      }
      function isOpen() { return panel && panel.classList.contains('open'); }
      function setOpen(open) { if (!panel || !scrim) return; panel.classList.toggle('open', open); panel.setAttribute('aria-hidden', open ? 'false' : 'true'); scrim.hidden = !open; document.querySelectorAll('[data-help-open]').forEach(btn => btn.setAttribute('aria-expanded', open ? 'true' : 'false')); if (open) { render(lang()); document.querySelectorAll('.help-unseen').forEach(btn => btn.classList.remove('help-unseen')); try { localStorage.setItem('pdfcompare.helpSeen', '1'); } catch (e) {} } }
      window.PDFCOMPARE_HELP_RENDER = render; window.PDFCOMPARE_HELP_INIT = button => { if (button) { button.dataset.helpOpen = ''; try { if (localStorage.getItem('pdfcompare.helpSeen') !== '1') button.classList.add('help-unseen'); } catch (e) {} button.addEventListener('click', () => setOpen(true)); } };
      document.querySelectorAll('[data-help-open]').forEach(btn => btn.addEventListener('click', () => setOpen(true)));
      if (close) close.addEventListener('click', () => setOpen(false)); if (scrim) scrim.addEventListener('click', () => setOpen(false));
      window.addEventListener('keydown', event => { if (event.key === 'Escape' && isOpen()) { event.preventDefault(); setOpen(false); } else if (event.key === '?' && !['input', 'textarea', 'select'].includes((event.target.tagName || '').toLowerCase())) { event.preventDefault(); setOpen(true); } });
      render(lang());
    })();
    """
