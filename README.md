# PDFCompare Local

Current release: `v0.1.0`

Локальный инструмент для сравнения двух многостраничных PDF (чертежи, схемы, рабочая документация) с генерацией HTML-отчета и режима визуального слайдера.

Local desktop tool for comparing two multi-page PDFs (drawings/specs) with HTML report output and an interactive slider view.

## Скачать / Download
- [PDFCompareLocal.exe](https://github.com/mikhalchankasm/AutoPDFCompare/releases/latest/download/PDFCompareLocal.exe) — Windows EXE, Python не нужен.
- [PDFCompareLocal-portable.zip](https://github.com/mikhalchankasm/AutoPDFCompare/releases/latest/download/PDFCompareLocal-portable.zip) — portable-вариант для машины с Python 3.

## Возможности / Features
- Постраничный маппинг между ревизиями (учет вставленных/удаленных листов).
- Визуальный diff с учетом допуска толщины линий.
- Отчет: сводка, навигация по листам, детальный просмотр OLD/NEW/DIFF, режим слайдера.
- История запусков и восстановление последней конфигурации.
- RU/EN локализация UI (переключатель языка в правом верхнем углу).

## Быстрый старт / Quick start
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python pdfcompare_gui.py
```

Portable Python-вариант:
```powershell
./scripts/setup.ps1
./scripts/run.ps1
```

Собрать ZIP с исходниками, скриптами запуска и зависимостями для установки:
```powershell
./scripts/package_portable.ps1
```
Архив будет создан в `dist_portable/PDFCompareLocal-portable.zip`. Он рассчитан на машину с установленным Python 3; если Python ставить нельзя, используйте EXE-сборку.

CLI режим:
```bash
python compare_pdfs.py --version
python compare_pdfs.py --input-dir TestDocs --out-dir runs --dpi 250 --stroke-tol 2.0
```
По умолчанию запуск не сохраняет лишние полноразмерные debug-копии (`b_raw.png`, `b_aligned.png`), чтобы уменьшить размер папки результата. Для отладки выравнивания добавьте `--keep-debug-images`.
Сравнение листов выполняется параллельно: `--workers 0` означает авто-режим (до 4 процессов), `--workers 1` отключает параллелизм, большее число задает количество процессов явно.

Полезные локальные проверки:
```powershell
./scripts/lint.ps1
./scripts/test.ps1
./scripts/ai_review_context.ps1
```

## Сборка EXE / Build EXE
```bash
pyinstaller --noconfirm PDFCompareLocal.spec
```
Готовый файл: `dist/PDFCompareLocal.exe`.

EXE и portable-вариант лучше держать параллельно:
- EXE: удобен пользователю без Python, но сложнее отлаживать и пересобирать.
- Portable Python: быстрее обновлять, проще диагностировать ошибки и лучше подходит для внутренних пользователей/инженеров.

## Структура / Structure
- `pdfcompare_gui.py` — Windows GUI.
- `compare_pdfs.py` — движок сравнения и генератор отчетов.
- `run_gui.bat` — быстрый запуск GUI.
- `dist/` — локальные сборки (игнорируются в git).
- `runs/` — результаты сравнений (игнорируются в git).

## CI/CD (GitHub Actions)
- Workflow: `.github/workflows/build-exe.yml`
- На `push` в `master` запускаются lint/test, собираются Windows EXE и portable ZIP, публикуются как artifacts.
- На тегах `v*` EXE и portable ZIP прикрепляются к GitHub Release, release notes берутся из `docs/releases/<tag>.md`.

## Релизы / Releases
- История изменений: `CHANGELOG.md`.
- Процесс выпуска: `docs/RELEASE_PROCESS.md`.

## Лицензия / License
Лицензия пока не указана. Перед приемом внешних contribution или объявлением проекта open-source нужно добавить `LICENSE`.
