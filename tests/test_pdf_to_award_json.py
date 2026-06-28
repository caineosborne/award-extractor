import json
import tempfile
import unittest
from pathlib import Path

from src.script_1_pdf_to_award_json import (
    CONTENT_KEY,
    body_start_page_number,
    parse_clause_heading,
    parse_markdown_events,
    parse_table_markdown,
    split_markdown_events,
    write_pdf_outputs,
)


class PdfToAwardJsonTests(unittest.TestCase):
    def test_parse_clause_heading_handles_numeric_alpha_and_roman_markers(self):
        top_level = parse_clause_heading(
            "1. About this Agreement",
            current_numeric_depth=None,
            current_alpha_depth=None,
        )
        self.assertIsNotNone(top_level)
        assert top_level is not None
        self.assertEqual(top_level.reference, "1")
        self.assertEqual(top_level.level, 1)

        nested_numeric = parse_clause_heading(
            "1.2.3 Overtime meal breaks",
            current_numeric_depth=1,
            current_alpha_depth=None,
        )
        self.assertIsNotNone(nested_numeric)
        assert nested_numeric is not None
        self.assertEqual(nested_numeric.reference, "1.2.3")
        self.assertEqual(nested_numeric.level, 3)

        alpha_marker = parse_clause_heading(
            "a. Casual team members",
            current_numeric_depth=2,
            current_alpha_depth=None,
        )
        self.assertIsNotNone(alpha_marker)
        assert alpha_marker is not None
        self.assertEqual(alpha_marker.reference, "a")
        self.assertEqual(alpha_marker.level, 3)

        roman_marker = parse_clause_heading(
            "i. Saturday",
            current_numeric_depth=2,
            current_alpha_depth=3,
        )
        self.assertIsNotNone(roman_marker)
        assert roman_marker is not None
        self.assertEqual(roman_marker.reference, "i")
        self.assertEqual(roman_marker.level, 4)

    def test_split_markdown_events_keeps_text_and_tables(self):
        page_chunks = [
            {
                "metadata": {"page_number": 6},
                "text": "## **1. About this Agreement**\n\n|Day|Rate|\n|---|---|\n|Sat|150%|",
            }
        ]

        events = split_markdown_events(page_chunks)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].kind, "text")
        self.assertEqual(events[1].kind, "table")

    def test_body_start_page_number_skips_contents_pages(self):
        page_chunks = [
            {
                "metadata": {"page_number": 2},
                "text": "Table of Contents\n1. About this Agreement........5\n1.1. This Agreement........5",
            },
            {
                "metadata": {"page_number": 6},
                "text": (
                    "## **1. About this Agreement**\n\n"
                    "This Agreement applies nationally and sets out the main terms and conditions for team members."
                ),
            },
        ]

        page_number = body_start_page_number(split_markdown_events(page_chunks))
        self.assertEqual(page_number, 6)

    def test_parse_markdown_events_builds_nested_tree_and_excludes_appendices(self):
        page_chunks = [
            {
                "metadata": {"page_number": 6},
                "text": (
                    "## **1. About this Agreement**\n\n"
                    "## **1.1 This Agreement**\n\n"
                    "- a. This Agreement applies nationally.\n\n"
                    "- i. It also applies to support roles.\n\n"
                    "## **2. Overtime**\n\n"
                    "## **2.1 Ordinary hours**\n\n"
                    "Work must be rostered in advance."
                ),
            },
            {
                "metadata": {"page_number": 20},
                "text": (
                    "## **A1. APPENDIX A - CLASSIFICATIONS**\n\n"
                    "## **A1.1 Retail classifications**\n\n"
                    "Classification content."
                ),
            },
        ]

        award, excluded_sections, diagnostics = parse_markdown_events(
            split_markdown_events(page_chunks),
            "Synthetic Agreement",
        )

        self.assertIn("Synthetic Agreement", award)
        main_part = award["Synthetic Agreement"]
        self.assertIn("1", main_part)
        self.assertIn("2", main_part)
        self.assertEqual(main_part["1"][CONTENT_KEY], ["About this Agreement"])
        self.assertEqual(main_part["1"]["1.1"][CONTENT_KEY], ["This Agreement"])
        self.assertEqual(main_part["1"]["1.1"]["a"][CONTENT_KEY], ["This Agreement applies nationally."])
        self.assertEqual(
            main_part["1"]["1.1"]["a"]["i"][CONTENT_KEY],
            ["It also applies to support roles."],
        )
        self.assertEqual(
            main_part["2"]["2.1"][CONTENT_KEY],
            ["Ordinary hours", "Work must be rostered in advance."],
        )

        self.assertIn("A1 APPENDIX A - CLASSIFICATIONS", excluded_sections)
        self.assertIn("A1.1", excluded_sections["A1 APPENDIX A - CLASSIFICATIONS"])
        self.assertTrue(any(item["target"] == "excluded" for item in diagnostics))

    def test_parse_markdown_events_starts_new_part_for_standalone_part_heading(self):
        page_chunks = [
            {
                "metadata": {"page_number": 35},
                "text": (
                    "## **11.2 Consultation about changes to your roster or hours of work**\n\n"
                    "- 11.2.5 These provisions are to be read in conjunction with other Agreement provisions concerning the scheduling of work and notice requirements."
                ),
            },
            {
                "metadata": {"page_number": 36},
                "text": (
                    "## **PART 12 - UNION RECOGNITION**\n\n"
                    "## **12.1 Freedom of Association and Noticeboards**\n\n"
                    "- 12.1.1 Union delegates will be granted leave with pay."
                ),
            },
        ]

        award, _excluded_sections, _diagnostics = parse_markdown_events(
            split_markdown_events(page_chunks),
            "Synthetic Agreement",
        )

        self.assertIn("Synthetic Agreement", award)
        self.assertIn("PART 12 - UNION RECOGNITION", award)
        self.assertIn("11.2", award["Synthetic Agreement"])
        self.assertNotIn("12.1", award["Synthetic Agreement"])
        self.assertIn("12.1", award["PART 12 - UNION RECOGNITION"])

    def test_parse_table_markdown_returns_table_structure(self):
        table = parse_table_markdown("|Day|Rate|\n|---|---|\n|Sat|150%|")

        self.assertEqual(table["type"], "table")
        self.assertEqual(table["headers"], ["Day", "Rate"])
        self.assertEqual(table["rows"][0]["Rate"], "150%")

    def test_write_pdf_outputs_writes_expected_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            processed_dir = temp_path / "processed"
            raw_dir = temp_path / "raw"
            pdf_path = temp_path / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.7")

            award = {
                "Synthetic Agreement": {
                    "_content": [],
                    "1": {"_content": ["About this Agreement"]},
                }
            }
            excluded_sections = {
                "A1 APPENDIX A - CLASSIFICATIONS": {
                    "_content": [],
                    "A1.1": {"_content": ["Retail classifications"]},
                }
            }
            diagnostics = [
                {
                    "page_number": 6,
                    "source_text": "1. About this Agreement",
                    "detected_level": 1,
                    "marker_kind": "numeric",
                    "reference": "1",
                    "title": "About this Agreement",
                    "target": "main",
                }
            ]

            write_pdf_outputs(
                pdf_path=pdf_path,
                markdown_text="## 1. About this Agreement",
                award=award,
                excluded_sections=excluded_sections,
                diagnostics=diagnostics,
                output_stem_value="sample",
                raw_dir=raw_dir,
                processed_dir=processed_dir,
            )

            main_json_path = processed_dir / "sample" / "sample.json"
            supporting_dir = main_json_path.parent / "supporting"

            self.assertTrue((raw_dir / "sample.md").exists())
            self.assertTrue(main_json_path.exists())
            self.assertTrue((supporting_dir / "sample_sections.json").exists())
            self.assertTrue((supporting_dir / "sample.csv").exists())
            self.assertTrue((supporting_dir / "sample_diagnostics.json").exists())
            self.assertTrue((supporting_dir / "sample_excluded_sections.json").exists())

            excluded_payload = json.loads(
                (supporting_dir / "sample_excluded_sections.json").read_text(encoding="utf-8")
            )
            self.assertTrue(excluded_payload["excluded_from_downstream"])


if __name__ == "__main__":
    unittest.main()
