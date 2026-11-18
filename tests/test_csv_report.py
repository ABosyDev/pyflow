import json
import subprocess
import sys
from pathlib import Path


def test_csv_to_json_example():
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "examples.csv_report"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )

    assert json.loads(completed.stdout) == {"apple": 5, "pear": 4}
    assert [line.split(" [")[0] for line in completed.stderr.splitlines()] == [
        "read_csv",
        "clean_records",
        "aggregate",
        "render_json",
        "Cały przebieg",
    ]
    assert completed.stderr.count("[SUCCEEDED]") == 5
