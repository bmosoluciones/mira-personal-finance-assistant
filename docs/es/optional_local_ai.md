# Chat IA opcional

MIRA no necesita un LLM para registrar transacciones o generar reportes estructurados.

## Qué hace el modo chat

El modo chat opcional solo se usa para:

- modo chat
- respuestas conversacionales
- preguntas abiertas dentro de la app

## Qué no hace el modo chat

El modo chat no participa en:

- registrar ingresos
- registrar gastos
- analizar prompts estructurados del asistente
- traducir lenguaje natural a transacciones

Eso lo hace siempre `TransactionParserEngine`.

## Cómo activarlo

1. Abre `Ajustes` y elige un proveedor de IA.
2. Ingresa la URL base, el nombre del modelo y la API key (un endpoint compatible con OpenAI o Anthropic).
3. Acepta el aviso a terceros si el endpoint no es local.
4. Cambia el modo de interacción a `Chat`.

Los endpoints OpenAI compatibles remotos deben usar HTTPS para cifrar el texto
del chat y las API keys durante el envío. HTTP solo se permite para endpoints de
loopback como `localhost`. Anthropic usa su endpoint fijo con HTTPS.

Solo se envían peticiones al proveedor cuando usas el modo chat. La API key se
guarda junto a la base en `llm-secrets.json` con permisos `0600` y nunca forma
parte de un respaldo.

Si no hay ningún proveedor configurado, MIRA vuelve automáticamente al modo asistente.

La linea de comandos y el servidor MCP se documentan aparte. Ver [Linea de comandos y servidor MCP](command_line.md).
