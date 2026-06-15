import json
import subprocess
import sys
import textwrap


WATCH_MODULES = ("numpy", "scipy", "scipy.signal", "pandas", "fitparse", "garmin_fit_sdk")


def _run_python(code: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])


def test_import_main_keeps_heavy_numeric_and_dataframe_stack_lazy():
    payload = _run_python(
        textwrap.dedent(
            """
            import json
            import sys
            import time

            watched = ("numpy", "scipy", "scipy.signal", "pandas", "fitparse", "garmin_fit_sdk")
            started = time.perf_counter()
            import main
            elapsed = time.perf_counter() - started
            print(json.dumps({
                "elapsed_sec": elapsed,
                "loaded": {name: name in sys.modules for name in watched},
            }, sort_keys=True))
            """
        )
    )

    assert payload["elapsed_sec"] < 3.0
    assert payload["loaded"] == {name: False for name in WATCH_MODULES}


def test_startup_measurement_script_reports_import_contract():
    result = subprocess.run(
        [sys.executable, "scripts/measure_startup_imports.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[-1])

    assert isinstance(payload["elapsed_sec"], float)
    for name in WATCH_MODULES:
        assert payload["loaded"][name] is False
