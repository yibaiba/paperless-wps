"""Compare isolated occupancy calculation with the previous committed implementation."""

import argparse
import json
import signal
import statistics
import subprocess
import time
from pathlib import Path

from presales.configuration.projects.calculation.included_capacity import IncludedCapacity

BASELINE = "2b34789"
MODULE_PATH = "backend/src/presales/configuration/projects/calculation/included_capacity.py"
REPEATS = 3


def fixture(count):
    roles = [dict(id=f"r{i}", device_id="host", allocated_quantity="1") for i in range(count)]
    demands, allocations = [], []
    for index in range(0, count - 2, 3):
        for offset, amount in ((0, "1.5"), (1, "0.5")):
            identity = f"d{index}-{offset}"
            demands.append(
                dict(
                    id=identity,
                    quantity_inputs=[
                        dict(device_id="host", requirement_id=f"r{r}")
                        for r in (index + offset, index + offset + 1)
                    ],
                )
            )
            allocations.append(
                dict(
                    device_id="host", included_item_id="bundle", demand_id=identity, quantity=amount
                )
            )
    return dict(
        data=dict(requirements=roles, included_allocations=allocations),
        demands=demands,
        device=dict(id="host", quantity=str(count)),
        fact=dict(id="bundle", quantity="1"),
    )


def measure(capacity_class, case):
    samples = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        capacity = capacity_class(case["data"], case["demands"])
        for demand in case["demands"]:
            capacity.quantities(case["device"], case["fact"], demand=demand)
            capacity.conflict(case["device"], case["fact"], demand=demand)
        samples.append(round((time.perf_counter() - started) * 1000, 3))
    return dict(median_ms=statistics.median(samples), samples_ms=samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    namespace = {}
    # Read the fixed, reviewed local baseline; never write it into the checkout.
    exec(
        subprocess.check_output(["git", "show", BASELINE + ":" + MODULE_PATH], text=True), namespace
    )
    rows = []
    for count in (100, 500):
        case = fixture(count)
        rows.append(
            dict(
                role_rows=count,
                scope_count=len(case["demands"]),
                before=measure(namespace["IncludedCapacity"], case),
                after=measure(IncludedCapacity, case),
            )
        )
    args.output.write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    signal.alarm(60)
    main()
