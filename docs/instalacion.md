# Installation and Launch

## Core dependencies

MIRA runs with:

- `openpyxl>=3.1.5`
- `PySide6>=6.10.2`
- `qt-material>=2.14`

## Official downloads

Published MIRA distributions are available at:

- https://mira.bmogroup.solutions/releases/

MIRA is not planned for publication on PyPI, so `pip` is not the recommended end-user installation path.

Published artifacts:

- `.exe`: recommended Windows installer.
- `.zip`: portable Windows distribution.
- `.whl`: package published to support the Flatpak build.
- `.tar.gz`: source release published to comply with the GPL license.

## Launch

- If you installed the `.exe`, launch MIRA from the Start menu.
- If you downloaded the `.zip`, extract it and run `MIRA.exe`.
- If you use Flatpak, run `flatpak run solutions.bmogroup.MIRA`.

## Useful parameters

- `--db PATH`: custom SQLite database path.
- `--model PATH`: optional GGUF model for chat mode.
- `--debug`: enables verbose logging.

## Important notes

- Assistant mode always uses the deterministic parser.
- The local model is not used to record transactions.
- Model download and selection are handled from `Settings`.
- If you are working from the repository as a developer, follow the development workflow described in the `README`.
