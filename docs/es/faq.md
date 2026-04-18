# FAQ

## ¿MIRA necesita internet para funcionar?

No. MIRA funciona offline para operaciones financieras principales.

## ¿Mis datos salen de mi equipo?

No por diseño normal de uso. La base es local y el procesamiento principal puede operar sin red.

## ¿Puedo usar MIRA sin modelos IA?

Sí. Incluye un parser determinístico para entrada en lenguaje natural.

## ¿Qué diferencia hay entre Assistant y Chat?

- Assistant ejecuta acciones financieras estructuradas.
- Chat es conversación libre y requiere LLM local listo.

## ¿Dónde está mi base de datos?

Ruta por defecto: el directorio de datos de aplicación según la plataforma/XDG; por ejemplo `~/.local/share/mira/mira.db` en Linux.

Puedes cambiarla con `--db` al iniciar.

Desde `0.0.1a2`, MIRA ya no busca ni copia bases desde la ubicación legacy `~/.mira/` durante el arranque.

## ¿Cómo evito perder información?

1. Backup frecuente de SQLite.
2. Exportación CSV periódica.
3. Verificación antes de restaurar.

## ¿Se puede usar en Windows?

Sí. Existe lanzamiento GUI (`mira`) y CLI (`mira-cli`).
