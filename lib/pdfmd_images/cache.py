"""Atomic writes to the image cache, shared by concurrent builds."""

from pathlib import Path
from tempfile import NamedTemporaryFile


def write_cached(target: Path, data: bytes) -> None:
    temporary = None
    try:
        with NamedTemporaryFile(dir=target.parent, suffix=".part", delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
