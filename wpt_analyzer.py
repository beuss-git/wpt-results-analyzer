import json
import argparse
from typing import Dict, List, Any, Callable
from collections import Counter

GREEN, RED, ORANGE, BOLD, RESET = (
    "\033[92m",
    "\033[91m",
    "\033[93m",
    "\033[1m",
    "\033[0m",
)
REGRESSION, IMPROVEMENT, LATERAL, NO_CHANGE = (
    "Regression",
    "Improvement",
    "Lateral",
    "No Change",
)
PASS, OK, FAIL, TIMEOUT, ERROR, CRASH = (
    "PASS",
    "OK",
    "FAIL",
    "TIMEOUT",
    "ERROR",
    "CRASH",
)

STATUS_RANK = {PASS: 0, OK: 1, FAIL: 2, TIMEOUT: 2, ERROR: 2, CRASH: 2}


def classify_change(old_status: str, new_status: str) -> tuple:
    old_rank, new_rank = STATUS_RANK.get(old_status, 3), STATUS_RANK.get(new_status, 3)
    if old_rank > new_rank:
        return IMPROVEMENT, GREEN
    elif old_rank < new_rank:
        return REGRESSION, RED
    elif old_rank == new_rank and old_status != new_status:
        return LATERAL, ORANGE
    return NO_CHANGE, RESET


def color_diff(value: int, positive_good: bool = True) -> str:
    if value == 0:
        return str(value)
    color = GREEN if (value > 0) == positive_good else RED
    return f"{color}{value}{RESET}"


class WPTReportParser:
    def __init__(self, json_data: str):
        self.data = json.loads(json_data)
        self.results = self.data.get("results", [])

    def get_total_tests(self) -> int:
        return len(self.results)

    def get_total_subtests(self) -> int:
        return sum(len(result.get("subtests", [])) for result in self.results)

    def get_status_summary(self, for_subtests: bool = False) -> Dict[str, int]:
        if for_subtests:
            return Counter(
                subtest["status"]
                for result in self.results
                for subtest in result.get("subtests", [])
            )
        return Counter(result["status"] for result in self.results)

    def get_results(self, for_subtests: bool = False) -> Dict[str, str]:
        if for_subtests:
            return {
                f"{result['test']}::{subtest['name']}": subtest["status"]
                for result in self.results
                for subtest in result.get("subtests", [])
            }
        return {result["test"]: result["status"] for result in self.results}

    def get_details(self, for_subtests: bool = False) -> List[Dict[str, Any]]:
        if for_subtests:
            details = [
                {
                    "test": result["test"],
                    "subtest": subtest["name"],
                    "status": subtest["status"],
                }
                for result in self.results
                for subtest in result.get("subtests", [])
            ]
        else:
            details = self.results
        return sorted(
            details, key=lambda x: (STATUS_RANK.get(x["status"], 3), x["test"])
        )

    def format_single_file_report(
        self,
        detail_level: str = "summary",
        show_subtests: bool = False,
        max_details: int = 10,
    ) -> str:
        output = []

        def add_summary(title: str, total: int, status_summary: Dict[str, int]):
            output.append(f"\n{BOLD}{title}{RESET}: {total}")
            output.append(f"\n{BOLD}{title} Status Summary:{RESET}")
            for status in sorted(
                status_summary.keys(), key=lambda s: (STATUS_RANK.get(s, 3), s)
            ):
                count = status_summary[status]
                color = GREEN if status in [PASS, OK] else RED
                output.append(f"  {status:<10} {color}{count}{RESET}")

        def add_details(title: str, details: List[Dict[str, Any]]):
            output.append(f"\n{BOLD}{title}{RESET}:")
            for item in details[:max_details]:
                color = GREEN if item["status"] in [PASS, OK] else RED
                if "subtest" in item:
                    output.append(
                        f"  {color}{item['test']}::{item['subtest']} ({item['status']}){RESET}"
                    )
                else:
                    output.append(f"  {color}{item['test']} ({item['status']}){RESET}")
            if len(details) > max_details:
                output.append(f"  ... and {len(details) - max_details} more")

        # Test summary
        add_summary("Tests", self.get_total_tests(), self.get_status_summary())
        if detail_level in ["all", "changes"]:
            add_details("Test Details", self.get_details())

        if show_subtests:
            add_summary(
                "Subtests",
                self.get_total_subtests(),
                self.get_status_summary(for_subtests=True),
            )
            if detail_level in ["all", "changes"]:
                add_details("Subtest Details", self.get_details(for_subtests=True))

        return "\n".join(output)


class WPTReportComparator:
    def __init__(
        self,
        parser_a: WPTReportParser,
        parser_b: WPTReportParser,
        detail_level: str = "summary",
        max_details: int = 10,
        show_subtests: bool = False,
    ):
        self.parser_a, self.parser_b = parser_a, parser_b
        self.detail_level, self.max_details, self.show_subtests = (
            detail_level,
            max_details,
            show_subtests,
        )

    def compare_counts(self, getter: Callable) -> Dict[str, int]:
        return {
            "file_a": getter(self.parser_a),
            "file_b": getter(self.parser_b),
            "difference": getter(self.parser_b) - getter(self.parser_a),
        }

    def compare_summaries(self, getter: Callable) -> Dict[str, Dict[str, int]]:
        summary_a, summary_b = getter(self.parser_a), getter(self.parser_b)
        all_statuses = set(summary_a.keys()) | set(summary_b.keys())
        return {
            status: {
                "file_a": summary_a.get(status, 0),
                "file_b": summary_b.get(status, 0),
                "difference": summary_b.get(status, 0) - summary_a.get(status, 0),
            }
            for status in all_statuses
        }

    def compare_results(
        self, results_a: Dict[str, str], results_b: Dict[str, str]
    ) -> Dict[str, Any]:
        all_tests = set(results_a.keys()) | set(results_b.keys())
        return {
            "new": [
                (test, results_b[test]) for test in all_tests if test not in results_a
            ],
            "removed": [
                (test, results_a[test]) for test in all_tests if test not in results_b
            ],
            "status_changes": [
                (test, results_a[test], results_b[test])
                for test in all_tests
                if test in results_a
                and test in results_b
                and results_a[test] != results_b[test]
            ],
        }

    def _add_details(self, output: List[str], items: List[tuple], change_type: str):
        if items:
            output.append(f"\n  {change_type.capitalize()} Details:")
            passing = [(item, status) for item, status in items if status in [PASS, OK]]
            non_passing = [
                (item, status) for item, status in items if status not in [PASS, OK]
            ]

            for category, color in [(passing, GREEN), (non_passing, RED)]:
                if category:
                    output.append(
                        f"    {'Passing' if color == GREEN else 'Non-passing'}:"
                    )
                    for item, status in sorted(category)[: self.max_details]:
                        output.append(f"      {color}{item} ({status}){RESET}")
                    if len(category) > self.max_details:
                        output.append(
                            f"      {color}... and {len(category) - self.max_details} more{RESET}"
                        )

    def _add_change_details(
        self, output: List[str], analysis: Dict[str, Any], change_type: str, color: str
    ):
        changes = [
            (test, old, new)
            for test, old, new in analysis["status_changes"]
            if classify_change(old, new)[0] == change_type
        ]
        if changes:
            output.append(f"\n  {change_type}s:")
            for test, _, new in sorted(changes)[: self.max_details]:
                output.append(f"    {color}{test}: {new}{RESET}")
            if len(changes) > self.max_details:
                output.append(
                    f"    {color}... and {len(changes) - self.max_details} more{RESET}"
                )

    def format_analysis(self, analysis: Dict[str, Any], title: str) -> List[str]:
        output = [f"\n{BOLD}{title}{RESET}:"]

        for change_type in ["new", "removed"]:
            count = len(analysis[change_type])
            color = (
                GREEN
                if change_type == "new" and count > 0
                else RED if change_type == "removed" and count > 0 else RESET
            )
            output.append(f"  {change_type.capitalize()}: {color}{count}{RESET}")
            status_counts = Counter(status for _, status in analysis[change_type])
            for status, count in sorted(
                status_counts.items(), key=lambda x: (STATUS_RANK.get(x[0], 3), x[0])
            ):
                status_color = GREEN if status in [PASS, OK] else RED
                output.append(f"    {status}: {status_color}{count}{RESET}")

            if self.detail_level in ["all", change_type]:
                self._add_details(output, analysis[change_type], change_type)

        output.append("  Changed status:")
        change_counts = Counter(
            f"{old}->{new}" for _, old, new in analysis["status_changes"]
        )
        for change, count in sorted(
            change_counts.items(),
            key=lambda x: (
                STATUS_RANK.get(x[0].split("->")[0], 3),
                STATUS_RANK.get(x[0].split("->")[1], 3),
                x[0],
            ),
        ):
            old_status, new_status = change.split("->")
            change_type, color = classify_change(old_status, new_status)
            if change_type != NO_CHANGE:
                output.append(f"    {change}: {color}{count} {RESET}")

        if self.detail_level in ["all", "changes"]:
            self._add_change_details(output, analysis, REGRESSION, RED)
            self._add_change_details(output, analysis, IMPROVEMENT, GREEN)

        return output

    def format_comparison(self) -> str:
        output = []

        def add_summary(title: str, total_getter: Callable, status_getter: Callable):
            total = self.compare_counts(total_getter)
            output.append(f"\n{BOLD}{title}{RESET}:")
            output.append(self._format_count_change("Total", total))
            status = self.compare_summaries(status_getter)
            output.extend(
                self._format_status_summary(f"{title} Status Summary", status)
            )

        add_summary(
            "Tests",
            WPTReportParser.get_total_tests,
            WPTReportParser.get_status_summary,
        )
        test_analysis = self.compare_results(
            self.parser_a.get_results(), self.parser_b.get_results()
        )
        output.extend(self.format_analysis(test_analysis, "Detailed Test Summary"))

        if self.show_subtests:
            add_summary(
                "Subtests",
                WPTReportParser.get_total_subtests,
                lambda parser: parser.get_status_summary(for_subtests=True),
            )
            subtest_analysis = self.compare_results(
                self.parser_a.get_results(for_subtests=True),
                self.parser_b.get_results(for_subtests=True),
            )
            output.extend(
                self.format_analysis(subtest_analysis, "Detailed Subtest Summary")
            )

        return "\n".join(output)

    def _format_count_change(self, title: str, counts: Dict[str, int]) -> str:
        return f"{title}: {counts['file_a']} -> {counts['file_b']} ({color_diff(counts['difference'])})"

    def _format_status_summary(
        self, title: str, summary: Dict[str, Dict[str, int]]
    ) -> List[str]:
        output = [f"\n{BOLD}{title}{RESET}:"]
        for status, data in sorted(
            summary.items(), key=lambda x: (STATUS_RANK.get(x[0], 3), x[0])
        ):
            positive_good = status in [PASS, OK]
            output.append(
                f"  {status:<10} {data['file_a']:>5} -> {data['file_b']:>5} "
                f"({color_diff(data['difference'], positive_good)})"
            )
        return output


def main():
    parser = argparse.ArgumentParser(
        description="Analyze WPT report JSON files.",
        epilog="Example usage: python wpt-analyze.py file_a.json [file_b.json]",
    )
    parser.add_argument(
        "file_a", help="Path to the first (or only) WPT report JSON file"
    )
    parser.add_argument(
        "file_b", nargs="?", help="Path to the second WPT report JSON file (optional)"
    )
    parser.add_argument(
        "--detail-level",
        choices=["summary", "new", "removed", "changes", "all"],
        default="summary",
        help="Level of detail to show in the output (for comparison mode)",
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=3,
        help="Maximum number of details to print for each change type",
    )
    parser.add_argument(
        "--show-subtests",
        action="store_true",
        default=False,
        help="Include subtest information in the output",
    )
    args = parser.parse_args()

    try:
        with open(args.file_a, "r") as f:
            parser_a = WPTReportParser(f.read())

        if args.file_b:
            with open(args.file_b, "r") as f:
                parser_b = WPTReportParser(f.read())
            comparator = WPTReportComparator(
                parser_a,
                parser_b,
                args.detail_level,
                args.max_details,
                args.show_subtests,
            )
            print(comparator.format_comparison())
        else:
            print(
                parser_a.format_single_file_report(
                    args.detail_level, args.show_subtests, args.max_details
                )
            )

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please make sure the input file(s) exist and are accessible.")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in input file(s) - {e}")


if __name__ == "__main__":
    main()
