"""PyInstaller entry point.

PyInstaller runs its target file as a standalone top-level script, which
breaks yuvviewer/__main__.py's relative imports (`from .ui...`). Importing
the package properly here instead keeps __main__.py package-relative.
"""

from yuvviewer.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
