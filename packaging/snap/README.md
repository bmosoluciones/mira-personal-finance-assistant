# Build del paquete Snap

Este directorio contiene la configuracion de Snapcraft para empaquetar MIRA.

## Automatizacion en GitHub Actions

El workflow [`snap-package.yml`](../../.github/workflows/snap-package.yml) se ejecuta:

1. Solo con `push` a la rama `main`.
2. Solo cuando cambia `packaging/snap/snapcraft.yaml`.

El job fija `runs-on: ubuntu-24.04` para no depender de cambios futuros en
`ubuntu-latest`, ya que el manifiesto usa `base: core24`.

Durante la ejecucion, el workflow:

1. Hace checkout del repositorio.
2. Construye el Snap con `snapcore/action-build@v1` usando este directorio.
3. Sube el `.snap` generado como artifact del workflow.

Este disparador es intencional: en este manifiesto, los cambios mas relevantes
suelen ser la URL del wheel y su checksum, asi que cualquier actualizacion del
manifiesto amerita reconstruir el paquete.

## Requisitos para build local

1. Ubuntu con `snapd` activo.
2. `snapcraft` instalado en modo clasico:

```bash
sudo snap install snapcraft --classic
```

## Crear el paquete `.snap` localmente

Desde la raiz del repositorio:

```bash
cd packaging/snap
snapcraft pack --use-lxd --verbosity=verbose
```

Nota: en hosts Ubuntu 25.10 o superiores, para una base `core24` conviene usar
`--use-lxd` y evitar `--destructive-mode`.

## Resultado

Al finalizar, Snapcraft genera el archivo en este mismo directorio, por
ejemplo:

`mira-personal-finance-assistant_0.0.1b5_amd64.snap`

## Instalacion local para pruebas

```bash
sudo snap install --dangerous ./mira-personal-finance-assistant_0.0.1b5_amd64.snap
```

## Limpieza de artefactos de build

```bash
snapcraft clean
```
