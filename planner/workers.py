"""Per-worker project configuration files.

Every worker keeps their own projects file, named after them, under the
``workers/`` directory at the repository root::

    workers/pedro.json
    workers/alice.json

The app, the Quarto report and the CPOS extractor all resolve their config
through this module so a single worker name selects the right file everywhere.

For backwards compatibility, a legacy ``projects.json`` at the repository root
is treated as the default worker's file when ``workers/pedro.json`` is absent.
"""

import re
from pathlib import Path

DEFAULT_WORKER = "pedro"
WORKERS_DIRNAME = "workers"
LEGACY_CONFIG_NAME = "projects.json"

REPO_ROOT = Path(__file__).resolve().parent.parent

_VALID_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def normalize_worker(worker: str) -> str:
    """Normalize a worker name to its file-safe form.

    Args:
        worker: Worker name, e.g. "Pedro" or "pedro"

    Returns:
        Lowercased, stripped worker name

    Raises:
        ValueError: If the name is empty or not a plain identifier (this keeps
            worker names from escaping the workers directory)
    """
    name = (worker or "").strip().lower()
    if not _VALID_NAME.match(name):
        raise ValueError(
            f"Invalid worker name {worker!r}: use letters, digits, '-' or '_'."
        )
    return name


def workers_dir(root: Path | str | None = None) -> Path:
    """Return the directory holding per-worker project files."""
    return Path(root or REPO_ROOT) / WORKERS_DIRNAME


def worker_config_path(
    worker: str | None = None, root: Path | str | None = None
) -> Path:
    """Return the projects file path for a worker.

    Args:
        worker: Worker name (defaults to ``DEFAULT_WORKER``)
        root: Repository root (defaults to the installed package's root)

    Returns:
        Path to ``workers/<worker>.json``, or the legacy root ``projects.json``
        when it exists and the default worker has no file yet.
    """
    root = Path(root or REPO_ROOT)
    name = normalize_worker(worker or DEFAULT_WORKER)
    path = workers_dir(root) / f"{name}.json"
    if not path.exists() and name == DEFAULT_WORKER:
        legacy = root / LEGACY_CONFIG_NAME
        if legacy.exists():
            return legacy
    return path


def list_workers(root: Path | str | None = None) -> list[str]:
    """Return known worker names, default worker first, then alphabetical.

    A worker is "known" if ``workers/<name>.json`` exists. The default worker is
    always included so the app has something to select on a fresh checkout.
    """
    directory = workers_dir(root)
    names = sorted(
        p.stem.lower() for p in directory.glob("*.json") if _VALID_NAME.match(p.stem.lower())
    )
    if DEFAULT_WORKER in names:
        names.remove(DEFAULT_WORKER)
    return [DEFAULT_WORKER, *names]


def worker_label(worker: str) -> str:
    """Return a display label for a worker name ("ana-maria" -> "Ana Maria")."""
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", worker) if part)
