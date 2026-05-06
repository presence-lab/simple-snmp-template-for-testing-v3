#!/usr/bin/env python3
"""
Test Runner with Specification Grading Support
Runs tests organized by bundles (1, 2, 3) and reports grade level achieved.

This script:
- If the 'solution' directory contains Python files: copies them to src/, runs tests,
  then restores the original student files
- If no solution files are present: runs tests with the existing src/ implementation
- Supports bundle-focused runs while keeping pytest passthrough arguments available
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Belt-and-suspenders capture -- real commits happen in tests/conftest.py,
# this layer only fires if pytest itself never started (e.g., src/ won't import).
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from tests._capture import capture as _capture
except ImportError:
    _capture = None

try:
    from tools import preflight as _preflight
except ImportError:
    _preflight = None


def assert_in_venv() -> None:
    """Refuse to run unless invoked from the project's local venv.

    Strict check: sys.prefix must be a `venv/` or `.venv/` directory
    directly inside the project root. A global venv, a conda env, or a
    venv belonging to another project is rejected — capture infrastructure
    must not be installed outside the project boundary.

    Honors CAPTURE_FORCE_NO_VENV=<anything> as a test-only override that
    simulates the no-venv condition.
    """
    project_root = Path(__file__).resolve().parent
    if os.environ.get("CAPTURE_FORCE_NO_VENV"):
        in_local_venv = False
    else:
        sys.path.insert(0, str(project_root))
        try:
            from tests._capture.runtime_triggers import is_local_venv
        except ImportError:
            is_local_venv = None
        if is_local_venv is None:
            in_local_venv = False
        else:
            in_local_venv = is_local_venv(Path(sys.prefix), project_root)
    if not in_local_venv:
        sys.stderr.write(
            "ERROR: run_tests.py must be run from inside this project's "
            "local venv (a 'venv/' or '.venv/' directory inside this folder).\n"
            "\n"
            "Set up the venv:\n"
            "  python -m venv venv\n"
            "  venv\\Scripts\\activate    (Windows)\n"
            "  source venv/bin/activate   (macOS/Linux)\n"
            "  pip install -r requirements.txt\n"
            "\n"
            "Then re-run: python run_tests.py\n"
        )
        sys.exit(2)


# ANSI color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


class BundleTestRunner:
    def __init__(self, verbose=False, bundle=None, pytest_args=None, failed_only=False):
        self.root_dir = Path(__file__).parent.absolute()
        self.solution_dir = self.root_dir / "solution"
        self.src_dir = self.root_dir / "src"
        self.backup_dir = None
        self.verbose = verbose
        self.bundle = bundle
        self.pytest_args = list(pytest_args or [])
        self._capture_ctx = None
        self._pytest_proc = None

        if failed_only:
            self.pytest_args.append("--lf")

    def _subprocess_env(self):
        """Return an env for pytest subprocesses with capture session vars
        set if an outer capture session is active."""
        env = os.environ.copy()
        if self._capture_ctx is not None:
            env["CAPTURE_SESSION_ID"] = self._capture_ctx.session_id
            env["CAPTURE_STARTED_AT"] = str(self._capture_ctx.started_at)
        return env

    def _count_tests(self) -> int:
        """Pre-count the test suite so the watchdog deadline scales to reality.

        Runs pytest --collect-only -q. Returns the integer count, or 10 on
        any error (preserving the existing default). The probe costs about
        half a second -- trivial next to a test run that may be minutes long.
        """
        import re

        probe_env = os.environ.copy()
        probe_env["CAPTURE_DISABLED"] = "1"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--collect-only", "-q"],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                errors="replace",
                timeout=30,
                env=probe_env,
            )
        except (subprocess.SubprocessError, OSError):
            return 10
        # Scan the last 10 lines for the summary. pytest may emit earlier output.
        tail = "\n".join(result.stdout.splitlines()[-10:])
        m = re.search(r"(\d+)\s+tests?\s+collected", tail)
        if m:
            return int(m.group(1))
        return 10

    def _capture_is_enabled(self) -> bool:
        """Cheap read of project-template-config.json. Conservative: returns
        False on any error so we don't incur the count probe unnecessarily."""
        path = self.root_dir / "project-template-config.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return bool(data.get("capture_enabled"))

    def get_python_files(self, directory):
        """Get all top-level Python files in a directory."""
        if not directory.exists():
            return []
        return [f.name for f in directory.glob("*.py") if f.is_file()]

    def has_solution_files(self):
        """Return True when the solution directory contains actual Python files."""
        return bool(self.get_python_files(self.solution_dir))

    def create_backup(self):
        """Backup original src files."""
        if not self.src_dir.exists():
            return

        self.backup_dir = Path(tempfile.mkdtemp(prefix="test_backup_"))
        print(f"Creating backup in: {self.backup_dir}")

        for filename in self.get_python_files(self.src_dir):
            src = self.src_dir / filename
            dst = self.backup_dir / filename
            shutil.copy2(src, dst)
            if self.verbose:
                print(f"  Backed up: {filename}")

    def copy_solution_files(self):
        """Copy solution files to src directory."""
        if not self.solution_dir.exists():
            raise RuntimeError(f"Solution directory not found: {self.solution_dir}")

        self.src_dir.mkdir(exist_ok=True)

        print("Copying solution files to src directory...")
        solution_files = self.get_python_files(self.solution_dir)

        if not solution_files:
            print("  Warning: No Python files found in solution directory")
            return

        for filename in solution_files:
            src = self.solution_dir / filename
            dst = self.src_dir / filename
            shutil.copy2(src, dst)
            if self.verbose:
                print(f"  Copied: {filename}")

    def restore_backup(self):
        """Restore original files from backup."""
        if not self.backup_dir or not self.backup_dir.exists():
            return

        print("\nRestoring original files...")

        for filename in self.get_python_files(self.src_dir):
            (self.src_dir / filename).unlink()

        for filename in self.get_python_files(self.backup_dir):
            src = self.backup_dir / filename
            dst = self.src_dir / filename
            shutil.copy2(src, dst)
            if self.verbose:
                print(f"  Restored: {filename}")

        shutil.rmtree(self.backup_dir)
        print("Backup cleaned up")

    def get_test_markers(self):
        """Extract bundle and points markers by importing test modules.

        Handles both top-level test_ functions and Test* classes with
        test_ methods. Class-level pytestmark decorators are inherited
        by the methods unless the method overrides them.
        """

        def _resolve(obj, inherited=None):
            bundle, points = 1, 0
            marks = list(inherited or [])
            marks.extend(getattr(obj, "pytestmark", []))
            for mark in marks:
                if mark.name == "bundle" and mark.args:
                    bundle = mark.args[0]
                elif mark.name == "points" and mark.args:
                    points = mark.args[0]
            return bundle, points

        test_markers = {}
        tests_dir = self.root_dir / "tests"

        for test_file in tests_dir.glob("test_*.py"):
            spec = importlib.util.spec_from_file_location(
                f"tests.{test_file.stem}", test_file
            )
            if not spec or not spec.loader:
                continue

            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception:
                continue

            for name in dir(module):
                obj = getattr(module, name)

                if name.startswith("test_") and callable(obj):
                    bundle, points = _resolve(obj)
                    test_markers[f"{test_file.name}::{name}"] = {
                        "bundle": bundle,
                        "points": points,
                        "nodeid": str(test_file) + f"::{name}",
                    }
                    continue

                if name.startswith("Test") and isinstance(obj, type):
                    class_marks = getattr(obj, "pytestmark", [])
                    for attr_name in dir(obj):
                        if not attr_name.startswith("test_"):
                            continue
                        method = getattr(obj, attr_name)
                        if not callable(method):
                            continue
                        bundle, points = _resolve(method, class_marks)
                        test_markers[f"{test_file.name}::{attr_name}"] = {
                            "bundle": bundle,
                            "points": points,
                            "nodeid": (
                                f"{test_file}::{name}::{attr_name}"
                            ),
                        }

        return test_markers

    def get_selected_test_nodeids(self, test_markers):
        """Return pytest node ids for the selected bundle, if any."""
        if self.bundle is None:
            return None

        selected = [
            metadata["nodeid"]
            for metadata in test_markers.values()
            if metadata["bundle"] == self.bundle
        ]
        return selected or None

    def build_pytest_command(self, test_nodeids=None):
        """Build the pytest command for the current run."""
        cmd = [sys.executable, "-m", "pytest"]

        if test_nodeids:
            cmd.extend(test_nodeids)
        else:
            cmd.append(str(self.root_dir / "tests"))

        cmd.extend([
            "-v",
            "--tb=short",
            "--color=yes",
            "--strict-markers",
        ])
        cmd.extend(self.pytest_args)
        return cmd

    def run_subprocess(self, cmd):
        """Run a subprocess and print its output safely."""
        print(f"\nRunning: {' '.join(cmd)}")
        print("=" * 80)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            env=self._subprocess_env(),
        )
        self._pytest_proc = proc
        try:
            stdout, stderr = proc.communicate()
        finally:
            self._pytest_proc = None

        if stdout:
            print(stdout)
        if stderr:
            print(stderr)

        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)

    def run_tests_with_json(self):
        """Run pytest with JSON output to get detailed test information."""
        test_markers = self.get_test_markers()
        selected_tests = self.get_selected_test_nodeids(test_markers)

        cmd = self.build_pytest_command(selected_tests)
        cmd.extend([
            "--json-report",
            "--json-report-file=test_results.json",
        ])

        result = self.run_subprocess(cmd)

        bundles_data = {1: [], 2: [], 3: []}
        json_path = self.root_dir / "test_results.json"

        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as file_handle:
                    json_data = json.load(file_handle)

                for test in json_data.get("tests", []):
                    nodeid = test.get("nodeid", "")
                    outcome = test.get("outcome", "")
                    parts = nodeid.split("::")
                    filename = Path(parts[0]).name if parts else "unknown"
                    test_name = parts[-1] if len(parts) > 1 else "unknown"
                    test_class = parts[1] if len(parts) > 2 else None

                    markers = test_markers.get(
                        f"{filename}::{test_name}",
                        {"bundle": 1, "points": 0},
                    )
                    bundle = markers["bundle"]
                    points = markers["points"]

                    bundles_data[bundle].append({
                        "file": filename,
                        "class": test_class,
                        "name": test_name,
                        "passed": outcome == "passed",
                        "points": points,
                    })

                    if self.verbose:
                        status_icon = "[PASS]" if outcome == "passed" else "[FAIL]"
                        print(f"  {status_icon} Bundle {bundle}: {test_name} ({points} points)")
            except Exception as exc:
                if self.verbose:
                    print(f"Note: Could not parse JSON results: {exc}")
                    print("Falling back to basic test output parsing")
                bundles_data = self.parse_pytest_verbose_output(result.stdout, test_markers)
            finally:
                json_path.unlink(missing_ok=True)
        else:
            bundles_data = self.parse_pytest_verbose_output(result.stdout, test_markers)

        return result.returncode, bundles_data

    def run_tests_standard(self):
        """Run pytest and collect bundle information."""
        test_markers = self.get_test_markers()
        selected_tests = self.get_selected_test_nodeids(test_markers)

        try:
            import pytest_jsonreport  # noqa: F401
            return self.run_tests_with_json()
        except ImportError:
            pass

        cmd = self.build_pytest_command(selected_tests)
        result = self.run_subprocess(cmd)
        bundles_data = self.parse_pytest_verbose_output(result.stdout, test_markers)
        return result.returncode, bundles_data

    def parse_pytest_verbose_output(self, output, test_markers):
        """Parse verbose pytest output to extract test results and markers."""
        import re

        bundles = {1: [], 2: [], 3: []}

        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        clean_output = ansi_escape.sub("", output)

        lines = clean_output.splitlines()
        for line in lines:
            if "::test_" not in line or ("PASSED" not in line and "FAILED" not in line):
                continue

            match = re.search(
                r"(test_\w+\.py)::(?:(\w+)::)?(test_\w+)(?:\[.*\])?(?:\s+<-[^\r\n]+)?\s+(PASSED|FAILED)",
                line,
            )
            if not match:
                continue

            filename = match.group(1)
            test_class = match.group(2)
            test_name = match.group(3)
            status = match.group(4)

            metadata = test_markers.get(
                f"{filename}::{test_name}",
                {"bundle": 1, "points": 0},
            )
            bundle = metadata["bundle"]

            bundles[bundle].append({
                "file": filename,
                "class": test_class,
                "name": test_name,
                "passed": status == "PASSED",
                "points": metadata["points"],
            })

            if self.verbose:
                status_icon = "[PASS]" if status == "PASSED" else "[FAIL]"
                print(f"  {status_icon} Bundle {bundle}: {test_name}")

        return bundles

    def print_bundle_results(self, bundles_data):
        """Print test results organized by bundle."""
        bundle_status = {}
        for bundle in [1, 2, 3]:
            tests = bundles_data[bundle]
            total = len(tests)
            passed = sum(1 for test in tests if test["passed"])
            total_points = sum(test.get("points", 0) for test in tests)
            earned_points = sum(test.get("points", 0) for test in tests if test["passed"])

            bundle_status[bundle] = {
                "total": total,
                "passed": passed,
                "complete": total > 0 and passed == total,
                "total_points": total_points,
                "earned_points": earned_points,
            }

        grade = "Not Passing"
        grade_color = RED
        points = 0

        if bundle_status[1]["complete"]:
            grade = "C"
            grade_color = BLUE
            points = 70
            if bundle_status[2]["complete"]:
                grade = "B"
                grade_color = YELLOW
                points = 85
                if bundle_status[3]["complete"]:
                    grade = "A"
                    grade_color = GREEN
                    points = 100

        print("\n" + "=" * 80)
        print(f"{BOLD}SPECIFICATION GRADING RESULTS{RESET}")
        print("=" * 80)
        print(f"\n{BOLD}Grade Level Achieved: {grade_color}{grade}{RESET}")
        print(f"{BOLD}Grade Score: {points}/100{RESET}  "
              f"(specifications grading: bundle-completion based)\n")

        bundle_names = {
            1: "Bundle 1 (Core Requirements)",
            2: "Bundle 2 (Intermediate Features)",
            3: "Bundle 3 (Advanced Features)",
        }

        for bundle in [1, 2, 3]:
            status = bundle_status[bundle]
            if status["total"] == 0:
                print(f"[ ] {BOLD}{bundle_names[bundle]}{RESET}: No tests found")
                continue

            icon = f"{GREEN}[PASS]{RESET}" if status["complete"] else f"{RED}[FAIL]{RESET}"
            completion = f"{status['passed']}/{status['total']}"
            percentage = (status["passed"] / status["total"] * 100) if status["total"] > 0 else 0

            points_str = ""
            if status["total_points"] > 0:
                points_str = f" ({status['earned_points']}/{status['total_points']} pts)"

            print(
                f"{icon} {BOLD}{bundle_names[bundle]}{RESET}: "
                f"{completion} tests passed ({percentage:.0f}%){points_str}"
            )

            if not status["complete"] and self.verbose:
                failed_tests = [test for test in bundles_data[bundle] if not test["passed"]]
                if failed_tests:
                    print(f"  {RED}Failed tests:{RESET}")
                    for test in failed_tests:
                        if test["class"]:
                            print(f"    - {test['file']}::{test['class']}::{test['name']}")
                        else:
                            print(f"    - {test['file']}::{test['name']}")

        print(f"\n{BOLD}Grading Requirements:{RESET}")
        print("- You must pass ALL tests in a bundle to receive credit")
        print("- Higher bundles require completion of all lower bundles")
        print("- Bundle 1 = 70 points (C), Bundle 1+2 = 85 points (B), All = 100 points (A)")
        print("- Per-test \"(X/Y pts)\" beside each bundle is a progress indicator only;")
        print("  the Grade Score is awarded by bundle completion, not by summing test points.")

        print(f"\n{BOLD}Next Steps:{RESET}")
        if not bundle_status[1]["complete"]:
            print("-> Focus on Bundle 1 tests (core requirements)")
        elif not bundle_status[2]["complete"]:
            print("-> Work on Bundle 2 tests (intermediate features)")
        elif not bundle_status[3]["complete"]:
            print("-> Complete Bundle 3 tests (advanced features)")
        else:
            print(f"{GREEN}-> Congratulations! All bundles complete!{RESET}")

    def _install_sigterm_handler(self):
        """On Unix, ensure SIGTERM kills the pytest subprocess before we exit.

        The watchdog sends SIGTERM to this process when a hung session trips
        the deadline. Without this handler, subprocess.run's pytest child would
        be reparented and leak on macOS/Linux. On Windows, `taskkill /F /T /PID`
        already kills the whole tree, so no handler is needed.
        """
        if os.name == "nt":
            return
        import signal

        def _on_sigterm(signum, frame):
            proc = self._pytest_proc
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except (OSError, ProcessLookupError):
                    pass
            # Restore default handler and re-raise so we exit with the
            # conventional 128+SIGTERM exit code.
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGTERM)

        signal.signal(signal.SIGTERM, _on_sigterm)

    def run(self):
        """Main execution method."""
        self._install_sigterm_handler()
        self._capture_ctx = None
        exit_code = 1
        try:
            if _capture is not None and self._capture_is_enabled():
                n_tests = self._count_tests()
                self._capture_ctx = _capture.session_start(
                    self.root_dir, estimated_tests=n_tests,
                )
            print("=" * 80)
            print(f"{BOLD}Test Runner with Specification Grading{RESET}")
            print("=" * 80)
            print(f"Root directory: {self.root_dir}")

            if not self.has_solution_files():
                if self.solution_dir.exists():
                    # Directory exists but is empty -- worth flagging as a
                    # likely misconfiguration. Otherwise (the normal student
                    # case where solution/ does not exist at all), say nothing
                    # so the output focuses on the test run itself.
                    print("\n[INFO] solution/ exists but contains no Python files.")
                    print("   Running tests with existing src/ implementation.")

                exit_code, bundles_data = self.run_tests_standard()
                self.print_bundle_results(bundles_data)
                return exit_code

            print(f"Solution directory: {self.solution_dir}")
            print()

            self.create_backup()
            self.copy_solution_files()

            print("\n[WARN] Running tests with solution files copied to src/ directory")
            print("   Original files have been backed up and will be restored after tests")

            time.sleep(0.5)

            exit_code, bundles_data = self.run_tests_standard()
            self.print_bundle_results(bundles_data)
            return exit_code

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            exit_code = 2
            return exit_code
        except Exception as exc:
            print(f"\nError: {exc}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            exit_code = 3
            return exit_code
        finally:
            if self.backup_dir and self.backup_dir.exists():
                self.restore_backup()
            if _capture is not None and self._capture_ctx is not None:
                status = "completed" if exit_code == 0 else f"pytest_exit_{exit_code}"
                _capture.session_finish(self.root_dir, self._capture_ctx, status=status)


def main():
    assert_in_venv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        description="Run tests with specification grading support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script runs tests organized by specification grading bundles:
- Bundle 1: Core requirements (70 points)
- Bundle 2: Intermediate features (85 points total)
- Bundle 3: Advanced features (100 points total)

Tests are assigned to bundles using pytest markers:
  @pytest.mark.bundle(1)  # Assigns test to Bundle 1
  @pytest.mark.points(10)  # Assigns point value to test

You must pass ALL tests in a bundle to receive credit for that level.

Examples:
  python run_tests.py
  python run_tests.py -v
  python run_tests.py --bundle 1
  python run_tests.py -k basic
  python run_tests.py --failed

Note: If the 'solution' directory contains Python files, it will be tested automatically.
""",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output (shows failed test details)",
    )
    parser.add_argument(
        "--bundle",
        type=int,
        choices=[1, 2, 3],
        help="Run only tests assigned to the selected bundle",
    )
    parser.add_argument(
        "--failed",
        action="store_true",
        help="Run only the tests that failed on the previous pytest run",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help=(
            "Skip the environment check that gates test runs (instructor / "
            "edge-case use only)."
        ),
    )

    args, pytest_args = parser.parse_known_args()

    if not args.skip_preflight and _preflight is not None:
        repo = Path(__file__).resolve().parent
        failures = _preflight.check_environment(repo)
        if failures:
            _preflight.report(repo, failures)
            return 4

    runner = BundleTestRunner(
        verbose=args.verbose,
        bundle=args.bundle,
        pytest_args=pytest_args,
        failed_only=args.failed,
    )
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
