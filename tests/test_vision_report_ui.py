"""The AI report pages: what the reader sees about each sheet."""

from __future__ import annotations

import json
import unittest

from pdfcompare_core.vision_report_ui import _highlights_html, vision_index_html, vision_sheet_html
from pdfcompare_core.vision_review_ui import REVIEW_SCRIPT


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


def _sheet_index(html: str) -> list[dict]:
    start = html.index("<script id='sheetIndex' type='application/json'>") + len("<script id='sheetIndex' type='application/json'>")
    return json.loads(html[start:html.index("</script>", start)].replace("<\\/", "</"))


class SheetToolsTests(unittest.TestCase):
    def test_sheet_switcher_lists_every_sheet_with_counts_and_main_objects(self) -> None:
        sheets = [
            _sheet(3, [_zone(1, "real_change", "Узел 32/18: добавлен", object_ref="Узел 32/18"),
                       _zone(2, "alignment_or_rendering_noise", "Штамп")]),
            _sheet(7, [_zone(1, "uncertain", "Ссылка 21→25: не подтверждено")]),
        ]
        html = vision_sheet_html(sheets[1], [3, 7], sheets=sheets)
        self.assertIn("▦ Листы <span class='nav-pos'>2 / 2</span>", html)
        self.assertEqual(_sheet_index(html), [
            {"seq": 3, "counts": {"real_change": 1, "uncertain": 0, "alignment_or_rendering_noise": 1}, "labels": ["Узел 32/18"]},
            {"seq": 7, "counts": {"real_change": 0, "uncertain": 1, "alignment_or_rendering_noise": 0}, "labels": ["Ссылка 21→25"]},
        ])

    def test_sheet_switcher_without_sheet_data_still_lists_the_numbers(self) -> None:
        self.assertEqual(_sheet_index(vision_sheet_html(_sheet(1, []), [1, 2])), [{"seq": 1}, {"seq": 2}])

    def test_reader_decides_with_buttons_and_can_correct_the_outline(self) -> None:
        html = vision_sheet_html(_sheet(1, [_zone(1, "real_change", "A: x", rect={"x": 1, "y": 2, "w": 3, "h": 4})]), [1])
        for verdict in ("real_change", "uncertain", "alignment_or_rendering_noise"):
            self.assertIn(f"data-verdict='{verdict}'", html)
        for control in ("id='resetVerdict'", "id='editShape'", "id='resetShape'", "id='detailOldCanvas'", "Ctrl+Z — отменить"):
            self.assertIn(control, html)
        self.assertNotIn("manualClass", html)

    def test_overview_saves_and_loads_decisions_as_a_file(self) -> None:
        html = vision_index_html("Gemini", "m", [_sheet(1, [_zone(1, "real_change", "A: x")])])
        for control in ("id='exportReview'", "for='importReview'", "id='importReview' accept='.json,application/json'"):
            self.assertIn(control, html)
        # The file is checked for its format and only keys of zones in this report are taken.
        self.assertIn("data.format!=='pdfcompare-review'", html)
        self.assertIn("keys.has(key)&&reviewClasses.includes(value)", html)
        self.assertIn("keys.has(key)&&reviewShape(value)", html)

    def test_saved_decisions_stay_attached_after_an_outline_moves(self) -> None:
        # The zone key hashes the AI rect; a corrected outline must not change it, or the reader's
        # decisions saved before the edit would silently detach from their zones.
        self.assertIn("z.description,z.ai_rect||z.rect]", REVIEW_SCRIPT)
        self.assertIn("if(!('ai_rect' in z)){z.ai_rect=z.rect||null", REVIEW_SCRIPT)


if __name__ == "__main__":
    unittest.main()
