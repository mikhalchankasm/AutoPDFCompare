"""Markdown report writers (summary.md and engineer_report.md)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .models import MatchPair


def write_summary_md(
    out_path: Path,
    file_a: Path,
    file_b: Path,
    pairs: Sequence[MatchPair],
    details: Sequence[dict],
    lang: str = "ru",
) -> None:
    matched = sum(1 for p in pairs if p.status == "matched")
    added = sum(1 for p in pairs if p.status == "added")
    removed = sum(1 for p in pairs if p.status == "removed")
    unchanged = sum(1 for d in details if d["status"] == "matched" and d["change_level"] == "unchanged")
    changed = matched - unchanged

    en = str(lang).lower().startswith("en")
    if en:
        lines = [
            "# PDF Compare Report",
            "",
            f"- Document A: `{file_a.name}`",
            f"- Document B: `{file_b.name}`",
            f"- Matched pages: **{matched}**",
            f"- Changed pages: **{changed}**",
            f"- Unchanged pages: **{unchanged}**",
            f"- Added in B: **{added}**",
            f"- Removed from A: **{removed}**",
            "",
            "## Page mapping",
            "",
            "| A page | B page | status | score | drawn % | sheet % | level |",
            "|---:|---:|---|---:|---:|---:|---|",
        ]
    else:
        lines = [
            "# Отчет сравнения PDF",
            "",
            f"- Документ A: `{file_a.name}`",
            f"- Документ B: `{file_b.name}`",
            f"- Сопоставленных листов: **{matched}**",
            f"- Листов с изменениями: **{changed}**",
            f"- Листов без изменений: **{unchanged}**",
            f"- Добавлено листов в B: **{added}**",
            f"- Удалено листов из A: **{removed}**",
            "",
            "## Карта соответствия листов",
            "",
            "| Лист A | Лист B | статус | оценка | заполнено % | лист % | уровень |",
            "|---:|---:|---|---:|---:|---:|---|",
        ]
    for d in details:
        a = "-" if d["a_page"] is None else str(d["a_page"])
        b = "-" if d["b_page"] is None else str(d["b_page"])
        diffp = "-" if d["diff_percent"] is None else f'{d["diff_percent"]:.3f}'
        fgp = "-" if d.get("diff_foreground_percent") is None else f'{d["diff_foreground_percent"]:.2f}'
        lvl = "-" if d["change_level"] is None else d["change_level"]
        lines.append(f"| {a} | {b} | {d['status']} | {d['score']:.3f} | {fgp} | {diffp} | {lvl} |")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_engineer_report_md(
    out_path: Path,
    file_a: Path,
    file_b: Path,
    details: Sequence[dict],
    lang: str = "ru",
) -> None:
    en = str(lang).lower().startswith("en")
    matched = [d for d in details if d["status"] == "matched"]
    added = [d for d in details if d["status"] == "added"]
    removed = [d for d in details if d["status"] == "removed"]
    size_mismatch = [d for d in details if d["status"] == "size_mismatch"]

    unchanged = [d for d in matched if d["change_level"] == "unchanged"]
    minor = [d for d in matched if d["change_level"] == "minor"]
    moderate = [d for d in matched if d["change_level"] == "moderate"]
    major = [d for d in matched if d["change_level"] == "major"]

    if en:
        lines = [
            "# Engineering PDF Compare Report",
            "",
            f"- Base document (A): `{file_a.name}`",
            f"- New document (B): `{file_b.name}`",
            "",
            "## Summary",
            "",
            f"- Matched sheets: **{len(matched)}**",
            f"- Added in B: **{len(added)}**",
            f"- Removed from A: **{len(removed)}**",
            f"- Unchanged: **{len(unchanged)}**",
            f"- Minor changes: **{len(minor)}**",
            f"- Moderate changes: **{len(moderate)}**",
            f"- Major changes: **{len(major)}**",
        ]
    else:
        lines = [
            "# Инженерный отчёт сравнения PDF",
            "",
            f"- Базовый документ (A): `{file_a.name}`",
            f"- Новый документ (B): `{file_b.name}`",
            "",
            "## Краткий итог",
            "",
            f"- Сопоставлено листов: **{len(matched)}**",
            f"- Добавлено листов в B: **{len(added)}**",
            f"- Удалено листов из A: **{len(removed)}**",
            f"- Без изменений: **{len(unchanged)}**",
            f"- Небольшие изменения: **{len(minor)}**",
            f"- Заметные изменения: **{len(moderate)}**",
            f"- Сильные изменения: **{len(major)}**",
        ]

    if size_mismatch:
        lines.append(
            f"- {'Incompatible sheet format' if en else 'Несовместимый формат листа'}: **{len(size_mismatch)}**"
        )

    lines.extend(
        [
            "",
            "## Added sheets" if en else "## Добавленные листы",
            "",
        ]
    )
    if added:
        for d in added:
            lines.append(f"- B{d['b_page']}: {'new sheet in revision' if en else 'новый лист в ревизии'}")
    else:
        lines.append("- None" if en else "- Нет")

    lines.extend(
        [
            "",
            "## Removed sheets" if en else "## Удалённые листы",
            "",
        ]
    )
    if removed:
        for d in removed:
            lines.append(
                f"- A{d['a_page']}: {'sheet missing in new revision' if en else 'лист отсутствует в новой ревизии'}"
            )
    else:
        lines.append("- None" if en else "- Нет")

    def emit_changes(title: str, rows: Sequence[dict]) -> None:
        lines.extend(["", f"## {title}", ""])
        if not rows:
            lines.append("- None" if en else "- Нет")
            return
        for d in sorted(rows, key=lambda x: (x.get("diff_foreground_percent") or x.get("diff_percent") or 0.0), reverse=True):
            fgp = d.get("diff_foreground_percent")
            area = d.get("diff_area_mm2")
            fg_txt = "-" if fgp is None else f"{fgp:.2f}%"
            area_txt = "-" if area is None else f"{area:.1f} mm²"
            lines.append(
                f"- A{d['a_page']} -> B{d['b_page']}: {'drawn' if en else 'заполнено'}={fg_txt}"
                f", {'area' if en else 'площадь'}={area_txt}"
                f", {'zones' if en else 'зон'}={d.get('bboxes_count', '-')}"
            )

    emit_changes("Unchanged" if en else "Без изменений", unchanged)
    emit_changes("Minor changes" if en else "Небольшие изменения", minor)
    emit_changes("Moderate changes" if en else "Заметные изменения", moderate)
    emit_changes("Major changes" if en else "Сильные изменения", major)

    if size_mismatch:
        lines.extend(["", "## Incompatible sheet format" if en else "## Несовместимый формат листа", ""])
        for d in size_mismatch:
            lines.append(
                f"- A{d['a_page']} -> B{d['b_page']}: "
                f"{'sheet sizes do not match' if en else 'размеры листов не совпадают'}"
            )

    lines.extend(
        [
            "",
            "## Note" if en else "## Примечание",
            "",
            "- Each mapped pair has a folder `pages/<seq>__A_<n>__B_<m>/` with `overlay.png`, `mask.png`, `bboxes.json`."
            if en
            else "- Для каждой сопоставленной пары есть папка `pages/<seq>__A_<n>__B_<m>/` c `overlay.png`, `mask.png`, `bboxes.json`.",
        ]
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")
