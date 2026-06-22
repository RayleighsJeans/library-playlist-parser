#!/usr/bin/env python3
"""
Run all tests for the project with coverage reporting.

Usage:
    python3 test/run_all_tests.py              # Run all tests
    python3 test/run_all_tests.py --coverage   # Run with coverage report
"""

import sys
import os
import unittest
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_all_tests(with_coverage=False):
    """Run all test suites."""

    test_dir = Path(__file__).parent

    if with_coverage:
        try:
            import coverage

            # Configure coverage to focus on relevant modules
            cov = coverage.Coverage(
                source=[
                    str(project_root / 'soundcloud'),
                    str(project_root / 'playlist_matcher.py')
                ],
                omit=[
                    '*/test/*',
                    '*/tests/*',
                    '*/__pycache__/*',
                    '*/venv/*',
                    '*/env/*'
                ],
                data_file=str(test_dir / '.coverage')
            )
            cov.start()
            print("Running tests with coverage tracking...\n")
        except ImportError:
            print("Warning: coverage module not found. Install with: pip install coverage")
            print("Running tests without coverage...\n")
            with_coverage = False

    # Discover and run all tests
    loader = unittest.TestLoader()
    suite = loader.discover(str(test_dir), pattern='test_*.py')

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Generate coverage report
    if with_coverage:
        cov.stop()
        cov.save()

        print("\n" + "=" * 70)
        print("COVERAGE REPORT")
        print("=" * 70)
        cov.report()

        # Generate HTML report in test directory
        html_dir = test_dir / 'htmlcov'
        cov.html_report(directory=str(html_dir))
        print(f"\nHTML coverage report generated in: {html_dir}")
        print(f"Open {html_dir}/index.html in your browser to view detailed coverage")

        # Generate XML report for CI/CD
        xml_file = test_dir / 'coverage.xml'
        cov.xml_report(outfile=str(xml_file))
        print(f"XML coverage report: {xml_file}")

        # Print coverage summary by module
        print("\n" + "=" * 70)
        print("COVERAGE BY MODULE")
        print("=" * 70)

        # Get coverage data
        data = cov.get_data()
        total_statements = 0
        total_missing = 0

        for filename in sorted(data.measured_files()):
            if any(skip in filename for skip in ['test', '__pycache__', 'venv', 'env']):
                continue

            analysis = cov.analysis2(filename)
            statements = len(analysis[1])
            missing = len(analysis[3])
            covered = statements - missing

            if statements > 0:
                percent = (covered / statements) * 100
                rel_path = os.path.relpath(filename, project_root)
                print(f"{rel_path:50s} {covered:4d}/{statements:4d} ({percent:5.1f}%)")

                total_statements += statements
                total_missing += missing

        if total_statements > 0:
            total_percent = ((total_statements - total_missing) / total_statements) * 100
            print("-" * 70)
            print(f"{'TOTAL':50s} {total_statements - total_missing:4d}/{total_statements:4d} ({total_percent:5.1f}%)")

    # Print summary
    print("\n" + "=" * 70)
    print("OVERALL TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")

    print("=" * 70)

    return result.wasSuccessful()


if __name__ == '__main__':
    # Check for coverage flag
    with_coverage = '--coverage' in sys.argv or '-c' in sys.argv

    success = run_all_tests(with_coverage=with_coverage)
    sys.exit(0 if success else 1)

# Made with Bob
