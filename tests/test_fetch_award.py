import unittest

from bs4 import BeautifulSoup

from src.fetch_award import extract_award, extract_award_elements, nest_award_elements, table_to_dict


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


if __name__ == "__main__":
    unittest.main()
