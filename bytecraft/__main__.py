"""
Entry point for: py -m bytecraft file.bc
"""

import sys
from .interpreter import run


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: py -m bytecraft <script.bc>")
        print("       bytecraft <script.bc>")
        sys.exit(1)

    script = sys.argv[1]
    run(script)


if __name__ == "__main__":
    main()
