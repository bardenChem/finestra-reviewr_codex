from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdfFile:
    """Discovered PDF and its content hash."""

    path: Path
    sha256: str


def calculate_sha256(path: Path, *, block_size: int = 1024 * 1024) -> str:
    """Calculate a SHA-256 hash using streamed reads."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


class PdfScanner:
    """Recursive deterministic PDF discovery."""

    def discover(self, input_dir: Path) -> list[PdfFile]:
        if not input_dir.exists():
            msg = f"Input directory does not exist: {input_dir}"
            raise FileNotFoundError(msg)
        files = sorted(
            (
                path
                for path in input_dir.rglob("*")
                if path.is_file() and path.suffix.lower() == ".pdf"
            ),
            key=lambda path: str(path.resolve()).lower(),
        )
        return [PdfFile(path=path.resolve(), sha256=calculate_sha256(path)) for path in files]
