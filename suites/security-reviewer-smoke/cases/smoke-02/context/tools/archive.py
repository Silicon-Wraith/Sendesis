import subprocess
from pathlib import Path

EXPORT_ROOT = Path("/srv/exports")


def archive_folder(folder: str, out_name: str) -> Path:
    """Called from the export endpoint with folder and out_name from the request."""
    target = EXPORT_ROOT / out_name
    subprocess.run(f"tar -czf {out_name} {folder}", shell=True, check=True, cwd=EXPORT_ROOT)
    return target
