"""CLI entry point.

Full commands (create config, run over CSV, evaluate) are implemented in task
6.7. For now this provides a working ``mad`` entry point that reports the
version, so the console script declared in pyproject.toml resolves.
"""

from __future__ import annotations

import sys

from mad import __version__ as mad_version


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"-V", "--version", "version"}:
        print(f"mad {mad_version}")
        return 0
    print(
        f"mad {mad_version} — CLI commands are not implemented yet (see task 6.7).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
