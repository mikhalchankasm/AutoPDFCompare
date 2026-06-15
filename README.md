# PDFCompare Local

Current release: `v0.1.2`

Локальный инструмент для сравнения двух многостраничных PDF (чертежи, схемы, рабочая документация) с генерацией HTML-отчета и режима визуального слайдера.

Local desktop tool for comparing two multi-page PDFs (drawings/specs) with HTML report output and an interactive slider view.

## Скачать / Download
[![Download Windows EXE][download-exe-badge]][download-exe]
[![Download portable ZIP][download-zip-badge]][download-zip]
[![Latest Release][latest-release-badge]][latest-release]

- [PDFCompareLocal.exe](https://github.com/mikhalchankasm/AutoPDFCompare/releases/latest/download/PDFCompareLocal.exe) — Windows EXE, Python не нужен.
- [PDFCompareLocal-portable.zip](https://github.com/mikhalchankasm/AutoPDFCompare/releases/latest/download/PDFCompareLocal-portable.zip) — portable-вариант для машины с Python 3.

Для обычного пользователя самый простой вариант — скачать `PDFCompareLocal.exe` из Latest Release и запустить файл. Установка Python не требуется.

## MCP для агентов / MCP for agents
[![Add to Cursor][cursor-badge]][cursor-install]
[![Install in VS Code][vscode-badge]][vscode-install]

Кнопки устанавливают локальный MCP-сервер `pdfcompare` через bootstrap-команду: она клонирует репозиторий в `%LOCALAPPDATA%\PDFCompareMCP\AutoPDFCompare`, ставит зависимости и запускает stdio MCP. Для MCP-режима нужны Git, Python 3.10+ и доступ к GitHub.

Важно: MCP-кнопки запускают локальную PowerShell-команду и код из этого репозитория. Используйте их только если доверяете репозиторию; для обычного desktop-сценария безопаснее скачать готовый `PDFCompareLocal.exe`.

Для установки через любого локального агента вставьте один prompt:

```text
Прочитай https://raw.githubusercontent.com/mikhalchankasm/AutoPDFCompare/master/SETUP_PROMPT.md и выполни инструкцию по подключению PDFCompare MCP. Используй stdio transport, имя сервера pdfcompare.
```

Чтобы позже подтянуть изменения, попросите агента: `Обнови PDFCompare MCP по инструкции из SETUP_PROMPT.md`.

## Возможности / Features
- Постраничный маппинг между ревизиями (учет вставленных/удаленных листов).
- Визуальный diff с учетом допуска толщины линий.
- Отчет: сводка, навигация по листам, детальный просмотр OLD/NEW/DIFF, режим слайдера с быстрым переходом между листами.
- История запусков и восстановление последней конфигурации.
- RU/EN локализация UI (переключатель языка в правом верхнем углу).

## Демонстрация / Screenshots

Скриншоты показывают интерфейс; содержимое чертежей и спецификаций намеренно размыто.

### Change Matrix
![Change Matrix overview](img/01_change_matrix.png)

### Sheet Detail
![Detailed sheet comparison](img/02_change_matrix_detail.png)

### Slider Mode
![Interactive slider mode](img/03_slider_mode.png)

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

Если нужен агентский MCP-режим, установите дополнительные зависимости:
```powershell
./scripts/setup.ps1 -WithMcp
```
Готовые copy-paste prompts для агентов лежат в `SETUP_PROMPT.md` и `docs/AGENT_PROMPTS.md`.

Собрать ZIP с исходниками, скриптами запуска и зависимостями для установки:
```powershell
./scripts/package_portable.ps1
```
Архив будет создан в `dist_portable/PDFCompareLocal-portable.zip`. Он рассчитан на машину с установленным Python 3; если Python ставить нельзя, используйте EXE-сборку.

CLI режим:
```bash
python compare_pdfs.py --version
python compare_pdfs.py --input-dir TestDocs --out-dir runs --dpi 250 --stroke-tol 2.0
python compare_pdfs.py --old old.pdf --new new.pdf --out-dir runs --run-name My_Comparison
```
По умолчанию запуск не сохраняет лишние полноразмерные debug-копии (`b_raw.png`, `b_aligned.png`), чтобы уменьшить размер папки результата. Для отладки выравнивания добавьте `--keep-debug-images`.
Сравнение листов выполняется параллельно: `--workers 0` означает авто-режим (до 4 процессов), `--workers 1` отключает параллелизм, большее число задает количество процессов явно.

## Локальный MCP / Local MCP
Репозиторий может запускаться как локальный stdio MCP-сервер для агентов. MCP-режим валидирует PDF, предлагает имя папки результата, запускает сравнение в фоне и хранит статус задач в `.pdfcompare_mcp/jobs/`.

Основные инструменты MCP:
- `prepare_pdf_comparison` — проверяет пути, считает страницы, ищет похожие прошлые сравнения и предлагает имена папки.
- `start_pdf_comparison` — запускает фоновое сравнение и возвращает `job_id`, `run_dir`, `report_path`.
- `get_pdf_comparison_status` — возвращает прогресс или финальную сводку.
- `list_pdf_comparisons` — показывает завершенные сравнения.
- `cancel_pdf_comparison` — останавливает активную задачу.

Локальный запуск для проверки:
```powershell
./scripts/setup.ps1 -WithMcp
./scripts/run_mcp.ps1
```

Пример MCP-конфигурации клиента:
```json
{
  "mcpServers": {
    "pdfcompare": {
      "command": "D:\\GitHub\\PDFCompare\\.venv\\Scripts\\python.exe",
      "args": ["D:\\GitHub\\PDFCompare\\scripts\\pdfcompare_mcp.py"]
    }
  }
}
```

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
- `compare_pdfs.py` — совместимый facade и CLI entry point.
- `pdfcompare_core/` — движок сравнения, маппинг страниц, HTML/Markdown отчеты.
- `pdfcompare_ui/` — GUI mixins, состояние, история, drag-and-drop.
- `SETUP_PROMPT.md` — один prompt для агента, который устанавливает и подключает MCP.
- `docs/AGENT_PROMPTS.md` — короткие prompts для подключения MCP в локальном агенте.
- `scripts/pdfcompare_mcp.py` — stdio MCP-сервер для локальных агентов.
- `scripts/pdfcompare_worker.py` — фоновый worker MCP-задач.
- `scripts/run_mcp_bootstrap.ps1` — MCP bootstrap с проверкой зависимостей и opt-in обновлением.
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

[download-exe]: https://github.com/mikhalchankasm/AutoPDFCompare/releases/latest/download/PDFCompareLocal.exe
[download-zip]: https://github.com/mikhalchankasm/AutoPDFCompare/releases/latest/download/PDFCompareLocal-portable.zip
[latest-release]: https://github.com/mikhalchankasm/AutoPDFCompare/releases/latest
[download-exe-badge]: https://img.shields.io/badge/Download-Windows_EXE-2ea44f?logo=windows&logoColor=white
[download-zip-badge]: https://img.shields.io/badge/Download-Portable_ZIP-0969da?logo=github&logoColor=white
[latest-release-badge]: https://img.shields.io/github/v/release/mikhalchankasm/AutoPDFCompare?label=Latest%20Release
[cursor-badge]: https://cursor.com/deeplink/mcp-install-dark.svg
[cursor-install]: https://cursor.com/install-mcp?name=pdfcompare&config=eyJjb21tYW5kIjoicG93ZXJzaGVsbCIsImFyZ3MiOlsiLU5vUHJvZmlsZSIsIi1FeGVjdXRpb25Qb2xpY3kiLCJCeXBhc3MiLCItQ29tbWFuZCIsIiRFcnJvckFjdGlvblByZWZlcmVuY2U9J1N0b3AnOyAkcmVwbz1Kb2luLVBhdGggJGVudjpMT0NBTEFQUERBVEEgJ1BERkNvbXBhcmVNQ1BcXEF1dG9QREZDb21wYXJlJzsgJGxvZz1Kb2luLVBhdGggJGVudjpURU1QICdwZGZjb21wYXJlX21jcF9ib290c3RyYXAubG9nJzsgaWYgKCEoVGVzdC1QYXRoICRyZXBvKSkgeyBOZXctSXRlbSAtSXRlbVR5cGUgRGlyZWN0b3J5IC1Gb3JjZSAtUGF0aCAoU3BsaXQtUGF0aCAkcmVwbykgKj4gJGxvZzsgZ2l0IGNsb25lIGh0dHBzOi8vZ2l0aHViLmNvbS9taWtoYWxjaGFua2FzbS9BdXRvUERGQ29tcGFyZS5naXQgJHJlcG8gKj4+ICRsb2cgfTsgJiAoSm9pbi1QYXRoICRyZXBvICdzY3JpcHRzXFxydW5fbWNwX2Jvb3RzdHJhcC5wczEnKSJdfQ==
[vscode-badge]: https://img.shields.io/badge/VS_Code-Install_MCP-007ACC?logo=visualstudiocode&logoColor=white
[vscode-install]: https://insiders.vscode.dev/redirect/mcp/install?name=pdfcompare&config=%7B%22name%22%3A%22pdfcompare%22%2C%22command%22%3A%22powershell%22%2C%22args%22%3A%5B%22-NoProfile%22%2C%22-ExecutionPolicy%22%2C%22Bypass%22%2C%22-Command%22%2C%22%24ErrorActionPreference%3D%27Stop%27%3B%20%24repo%3DJoin-Path%20%24env%3ALOCALAPPDATA%20%27PDFCompareMCP%5C%5CAutoPDFCompare%27%3B%20%24log%3DJoin-Path%20%24env%3ATEMP%20%27pdfcompare_mcp_bootstrap.log%27%3B%20if%20%28%21%28Test-Path%20%24repo%29%29%20%7B%20New-Item%20-ItemType%20Directory%20-Force%20-Path%20%28Split-Path%20%24repo%29%20%2A%3E%20%24log%3B%20git%20clone%20https%3A//github.com/mikhalchankasm/AutoPDFCompare.git%20%24repo%20%2A%3E%3E%20%24log%20%7D%3B%20%26%20%28Join-Path%20%24repo%20%27scripts%5C%5Crun_mcp_bootstrap.ps1%27%29%22%5D%7D
