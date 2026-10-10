"""The AI report pages: what the reader sees about each sheet."""

from __future__ import annotations

import unittest

from pdfcompare_core.vision_report_ui import _highlights_html, vision_index_html, vision_sheet_html


def _sheet(seq: int, zones: list[dict], **source: str) -> dict:
    counts = {"real_change": 0, "alignment_or_rendering_noise": 0, "uncertain": 0}
    for zone in zones:
        counts[zone["classification"]] += 1
    return {
        "seq": seq,
        "size_px": [100, 80],
        "counts": counts,
        "zones": zones,
        "report_schema": "semantic-v1",
        "source": {"old_name": "old.pdf", "new_name": "new.pdf", **source},
    }


def _zone(zone_id: int, classification: str, description: str, **fields: object) -> dict:
    return {"id": zone_id, "classification": classification, "description": description, "confidence": 90, "rect": None, **fields}


class HighlightsTests(unittest.TestCase):
    def test_sheet_row_names_the_changed_objects_edits_first(self) -> None:
        html = _highlights_html([
            _zone(1, "uncertain", "Ссылка 21→25: не подтверждено"),
            _zone(2, "real_change", "Узел 32/18: добавлен", object_ref="Узел 32/18"),
            _zone(3, "real_change", "Узел 32/18: вторая часть", object_ref="Узел 32/18"),
            _zone(4, "alignment_or_rendering_noise", "Сдвиг штампа"),
        ])
        self.assertLess(html.index("Узел 32/18"), html.index("Ссылка 21→25"))
        self.assertEqual(html.count("Узел 32/18"), 2)  # once as text, once as title; duplicates merged
        self.assertNotIn("Сдвиг штампа", html)

    def test_sheet_without_edits_says_so_and_counts_noise(self) -> None:
        self.assertIn("Только оформление / шум (1)", _highlights_html([_zone(1, "alignment_or_rendering_noise", "Сдвиг")]))
        self.assertIn("Правок не найдено", _highlights_html([]))

    def test_long_lists_are_capped(self) -> None:
        zones = [_zone(i, "real_change", f"Объект {i}: правка") for i in range(1, 8)]
        self.assertIn("и ещё 3", _highlights_html(zones))


class PageTests(unittest.TestCase):
    def test_placeholder_revisions_are_not_repeated(self) -> None:
        sheet = _sheet(1, [], old_revision="OLD", new_revision="NEW")
        for html in (vision_index_html("Gemini", "m", [sheet]), vision_sheet_html(sheet, [1])):
            self.assertNotIn("OLD · OLD", html)
            self.assertNotIn("NEW · NEW", html)

    def test_real_revisions_are_shown(self) -> None:
        sheet = _sheet(1, [], old_revision="Изм. 1", new_revision="Изм. 2")
        self.assertIn("ревизия Изм. 1", vision_index_html("Gemini", "m", [sheet]))
        self.assertIn("Лист 1 · Изм. 1 → Изм. 2", vision_sheet_html(sheet, [1]))

    def test_index_filters_count_sheets_by_outcome(self) -> None:
        sheets = [
            _sheet(1, [_zone(1, "real_change", "A: x")]),
            _sheet(2, [_zone(1, "uncertain", "B: y")]),
            _sheet(3, [_zone(1, "alignment_or_rendering_noise", "C: z")]),
        ]
        html = vision_index_html("Gemini", "m", sheets)
        self.assertIn("С правками<b data-sheet-count='real'>1</b>", html)
        self.assertIn("Проверить<b data-sheet-count='uncertain'>1</b>", html)
        self.assertIn("Без правок<b data-sheet-count='none'>1</b>", html)


if __name__ == "__main__":
    unittest.main()
