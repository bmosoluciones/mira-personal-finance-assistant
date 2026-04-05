# Advanced documentation: remote GUI access over SSH (X11)

This advanced guide explains how to run MIRA (PySide6) on a headless Linux server and display its graphical interface on a local machine using an SSH tunnel with X11 Forwarding.

## Can MIRA run on a headless server?

Yes. MIRA can be installed and launched on a remote headless server, and its GUI can be displayed remotely through SSH with X11 Forwarding.

## Requirements

### On the remote server (Linux)

1. Python 3.12 (MIRA requires at least 3.9).
2. A virtual environment is recommended.
3. Base graphical dependencies for Qt/PySide6.
4. `xauth` installed.
5. An SSH service with X11 enabled.

> Note: although PySide6 may support a wider range of Python versions depending on the release, this project declares `requires-python = ">=3.9"`.

### Recommended packages on the remote host (modern distributions)

#### Debian / Ubuntu

Install the base Python packages, SSH server, X11 forwarding tools, and common Qt libraries:

```bash
sudo apt update
sudo apt install -y \
  openssh-server xauth x11-apps \
  python3 python3-venv python3-pip \
  libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0 \
  libx11-xcb1 libxcb1 libdbus-1-3 libfontconfig1 \
  libxrender1 libxext6 libsm6 libice6
```

#### Fedora / RHEL

Install the equivalent OpenSSH, X11, and graphical runtime packages:

```bash
sudo dnf install -y \
  openssh-server xauth xorg-x11-xauth xorg-x11-apps \
  python3 python3-pip \
  mesa-libGL mesa-libEGL libxkbcommon-x11 libxcb \
  libX11 libXcomposite libXcursor libXdamage libXext \
  libXi libXrender libXtst libXrandr \
  fontconfig dbus-libs
```

Configure `/etc/ssh/sshd_config`:

```ini
X11Forwarding yes
X11UseLocalhost yes
```

Apply the changes:

```bash
sudo systemctl restart sshd
```

### On the local client

- Linux/macOS: an OpenSSH client with X11 support.
- Windows: an SSH client plus a local X server such as VcXsrv or Xming.

## Installing MIRA on the remote server

From the repository:

```bash
python3 -m venv mira_env
source mira_env/bin/activate
pip install --upgrade pip
pip install https://mira.bmogroup.solutions/releases/mira_personal_finance_assistant-0.0.1rc3-py3-none-any.whl
```

## Remote connection and GUI launch

### Option A: Linux/macOS (OpenSSH)

Connect with X11 forwarding enabled using the more restrictive default mode:

```bash
ssh -X user@remote-server
```

Launch MIRA:

```bash
/path/to/project/mira_venv/bin/mira
```

### Option B: Windows (PuTTY)

1. Start your local X server (VcXsrv/Xming).
2. In PuTTY, open `Connection > SSH > X11`.
3. Enable **X11 forwarding**.
4. Set **X display location** to `localhost:0`.
5. Connect to the server.
6. Run in the remote session:

```bash
/path/to/project/.venv/bin/mira
```

### Option C: other SSH clients with X11

Clients such as OpenSSH, MobaXterm, or Bitvise work with the same general pattern:

1. Enable X11 Forwarding in the client.
2. Connect to the remote server.
3. Run `mira`.

## Verifying the X11 tunnel

In the remote session:

```bash
echo $DISPLAY
```

If it returns a value such as `localhost:10.0`, forwarding is active.

## Common issues

### Empty `DISPLAY`

- Verify that the client is actually enabling X11.
- Check that `sshd_config` includes `X11Forwarding yes`.
- Install `xauth` on the server if it is missing.

### Qt/XCB plugin error

This usually indicates incomplete X11 libraries on the server. Install the Qt/PySide6 runtime packages required by your distribution.

### Slow interface

This is expected on high-latency links. If the connection is unstable, consider using `mira-cli` for non-visual tasks.

## Security recommendations

SSH X11 Forwarding encrypts tunnel traffic, but it is **not automatically "secure in every scenario"**. Recommended practices:

- Prefer `ssh -X` over `ssh -Y`.
- Use `ssh -Y` only if an application explicitly requires it, since it grants broader trust to the server over your local display.
- Disable password-based SSH authentication and use keys only.
- Disable direct `root` login over SSH.
- Limit allowed SSH users with `AllowUsers` or `AllowGroups`.
- Avoid exposing SSH directly to the public internet without additional controls.
- Restrict access with a firewall, rate limiting, and, if possible, MFA.
- For frequent remote operation, prefer VPN access and private networks.
- Keep the server updated with system and OpenSSH security patches.

### `-X` or `-Y`?

- `-X` (untrusted forwarding): safer, with some X11 capabilities restricted.
- `-Y` (trusted forwarding): more compatible, but with a larger client-side risk surface.

If MIRA works with `-X`, that is the recommended mode.
