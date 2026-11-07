"""Console output that cannot crash on a narrow terminal encoding."""

from __future__ import annotations

import sys


def safe_stdio() -> None:
    """Replace unencodable characters on stdout/stderr instead of raising.

    The CLIs print arrows and check marks. On a Windows console with a legacy code page
    (cp1252) Python raises UnicodeEncodeError on them, which killed the gate mid-report
    with a traceback and a wrong exit code.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
