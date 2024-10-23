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

    def test_failures_only_single_file(self):
        # Test that --failures-only works in single file mode
        report = self.create_report(
            [
                {"test": "test1", "status": "PASS"},
                {"test": "test2", "status": "FAIL"},
                {"test": "test3", "status": "CRASH"},
                {"test": "test4", "status": "OK"},
            ]
        )

        parser = WPTReportParser(report)

        # With show_passing=True (default)
        output_with_passing = parser.format_single_file_report(
            detail_level="all", show_passing=True
        )
        self.assertIn("test1", output_with_passing)
        self.assertIn("test4", output_with_passing)

        # With show_passing=False (--failures-only)
        output_failures_only = parser.format_single_file_report(
            detail_level="all", show_passing=False
        )
        self.assertNotIn("test1", output_failures_only)
        self.assertNotIn("test4", output_failures_only)
        self.assertIn("test2", output_failures_only)
        self.assertIn("test3", output_failures_only)

    def test_failures_only_comparison(self):
        report_a = self.create_report(
            [
                {"test": "test1.html", "status": "FAIL"},
                {"test": "test2.html", "status": "PASS"},
                {"test": "test3.html", "status": "FAIL"},
            ]
        )
        report_b = self.create_report(
            [
                {"test": "test1.html", "status": "PASS"},  # Improvement
                {"test": "test2.html", "status": "FAIL"},  # Regression
                {"test": "test3.html", "status": "CRASH"},  # Lateral change
                {"test": "test4.html", "status": "PASS"},  # New passing
                {"test": "test5.html", "status": "CRASH"},  # New failing
            ]
        )

        parser_a = WPTReportParser(report_a)
        parser_b = WPTReportParser(report_b)
        comparator = WPTReportComparator(
            parser_a,
            parser_b,
            detail_level="changes",
            show_passing=True,
            max_details=10,
        )
        output_with_passing = comparator.format_comparison()

        # Verify improvements and regressions are shown with show_passing=True
        self.assertIn("test1.html", output_with_passing)
        self.assertIn("test2.html", output_with_passing)

        # Test with failures only
        comparator = WPTReportComparator(
            parser_a,
            parser_b,
            detail_level="changes",
            show_passing=False,
            max_details=10,
        )
        output_failures_only = comparator.format_comparison()

        # Verify only failures are shown
        self.assertNotIn("test1.html", output_failures_only)  # No improvements
        self.assertNotIn("test4.html", output_failures_only)  # No new passing
        self.assertIn("test2.html", output_failures_only)  # Show regression
        self.assertIn("test5.html", output_failures_only)  # Show new failure

    def test_failures_only_with_subtests(self):
        report_a = self.create_report(
            [
                {
                    "test": "test1.html",
                    "status": "OK",
                    "subtests": [
                        {"name": "stable", "status": "PASS"},
                        {"name": "will_pass", "status": "FAIL"},
                        {"name": "will_crash", "status": "FAIL"},
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
                        {"name": "stable", "status": "PASS"},
                        {"name": "will_pass", "status": "PASS"},
                        {"name": "will_crash", "status": "CRASH"},
                        {"name": "new_fail", "status": "FAIL"},
                    ],
                }
            ]
        )

        parser_a = WPTReportParser(report_a)
        parser_b = WPTReportParser(report_b)
        comparator = WPTReportComparator(
            parser_a,
            parser_b,
            detail_level="changes",
            show_subtests=True,
            show_passing=False,
            max_details=10,
        )
        output = comparator.format_comparison()

        # Verify subtest behavior with failures only
        self.assertNotIn("test1.html::stable", output)  # Stable pass not shown
        self.assertNotIn("test1.html::will_pass", output)  # Improvement not shown
        self.assertNotIn(
            "test1.html::will_crash", output
        )  # Lateral, changed to crash shown
        self.assertIn("test1.html::new_fail", output)  # New failure shown

    def test_multiple_detail_levels_with_failures_only(self):
        report_a = self.create_report(
            [
                {"test": "test1.html", "status": "FAIL"},
                {"test": "test2.html", "status": "PASS"},
            ]
        )
        report_b = self.create_report(
            [
                {"test": "test1.html", "status": "PASS"},  # Improvement
                {"test": "test2.html", "status": "FAIL"},  # Regression
                {"test": "test3.html", "status": "PASS"},  # New passing
                {"test": "test4.html", "status": "CRASH"},  # New crashing
                {"test": "test5.html", "status": "FAIL"},  # New failing
            ]
        )

        parser_a = WPTReportParser(report_a)
        parser_b = WPTReportParser(report_b)

        # Test each detail level with failures only
        for detail_level in ["new", "changes", "all"]:
            comparator = WPTReportComparator(
                parser_a,
                parser_b,
                detail_level=detail_level,
                show_passing=False,
                max_details=10,
            )
            output = comparator.format_comparison()

            # Common assertions for all detail levels with failures only
            self.assertNotIn("test1.html", output)  # Improvement not shown
            self.assertNotIn("test3.html", output)  # New passing not shown

            # Detail level specific checks
            if detail_level in ["new", "all", "changes"]:
                self.assertIn("test4.html", output)  # New crash shown
                self.assertIn("test5.html", output)  # New failure shown

            if detail_level in ["changes", "all"]:
                self.assertIn("test2.html", output)  # Regression shown


if __name__ == "__main__":
    unittest.main()
