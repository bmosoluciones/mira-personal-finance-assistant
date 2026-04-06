# Manual Linux installation from sources

This guide explains how to manually install **MIRA** in Linux using a python virtual environment under `$HOME`, and then integrate the app with the desktop menu.

## Target result

At the end of this guide you will have:

- MIRA installed in `~/.mira` (Python virtual environment).
- The MIRA icon installed as `~/.local/share/icons/hicolor/256x256/apps/solutions.bmogroup.mira.png`.
- A desktop entry at `~/.local/share/applications/solutions.bmogroup.mira.desktop`.

## Prerequisites

- Linux system with a desktop environment.
- Python available as `python3` (python3.12+) with support for `pip` and `venv`. 

## Tutorial

### Create the virtual environment

From your home directory:

```bash
python3 -m venv ~/.mira
```

Upgrade packaging tools:

```bash
~/.mira/bin/pip install --upgrade pip setuptools wheel
```

### Install MIRA from the repository

```bash
~/.mira/bin/pip install https://github.com/bmosoluciones/mira-personal-finance-assistant/archive/refs/heads/main.zip
```

Validation:

```bash
~/.mira/bin/mira-cli --check
```

### Reuse the existing icon from `packaging/snap`

Copy the repository icon (`packaging/snap/256x256.png`) to the standard local icon location and required app name:

```bash
wget -o  ~/.local/share/icons/hicolor/256x256/apps/solutions.bmogroup.mira.png https://github.com/bmosoluciones/mira-personal-finance-assistant/blob/main/packaging/snap/256x256.png?raw=true
```

Optional cache refresh:

```bash
gtk-update-icon-cache ~/.local/share/icons/hicolor || true
```

### Reuse the existing `.desktop` file and update `Exec`

Start from the repository desktop file and patch only the executable path:

```bash
wget -o ~/.local/share/applications/solutions.bmogroup.mira.desktop https://raw.githubusercontent.com/bmosoluciones/mira-personal-finance-assistant/refs/heads/main/packaging/snap/solutions.bmogroup.mira.desktop
```

Replace `Exec=mira` with a user-specific launcher path:

```bash

```

The key fields should look like:

```ini
[Desktop Entry]
Type=Application
Name=MIRA
Comment=Personal Finance Assistant
Exec=/home/<user>/.mira/bin/mira
Icon=solutions.bmogroup.mira
Categories=Office;Finance;
StartupNotify=true
Terminal=false
```

Replace <user> with your unix user.

### Verify desktop integration

Check desktop file validity:

```bash
desktop-file-validate ~/.local/share/applications/solutions.bmogroup.mira.desktop
```

Run MIRA from terminal:

```bash
~/.mira/bin/mira
```

Then search for **MIRA** in your desktop launcher/application menu.
