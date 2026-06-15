import json
import subprocess
import sys
import textwrap


def _run_python(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_gap_calculator_import_does_not_load_numeric_stack():
    output = _run_python(
        textwrap.dedent(
            """
            import sys
            import gap_calculator
            loaded = [
                name for name in sys.modules
                if name == "numpy" or name.startswith("numpy.")
                or name == "scipy.signal" or name.startswith("scipy.signal.")
            ]
            print(len(loaded))
            """
        )
    )
    assert output == "0"


def test_gap_calculator_calculate_loads_numeric_stack_and_preserves_output():
    output = _run_python(
        textwrap.dedent(
            """
            import json
            import sys
            from datetime import datetime, timedelta
            from gap_calculator import GapCalculator

            base = datetime(2026, 1, 1, 8, 0, 0)
            records = [
                {
                    "altitude": 100.0 + i * 0.5,
                    "distance": i * 10.0,
                    "heart_rate": 120 + (i % 5),
                    "timestamp": base + timedelta(seconds=i * 5),
                }
                for i in range(20)
            ]
            result = GapCalculator().calculate(records)
            payload = {
                "numeric_loaded": "numpy" in sys.modules and "scipy.signal" in sys.modules,
                "gap_len": len(result.get("gap_curve") or []),
                "eff_len": len(result.get("efficiency_curve") or []),
                "grade_len": len(result.get("grade_curve") or []),
                "alt_len": len(result.get("smoothed_altitude") or []),
                "source": result.get("source"),
            }
            print(json.dumps(payload, sort_keys=True))
            """
        )
    )
    payload = json.loads(output)
    assert payload == {
        "numeric_loaded": True,
        "gap_len": 20,
        "eff_len": 20,
        "grade_len": 20,
        "alt_len": 20,
        "source": "resolver",
    }
