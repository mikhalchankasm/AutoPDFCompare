# Repository Guidelines

PDFCompare Local — Windows-приложение для сравнения двух ревизий PDF-чертежей: Tkinter GUI, рендер PyMuPDF, дифф OpenCV/NumPy, статический HTML-отчёт. Плюс CLI, MCP-сервер для агентов, EXE и инсталлятор.

Этот файл — карта для того, кто (или что) правит репозиторий. Он описывает то, что есть.

## Структура

- `pdfcompare_core/` — движок, без Tk и без сети:
  - `runner.py` — оркестрация прогона, перегенерация страниц, отмена, транзакции;
  - `diff_engine.py`, `alignment.py`, `classification.py` — дифф, выравнивание (ECC), уровни изменений;
  - `exclusions.py` — зоны исключения: `percent` / `mm` / `px` + якорь угла;
  - `html_report.py` — генератор отчёта (оркестратор + билдеры страниц), `html_fragments.py` (`ReportI18n`, `ReportBadges`), `html_css.py` (все стили), `html_i18n.py`, `html_icons.py`;
  - `pdf_io.py`, `cli.py`, `constants.py` (здесь же `APP_VERSION`).
- `pdfcompare_gui.py` + `pdfcompare_ui/` — GUI. Миксин на вкладку (`compare_tab`, `rerender_tab`, `history_tab`, `dnd`, `state_persistence`), общий типовой контракт — `contracts.AppProtocol`. Визуальный редактор зон — `exclusion_picker.py`. Строки — `i18n.py` (RU/EN).
- `scripts/` — операционные точки входа: `pdfcompare_mcp.py` (MCP, stdio), `pdfcompare_worker.py` (фоновый worker), `setup.ps1`, `lint.ps1`, `test.ps1`, `run*.ps1`.
- `packaging/` — PyInstaller spec'и (one-file для отдельной загрузки, **one-dir для инсталлятора**) и `installer.iss`.
- `tests/`, `docs/` (`releases/`, `reviews/`), `requirements/`.

Генерируемое (прогоны, временные файлы) в git не попадает: `runs/`, `tmp/`, `dist*/`, `build*/` уже в `.gitignore`.

## Команды

```powershell
.\scripts\lint.ps1     # ruff + strict mypy — оба жёсткие гейты
.\scripts\test.ps1     # pytest + порог покрытия pdfcompare_core (>= 82%)
.\scripts\setup.ps1    # окружение из hash-lock (-Loose — свободные диапазоны)
```

CI (`.github/workflows/build-exe.yml`): job `test` (lint + тесты, read-only, идёт и на PR) → job `build` (EXE, portable ZIP, инсталлятор, `SHA256SUMS.txt`; публикует релиз на теге `v*`).

## Что здесь легко сломать

Прежде чем менять эти места, поймите, почему они такие:

- **Зоны исключения — физические.** Редактор отдаёт миллиметры от угла привязки (`unit: "mm"`), а не проценты: 185 мм — это 62% ширины A4, но 16% ширины A0, поэтому процентная зона штампа на большом листе накрывает четверть чертежа. Не «упрощайте» обратно в проценты. Открытие старых процентных зон не должно молча переписывать их в мм.
- **Эффективный DPI.** Есть megapixel-cap: реальный DPI растра может быть ниже запрошенного. Все физические метрики (мм², мм-зоны, gap объединения рамок) считаются от **эффективного** DPI, а не от запрошенного.
- **Транзакции.** Перегенерация правит отчёт на месте: страницы, `summary.json`, бандл отчёта и `start.html` меняются как одно целое, при любой ошибке — полный откат. Бэкап нельзя удалять, пока новое не записано; если восстановление не удалось, бэкап **оставляем** — это последняя копия.
- **Отмена кооперативная.** Флаг доезжает до воркеров пула через `initializer/initargs` (`multiprocessing.Event` нельзя передать аргументом `submit` под spawn). MCP отменяет файлом-маркером и убивает процесс только по таймауту — иначе транзакция оборвётся посередине.
- **Инсталлятор ставит one-dir сборку.** One-file распаковывает рантайм в `%TEMP%\_MEI<PID>` и удаляет его при выходе, что гонялось с тихим перезапуском при автообновлении. UPX выключен намеренно.
- **Tk только из главного потока.** Воркеры общаются с UI через `queue`.
- **i18n RU/EN.** Ключи в `pdfcompare_ui/i18n.py` (GUI) и `pdfcompare_core/html_i18n.py` (отчёт) должны существовать в обоих языках.

## Тесты

`tests/test_<feature>.py`, обычный `unittest` под pytest. Кроме юнит-тестов есть **golden-тесты** — страховка при рефакторинге:

- `test_html_report_golden.py` — хеши всего сгенерированного HTML/JSON (RU и EN) плюс отдельная проверка детерминизма;
- `test_gui_layout.py` — снапшот дерева виджетов главного окна.

Если вывод изменён намеренно, перезапишите эталон и **посмотрите дифф**, а не переписывайте вслепую:

```powershell
$env:PDFCOMPARE_UPDATE_GOLDEN='1'; .\.venv\Scripts\python.exe -m pytest tests/test_html_report_golden.py
```

Тесты не должны открывать окна и ходить в сеть.

## Стиль

4 пробела, UTF-8, `snake_case` для функций и модулей, `PascalCase` для классов. Аннотации типов обязательны — mypy в strict. Комментарий пишем только там, где код не может объяснить сам, **почему** так (ограничение, неочевидная причина), а не что он делает.

## Коммиты и релизы

Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`). В теле — что было сломано и почему, а не пересказ дифа.

Релиз: поднять `APP_VERSION` в `pdfcompare_core/constants.py`, обновить `README.md`, `CHANGELOG.md` и `docs/releases/v<версия>.md`, затем поставить тег `v<версия>` — CI соберёт и опубликует. Подробнее: `docs/RELEASE_PROCESS.md`.

Полное ревью репозитория — промпт в `docs/REVIEW_PROMPT.md`, отчёты складываем в `docs/reviews/`.
