from __future__ import annotations

from pathlib import Path

from .gui import AppView


def main() -> None:
    base_dir = Path.cwd()
    app = AppView(base_dir)
    app.run()


if __name__ == "__main__":
    main()
