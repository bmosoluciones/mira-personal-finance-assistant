# Documentación avanzada: acceso GUI remoto a través de SSH (X11)

Esta guía avanzada explica cómo ejecutar MIRA (PySide6) en un servidor Linux sin monitor (headless) y mostrar su interfaz gráfica en una máquina local utilizando un túnel SSH con X11 Forwarding.

## ¿Puede MIRA ejecutarse en un servidor headless?

Sí. MIRA puede instalarse e iniciarse en un servidor remoto sin monitor, y su interfaz gráfica puede mostrarse de forma remota a través de SSH con X11 Forwarding.

## Requisitos

### En el servidor remoto (Linux)

1. Python 3.12 (MIRA requiere al menos 3.9).
2. Se recomienda un entorno virtual.
3. Dependencias gráficas base para Qt/PySide6.
4. `xauth` instalado.
5. Un servicio SSH con X11 habilitado.

> Nota: aunque PySide6 puede soportar una gama más amplia de versiones de Python dependiendo del lanzamiento, este proyecto declara `requires-python = ">=3.9"`.

### Paquetes recomendados en el host remoto (distribuciones modernas)

#### Debian / Ubuntu

Instala los paquetes base de Python, el servidor SSH, las herramientas de reenvío X11 y las librerías comunes de Qt:

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

Instala los paquetes equivalentes de OpenSSH, X11 y el runtime gráfico:

```bash
sudo dnf install -y \
  openssh-server xauth xorg-x11-xauth xorg-x11-apps \
  python3 python3-pip \
  mesa-libGL mesa-libEGL libxkbcommon-x11 libxcb \
  libX11 libXcomposite libXcursor libXdamage libXext \
  libXi libXrender libXtst libXrandr \
  fontconfig dbus-libs
```

Configura `/etc/ssh/sshd_config`:

```ini
X11Forwarding yes
X11UseLocalhost yes
```

Aplica los cambios:

```bash
sudo systemctl restart sshd
```

### En el cliente local

- Linux/macOS: un cliente OpenSSH con soporte para X11.
- Windows: un cliente SSH más un servidor X local como VcXsrv o Xming.

## Instalar MIRA en el servidor remoto

Desde el repositorio:

```bash
python3 -m venv mira_env
source mira_env/bin/activate
pip install --upgrade pip
pip install https://mira.bmogroup.solutions/releases/mira_personal_finance_assistant-0.0.1rc3-py3-none-any.whl
```

## Conexión remota e inicio de la GUI

### Opción A: Linux/macOS (OpenSSH)

Conéctate con el reenvío X11 habilitado utilizando el modo predeterminado más restrictivo:

```bash
ssh -X usuario@servidor-remoto
```

Inicia MIRA:

```bash
/ruta/al/proyecto/mira_env/bin/mira
```

### Opción B: Windows (PuTTY)

1. Inicia tu servidor X local (VcXsrv/Xming).
2. En PuTTY, abre `Connection > SSH > X11`.
3. Habilita **X11 forwarding**.
4. Establece **X display location** en `localhost:0`.
5. Conéctate al servidor.
6. Ejecuta en la sesión remota:

```bash
/ruta/al/proyecto/.venv/bin/mira
```

### Opción C: otros clientes SSH con X11

Clientes como OpenSSH, MobaXterm o Bitvise funcionan con el mismo patrón general:

1. Habilita X11 Forwarding en el cliente.
2. Conéctate al servidor remoto.
3. Ejecuta `mira`.

## Verificar el túnel X11

En la sesión remota:

```bash
echo $DISPLAY
```

Si devuelve un valor como `localhost:10.0`, el reenvío está activo.

## Problemas comunes

### `DISPLAY` vacío

- Verifica que el cliente realmente esté habilitando X11.
- Comprueba que `sshd_config` incluya `X11Forwarding yes`.
- Instala `xauth` en el servidor si falta.

### Error del plugin Qt/XCB

Esto suele indicar que faltan librerías X11 en el servidor. Instala los paquetes de tiempo de ejecución Qt/PySide6 requeridos por tu distribución.

### Interfaz lenta

Esto es de esperar en enlaces de alta latencia. Si la conexión es inestable, considera usar `mira-cli` para tareas no visuales.

## Recomendaciones de seguridad

El reenvío SSH X11 cifra el tráfico del túnel, pero **no es automáticamente "seguro en todos los escenarios"**. Prácticas recomendadas:

- Prefiere `ssh -X` sobre `ssh -Y`.
- Usa `ssh -Y` solo si una aplicación lo requiere explícitamente, ya que otorga una confianza más amplia al servidor sobre tu pantalla local.
- Deshabilita la autenticación SSH basada en contraseña y usa solo claves.
- Deshabilita el inicio de sesión directo de `root` a través de SSH.
- Limita los usuarios SSH permitidos con `AllowUsers` o `AllowGroups`.
- Evita exponer SSH directamente al internet público sin controles adicionales.
- Restringe el acceso con un firewall, limitación de tasa y, si es posible, MFA.
- Para operaciones remotas frecuentes, prefiere el acceso VPN y redes privadas.
- Mantén el servidor actualizado con los parches de seguridad del sistema y de OpenSSH.

### ¿`-X` o `-Y`?

- `-X` (reenvío no confiable): más seguro, con algunas capacidades X11 restringidas.
- `-Y` (reenvío confiable): más compatible, pero con una mayor superficie de riesgo en el lado del cliente.

Si MIRA funciona con `-X`, ese es el modo recomendado.
