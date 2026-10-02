"""Snapshot, execute, and compare selected regression tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import sys
import time

from . import __version__

MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 100 * 1024 * 1024


def git(repo, *args, raw=False, data=None):
    p = subprocess.run(["git", "-C", str(repo), *args], input=data,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if p.returncode:
        raise ValueError(p.stderr.decode("utf-8", "replace").strip())
    return p.stdout if raw else p.stdout.decode("utf-8").strip()


def safe_name(name):
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or ".." in p.parts or "\\" in name
            or ":" in name or str(p) != name or ".git" in p.parts):
        raise ValueError(f"Unsupported repository path: {name!r}")
    return name


def validate_size(files):
    if len(files) > 5000 or sum(len(data) for data, mode in files.values()) > MAX_TOTAL:
        raise ValueError("Snapshot exceeds 5,000 files or 100 MiB; narrow the repository.")
    for name, (data, mode) in files.items():
        if len(data) > MAX_FILE:
            raise ValueError(f"File exceeds 10 MiB: {name}")
        if data.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            raise ValueError(f"Git LFS pointers are unsupported: {name}")


def committed(repo, ref):
    oid = git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
    entries = []
    for record in git(repo, "ls-tree", "-rz", oid, raw=True).split(b"\0"):
        if not record:
            continue
        meta, name = record.split(b"\t", 1)
        mode, kind, blob = meta.decode().split()
        name = safe_name(name.decode("utf-8"))
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"Symlinks and submodules are unsupported: {name}")
        entries.append((name, blob, mode))
    if len(entries) > 5000:
        raise ValueError("Snapshot exceeds 5,000 files.")
    sizes = git(repo, "cat-file", "--batch-check=%(objectsize)", raw=True,
                data="".join(blob + "\n" for _, blob, _ in entries).encode())
    sizes = [int(n) for n in sizes.splitlines()]
    if any(n > MAX_FILE for n in sizes) or sum(sizes) > MAX_TOTAL:
        raise ValueError("Git snapshot exceeds file or total size limit.")
    content = git(repo, "cat-file", "--batch", raw=True,
                  data="".join(blob + "\n" for _, blob, _ in entries).encode())
    files, offset = {}, 0
    for (name, blob, mode), size in zip(entries, sizes):
        offset = content.index(b"\n", offset) + 1
        files[name] = (content[offset:offset + size], mode)
        offset += size + 1
    validate_size(files)
    return oid, files


def working(repo):
    names = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard", raw=True)
    files = {}
    for entry in names.split(b"\0"):
        if not entry:
            continue
        name = safe_name(entry.decode("utf-8"))
        path = repo / name
        if path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise ValueError(f"Linked paths are unsupported: {name}")
        if not path.exists():  # A tracked file deleted in the working tree.
            continue
        if not path.is_file():
            raise ValueError(f"Expected ordinary file; submodules unsupported: {name}")
        if path.stat().st_size > MAX_FILE:
            raise ValueError(f"File exceeds 10 MiB: {name}")
        files[name] = (path.read_bytes(), "100755" if path.stat().st_mode & stat.S_IXUSR else "100644")
        validate_size(files)
    return files


def manifest(files):
    return {name: {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode}
            for name, (data, mode) in sorted(files.items())}


def materialize(files, root):
    root.mkdir(parents=True)
    for name, (data, mode) in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if os.name != "nt":
            path.chmod(0o755 if mode == "100755" else 0o644)


def run_once(files, tests, folder, python, timeout, runner="unittest"):
    source = folder / "source"
    materialize(files, source)
    evidence = folder / "outcomes.json"
    runner_file = "runner.py" if runner == "unittest" else "pytest_runner.py"
    command = [python, "-I", "-B", str(Path(__file__).with_name(runner_file)),
               str(evidence), *tests]
    start = time.monotonic()
    status, code = "finished", None
    with (folder / "stdout.txt").open("wb") as out, (folder / "stderr.txt").open("wb") as err:
        try:
            p = subprocess.Popen(command, cwd=source, stdout=out, stderr=err,
                                 start_new_session=os.name != "nt")
            try:
                code = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                status = "timeout"
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                else:
                    os.killpg(p.pid, signal.SIGKILL)
                p.kill()
                p.wait(timeout=10)
        except OSError as exc:
            status = "launch_error"
            err.write(str(exc).encode("utf-8"))
    changed = []
    for name, (data, mode) in files.items():
        path = source / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            changed.append(name)
    try:
        payload = json.loads(evidence.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {"events": [], "tests_run": 0, "runner_error": "No valid runner result"}
    return {"status": status, "exit_code": code, "seconds": round(time.monotonic() - start, 3),
            "source_changes": changed, "result": payload, "directory": str(folder)}


def states(run):
    payload = run["result"]
    if (run["status"] != "finished" or run["exit_code"] not in (0, 1)
            or run["source_changes"] or payload.get("runner_error") or not payload.get("tests_run")):
        return None
    found = {}
    # A failing subtest can produce several events for one test method.
    priority = {"pass": 0, "failure": 1, "skip": 2, "expected_failure": 2,
                "unexpected_success": 2, "error": 3}
    for event in payload["events"]:
        previous = found.get(event["id"], "pass")
        found[event["id"]] = max(previous, event["status"], key=lambda s: priority[s])
    if not found or any(value not in {"pass", "failure"} for value in found.values()):
        return None
    if (run["exit_code"] == 0) != all(v == "pass" for v in found.values()):
        return None
    return found


def classify(base_runs, head_runs):
    base = [states(r) for r in base_runs]
    head = [states(r) for r in head_runs]
    if any(s is None for s in base + head):
        return "inconclusive", [], "A run errored, skipped tests, timed out, ran no tests, or changed its inputs."
    if any(set(s) != set(base[0]) for s in base + head):
        return "inconclusive", [], "The two versions did not execute matching test identities."
    if any(s != base[0] for s in base) or any(s != head[0] for s in head):
        return "unstable", [], "Repeated runs produced different outcomes."
    if any(v != "pass" for v in head[0].values()):
        return "fix_fails", [], "At least one selected test still fails on the current code."
    transitions = [name for name, status in base[0].items() if status == "failure"]
    if not transitions:
        return "not_demonstrated", [], "All selected tests already pass on the old code."
    return "regression_observed", transitions, "Matching tests fail by assertion before the fix and pass after it."


def error_summary(error, stdout_path=None):
    """Give an actionable, bounded cause while retaining the full runner log."""
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]
    if stdout_path and lines and lines[-1].startswith("Collection failed:"):
        try:
            with Path(stdout_path).open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                stream.seek(max(0, stream.tell() - 65536))
                output = stream.read().decode("utf-8", "replace")
            lines += [line.strip().removeprefix("E   ").strip()
                      for line in output.splitlines() if "ModuleNotFoundError:" in line
                      or "ImportError:" in line]
        except OSError:
            pass
    if not lines:
        return "Runner failed without an error message"
    missing = [line for line in lines if line.startswith(("ModuleNotFoundError:", "ImportError:"))]
    summary = missing[-1] if missing else lines[-1]
    summary = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", summary)
    summary = "".join(char for char in summary if char.isprintable())
    return summary.replace("`", "'")[:240]


def blockers_for(runs):
    """Explain invalid runs without promoting partial transitions to a verdict."""
    blockers = []
    for side, side_runs in runs.items():
        for index, run in enumerate(side_runs, 1):
            label = f"{side}-{index}"
            payload = run["result"]
            if run["status"] != "finished":
                blockers.append({"run": label, "issue": run["status"]})
            if run["source_changes"]:
                blockers.append({"run": label, "issue": "input_changed",
                                 "files": run["source_changes"]})
            if payload.get("runner_error"):
                blockers.append({"run": label, "issue": "runner_error",
                                 "detail": error_summary(payload["runner_error"],
                                                         Path(run["directory"]) / "stdout.txt")})
            if not payload.get("tests_run"):
                blockers.append({"run": label, "issue": "no_tests"})
            for event in payload.get("events", []):
                if event["status"] not in {"pass", "failure"}:
                    issue = {"run": label, "issue": "test_outcome", "test": event["id"],
                             "status": event["status"]}
                    if event.get("error_type"):
                        issue["error_type"] = event["error_type"]
                    blockers.append(issue)
            if (run["status"] == "finished" and run["exit_code"] not in (0, 1)
                    and not payload.get("runner_error")):
                blockers.append({"run": label, "issue": "unexpected_exit",
                                 "exit_code": run["exit_code"]})
    if not blockers:
        first = {event["id"] for event in runs["base"][0]["result"]["events"]}
        for side, side_runs in runs.items():
            for index, run in enumerate(side_runs, 1):
                names = {event["id"] for event in run["result"]["events"]}
                if names != first:
                    blockers.append({"run": f"{side}-{index}",
                                     "issue": "test_identity_mismatch"})
    if not blockers:
        blockers.append({"run": "all", "issue": "inconsistent_runner_result"})
    return blockers


def likely_test_file(name):
    parts = PurePosixPath(name).parts
    filename = parts[-1].lower()
    return (filename == "conftest.py" or filename.startswith("test_")
            or filename.endswith("_test.py") or "tests" in parts[:-1]
            or "test" in parts[:-1])


def check(repo, base, head, tests, output, python=sys.executable, timeout=30.0, repeat=2,
          runner="unittest"):
    repo = Path(repo).resolve()
    output = Path(output).resolve()
    root = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    if repo != root:
        raise ValueError("--repo must name the Git repository root.")
    if output.is_relative_to(repo):
        raise ValueError("Choose an output directory outside the tested repository.")
    if output.exists():
        raise ValueError("Output directory already exists; choose a new directory.")
    if not 1 <= repeat <= 10 or not 0 < timeout <= 3600:
        raise ValueError("repeat must be 1..10; timeout must be greater than 0 and at most 3600 seconds.")
    if runner not in {"unittest", "pytest"}:
        raise ValueError("runner must be unittest or pytest.")
    if not tests or len(set(tests)) != len(tests):
        raise ValueError("Select at least one test file, without duplicates.")
    base_oid, old = committed(repo, base)
    head_oid, current = ("working-tree", working(repo)) if head == "working" else committed(repo, head)
    test_files = []
    for selection in tests:
        name, marker, node = selection.partition("::")
        safe_name(name)
        if marker and not node:
            raise ValueError(f"Test selector must name a test after '::': {selection}")
        if not name.endswith(".py") or name not in current:
            raise ValueError(f"Test must be an existing Python file in the current snapshot: {name}")
        test_files.append(name)
    transplanted = dict(old)
    for name in set(test_files):
        transplanted[name] = current[name]
    output.mkdir(parents=True)
    runs = {"base": [], "head": []}
    for side, files in (("base", transplanted), ("head", current)):
        for index in range(repeat):
            runs[side].append(run_once(files, tests, output / f"{side}-{index + 1}", python, timeout, runner))
    verdict, transitions, reason = classify(runs["base"], runs["head"])
    diff_args = ["diff", "--name-only", "-z", "--no-ext-diff", "--no-textconv",
                 "--no-renames", base_oid]
    if head != "working":
        diff_args.append(head_oid)
    diff_args.append("--")
    changed_files = sorted({safe_name(entry.decode("utf-8"))
                            for entry in git(repo, *diff_args, raw=True).split(b"\0") if entry}
                           | (current.keys() - old.keys()))
    if verdict == "regression_observed" and not any(
            not likely_test_file(name) for name in changed_files):
        verdict, transitions = "inconclusive", []
        reason = "Only test files changed according to Git; a transition cannot establish a source regression."
        blockers = [{"run": "all", "issue": "no_non_test_changes"}]
    else:
        blockers = blockers_for(runs) if verdict == "inconclusive" else []
    report = {"schema_version": 2, "product": "Bugbix", "version": __version__,
              "verdict": verdict, "reason": reason, "regression_tests": transitions,
              "blockers": blockers, "changed_files": changed_files,
              "repo": str(repo), "base": base_oid, "head": head_oid, "tests": tests,
              "python": python, "runner": runner, "repeat": repeat, "timeout": timeout,
              "snapshots": {"base_with_current_tests": manifest(transplanted), "head": manifest(current)},
              "runs": runs,
              "limits": "Observed test transitions only; not proof of bug relevance, full-suite health, or sandbox isolation."}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Bugbix report", "", f"**{verdict}**", "", reason, "",
             f"Base: `{base_oid}`  ", f"Current: `{head_oid}`  ",
             f"Runs per version: {repeat}", "", "## Tests that caught a difference", ""]
    lines += [f"- `{name}`" for name in transitions] or ["No qualifying failure-to-pass transition."]
    if blockers:
        lines += ["", "## Why the result is inconclusive", ""]
        for item in blockers[:30]:
            detail = item["issue"]
            if item.get("test"):
                detail += f" in `{item['test']}`"
            if item.get("status"):
                detail += f" ({item['status']})"
            if item.get("error_type"):
                detail += f" [{item['error_type']}]"
            if item.get("detail"):
                detail += f": {item['detail']}"
            lines.append(f"- `{item['run']}`: {detail}")
        if len(blockers) > 30:
            lines.append(f"- {len(blockers) - 30} more issue(s) in report.json")
    lines += ["", "## Git-visible file changes", "",
              f"{len(changed_files)} changed or new file(s) relative to the base commit."]
    lines += [f"- `{name}`" for name in changed_files[:30]]
    if len(changed_files) > 30:
        lines.append(f"- {len(changed_files) - 30} more file(s) in report.json")
    lines += ["", "## Evidence", "", "| Run | Process | Exit | Tests | Input edits | Log |",
              "| --- | --- | --- | --- | --- | --- |"]
    for side in runs:
        for index, run in enumerate(runs[side], 1):
            directory = f"{side}-{index}"
            lines.append(f"| {directory} | {run['status']} | {run['exit_code']} | {run['result']['tests_run']} | {len(run['source_changes'])} | [stdout]({directory}/stdout.txt), [stderr]({directory}/stderr.txt) |")
    lines += ["", "## Interpretation", "", report["limits"], "",
              "Only the selected test files were copied from current code onto the baseline.",
              "Snapshots and raw logs are retained beside this report. Review assertions and traces.",
              f"{repeat} run(s) per state reveal only obvious instability; they do not establish statistical reliability.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report
