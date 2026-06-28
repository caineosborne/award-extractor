import json
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from src.script_1_fetch_award import (
    extract_award,
    extract_award_elements,
    nest_award_elements,
    table_to_dict,
    write_primary_outputs,
    write_step_1_outputs,
)
from src.script_1b_generate_fetch_supporting_artifacts import write_supporting_outputs


class FetchAwardTests(unittest.TestCase):
    def test_extract_award_elements_reads_only_paragraphs_and_tables(self):
        soup = BeautifulSoup(
            """
            <div id="MainContent">
                <h1 class="level1">Ignored heading tag</h1>
                <p class="partheading">Part 1 - Application</p>
                <p class="level1">1 Transitional arrangements</p>
                <div class="block1">Ignored div content</div>
                <table>
                    <tr><th>Item</th><th>Rate</th></tr>
                    <tr><td>A</td><td>10</td></tr>
                </table>
            </div>
            """,
            "html.parser",
        )

        elements = extract_award_elements(soup.find(id="MainContent"))

        self.assertEqual([element.kind for element in elements], ["part", "level1", "table"])
        self.assertEqual(elements[0].text, "Part 1 - Application")
        self.assertEqual(elements[2].table["rows"][0]["Rate"], "10")

    def test_skipped_heading_levels_attach_to_nearest_real_parent(self):
        soup = BeautifulSoup(
            """
            <div id="MainContent">
                <p class="partheading">Part 1 - Application</p>
                <p class="level1">1 Transitional arrangements</p>
                <p class="block1">This award contains transitional arrangements.</p>
                <p class="level4">(a) \uf0b7 minimum wages and piecework rates</p>
                <p class="level4">(b) \uf0b7 casual or part-time loadings</p>
            </div>
            """,
            "html.parser",
        )

        award = extract_award(soup.find(id="MainContent"))

        clause = award["Part 1 - Application"]["1"]
        self.assertEqual(
            clause["_content"],
            ["Transitional arrangements", "This award contains transitional arrangements."],
        )
        self.assertIn("a", clause)
        self.assertIn("b", clause)
        self.assertNotIn("No Level 2", clause)
        self.assertEqual(clause["a"]["_content"], ["- minimum wages and piecework rates"])

    def test_nest_award_elements_accepts_flat_element_list(self):
        soup = BeautifulSoup(
            """
            <div id="MainContent">
                <p class="partheading">Part 1 - Application</p>
                <p class="level1">1 Title</p>
                <p class="block1">Coverage text.</p>
            </div>
            """,
            "html.parser",
        )

        award = nest_award_elements(extract_award_elements(soup.find(id="MainContent")))

        self.assertEqual(award["Part 1 - Application"]["1"]["_content"], ["Title", "Coverage text."])

    def test_table_to_dict_turns_header_table_into_row_dicts(self):
        soup = BeautifulSoup(
            """
            <table>
                <tr><th>Classification</th><th>Rate</th></tr>
                <tr><td>Level 1</td><td>$25.00</td></tr>
            </table>
            """,
            "html.parser",
        )

        table = table_to_dict(soup.table)

        self.assertEqual(table["type"], "table")
        self.assertEqual(table["headers"], ["Classification", "Rate"])
        self.assertEqual(table["rows"][0]["Classification"], "Level 1")
        self.assertEqual(table["rows"][0]["Rate"], "$25.00")

    def test_table_to_dict_keeps_rows_when_headers_are_not_usable(self):
        soup = BeautifulSoup(
            """
            <table>
                <tr><th>Item</th><th>Item</th></tr>
                <tr><td>A</td><td>B</td></tr>
            </table>
            """,
            "html.parser",
        )

        table = table_to_dict(soup.table)

        self.assertEqual(table["headers"], ["Item", "Item"])
        self.assertEqual(table["rows"], [["A", "B"]])

    def test_write_primary_outputs_writes_raw_html_and_main_award_json(self):
        soup = BeautifulSoup(
            """
            <div id="mainContent">
                <p class="partheading">Part 1 - Application</p>
                <p class="level1">1 Title</p>
            </div>
            """,
            "html.parser",
        )
        award = extract_award(soup.find(id="mainContent"))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            write_primary_outputs(
                "https://awards.fairwork.gov.au/MA000018.html",
                soup.find(id="mainContent"),
                award,
                temp_path / "raw",
                temp_path / "processed",
            )

            fetch_award_dir = temp_path / "processed" / "MA000018"
            archive_dir = fetch_award_dir / "archive"

            self.assertTrue((fetch_award_dir / "MA000018.json").exists())
            self.assertEqual(len(list(archive_dir.glob("MA000018_[0-9]*.json"))), 1)
            self.assertTrue((temp_path / "raw" / "MA000018.html").exists())

    def test_write_supporting_outputs_writes_files_to_supporting_subfolder(self):
        soup = BeautifulSoup(
            """
            <div id="mainContent">
                <p class="partheading">Part 1 - Application</p>
                <p class="level1">1 Title</p>
            </div>
            """,
            "html.parser",
        )
        award = extract_award(soup.find(id="mainContent"))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fetch_award_dir = temp_path / "processed" / "MA000018"
            fetch_award_dir.mkdir(parents=True, exist_ok=True)
            award_json_path = fetch_award_dir / "MA000018.json"
            award_json_path.write_text(json.dumps(award), encoding="utf-8")

            write_supporting_outputs(award_json_path)

            supporting_dir = fetch_award_dir / "supporting"
            archive_dir = supporting_dir / "archive"

            self.assertTrue((supporting_dir / "MA000018_sections.json").exists())
            self.assertTrue((supporting_dir / "MA000018.csv").exists())
            self.assertEqual(len(list(archive_dir.glob("MA000018_sections_*.json"))), 1)
            self.assertEqual(len(list(archive_dir.glob("MA000018_*.csv"))), 1)

    def test_write_step_1_outputs_runs_primary_and_supporting_outputs(self):
        soup = BeautifulSoup(
            """
            <div id="mainContent">
                <p class="partheading">Part 1 - Application</p>
                <p class="level1">1 Title</p>
            </div>
            """,
            "html.parser",
        )
        award = extract_award(soup.find(id="mainContent"))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            write_step_1_outputs(
                "https://awards.fairwork.gov.au/MA000018.html",
                soup.find(id="mainContent"),
                award,
                temp_path / "raw",
                temp_path / "processed",
            )

            fetch_award_dir = temp_path / "processed" / "MA000018"
            self.assertTrue((fetch_award_dir / "MA000018.json").exists())
            self.assertTrue((fetch_award_dir / "supporting" / "MA000018_sections.json").exists())
            self.assertTrue((fetch_award_dir / "supporting" / "MA000018.csv").exists())


if __name__ == "__main__":
    unittest.main()
