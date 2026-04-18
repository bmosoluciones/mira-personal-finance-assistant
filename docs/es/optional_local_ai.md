# Modelos locales opcionales

MIRA no necesita un LLM para registrar transacciones o generar reportes estructurados.

## Qué hace el modelo local

Un modelo GGUF local solo se usa para:

- modo chat
- respuestas conversacionales
- preguntas abiertas dentro de la app

## Qué no hace el modelo local

El modelo local no participa en:

- registrar ingresos
- registrar gastos
- analizar prompts estructurados del asistente
- traducir lenguaje natural a transacciones

Eso lo hace siempre `TransactionParserEngine`.

## Cómo activarlo

1. Si usas una distribución oficial (`.exe` o `.zip`), abre `Ajustes`.
2. Descarga o selecciona un `.gguf`.
3. Cambia el modo de interacción a `Chat`.

Si estás armando MIRA desde el repositorio para desarrollo o empaquetado, instala el extra opcional con:

```bash
pip install ".[chat]"
```

Si no hay modelo activo, MIRA vuelve automáticamente al modo asistente.
