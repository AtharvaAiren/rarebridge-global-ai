"""Build a portable review/deployment archive from explicitly selected sources."""

from hashlib import sha256
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("README.txt", "README.md", ".env.example", ".gitignore", ".vercelignore", "app.py",
              "pyproject.toml", "package.json", "vercel.json", "requirements-ai.txt",
              "requirements-backend.txt", "PROTOTYPE_SCOPE.txt")
DIRECTORIES = ("rarebridge", "frontend", "curation", "evaluation", "scripts", "submission", "tests", "handoffs/contracts")
EXCLUDED_PARTS = {"node_modules", "dist", "__pycache__", ".pytest_cache", "cache", "runs", ".tools", ".vercel", ".git", "screenshots"}
EXCLUDED_PATHS = {"submission/RELEASE_ARCHIVE.json", "submission/SOURCE_REPOSITORY.json", "submission/walkthrough/capture.json"}


def selected_paths():
    paths = [ROOT / name for name in ROOT_FILES]
    for name in DIRECTORIES:
        paths.extend(path for path in (ROOT / name).rglob("*") if path.is_file())
    paths.append(ROOT / "handoffs/GRAPH_MOTION_BRIEF.txt")
    paths.append(ROOT / "handoffs/CLAUDE_POLISH_KICKOFF.txt")
    for path in sorted(set(paths)):
        relative = path.relative_to(ROOT)
        if (not path.is_file() or path.is_symlink()
                or set(relative.parts).intersection(EXCLUDED_PARTS)
                or relative.as_posix() in EXCLUDED_PATHS):
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        if path.suffix in {".zip", ".pyc", ".pyo", ".tsbuildinfo"} or path.name == ".DS_Store":
            continue
        if path.name.startswith("package_release") and path.name != "package_release.py":
            continue
        yield path


def main():
    # Templates may have been accidentally populated. Never package a secret.
    for line in (ROOT / ".env.example").read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if (name.strip().endswith(("API_KEY", "TOKEN", "WORKSPACE_ID"))
                and value.strip().strip("\"'")):
            raise ValueError("Clear credential fields in .env.example before packaging")
    paths = list(selected_paths())
    required = {"app.py", "pyproject.toml", "vercel.json", "frontend/package-lock.json",
                "frontend/src/styles/token.css", "curation/atlas-overlay.json", "curation/source-review-log.json",
                "rarebridge/data/graph.json", "handoffs/contracts/overlay.schema.json"}
    names = {path.relative_to(ROOT).as_posix() for path in paths}
    if not required <= names:
        raise ValueError("Release inputs are missing: " + ", ".join(sorted(required - names)))
    destination = ROOT / "rarebridge-vercel-ready.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == names
        assert ".env" not in names
    report = {"archive": destination.name, "files": len(names), "bytes": destination.stat().st_size,
              "sha256": sha256(destination.read_bytes()).hexdigest(), "integrity_checked": True,
              "excluded": "Credentials, private attachments, runtime caches/runs, dependencies, local tooling, builds, frontend screenshots and workspace-only capture metadata.",
              "included_verification": "Public verification captures and final walkthrough/team videos are included when present in the selected source tree.",
              "deployment_verification_files": ["submission/public-release-verification/summary.json", "submission/research-public-verification/summary.json"],
              "deployment_verification": "The referenced reports record their own actual public checks; creating this archive does not rerun or certify a cloud build."}
    (ROOT / "submission/RELEASE_ARCHIVE.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
