"""Build and verify the actual wheel/source distributions before upload."""
import ast
from email.parser import BytesParser
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def release_version():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("Release version must be stable SemVer")
    values = [ast.literal_eval(n.value) for n in ast.parse((ROOT / "bugbix/__init__.py").read_text()).body
              if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets)]
    if values != [version] or project["name"] != "bugbix" or project["license"] != "MIT" or project["license-files"] != ["LICENSE"] or project["dependencies"]:
        raise ValueError("Package, runtime version, license or dependency metadata mismatch")
    return version


def safe_members(names):
    if len(names) != len(set(names)):
        raise ValueError("Duplicate archive entry")
    for name in names:
        path = PurePosixPath(name.rstrip("/"))
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            raise ValueError("Unsafe archive entry")
        if any(part in {".git", ".venv", "__pycache__", "artifacts", "build", "dist", "qa-v1"} for part in path.parts):
            raise ValueError("Private/build content in archive")


def metadata(data, version):
    info = BytesParser().parsebytes(data)
    if info["Name"] != "bugbix" or info["Version"] != version or info["Requires-Python"] != ">=3.11" or info.get_all("Requires-Dist"):
        raise ValueError("Distribution metadata mismatch")
    if (info["License-Expression"] or info["License"]) != "MIT":
        raise ValueError("Distribution license mismatch")


def verify(directory, version):
    wheel = directory / f"bugbix-{version}-py3-none-any.whl"
    source = directory / f"bugbix-{version}.tar.gz"
    modules = {f"bugbix/{p.name}": p.read_bytes() for p in (ROOT / "bugbix").glob("*.py")}
    license = (ROOT / "LICENSE").read_bytes()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist(); safe_members(names)
        if archive.testzip() is not None:
            raise ValueError("Wheel CRC failure")
        actual = {name for name in names if name.startswith("bugbix/")}
        if actual != set(modules):
            raise ValueError("Wheel contains unexpected/missing runtime files")
        for name, data in modules.items():
            if archive.read(name) != data:
                raise ValueError("Wheel runtime source differs: " + name)
        info = f"bugbix-{version}.dist-info/"
        metadata(archive.read(info + "METADATA"), version)
        if "bugbix = bugbix.cli:main" not in archive.read(info + "entry_points.txt").decode():
            raise ValueError("Wheel CLI entry point missing")
        licenses = [name for name in names if name.startswith(info) and name.endswith("/LICENSE")]
        if len(licenses) != 1 or archive.read(licenses[0]) != license:
            raise ValueError("Wheel MIT license differs")
    with tarfile.open(source, "r:gz") as archive:
        members = archive.getmembers(); safe_members([m.name for m in members])
        if any(not (m.isfile() or m.isdir()) for m in members):
            raise ValueError("Linked/special source archive entry")
        prefix = f"bugbix-{version}/"
        if any(not (m.name == prefix.rstrip("/") or m.name.startswith(prefix)) for m in members):
            raise ValueError("Source archive prefix mismatch")
        for name, data in {**modules, "LICENSE": license}.items():
            if archive.extractfile(prefix + name).read() != data:
                raise ValueError("Source distribution differs: " + name)
        metadata(archive.extractfile(prefix + "PKG-INFO").read(), version)
        for name in ["README.md", "docs/stability.md", "docs/recovery.md", "tests/test_product.py"]:
            if archive.extractfile(prefix + name).read() != (ROOT / name).read_bytes():
                raise ValueError("Source guide/test differs: " + name)
    lines = []
    for artifact in sorted([wheel, source]):
        line = hashlib.sha256(artifact.read_bytes()).hexdigest() + "  " + artifact.name + "\n"
        artifact.with_name(artifact.name + ".sha256").write_text(line, encoding="utf-8", newline="\n")
        lines.append(line)
    (directory / "SHA256SUMS").write_text("".join(lines), encoding="utf-8", newline="\n")
    return [wheel.name, source.name]


if __name__ == "__main__":
    version = release_version()
    directory = ROOT / "artifacts"
    directory.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(directory)], cwd=ROOT, check=True)
    print("Verified distributions: " + ", ".join(verify(directory, version)))
