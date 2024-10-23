import unittest
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from wpt_analyzer import WPTReportParser, WPTReportComparator


class TestWPTReportAnalyzer(unittest.TestCase):
    def create_report(self, results: list) -> str:
        return json.dumps({"results": results})

    def test_basic_subtest_handling(self):
        report = self.create_report(
            [
                {
                    "test": "test1.html",
                    "status": "OK",
                    "subtests": [
                        {"name": "subtest1.html", "status": "PASS"},
                        {"name": "subtest2.html", "status": "FAIL"},
                    ],
                }
            ]
        )

        parser = WPTReportParser(report)
        self.assertEqual(parser.get_total_subtests(), 2)

        subtest_results = parser.get_results(for_subtests=True)
        self.assertEqual(len(subtest_results), 2)
        self.assertEqual(subtest_results["test1.html::subtest1.html"], "PASS")
        self.assertEqual(subtest_results["test1.html::subtest2.html"], "FAIL")

    def test_subtest_comparison(self):
        report_a = self.create_report(
            [
                {
                    "test": "test1.html",
                    "status": "OK",
                    "subtests": [
                        {"name": "subtest1.html", "status": "PASS"},
                        {"name": "subtest2.html", "status": "FAIL"},
                    ],
                }
            ]
        )
        report_b = self.create_report(
            [
                {
                    "test": "test1.html",
                    "status": "OK",
                    "subtests": [
                        {"name": "subtest1.html", "status": "FAIL"},
                        {"name": "subtest2.html", "status": "PASS"},
                        {"name": "subtest3.html", "status": "CRASH"},
                    ],
                }
            ]
        )

        parser_a = WPTReportParser(report_a)
        parser_b = WPTReportParser(report_b)
        comparator = WPTReportComparator(
            parser_a, parser_b, show_subtests=True, detail_level="all"
        )

        output = comparator.format_comparison()
        self.assertIn("test1.html::subtest3.html", output)
        self.assertIn("CRASH", output)

    def test_crash_detail_printing(self):
        report_a = self.create_report([{"test": "test1.html", "status": "PASS"}])
        report_b = self.create_report(
            [
                {"test": "test1.html", "status": "PASS"},
                {"test": "test2.html", "status": "CRASH"},
                {"test": "test3.html", "status": "CRASH"},
            ]
        )

        parser_a = WPTReportParser(report_a)
        parser_b = WPTReportParser(report_b)
        comparator = WPTReportComparator(
            parser_a, parser_b, detail_level="all", max_details=10
        )

        output = comparator.format_comparison()

        self.assertIn("test2.html (CRASH)", output)
        self.assertIn("test3.html (CRASH)", output)

        self.assertIn("New Details:", output)

        lines = output.split("\n")
        new_details_index = next(
            i for i, line in enumerate(lines) if "New Details:" in line
        )
        details_section = "\n".join(lines[new_details_index : new_details_index + 10])
        self.assertIn("test2.html (CRASH)", details_section)
        self.assertIn("test3.html (CRASH)", details_section)

    def test_complex_subtest_scenario(self):
        report_a = self.create_report(
            [
                {
                    "test": "test1.html",
                    "status": "OK",
                    "subtests": [
                        {"name": "stable_pass", "status": "PASS"},
                        {"name": "will_fail", "status": "PASS"},
                        {"name": "will_remove", "status": "FAIL"},
                    ],
                },
                {
                    "test": "test2.html",
                    "status": "FAIL",
                    "subtests": [
                        {"name": "sub1", "status": "PASS"},
                        {"name": "sub2", "status": "FAIL"},
                    ],
                },
            ]
        )

        report_b = self.create_report(
            [
                {
                    "test": "test1.html",
                    "status": "OK",
                    "subtests": [
                        {"name": "stable_pass", "status": "PASS"},
                        {"name": "will_fail", "status": "FAIL"},
                        {"name": "new_crash", "status": "CRASH"},
                    ],
                },
                {
                    "test": "test2.html",
                    "status": "ERROR",
                    "subtests": [
                        {"name": "sub1", "status": "TIMEOUT"},
                        {"name": "sub2", "status": "ERROR"},
                        {"name": "sub3", "status": "CRASH"},
                    ],
                },
            ]
        )

        parser_a = WPTReportParser(report_a)
        parser_b = WPTReportParser(report_b)
        comparator = WPTReportComparator(
            parser_a, parser_b, detail_level="all", show_subtests=True, max_details=20
        )

        output = comparator.format_comparison()

        self.assertIn("test1.html::new_crash (CRASH)", output)
        self.assertIn("test2.html::sub3 (CRASH)", output)
        self.assertIn("test1.html::will_fail", output)  # Status change
        self.assertIn("test1.html::will_remove", output)  # Removed test

        self.assertIn("Detailed Subtest Summary", output)

        results_a = parser_a.get_results(for_subtests=True)
        results_b = parser_b.get_results(for_subtests=True)
        analysis = comparator.compare_results(results_a, results_b)

        self.assertEqual(len(analysis["new"]), 2)  # new_crash and sub3
        self.assertEqual(len(analysis["removed"]), 1)  # will_remove
        self.assertEqual(len(analysis["status_changes"]), 3)  # will_fail, sub1, sub2

        new_tests = [test for test, status in analysis["new"]]
        self.assertIn("test1.html::new_crash", new_tests)
        self.assertIn("test2.html::sub3", new_tests)


if __name__ == "__main__":
    unittest.main()
