# Installation and Launch

## Core dependencies

MIRA runs with:

- `openpyxl>=3.1.5`
- `PySide6>=6.10.2`
- `qt-material>=2.14`

## Official downloads

Published MIRA distributions are available on GitHub Releases:

- https://github.com/bmosoluciones/mira-personal-finance-assistant/releases/latest

MIRA is not planned for publication on PyPI, so `pip` is not the recommended end-user installation path.

Release artifacts:

- `.whl`: Python package for installation and packaging.
- `.tar.gz`: source distribution, including the source and license.

## Launch

- From a source checkout, install the desktop app with `pip install '.[gui]'`.
- The CLI and MCP server do not require the GUI extra.

## Useful parameters

- `--db PATH`: custom SQLite database path.
- `--debug`: enables verbose logging.

## Important notes

- Natural-language transactions always use the deterministic parser.
- If you are working from the repository as a developer, follow the development workflow described in the `README`.
