# MIRA - Personal Finance Assistant

[![CI](https://github.com/bmosoluciones/mira-personal-finance-assistant/actions/workflows/python-package.yml/badge.svg)](https://github.com/bmosoluciones/mira-personal-finance-assistant/actions/workflows/python-package.yml)

> **M**anage **I**ncome & **R**esources **A**llocations

MIRA is a personal finance desktop app focused on privacy, fast local workflows, and deterministic transaction parsing.

### Key Features

- **Local-First Privacy**: Your data stays on your device.
- **Natural Language Parsing**: Register transactions using plain English or Spanish commands.
- **Account Reconciliation**: Match your internal records against bank statements.
- **MIRA Analysis**: Advanced financial insights.
- **Bilingual Support**: Full interface and documentation in English and Spanish.

## Screenshots

<p align="center">
  <img src="https://raw.githubusercontent.com/bmosoluciones/mira-personal-finance-assistant/main/docs/images/mira_dashboard.png" alt="MIRA dashboard view" width="31%">
  <img src="https://raw.githubusercontent.com/bmosoluciones/mira-personal-finance-assistant/main/docs/images/mira_budget.png" alt="MIRA budget view" width="31%">
  <img src="https://raw.githubusercontent.com/bmosoluciones/mira-personal-finance-assistant/main/docs/images/mira_main_report.png" alt="MIRA main report view" width="31%">
</p>

## Documentation

Official documentation is published at:

- https://mira.bmogroup.solutions

## Runtime dependencies

Base runtime:

- `et-xmlfile==2.0.0`
- `jinja2==3.1.6`
- `MarkupSafe==2.1.5`
- `openpyxl==3.1.5`
- `peewee==4.0.2`
- `PySide6==6.10.2`
- `qt-material==2.14`

Optional local chat (experimental):

- `llama-cpp-python==0.2.0`

## Installation

Official downloads and release artifacts are published at:

- https://mira.bmogroup.solutions/releases/

MIRA is not planned for publication on PyPI, so end users should install it from the release site instead of relying on `pip install` or
install from sources.

Available release artifacts:

- `.exe`: Windows installer for the recommended desktop installation flow.
- `.zip`: portable Windows distribution that can be extracted and run without an installer.
- `.whl`: published to support Flatpak packaging, not as a PyPI distribution channel for end users.
- `.tar.gz`: source release published to comply with GPL license obligations.

## Running MIRA

Recommended release flows:

- Windows installer: install from the `.exe` package and launch MIRA from the Start menu.
- Portable build: extract the `.zip` package and run `MIRA.exe`.
- Flatpak: run `flatpak run solutions.bmogroup.MIRA`.

## Source and development workflows

If you are building MIRA from this repository for development or packaging work:

```bash
pip install .
```

For local development with the full test/tooling stack:

```bash
pip install ".[dev]"
```

Optional local chat support (experimental) for source builds:

```bash
pip install ".[chat]"
```

CLI and source-installed entry points:

```bash
mira
mira-cli
```

Useful flags:

- `--db PATH`: custom SQLite database path
- `--model PATH`: optional GGUF model path for chat mode
- `--debug`: verbose logging

## Product flow

First-run setup covers onboarding basics:

- user name
- language and theme
- currency and number formatting
- accounts setup

### Chat mode

If you want local chat:

1. Open `Settings`
2. Download or select a GGUF model
3. Switch interaction mode to `Chat`

If no model is active, MIRA stays in deterministic assistant mode.

## How natural-language parsing works

Assistant mode does not depend on an LLM.

The flow is:

1. **Normalize**: User text is cleaned and standardized.
2. **Parse**: The `TransactionParserEngine` extracts amounts, dates, and categories.
3. **Validate**: Results are checked against the schema contract.
4. **Execute**: The action is applied to the local database.

The curated prompt catalog used to pressure-test the parser lives in:

- `src/mira/ai/nl_examples.csv`

## Architecture snapshot

- `src/mira/ai/engine.py`: deterministic parser + optional local chat engine
- `src/mira/ai/pipeline.py`: assistant processing and optional chat orchestration
- `src/mira/ai/executor.py`: applies validated actions to the database
- `src/mira/ui/`: Qt dialogs, views, and main window
- `src/mira/db/`: facade-based database layer backed by Peewee models and explicit ORM transactions

## Development

Run the quality gates:

```bash
python -m black src/
python -m ruff check src/
python -m flake8 src/
python -m pytest
python -m pytest -m full
```

## Distribution

> Supported Python version for packaging: **Python 3.12**.

Packaging assets live under `packaging/`.
All Flatpak packaging files live inside the `packaging/flatpak/` submodule so that directory.

Current packaging layout:

```text
packaging/
├── flatpak/          # Flatpak submodule: manifest, metadata, icons, GitHub Actions CI
├── scripts/          # project-level build entry points for wheel/sdist and Windows packaging
└── windows/          # Windows launcher, NSIS installer, PyInstaller spec
└── snap/             # Snap packaging manifest.
```

Common local packaging commands:

```bash
bash packaging/scripts/build_python_dist.sh
bash packaging/scripts/build_exe.sh
```

### Linux (Flatpak)

Prerequisites (Linux host):

- `flatpak`
- `flatpak-builder`
- `python3.12`
- `req2flatpak`

1. Generate the PyPI dependency lock used for Flatpak:

```bash
python3.12 -m pip install req2flatpak
req2flatpak --requirements-file packaging/flatpak/requirements-flatpak.txt --target-platforms cp312-x86_64 --outfile packaging/flatpak/pypi-dependencies.json
```

2. Build locally with Flatpak Builder:

```bash
flatpak-builder --user --install-deps-from=flathub --install --force-clean build-flatpak packaging/flatpak/solutions.bmogroup.mira.yml
```

3. Run the installed Flatpak app:

```bash
flatpak run solutions.bmogroup.MIRA
```

### Snap

The Snap packaging definition lives in `packaging/snap`.

Prerequisites (Ubuntu host):

- `snapd` active
- `snapcraft` installed in classic mode

Install Snapcraft if needed:

```bash
sudo snap install snapcraft --classic
```

Build the snap package from the repository root:

```bash
cd packaging/snap
snapcraft pack --use-lxd --verbosity=verbose
```

Install the generated snap locally for testing:

```bash
sudo snap install --dangerous ./mira-personal-finance-assistant_*.snap
```

### Windows (`.exe` with PyInstaller)

Install development dependencies, including `pyinstaller`:

```bash
pip install ".[dev]"
```

Generate a directory-style distribution (`onedir`, without `--onefile`) with the `.ico` icon:

```bash
python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name MIRA \
  --icon src/mira/ui/icons/mira.ico \
  --paths src \
  --add-data "src/mira/ui/icons;mira/ui/icons" \
  --copy-metadata mira-personal-finance-assistant \
  packaging/windows/mira_launcher.pyw
```

Expected result:

- Executable and supporting files in `dist/MIRA/`

To generate the NSIS `.exe` installer from that output (`dist/MIRA/`):

```bash
bash packaging/scripts/build_exe.sh
```

Or, if you already generated `dist/MIRA/`, compile NSIS directly with:

```bash
makensis packaging/windows/setup.nsi
```

### macOS

There is currently **no** maintained official packaging for macOS.

## Privacy

MIRA is a personal finance assistant that respects your privacy and does not share your data with anyone.

## License

GPL-3.0-or-later
