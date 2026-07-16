# Changelog

## v0.1.24 - 2026-07-16

### Added
- **Глобальная история сравнений, доступная из MCP.** У MCP не было ни вкладки «История», как в GUI, ни собственного журнала. Теперь оба журнала лежат в `~/.pdfcompare_local/` (домашняя папка пользователя, а не папка-клон MCP), поэтому переживают переустановку/переклонирование сервера. `list_comparison_history` отдаёт единый нумерованный список прошлых прогонов из GUI и MCP с пометкой источника и стабильным id; `restore_comparison` перезапускает выбранный прогон в два шага (сначала показывает параметры записи и наличие исходных PDF, затем по `confirm=true` стартует новое сравнение в новую папку, не трогая оригинал). Worker дописывает в историю каждый завершённый прогон (готово/отменён/ошибка). Логика чтения обоих журналов вынесена в `pdfcompare_core/history_index.py`.
- **`preview_pdf_comparison` — чек-лист перед запуском.** Инструмент валидирует ровно то же, что и `start_pdf_comparison` (пути, имя папки, DPI, строгость, зоны, коллизию папки), но ничего не запускает — возвращает готовый к показу чек-лист: какие файлы и сколько листов, допуски/строгость с пометкой «по умолчанию», исключаемые зоны построчно, папку и имя результата. Агент показывает его пользователю, спрашивает подтверждение и только потом зовёт `start`. Валидация вынесена в общий хелпер, чтобы preview и start не расходились.
- **Заметки к зонам в слайдере.** В режиме «Заметка» рисуешь полупрозрачный прямоугольник (🟢 нет изменений / 🟡 спорное / 🔴 изменение) и вписываешь комментарий — например, «штамп сместился, реального изменения нет». Заметки можно двигать за тело и менять размер за угловые ручки, скрывать/показывать и удалять; подпись сама встаёт на свободную сторону (снизу, если бокс у верхнего края листа, — иначе текст вылезал за лист). Хранятся в браузере (localStorage) по ключу «прогон + лист», переживают перезагрузку. Пока это первый шаг: заметки браузерные и не переживают перегенерацию отчёта — перенос в файл прогона запланирован отдельно.

### Changed
- **Подсветка зон («Зоны», клавиша `Z`/`H`) работает в текущем масштабе.** Раньше перед подсветкой лист принудительно вписывался целиком; теперь рамки рисуются там, где ты смотришь: зумнулся в область → снова нажал «Зоны» → изменения обвелись на месте. Клавиша `H` (и `Ctrl+H`) — синоним `Z`, обе теперь работают как переключатель.
- **Мелкий шаг зума.** Рядом с «Масштаб NN%» появились кнопки `−`/`+` с шагом 2% от текущего — тоньше колёсика, для точного кадрирования, когда колесо настроено на крупный шаг.
- **←/→ и кнопки листов в слайдере листают строго по соседнему листу, включая добавленные/удалённые** (для них открывается обычный вид листа), и больше не скроллят увеличенный лист вместо перехода к соседу.

### Проверка
- `lint.ps1` — чисто (38 файлов). `test.ps1` — 239 passed, 1 skipped, покрытие 88,26%. Golden отчёта пере-благословлён (изменились только слайдер-страницы).
- Новый модуль истории покрыт `tests/test_history_index.py`. MCP-инструменты (`preview_pdf_comparison`, `list_comparison_history`, `restore_comparison`) прогнаны сквозным вызовом на реальных PDF. Вьюер (подсветка/зум/листание/заметки) проверен в headless Edge: подпись заметки перескакивает на свободную сторону, seed-заметки из localStorage отрисовываются в нужном масштабе.

## v0.1.23 - 2026-07-15

### Added
- **Кнопка «Домой» на любой странице отчёта — в самое начало, к матрице изменений.** В режиме слайдера пути назад к матрице не было вовсе (только «К листу»). Теперь в шапке есть кнопка с домиком и неоновым контуром, ведущая на `index.html`: в слайдере — компактная круглая иконка слева, в детальном виде — с подписью «К матрице изменений». Контур светится постоянно (не пульсирует, чтобы не отвлекать при чтении чертежа) и ярче по наведению.
- **Кнопка «Зоны»: трёхсекундная подсветка мест, где сосредоточены изменения.** Иногда правки слабочитаемы — видно, что лист «Изменён», но не видно куда смотреть. Кнопка в шапке слайдера (клавиша `z`) вписывает лист целиком, группирует рамки bbox в зоны сосредоточения и на ~3 секунды обводит каждую зону габаритной рамкой с пульсирующим свечением, а внизу показывает счётчик «Зон с изменениями: N». Рамка строится по фактическим границам зоны — стопроцентное попадание, в отличие от круга, который разрастался до большей стороны и вылезал за лист, когда изменение шло вдоль края. Рамки живут в системе координат листа, поэтому точно ложатся на изменения и двигаются вместе с зумом/панорамой; `Esc` или повторное нажатие гасит их досрочно, а `prefers-reduced-motion` отключает пульсацию. На листе без изменений кнопка неактивна. Всё считается в браузере из уже имеющихся данных bbox — движок диффа не затронут.

### Changed
- **Одно поле вместо двух: «Папка отчёта».** «Папка вывода» + «Имя отчёта» были двумя половинами одного пути, и пустое имя означало папку с датой в названии. Теперь в поле лежит путь папки, которую создаст запуск: его можно вставить из буфера и дописать. Кнопка «Сгенерировать имя» собирает имя из имён обоих PDF — общая часть пишется один раз, дальше обе ревизии (`Проект_рев5.pdf` + `Проект_рев6.pdf` → `Проект_РЕВ5_vs_РЕВ6`), а занятое имя получает суффикс. Если в поле уже лежит существующая папка, она считается контейнером: имя внутри неё подбирается само — «выбрал папку, нажал Сравнить» больше не пишет отчёт поверх чужого содержимого.
- **Папка создаётся до запуска, и её отказ виден сразу.** Ошибка создания (недоступный путь, файл на месте папки, недопустимое имя) останавливает запуск и показывает предупреждение, а не всплывает через несколько минут из воркера.
- **Управление рамками (bbox) в слайдере — строкой в шапке, а не в выпадающем списке.** Цвет и прозрачность правят, *глядя на лист*; каждая корректировка стоила открыть меню → выбрать → закрыть → посмотреть → открыть снова. Теперь ON/OFF, три цвета и ползунок лежат открытыми в верхней панели.
- В слайдере появилась кнопка «В начало» (клавиша `Home` работала и раньше, но её никто не видел).
- Метка ревизии в предлагаемых именах папок сохраняет свой префикс: `plan_r1` → `R1`, а не `1` (`plan_1_vs_2` читается как диапазон страниц). Это же имя предлагает MCP-инструмент `prepare_pdf_comparison`.

### Fixed
- **Подписи кнопок листов ломались на две строки и выпирали из шапки слайдера.** Кнопка — flex-элемент и может сжаться уже своего содержимого: «Лист 9» переносился как «Лист» / «9», а шапка высотой ровно 48 px не давала кнопке места. Подписи больше не переносятся, а шапка при нехватке ширины сначала прячет хвост с метриками, потом подписи, и только затем переносит управление на вторую строку. Дублирующий счётчик «Лист 5 / 12» из навигации убран — он есть в заголовке.

## v0.1.22 - 2026-07-14

### Added
- **The app has its own icon.** It had none: Tk's feather in the title bar and the taskbar, the generic PyInstaller icon in Explorer. The glyph is Material Design Icons `select-compare` (Apache-2.0) — two panels either side of a divider, which is what the app does. It sits on a filled accent tile rather than on transparency, because the Windows taskbar is dark and a thin dark-blue glyph on a transparent background vanishes into it.

  Wired in three places, because they are three different mechanisms: the exe carries it as a resource (Explorer, shortcuts, the uninstall entry); the installer wizard gets `SetupIconFile`; and — the non-obvious one — Tk cannot read the exe's resource icon, so the `.ico` also ships as a data file and the window loads it at runtime. Without that last step the title bar keeps Tk's feather even though Explorer shows the right icon.

  The `.ico` is committed (a build must not depend on a rendering step) but generated from `packaging/icon.svg` by `scripts/make_icon.py`, using PyMuPDF, which is already a dependency. Every size is rendered from the vector: Windows takes 16 px for the title bar and 256 px for "extra large icons", and a single upscaled bitmap looks soft in the first and blocky in the last.

### Changed
- Dropped `style.theme_use("vista")` from `main()`: `configure_ttk_styles` sets `clam` immediately afterwards, so the line only looked like it did something.
- README screenshots rebuilt (they now carry the icon and the current version).

## v0.1.21 - 2026-07-14

Three defects the re-check of v0.1.20 found, plus a visual pass over the window.

### Fixed
- **Switching the sheet format rewrote percent zones.** Drawing 70/10/20/15 percent on A4, switching the preview to A0 and pressing OK gave back 17.4792/2.4979/4.9941/3.7468. The editor keeps every zone in millimetres, which is right for drawing and wrong for *storing* a percent zone: a percent zone is defined relative to the sheet, so re-deriving its millimetres against a different sheet silently converts it. Switching the format is meant to *show* where a zone lands on another sheet, not to migrate it. Percent zones now keep their percentages across a format change and mm zones keep their millimetres — which is exactly the disagreement the two units exist for.
- **The MCP server could still publish the wrong worker PID.** The worker records its own PID, but the server then wrote `Popen.pid` — the venv launcher's — into the same status file. If the worker got there first, the launcher's PID overwrote the real one, and an immediate cancel refused with `job_pid_foreign`. The server no longer guesses: it waits for the worker to publish itself (which the worker now does *before* its OpenCV/PyMuPDF imports, so the wait is milliseconds) and leaves status.json alone once the worker owns it. Cancel reads the PID the worker reported about itself.
- **The full test suite was red.** `test_gui_layout` created and immediately destroyed a probe `Tk()`, and the next `Tk()` then failed to load Tcl/Tk. In the full suite that either failed the determinism check or — worse — *skipped* the test with "no Tk display" while the suite stayed green, so the golden widget-tree snapshot silently guarded nothing. The session now uses a single Tk root (`tests/tk_support.py`) and builds each window as a `Toplevel`. `scripts/test.ps1` is green five runs in a row.

### Changed
- **The window had no visual hierarchy.** Window, panel and card were three shades of the same warm grey, so nothing read as a zone; section headings used the same weight and colour as the hints beneath them; and a selected chip differed from an unselected one by a single pixel of border. The palette now separates the surfaces, every section opens with a bold heading and an accent bar, the options sit on a real card, selected states are *filled*, and the slider value is the loud part of its row. Secondary text was `#999791` on a light panel — not quiet, illegible — and is now readable. The ttk theme is `clam`, because the native Windows theme draws tabs and buttons from bitmaps and ignores the colours.
- **The window opens at the size it needs.** The geometry was a constant the form had outgrown: the Compare button and the status line started below the bottom edge. It is now measured from the content, capped to the desktop work area, and centred (Tk cascades new windows down and to the right, which pushed a tall one off-screen).
- The options card heading was never re-translated on a language switch — it stayed Russian in the English UI.
- README screenshots rebuilt from the new interface.

## v0.1.20 - 2026-07-14

Closes the findings of the independent re-check (`docs/reviews/2026-07-14_recheck.md`).

### Fixed
- **A zone set that mixed percent and mm was silently rewritten to mm** (PDF-001). The editor held one unit for the whole dialog, so opening such a set and pressing OK — changing nothing — converted the percent zones. A percent zone and a mm zone mean different things on a differently sized sheet, so that quietly changed which part of an A0 sheet got excluded. Each region now carries its own unit and is written back in it; converting between the two is a data migration and happens only on an explicit click on the unit selector, after a confirmation. The editor also converts in exact millimetres now (`exclusion_regions_to_mm_rects`) instead of through rounded raster pixels, which was turning 70% into 70.04%.
- **A cancelled MCP job could kill an unrelated process** (RECHECK-003). The worker's PID was checked once, before the wait, and then only for existence. Windows hands a PID out again within seconds, so a worker that exited between two polls could get whatever inherited its number killed by the `taskkill /T /F` at the deadline. The process is now pinned by its **creation time** — which a recycled PID cannot fake — and re-verified on every poll and once more immediately before any signal. A PID that has changed hands is reported, not killed.
- **Cancel could refuse to work at all, on the machine where it mattered.** Proving this out on a real 600 DPI re-render turned up two things the mock tests could not have. First, in a virtualenv `Scripts\python.exe` is a *launcher*: it re-execs the real interpreter, so the PID `Popen` returns is not the process running the worker (measured: 62120 vs 41012). Pinning the spawned PID pinned the wrong process, so the worker now records its own identity (`worker.json`) and the server reads that. Second, identity used to be confirmed by reading the process command line, which spawns a PowerShell — and a cancel arrives exactly when every core is busy rendering, so that lookup timed out, came back empty, and the cancel refused with "not our worker", leaving the job running and staging on disk. The creation time is both a stronger identity and needs no subprocess, so it is now authoritative; the command line is only a fallback for jobs started before this release.
- **A slow but healthy worker was force-killed for being slow** (residual risk under PDF-003). `grace_sec` was a deadline for *finishing*: a real cancel of a 600 DPI re-render took ~18 s against a 20 s default, and one heavy A0 sheet outlasts any fixed grace — so the kill landed mid-transaction, which is exactly what cooperative cancel exists to avoid. It is now a limit on *silence*: the worker heartbeats, and acknowledges the cancel (`cancel_acknowledged_at`) once it starts unwinding. A worker that is alive, or already rolling back, is left alone until `max_wait_sec` (300 s). Force-kill is the last fallback for a process that has genuinely stopped responding, and still reports `forced=true`.

### Changed
- **The type gate is real, and the docs no longer oversell it** (RECHECK-001). `AGENTS.md` called mypy "strict" and a hard gate; the config was not strict and `scripts/` was not checked at all — so CI was green on a genuine type error (`FastMCP.run`'s `transport` is a `Literal`, not a `str`). `scripts/pdfcompare_mcp.py` and `scripts/pdfcompare_worker.py` are now in the gate, the transport is validated before `mcp.run()` (an unknown `PDFCOMPARE_MCP_TRANSPORT` used to slip past the non-stdio network guard), and every mypy flag that passes today is switched on — `check_untyped_defs` among them, which was explicitly *off*. What is still not enabled is listed, with counts, in `pyproject.toml`.
- **CLI and MCP errors are bilingual too** (RECHECK-002). v0.1.19 gave the engine a bilingual catalogue but only the GUI used it: `--lang en --dpi 5` and MCP tools called with `lang="en"` still answered in Russian. Both now translate at the boundary. `str(exc)` stays Russian on purpose — worker tracebacks and `worker.log` are matched against it — and travels alongside the translation as `error_detail`.

### Performance
- **The report no longer grows quadratically with the sheet count** (PDF-008). Every detail page inlined a full copy of the sheet list, and every slider re-walked all N sheets to emit its own copy of the drawer *plus* a JSON copy of the same list beside it. Measured: 100 sheets → 26 MB of HTML; 1000 sheets → **1.95 GB** and 32 s to generate, with a single slider page at 1.5 MB. The list now ships once as `nav-data.js` and every page renders from it: 1000 sheets → 83 MB and 5 s, and a page is a fixed size whatever N is. Ten times the sheets now costs ten times the bytes, not seventy-four. The report stays fully offline — a relative `<script src>`, not a `fetch()`, which the browser would block on `file://`.

## v0.1.19 - 2026-07-13

### Added
- **Hover tooltips on every option.** The hint labels explained the sliders, but the chips and buttons ("Строгость", "⇅", "Выбрать…") assumed you already knew. Now each one says what it does, in the interface language.
- **A "?" button (and F1) with a short guide**: what to do step by step, and what `Diff %`, `FG %` and `mm²` actually mean. The app had no answer for a first-time user.
- **Engine errors are bilingual.** The interface was RU/EN but the engine raised Russian-only text, so an English user saw "Не найден summary.json". Errors a user can trigger (DPI, strictness, run name, exclusion zones, a missing report) now render in the interface language. `str(exc)` stays Russian, so logs are unchanged.

### Changed
- `AGENTS.md` described a repository that does not exist ("bootstrap state, no source tree committed yet", a `src/` layout). Agents read it first, so every one of them — including review agents — started from a false map. It is now a real guide: the actual layout, the commands, and the invariants that are easy to break.
- CI audits the locked dependency set with `pip-audit` (advisory: an unfixable transitive advisory should not block shipping). Currently clean.
- Removed `scripts/ai_review_context.ps1` — unreferenced, superseded by `docs/REVIEW_PROMPT.md`.

## v0.1.18 - 2026-07-13

### Fixed
- **The silent auto-update could leave the app unable to start**: `Failed to load Python DLL '…\_MEI…\python312.dll'. LoadLibrary: не найден указанный модуль`. The installer shipped the one-**file** build, which unpacks the Python runtime into `%TEMP%\_MEI<pid>` on every start and deletes that folder when it exits. During a silent update the installer closes the running app and immediately relaunches the new one — and because Windows reuses process ids straight away, the fresh process could start extracting into the very folder the dying one was deleting. The result was a half-extracted runtime: `python312.dll` was there, its CRT dependencies were not.

  The installer now ships a one-**dir** build: the runtime sits next to the exe and there is no extraction step at all (it also starts faster). The single-file EXE remains as a standalone download — nothing races with it there.
- **UPX compression is off.** Compressing `python3xx.dll` and the CRT is the other documented way to produce exactly that error, and the size it saved was not worth that class of failure.

## v0.1.17 - 2026-07-13

The exclusion picker reworked around physical (mm) zones, plus the fixes from an external review of `db8c1d9` — its three `major` findings were reproduced and closed.

### Fixed — exclusion zones

- **Zones drawn in the picker are physical: millimetres from an anchor corner.** They used to be exported as percent of the page, which does not survive a format change — a 185×55 mm title block traced on A4 landscape is 62% × 26% of the sheet, and the same percent box on A0 covers **741×220 mm**, a quarter of the drawing. The diff engine already understood `unit: "mm"`; the picker now uses it, so one stamp zone stays 185×55 mm on A4, A3, A1 and A0 in both orientations. Percent remains available for zones that *should* scale with the sheet.
- **Opening saved percent zones and pressing OK no longer rewrites them.** Because the model is mm and the export always was too, simply opening a legacy `70,80,30,20` zone and confirming it silently changed which part of a differently sized sheet got excluded. The unit now follows what came in: an all-percent set opens — and leaves — as percent.
- **An unknown unit is an error, not silently percent.** A typo like `unit: "cm"` used to produce a valid region covering a completely different area.
- **The picker is localized.** It was handed the Tk root as its parent and looked for a `_tr` method on it, which `tk.Tk` does not have — so every string fell back to English while the Russian ones sat unused in `i18n.py`.
- **The region list could hang the window**: refreshing the list re-selected the row, which re-fired `<<TreeviewSelect>>`, which redrew and re-selected again.

### Changed — the picker

- **Settings are visible toggles in a panel beside the sheet**, not dropdowns: format (A4…A0), **orientation** (portrait/landscape), grid step, anchor corner and units. The current sheet is spelled out ("A4 · вертикальный · 210×297 мм") and the regions are listed with number, size and anchor.
- **The sheet is always blank — the drawing is never shown.** A zone is a size from a corner, so the artwork underneath is noise; and "Auto" (which rendered the real page) was indistinguishable from "A4" on an A4 document. The document's format is detected and preselected instead, with its true size named for a non-standard sheet ("Документ: 305×430 мм"). The backdrop-PDF option went with it — there is nothing left to trace over.
- **Switching format only changes the sheet the zones are drawn on**: that is how you check where they land on A0 before running anything.
- **The window fits the screen, and uses it.** The sheet size was capped by hardcoded numbers, which pushed OK/Cancel off the bottom of a smaller display and wasted space on a larger one. It is now measured against the desktop **work area** (the screen minus the taskbar, from the OS), and the sheet takes what is left.

### Fixed — integrity and safety (from the review)

- **A failed rollback no longer destroys the last copy.** `_RunUpdateTransaction.rollback()` swallowed an `OSError` while restoring a metadata file and then deleted the staging dir — which held the only remaining copy of it. Unrestored files are recorded and their backups kept: a recoverable failure instead of permanent data loss.
- **MCP cancellation asks before it kills.** `cancel_pdf_comparison` force-killed the worker, which could abort a re-render *after* the new pages were swapped in but *before* summary/report were written — the transaction lives in the worker's memory, so nothing rolled it back. The server now writes a cancel marker the worker polls, waits for it to unwind, and force-kills only after a grace period (reporting `forced: true` when it does).
- **Added/removed sheets are interruptible too**: they had one cancel check before two full renders and their writes.
- **The non-stdio guard enforces what it claimed.** It demanded "an environment-specific path allowlist" that did not exist in the code. `PDFCOMPARE_MCP_ALLOWED_DIRS` is now real and enforced (paths are resolved first, so symlinks cannot escape it) and required for a network transport.
- **The MCP checkout installs a hashed lock** (`requirements/lock-runtime.txt`) instead of loose ranges: it pulls master on every start, so the same commit could otherwise pick up a different NumPy/OpenCV/PyMuPDF than CI verified.
- **Agent-facing docs recommend mm + anchor** — they still told agents to collect percent boxes, i.e. exactly the model that breaks on a bigger sheet.

### Added

- **MCP: `check_pdfcompare_update`** — the running version, the checkout's branch and commit, how far behind `origin/master` it is, and anything blocking the pull. `fetch=false` checks offline.
- **MCP auto-update is on by default.** The server runs from its own git checkout, which the installer never touches; auto-update used to be opt-in, so an agent could keep running a months-old engine. Opt out with `-NoAutoUpdate` or `PDFCOMPARE_MCP_AUTO_UPDATE=0`.

### Known / deferred

- The report embeds a full navigation list into every page, so bundle size and generation time grow quadratically with the number of sheets. Fine for the tens-of-sheets sets this tool is used on; it needs a measurement on 100+ sheets before it is worth restructuring.

## v0.1.16 - 2026-07-13

### Added
- **Re-render can be cancelled**: while a re-render runs, its button turns into "Отмена" (like the compare button). Cancelling rolls the run back through the same transaction as a failure — the existing report is left untouched. Closing the window during a re-render now also cancels it and waits for the transaction to unwind, instead of killing the thread mid-swap.

### Fixed
- **Cancellation now stops the pages that are already running.** Previously "Отмена" only dropped the queued pages: the parent noticed the cancel request in its progress callback, which fires when a page *finishes*, so every started page ran to completion first — on a large sheet at high DPI that meant waiting tens of seconds. The parent now polls the cancel callback while it waits, and the workers poll a shared flag between the expensive phases of a page (before each render, before the diff, before writing output), so a cancelled run unwinds at the next phase boundary and leaves no partial run folder behind. The flag reaches the pool workers by inheritance through the pool initializer (a `multiprocessing.Event` cannot be pickled as a task argument under spawn, and a `Manager()` would add a server process to the frozen EXE). Cancellation is also honored outside the page loop (alignment, report generation), so a core caller that passes only `cancel_cb` can stop a run at any stage.

### Changed
- **Reproducible builds**: CI now installs a single hashed lock file (`requirements/lock.txt`, `pip install --require-hashes`) in both the test and the build job, so the same commit always builds against the same dependency set — PyInstaller included, instead of `pip install pyinstaller` picking up whatever is newest. GitHub Actions are pinned by commit SHA (a mutable `@v4` tag can be repointed at any time). `base.txt` / `dev.txt` / `mcp.txt` keep their loose ranges for running from source; `docs/RELEASE_PROCESS.md` documents how to regenerate the lock.

## v0.1.15 - 2026-07-13

Fixes driven by an external repository review (all P1 findings and most P2 confirmed and addressed). Note: the fixes below landed after the `v0.1.14` tag, so the artifacts published as `v0.1.14` do **not** contain them — this is the first release that does.

### Fixed
- **Render megapixel cap is now applied before rasterization**: the effective DPI is computed from the page geometry before `get_pixmap`, so an A0 sheet at high DPI no longer allocates a multi-gigabyte raster that was only downscaled afterwards.
- **Physical metrics honor the effective DPI**: when the cap reduces the render DPI, mm² areas, mm-based exclusion zones, and the bbox merge gap are computed from the DPI the raster actually has (previously they silently used the requested DPI — areas were understated up to ~2.4× on A0 at 250 DPI, and mm zones drifted). `summary.json` rows now record both `high_dpi` (requested) and `effective_dpi`.
- **Re-rendering is transactional**: page backups and pre-update copies of summary/CSV/MD now live until the whole update (pages + summary + HTML) succeeds; any failure rolls the run back to a fully consistent state. Previously the backups were deleted right after the page swap, so a failure while writing summary.json left new PNGs with stale metadata.
- **The report bundle and `start.html` are published together**: the previous report is kept in a backup until the new `start.html` has been written, so a failure in that last step no longer leaves a new report bundle behind a stale entry point while the pages and summary are rolled back. Covered by a failpoint test that hashes pages, summary, the whole report bundle and `start.html`.
- **A failed comparison no longer blocks its run name**: the partial run folder is renamed to `<name>.failed-…` (kept for debugging), so the same name can be retried immediately.
- **`scripts/test.ps1` propagates the pytest exit code** — CI can no longer publish a release with failing tests; mypy is now a hard lint gate too.
- **Cancelling a comparison stops queued pages**: pending ProcessPool futures are cancelled on cancel/error instead of grinding to the end.
- **Tkinter is no longer touched from worker threads**: re-render workers receive the report language as a plain string, and the update-check timestamp is saved via the UI-thread event queue.
- **CLI**: passing only one of `--old`/`--new` is now an explicit error instead of silently falling back to `--input-dir`.
- **Uniform DPI validation (72–1200)** for GUI, CLI, MCP, and per-page re-render overrides; per-page dialog no longer crashes on unparseable stroke/gap values.

### Added
- **Auto-update integrity check**: CI publishes `SHA256SUMS.txt` with every release; the in-app updater downloads the manifest, verifies the installer's SHA-256 before launching it, deletes the file on mismatch, and refuses silent install for releases without a manifest (falls back to the download page).
- **PR checks**: the workflow now runs lint + tests on pull requests in a read-only job; release permissions are limited to the build/publish job.
- **Coverage gate**: `scripts/test.ps1` (and therefore CI) fails if `pdfcompare_core` coverage drops below 82% (actual: ~85%; GUI is intentionally out of scope).
- **Schematic sheet mode in the exclusion picker**: choosing a format manually (A4–A0) switches the preview from the real page to a blank sheet of that format in true proportions — with a GOST-style drawing frame and a dashed 185×55 mm title-block guide in the bottom-right corner — so stamp zones can be traced on a clean sheet instead of a live drawing. "Auto" restores the real page render; the canvas resizes to the chosen format's aspect.
- **Backdrop PDF in the exclusion picker**: the "Подложка…" button loads any other PDF as the visual reference (e.g. a clean template sheet); zones stay in percent of the page and apply to the compared documents as usual. The chosen backdrop is persisted in the app state and preloaded next time; the page switcher follows the backdrop's page count.

### Fixed (history)
- History records now store the bbox-merge options (on/off, gap, max ratio) and the debug-images flag, so "Из истории" restores every parameter instead of resetting them to defaults; snapshot records now capture the full input set (previously they lacked even strictness and exclusion zones, and restoring a snapshot wiped the zones field).
- **License**: the repository is now MIT-licensed (note: the PyMuPDF dependency remains AGPL-3.0/commercial, and its terms apply to distributed builds regardless).

## v0.1.14 - 2026-07-12

### Added
- **Windows installer** (`PDFCompareLocal-setup.exe`, Inno Setup): per-user install without admin rights, Start menu / desktop shortcuts, clean uninstall, in-place upgrades. Built by CI and attached to every release.
- **In-app auto-update**: when a new release is available, the packaged app offers "Download and install now" — it downloads the installer, updates silently (`/SILENT`) and restarts itself. Running from source keeps the previous "open the release page" flow; the version can still be skipped.
- **MCP: text forms for exclude zones** — `start_pdf_comparison` and `rerender_pdf_comparison_pages` accept `exclude_regions` as text (percent `"x,y,w,h;…"` or JSON with `unit`/`anchor`) in addition to object lists, matching the GUI field exactly; an empty string on re-render means "inherit". Tool docstrings and the agent prompt document all forms.
- **MCP: picker parity** — `pick_pdf_exclude_region` now opens the same visual editor as the GUI (mm grid, paper formats, multiple regions, move/resize, per-region corner anchors) and returns an `exclude_regions` list; `existing` zones open for editing, `anchor` preselects the anchor for new boxes.

### Changed
- README redesigned: annotated GUI screenshot with a numbered zone legend, install options table (installer / portable EXE / from source), exclude-zone syntax reference with mm/anchor examples, report overview, and update behavior.

### Fixed
- "Выбрать…" dialogs (old/new PDF, output folder) now open at the folder already written in the field instead of the OS's last-used location.
- "Открыть папку" falls back to the output folder from the field when no comparison has been run yet, instead of only showing "folder not set".
- If tkinterdnd2 is importable but its tkdnd Tcl package fails to load, the app now starts without drag-and-drop (with the status-bar notice) instead of crashing on launch.

## v0.1.13 - 2026-07-12

### Added
- **Exclusion picker rework**: the visual exclude-region dialog now shows a millimetre grid overlay (off/5/10/25/50 mm step), auto-detects the paper format (A4/A3/A2/A1/A0, with manual override for scans whose nominal size differs), and displays a live size label in mm while drawing. Drawn boxes can be selected, moved, resized via 8 handles, and deleted (Del); each box shows its size in mm. Multi-page PDFs get a page switcher. Regions already present in the "Exclude regions" field open as editable boxes, and OK writes the edited set back (so zones can also be removed).
- **Region anchors in the picker**: each zone can be anchored to any page corner (↖/↗/↙/↘). A bottom-right-anchored stamp zone stays in place on sheets of different formats. The anchored corner is marked on the box; the size label and the toolbar readout show offsets from that corner. Anchored sets are written to the field as JSON (`unit: percent`, `anchor: …`); plain top-left sets keep the old `x,y,w,h` text.
- **Exclude picker in the re-render tab**: the uniform "Exclude regions" field got the same picker button. It opens the loaded run's old PDF (the selected row's page when exactly one row is selected) with the field's current zones pre-loaded for editing.

### Fixed
- Pinned sidebar squeezed the whole slider view into the 48px header row: the comparison stage collapsed to the top and auto-fit zoomed to ~1%. The main column now owns the header/stage/controls rows itself; the page grid only splits sidebar/content columns.
- Pin state was not saved to localStorage due to an undefined variable in the pin handler (also broke the button label update).
- Toggling the pin now re-fits the image to the new viewport width after the sidebar transition.
- Slider header no longer overlaps: the title metrics clip with an ellipsis and button labels collapse to icons when the content column is narrow (container queries).
- Embedded slider (iframe on the sheet view page) no longer reserves the 300px pinned sidebar column; the drawer is hidden in embed mode.

## v0.1.12 - 2026-07-12

### Added
- Slider report sidebar is now **pinned by default**: the sheet navigation panel is visible on the left and pushes the comparison content to the right, so you can click any sheet without hovering the edge. A 📌 button in the panel header toggles to the previous floating (hover-to-open) mode. The pin state persists across pages via localStorage.

## v0.1.11 - 2026-07-12

### Changed
- Update check interval reduced from 24 hours to 1 hour.
- Replaced the gear (⚙) icon with an explicit refresh icon (↻) for "check for updates" in the header.

## v0.1.10 - 2026-07-12

### Changed
- The primary change metric is now **% of drawn content** (foreground-relative), not % of the whole sheet. On large A0/A1 drawings where lines cover 3–10% of the page, a significant change that previously read as "0.1%" now shows a meaningful percentage relative to the actual drawing content.
- Composite severity classification: the change level (minor/moderate/major) is now the maximum across three independent signals — FG% (≥1/8/20%), largest change region in mm² (≥100/2500/10000), and number of change zones (≥1/15/40). A significant change is no longer masked by a mostly-empty sheet.
- HTML report: the change matrix leads with the FG% meter bar (heat colors keyed to 1/8/20%); sheet diff% is secondary. Per-page toolbar, slider header, and navigation show FG% first.
- Markdown and live reports: FG% column added ahead of sheet diff%; engineer report sorts by FG%.
- GUI re-render tab: "Drawn %" column promoted ahead of "Diff %".
- Page note: "Changed ≈ X% of drawn content (Y mm², zones: N, max zone: Z mm²)".

### Added
- `foreground_sparse` flag: pages with less than 0.05% drawn content are flagged; on such pages FG% is unreliable and classification falls back to absolute metrics (mm², zones).
- FG% is clamped to 100.0 (mask morphing could push it past 100 on near-empty pages).
- Legend updated to the 1/8/20% FG thresholds.

### Compatibility
- Legacy runs without `foreground_sparse` / `diff_foreground_percent` fall back to the old diff-percent classification and render with "—" for missing fields.

## v0.1.9 - 2026-07-12

### Fixed
- Resolved "coordinates must fit in 0..100%" error when using the visual exclusion picker. The picker rounded x and w independently, so their sum could exceed 100% by a tiny amount and be rejected by validation. The picker now clamps the width/height so x+w and y+h never exceed 100; the validator also tolerates sub-0.01% overflow from rounding instead of rejecting it.

## v0.1.8 - 2026-07-11

### Changed
- Increased default window height (740→820 px) and minimum height (640→700 px) so the bottom action buttons are visible on launch.
- Replaced the bbox-merge and debug-images on/off chips with checkboxes so the pressed/unpressed state is visually obvious.
- Reformulated the stroke-tolerance hint to explain what higher and lower values do.
- Removed the Workers (Auto/1/4) control entirely; the app always uses automatic parallel processing.
- Open Report and Open Folder buttons next to Run are now always enabled and show an informational message when no report/folder exists, instead of being greyed out.
- Removed the duplicate Open report / Open folder hyperlinks from the status bar.

### Added
- A bold, clickable "✓ Report ready to open" banner appears in the status bar as soon as a live report is available mid-comparison, and disappears when the run completes, is cancelled, or errors out.
- Hint label under the report-name field explaining it is optional (empty = auto timestamped folder).

## v0.1.7 - 2026-07-11

### Added
- Auto-update check: on launch the app queries the GitHub releases API (at most once per 24h) and, if a newer version exists, shows a dialog with a link to the download page plus a clickable update badge in the header. The gear icon in the top-right triggers a manual check. Users can skip a specific version to suppress repeated prompts. Network failures are silent on automatic checks.

## v0.1.6 - 2026-07-11

### Added
- Slider report mode: middle-mouse (wheel button) drag to draw a rectangle and zoom the view to fit that rectangle. Left-drag still moves the split divider; right-drag still pans; the browser's middle-click autoscroll is suppressed during the drag. Return to the full view with the existing Fit button or Ctrl+wheel-out.

## v0.1.5 - 2026-07-11

### Fixed
- Resolved out-of-memory crash (`cv2.error: -4 Insufficient memory`, ~1 GB allocation) on large A0/A1 sheets at high DPI. The two full-frame `distanceTransform` buffers are now computed and released one at a time instead of held simultaneously, halving peak memory in the diff engine.
- Added a render-area guard (`MAX_RENDER_MEGAPIXELS = 40`): pages rendered above this size are area-downscaled before the diff to keep memory bounded, while preserving stroke geometry.

## v0.1.4 - 2026-07-11

### Added
- GUI now exposes the same comparison controls as the MCP server: experimental bbox merge (toggle, gap, max-area ratio) and a debug-images toggle, wired through to `compare_pdfs`.
- Visual exclusion-region picker (✏ Pick…) on the Compare tab: draw one or more rectangles on a rendered PDF page instead of typing `x,y,w,h` by hand.
- Re-render tab now shows the `FG %` and `mm²` content-relative metrics per row, alongside `Diff %`.
- Re-render tab supports override fields (stroke tolerance, strictness, exclude regions, bbox merge) and a per-page (mixed-precision) mode that routes selected pages through `regenerate_report_pages_mixed`.
- CLI gained `--bbox-merge-gap-mm` and `--bbox-merge-max-area-ratio` flags for parity with GUI and MCP.

### Changed
- Moved packaging, requirements, launchers, and agent setup prompt files into dedicated folders to keep the repository root smaller.
- `start_pdf_comparison` signature in the MCP docs now lists the full parameter set (`diff_strictness`, `exclude_regions`, `bbox_merge_max_area_ratio`).

### Fixed
- PyInstaller spec resolves its root from `SPECPATH` after the spec moved into `packaging/`, so EXE builds work regardless of the invocation working directory.

## v0.1.3 - 2026-07-03

### Added
- Excluded page regions for ignoring title blocks, stamps, or author tables during visual diff.
- Diff strictness presets (`strict`, `normal`, `loose`) across CLI, GUI, and MCP.
- Content-relative `FG %` and physical `mm²` change metrics in report data and HTML.
- Safe per-page rerendering through MCP with visible custom-precision markers.

### Changed
- Bbox merging remains disabled by default and is documented as experimental.
- Optional bbox merging now groups from the diff mask and rejects sparse, page-sized groups.
- Change severity can use content-relative foreground percentage when available, not only whole-sheet page percentage.

## v0.1.2 - 2026-06-15

### Added
- Local stdio MCP server scripts and agent documentation for background PDF comparison jobs.
- Optional named result folders via `--run-name`, GUI report-name field, and shared run-name sanitization.
- Tests for named result folder sanitization and path construction.
- Copy-paste agent prompts for connecting PDFCompare MCP and starting comparisons.
- One-click Cursor/VS Code MCP setup buttons and `SETUP_PROMPT.md` for agent-driven installation.
- MCP bootstrap wrapper that refreshes dependencies, starts the stdio server, and supports opt-in repository updates.

### Changed
- Portable ZIP packaging now ships a runtime-focused set: core/UI modules, GUI/MCP launch scripts, and short user/agent docs.
- MCP dependencies are split into `requirements-mcp.txt`; base desktop installs stay lightweight.
- `pytest` is scoped to `tests/` so generated portable builds do not create duplicate test collection.
- Release/download links are surfaced as README buttons for direct EXE and portable ZIP access.

### Fixed
- OpenCV typing noise in lint/mypy checks for normalization and ECC calls.

## v0.1.1 - 2026-05-12

### Added
- Slider pages now have previous/next navigation between comparable sheets.
- Slider pages now include a hover/click sheet picker with status, diff percentage, change-zone count, and search.
- Detail and slider pages now include a `Save DIFF as` action for downloading the generated overlay image for the current sheet.

### Changed
- The current sheet highlight in report navigation is more visible with a green accent and stronger background.

## v0.1.0 - 2026-05-06

First public release of PDFCompare Local.

### Added
- Windows GUI for comparing two PDF revisions locally.
- CLI entry point with `--old`/`--new` or `--input-dir` modes.
- Visual HTML report with summary, mapped pages, OLD/NEW/DIFF views, and slider comparison.
- Page mapping that handles inserted and removed sheets.
- Parallel page comparison via `--workers`.
- RU/EN UI and report language support.
- Run history, configuration restore, and selected-page re-rendering.
- Portable Python ZIP packaging script.
- GitHub Actions pipeline for lint, tests, EXE build, portable ZIP build, and tagged releases.

### Changed
- Generated run internals are stored under `_pdfcompare/` with a lightweight `start.html` launcher at the run root.
- Full-size alignment debug images are disabled by default and can be restored with `--keep-debug-images`.

### Known Limitations
- No project license is declared yet.
- Current public test coverage focuses on change classification and report generation smoke checks.
