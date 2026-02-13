# PDFCompare Local

Локальный инструмент для сравнения двух многостраничных PDF (чертежи, схемы, рабочая документация) с генерацией HTML-отчета и режима визуального слайдера.

Local desktop tool for comparing two multi-page PDFs (drawings/specs) with HTML report output and an interactive slider view.

## Скачать / Download
- Последний EXE:  
  `https://github.com/mikhalchankasm/AutoPDFCompare/releases/latest/download/PDFCompareLocal.exe`

## Возможности / Features
- Постраничный маппинг между ревизиями (учет вставленных/удаленных листов).
- Визуальный diff с учетом допуска толщины линий.
- Отчет: сводка, навигация по листам, детальный просмотр OLD/NEW/DIFF, режим слайдера.
- История запусков и восстановление последней конфигурации.
- RU/EN локализация UI (переключатель языка в правом верхнем углу).

## Быстрый старт / Quick start
```bash
python -m pip install --upgrade pip
pip install numpy opencv-python-headless pymupdf
python pdfcompare_gui.py
```

CLI режим:
```bash
python compare_pdfs.py --input-dir TestDocs --out-dir runs --dpi 250 --stroke-tol 2.0
```

## Сборка EXE / Build EXE
```bash
pyinstaller --noconfirm PDFCompareLocal.spec
```
Готовый файл: `dist/PDFCompareLocal.exe`.

## Структура / Structure
- `pdfcompare_gui.py` — Windows GUI.
- `compare_pdfs.py` — движок сравнения и генератор отчетов.
- `run_gui.bat` — быстрый запуск GUI.
- `dist/` — локальные сборки (игнорируются в git).
- `runs/` — результаты сравнений (игнорируются в git).

## CI/CD (GitHub Actions)
- Workflow: `.github/workflows/build-exe.yml`
- На `push` в `master` (по ключевым файлам) собирается Windows EXE и публикуется как artifact.
- На тегах `v*` EXE прикрепляется к GitHub Release.
