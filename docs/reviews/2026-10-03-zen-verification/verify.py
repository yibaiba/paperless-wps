"""Run isolated ZEN verification; each test and each batch has a 60s hard timeout."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
TESTS = "backend/tests/configuration/"


def run_batch(index, tests):
    command = [sys.executable, "-m", "pytest", *tests, "--timeout=60", "-q"]
    process = subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        (REPORT / f"batch-{index:02}.txt").write_text(output + "\nBATCH TIMEOUT (60s)\n")
        raise
    (REPORT / f"batch-{index:02}.txt").write_text(output)
    print(f"batch {index}: {output.strip().splitlines()[-1]}", flush=True)
    if process.returncode:
        raise RuntimeError(f"Batch {index} failed; see its log")
    return dict(command=command, result=output.strip().splitlines()[-1])


def main():
    protocol = TESTS + "test_zen_protocol.py"
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", protocol, "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=60,
    )
    relative = protocol.removeprefix("backend/")
    nodes = [
        "backend/" + line for line in collected.stdout.splitlines()
        if line.startswith(relative + "::")
    ]
    if not nodes:
        raise RuntimeError("No stdio protocol cases collected")
    groups = [
        [
            "backend/tests/test_rules.py", TESTS + "decisions/test_runtime.py",
            TESTS + "test_evolution_sharing.py", TESTS + "test_quantity_review_fixes.py",
            TESTS + "test_scoped_quantity_setup.py", TESTS + "test_alias_quantity_checks.py",
            TESTS + "test_fulfilled_role_quantity_review.py",
        ],
        [TESTS + name + ".py" for name in (
            "test_zen_combinations", "test_decision_versions", "test_zen_execution_pipeline",
            "test_candidate_combination_inputs", "test_shared_calculation_context",
            "test_package_trials", "test_inspection_profiles",
        )],
        *[nodes[i:i + 4] for i in range(0, len(nodes), 4)],
        [TESTS + name + ".py" for name in (
            "test_list_mcp", "test_mcp_protocol", "test_mcp_error_contract",
            "test_proposal_protocol", "test_proposal_prices_and_cycles",
        )],
    ]
    results = [run_batch(i, group) for i, group in enumerate(groups, 1)]
    (REPORT / "batches.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
