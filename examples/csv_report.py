import csv
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from pyflow import Task, Workflow, format_report, run


SAMPLE_CSV = Path(__file__).with_name("sales.csv")


def read_csv(inputs: Mapping[str, object], params: Mapping[str, Path]) -> list[dict[str, str]]:
    with params["path"].open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def clean_records(
    inputs: Mapping[str, Sequence[Mapping[str, str]]], params: Mapping[str, object]
) -> list[tuple[str, int]]:
    return [
        (row["product"].strip().lower(), int(row["quantity"]))
        for row in inputs["read_csv"]
    ]


def aggregate(
    inputs: Mapping[str, Sequence[tuple[str, int]]], params: Mapping[str, object]
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for product, quantity in inputs["clean_records"]:
        totals[product] = totals.get(product, 0) + quantity
    return totals


def render_json(
    inputs: Mapping[str, Mapping[str, int]], params: Mapping[str, object]
) -> str:
    return json.dumps(inputs["aggregate"], sort_keys=True, indent=2)


def build_workflow(csv_path: Path = SAMPLE_CSV) -> Workflow:
    workflow = Workflow()
    workflow.add_task(Task("read_csv", read_csv, params={"path": csv_path}))
    workflow.add_task(Task("clean_records", clean_records, frozenset({"read_csv"})))
    workflow.add_task(Task("aggregate", aggregate, frozenset({"clean_records"})))
    workflow.add_task(Task("render_json", render_json, frozenset({"aggregate"})))
    return workflow


if __name__ == "__main__":
    result = run(build_workflow())
    print(result.outputs["render_json"])
    print(format_report(result), file=sys.stderr)
