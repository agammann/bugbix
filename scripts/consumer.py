"""Install each delivered artifact outside the checkout and run the real CLI."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import venv

from package import ROOT, release_version

OLD = "def total(price, discount, tax):\n    return price * (100 + tax) // 100 - discount\n"
FIX = "def total(price, discount, tax):\n    return (price - discount) * (100 + tax) // 100\n"
TEST = "import unittest\nfrom pricing import total\nclass PricingTests(unittest.TestCase):\n    def test_discount(self):\n        self.assertEqual(total(100, 20, 10), 88)\n"


def call(command, cwd, expected=0):
    result = subprocess.run([str(p) for p in command], cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode != expected:
        raise RuntimeError(f"Command exit {result.returncode}, expected {expected}: {command}\n{result.stdout}\n{result.stderr}")
    return result


def fingerprint(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


def fixture(path):
    path.mkdir()
    call(["git", "init", "--quiet"], path)
    (path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (path / "pricing.py").write_text(OLD, encoding="utf-8")
    call(["git", "add", "."], path)
    call(["git", "-c", "user.name=Bugbix test", "-c", "user.email=test@example.invalid", "commit", "--quiet", "-m", "Baseline fixture"], path)
    (path / "pricing.py").write_text(FIX, encoding="utf-8")
    (path / "test_pricing.py").write_text(TEST, encoding="utf-8")


def exercise(directory, artifact, version):
    directory.mkdir()
    environment = directory / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    binary = environment / ("Scripts" if sys.platform == "win32" else "bin")
    python = binary / ("python.exe" if sys.platform == "win32" else "python")
    cli = binary / ("bugbix.exe" if sys.platform == "win32" else "bugbix")
    installed = call([python, "-m", "pip", "install", "--no-deps", artifact], directory)
    (directory / "install.log").write_text(installed.stdout + installed.stderr, encoding="utf-8")
    if call([cli, "--version"], directory).stdout.strip() != f"Bugbix {version}":
        raise ValueError("Installed CLI version mismatch")
    probe = "import bugbix,json,pathlib; print(json.dumps({'version':bugbix.__version__,'file':bugbix.__file__}))"
    identity = json.loads(call([python, "-I", "-c", probe], directory).stdout)
    if identity["version"] != version or not Path(identity["file"]).resolve().is_relative_to(environment.resolve()):
        raise ValueError("Consumer imported source checkout instead of installed package")
    package = Path(identity["file"]).parent
    for source in (ROOT / "bugbix").glob("*.py"):
        if (package / source.name).read_bytes() != source.read_bytes():
            raise ValueError("Installed runtime bytes differ: " + source.name)
    repo = directory / "repo"
    fixture(repo)
    cases = []
    def check(name, content, verdict, exit_code, timeout="10"):
        (repo / "test_pricing.py").write_text(content, encoding="utf-8")
        status = call(["git", "status", "--porcelain=v1"], repo).stdout
        before = fingerprint(repo)
        output = directory / name
        command = [cli, "check", "--repo", repo, "--base", "HEAD", "--test", "test_pricing.py", "--out", output, "--timeout", timeout]
        result = call(command, directory, exit_code)
        value = json.loads(result.stdout)
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        if value["verdict"] != verdict or report["version"] != version or report["schema_version"] != 2:
            raise ValueError("Installed verdict/report contract mismatch")
        after_status = call(["git", "status", "--porcelain=v1"], repo).stdout
        after = fingerprint(repo)
        if before != after or status != after_status:
            changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
            raise ValueError("Original checkout changed during check: " + ", ".join(changed))
        (output / "cli.json").write_text(result.stdout, encoding="utf-8")
        cases.append({"name": name, "verdict": verdict, "exit": exit_code, "repositoryPreserved": True})
        return command, output
    check("regression", TEST, "regression_observed", 0)
    check("weak-test", TEST.replace("100, 20, 10), 88", "100, 0, 0), 100"), "not_demonstrated", 1)
    (repo / "pricing.py").write_text(OLD, encoding="utf-8")
    check("broken-fix", TEST, "fix_fails", 1)
    (repo / "pricing.py").write_text(FIX, encoding="utf-8")
    command, output = check("import-error", "import missing_consumer_dependency\n" + TEST, "inconclusive", 1)
    preserved = fingerprint(output)
    error = call(command, directory, 2)
    if "already exists" not in json.loads(error.stdout).get("error", "") or preserved != fingerprint(output):
        raise ValueError("Existing evidence was not preserved")
    cases.append({"name": "existing-output-refusal", "exit": 2, "evidencePreserved": True})
    check("recovered", TEST, "regression_observed", 0)
    check("skipped", TEST.replace("    def test_", "    @unittest.skip('not exercised')\n    def test_"), "inconclusive", 1)
    check("timeout", "import time\ntime.sleep(30)\n" + TEST, "inconclusive", 1, "0.5")
    syntax = call([cli, "check"], directory, 2)
    if syntax.stdout or not syntax.stderr:
        raise ValueError("CLI syntax error channel mismatch")
    cases.append({"name": "syntax-error", "exit": 2, "diagnostic": "stderr"})
    if call([cli, "--help"], directory).returncode != 0:
        raise ValueError("CLI help failed")
    return {"artifact": artifact.name, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "installedVersion": version,
            "runtimeBytes": "match", "runtimeDependencies": 0, "cases": cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--artifacts", default=str(ROOT / "artifacts"))
    args = parser.parse_args()
    destination = Path(args.out).resolve()
    if destination.exists() or destination.is_relative_to(ROOT.resolve()):
        raise ValueError("Use a new consumer folder outside the source checkout")
    destination.mkdir(parents=True)
    version = release_version()
    artifacts = Path(args.artifacts).resolve()
    results = []
    for label, filename in [("wheel", f"bugbix-{version}-py3-none-any.whl"), ("source", f"bugbix-{version}.tar.gz")]:
        artifact = artifacts / filename
        expected = hashlib.sha256(artifact.read_bytes()).hexdigest() + "  " + filename + "\n"
        if (artifacts / (filename + ".sha256")).read_text(encoding="utf-8") != expected:
            raise ValueError("Consumer artifact checksum mismatch")
        results.append(exercise(destination / label, artifact, version))
    summary = {"version": version, "python": sys.version.split()[0], "platform": sys.platform, "artifacts": results}
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
