# Línea de comandos y servidor MCP

MIRA trae dos puntos de entrada: `mira` abre la interfaz de escritorio y
`mira-cli` trabaja sobre un fichero de base de datos sin GUI. El comando
`mira-cli mcp` habla [MCP](https://modelcontextprotocol.io) por stdio para que
un asistente pueda llamar a los mismos comandos.

Todo lo de esta página es local: la CLI nunca necesita Qt y el servidor MCP
nunca necesita un LLM.

## Línea de comandos

### Opciones

| Opción | Punto de entrada | Efecto |
| --- | --- | --- |
| `--db PATH` | `mira-cli` | Fichero SQLite que usar. Por defecto, el directorio de datos del usuario. |
| `--json` | `mira-cli` | Imprimir JSON legible por máquina en lugar de texto. |
| `--version` | `mira-cli` | Imprimir la versión del paquete instalado. |
| `--check` | `mira-cli` | Comprobación de dependencias sin interfaz. No importa Qt. |
| `--debug` | `mira` | Log detallado en la interfaz de escritorio. |

`--check` es la forma más rápida de confirmar que la instalación funciona:

```bash
mira-cli --check
```

### Subcomandos

| Subcomando | Qué hace |
| --- | --- |
| `backup` | Copia la base de datos a `--output-file PATH`. |
| `restore` | Sustituye la base de datos por `--input-file PATH`. |
| `seed` | Rellena la base de datos del año actual con presupuesto y transacciones de demostración. |
| `income add` | Registrar un ingreso. |
| `expense add` | Registrar un gasto. |
| `transfer` | Transferir dinero entre cuentas. |
| `transactions list` | Listar transacciones. |
| `report` | Imprimir un resumen local. |
| `record` | Registrar una transacción con el parser local. |

Ejemplos:

```bash
mira-cli --db ~/finanzas.db backup --output-file ~/finanzas-2026.db
mira-cli expense add --account "Efectivo" --amount 12.50 --category "Comida"
mira-cli transfer --from "Efectivo" --to "Banco" --amount 100
mira-cli --json transactions list --limit 10 --since 2026-05-01
mira-cli report --since 2026-01-01
mira-cli record "gasté 30 euros en el supermercado el 3 de mayo"
```

`record` usa `TransactionParserEngine`, el mismo parser de prompts
estructurados que usa la interfaz. No contacta con ningún proveedor y no es el
modo chat.

Los importes aceptan un separador decimal y `--date` usa `YYYY-MM-DD`. Los
nombres de cuenta se resuelven tal cual; un nombre que no existe se informa
como error en lugar de crear una cuenta.

## Servidor MCP

### Cómo activarlo

El servidor está apagado hasta que lo aceptes en la interfaz, porque un cliente
MCP puede leer y modificar tus finanzas y puede reenviarlas a otro sitio:

1. Abre `Ajustes`, busca la sección MCP y actívala.
2. Acepta el aviso de terceros.

Hacen falta los dos ajustes (`mcp_enabled` y `mcp_third_party_ack`). Hasta
entonces `mira-cli mcp` termina con estado `2` y explica por qué. Nada más de la
CLI se ve afectado.

El consentimiento se comprueba antes de cada llamada a una herramienta. Si
desactivas MCP o revocas el aviso mientras un cliente está conectado, se
rechazará su siguiente lectura o escritura. Para volver a usar las herramientas,
activa MCP otra vez y reinicia el proceso del cliente.

### Cómo ejecutarlo

```bash
mira-cli --db ~/finanzas.db mcp
```

El proceso lee JSON-RPC delimitado por saltos de línea desde la entrada estándar
y lo escribe en la salida estándar, un mensaje por línea. Los avisos y errores
van a la salida de error, así que el canal del protocolo queda limpio. Sigue
funcionando hasta que el cliente cierra el flujo.

Apunta un cliente MCP al comando, por ejemplo:

```json
{
  "mcpServers": {
    "mira": {
      "command": "mira-cli",
      "args": ["--db", "/home/tu/finanzas.db", "mcp"]
    }
  }
}
```

### Herramientas

| Herramienta | Obligatorio | Opcional |
| --- | --- | --- |
| `add_income` | `amount`, `account` | `description`, `category`, `date`, `note` |
| `add_expense` | `amount`, `account` | `description`, `category`, `date`, `note` |
| `transfer` | `source`, `target`, `amount` | `date`, `note` |
| `list_transactions` | ninguno | `limit`, `account`, `since`, `until` |
| `report` | ninguno | `since` |

Los importes son cadenas para que no haya redondeo al entrar, y las fechas son
`YYYY-MM-DD`. Las cuentas se resuelven por nombre.

Los errores vuelven como errores JSON-RPC con un motivo corto: un nombre de
cuenta que no existe lo dice, en lugar de crear una segunda cuenta. Los
métodos desconocidos devuelven el error `-32601`.

### Qué no hace

El servidor no tiene chat, ni LLM, ni acceso a la red. Expone las mismas cinco
operaciones locales que los subcomandos de la CLI de arriba, y nada más.
