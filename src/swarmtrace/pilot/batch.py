"""Run one set of a protocol's run table, one run directory per row.

Rows whose directory already holds a complete run are skipped; any other existing directory stops
the batch. A run that ends with FAILED.txt is reported as failed.
"""

import json
import threading
import time
from pathlib import Path

from swarmtrace.pilot.harness import RunConfig, run
from swarmtrace.pilot.publish import RUN_FILES

SETS = {"development": "development_runs", "test": "test_runs"}
LOOKALIKE_DURATION = 150.0
TIMEOUT = 900.0


def complete(run_dir: Path) -> bool:
    return all((run_dir / n).exists() for n in RUN_FILES) and not (run_dir / "FAILED.txt").exists()


def row_config(row: dict, out: Path, dry_run: bool = False,
               duration: float = LOOKALIKE_DURATION, timeout: float = TIMEOUT,
               parallel: int | None = None) -> RunConfig:
    """RunConfig for one protocol row."""
    common = dict(condition=row["condition"], out=out, seed=int(row["seed"]),
                  background=bool(row.get("background")), dry_run=dry_run, duration=duration,
                  timeout=timeout, batch_parallel=parallel)
    if dry_run:
        common.update(stagger=0.05, jitter=0.05)
    if row["condition"] == "lookalike":
        return RunConfig(mix=list(row["mix"]), **common)
    launchers = list(row["launchers"])
    return RunConfig(launchers=launchers, models=list(row["models"]), agents=len(launchers),
                     tasks=list(row.get("tasks") or []), subagents=int(row.get("subagents", 3)),
                     **common)


def batch(protocol: Path, set_name: str, out: Path, parallel: int = 1,
          only: list[str] | None = None, dry_run: bool = False,
          duration: float = LOOKALIKE_DURATION, timeout: float = TIMEOUT, echo=print) -> list[dict]:
    """Execute the rows of one set.

    Rows whose directory holds a complete run are skipped; any other existing directory stops
    the batch before anything runs.
    """
    rows = json.loads(Path(protocol).read_text(encoding="utf-8"))[SETS[set_name]]
    if only:
        unknown = set(only) - {r["run"] for r in rows}
        if unknown:
            raise ValueError(f"no such runs in {set_name}: {sorted(unknown)}")
        rows = [r for r in rows if r["run"] in only]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pending, results, lock = [], [], threading.Lock()
    parallel = max(1, parallel)
    incomplete = [r["run"] for r in rows
                  if (out / r["run"]).exists() and not complete(out / r["run"])]
    if incomplete:
        raise RuntimeError(f"incomplete run directories in {out}: {', '.join(incomplete)}")
    echo(f"parallel: {parallel}")
    for row in rows:
        if (out / row["run"]).exists():
            results.append({"run": row["run"], "condition": row["condition"], "skipped": True})
            echo(f"{row['run']}\t{row['condition']}\tskipped (exists)")
        else:
            pending.append(row)

    def worker() -> None:
        while True:
            with lock:
                if not pending:
                    return
                row = pending.pop(0)
            start = time.monotonic()
            result = {"run": row["run"], "condition": row["condition"], "skipped": False}
            try:
                run_dir = run(row_config(row, out / row["run"], dry_run, duration, timeout,
                                        parallel))
                manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
                result["timeout_hit"] = manifest["timeout_hit"]
                if (run_dir / "FAILED.txt").exists():
                    failed = (run_dir / "FAILED.txt").read_text(encoding="utf-8").strip()
                    result["error"] = f"run failed: {failed}"
            except Exception as error:
                result["error"] = f"{type(error).__name__}: {error}"
            result["wall_s"] = round(time.monotonic() - start, 1)
            with lock:
                results.append(result)
                status = result.get("error") or ("timeout" if result["timeout_hit"] else "ok")
                echo(f"{row['run']}\t{row['condition']}\t{result['wall_s']}s\t{status}")

    threads = [threading.Thread(target=worker) for _ in range(parallel)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results
