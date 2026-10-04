"""Package only the lead-owned integration files; never credentials or model runs."""

from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.txt", ".env.example", ".gitignore", "requirements-ai.txt",
         "scripts/check_workspace.py", "scripts/package_lead.py"]
DIRECTORIES = ["rarebridge/ai", "submission"]
EXCLUDED_PARTS = {"__pycache__", "cache", "runs"}


def main():
    # The user may configure the template accidentally. Never ship populated
    # credential fields, even though this template is intentionally included.
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        raw = line.strip().removeprefix("export ")
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        if name.strip().endswith("API_KEY") and value.strip().strip("\"'"):
            raise ValueError("Clear API key fields in .env.example before packaging")
    paths = [ROOT / item for item in FILES]
    for name in DIRECTORIES:
        paths.extend(path for path in (ROOT / name).rglob("*") if path.is_file())
    included = sorted({path for path in paths
                       if not (set(path.relative_to(ROOT).parts) & EXCLUDED_PARTS)
                       and not path.name.endswith((".pyc", ".pyo"))})
    destination = ROOT / "lead-ai-handoff.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in included:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Lead archive integrity check failed")
        names = archive.namelist()
        if any(name in {".env"} or "/cache/" in name or "/runs/" in name for name in names):
            raise ValueError("Lead archive contains excluded runtime configuration")
    print(f"Created {destination.name}: {len(included)} files, {destination.stat().st_size} bytes; integrity checked")


if __name__ == "__main__":
    main()
