"""Explicit test layers; an unclassified new test stays in production coverage."""

import json
from pathlib import Path
import time

import pytest


ROOT = Path(__file__).resolve().parent
LAYERS = {
    "fast": {"fast"},
    "production": {"fast", "production"},
    "full": {"fast", "production", "full", "history"},
    "history": {"history"},
}


def pytest_addoption(parser):
    parser.addoption("--suite", choices=tuple(LAYERS), default=None,
                     help="Default: production; explicit test paths run without layer filtering.")
    parser.addoption("--inventory-json", default=None,
                     help="Write collected counts and measured setup/call/teardown seconds per file.")


def pytest_configure(config):
    config._suite_catalog = json.loads((ROOT / "tests/suites.json").read_text(encoding="utf-8"))
    for path, entry in config._suite_catalog.items():
        if entry["tier"] not in LAYERS:
            raise pytest.UsageError(f"Invalid test tier for {path}: {entry['tier']}")
    config._suite_name = config.getoption("suite") or (
        "full" if config.getoption("file_or_dir") else "production"
    )
    config._suite_inventory = {}
    config._suite_started = time.perf_counter()


def pytest_report_header(config):
    return f"test suite: {config._suite_name} (see tests/README.md)"


def pytest_ignore_collect(collection_path, config):
    if not collection_path.name.startswith("test_") or collection_path.suffix != ".py":
        return None
    try:
        relative = collection_path.relative_to(ROOT).as_posix()
    except ValueError:
        return None
    # Fail open for coverage: new/unclassified tests are production tests.
    tier = config._suite_catalog.get(relative, {}).get("tier", "production")
    if tier not in LAYERS[config._suite_name]:
        return True
    return None


def pytest_collection_modifyitems(config, items):
    for item in items:
        path = item.path.relative_to(ROOT).as_posix()
        row = config._suite_inventory.setdefault(path, {
            "count": 0, "executed": 0, "seconds": None, "failed": 0,
        })
        row["count"] += 1


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    row = item.config._suite_inventory[item.path.relative_to(ROOT).as_posix()]
    row["seconds"] = (row["seconds"] or 0.0) + report.duration
    if report.when == "setup":
        row["executed"] += 1
    if report.failed:
        row["failed"] += 1


def pytest_sessionfinish(session, exitstatus):
    destination = session.config.getoption("inventory_json")
    if destination:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "suite": session.config._suite_name,
            "exit_code": int(exitstatus),
            "elapsed_seconds": time.perf_counter() - session.config._suite_started,
            "files": session.config._suite_inventory,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
