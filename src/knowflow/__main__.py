"""Allow ``python -m knowflow`` to behave like the ``knowflow`` script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
