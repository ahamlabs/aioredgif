"""Entry point for ``python -m aioredgif``; the command line lives in :mod:`aioredgif.cli`."""

import sys

from aioredgif.cli import main

if __name__ == "__main__":
    sys.exit(main())
