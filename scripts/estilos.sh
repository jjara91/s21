#!/usr/bin/env bash
# Genera app/web/static/estilos.css desde assets/estilos.css con Tailwind.
# Solo hace falta correrlo cuando cambian las plantillas o assets/estilos.css:
# el CSS resultante está versionado, así que la imagen Docker no necesita Node.
set -euo pipefail
cd "$(dirname "$0")/.."

# Dependencias de build la primera vez (solo desarrollo, no van en la imagen).
[ -d node_modules ] || npm install --no-audit --no-fund

npx tailwindcss -i assets/estilos.css -o app/web/static/estilos.css --minify
echo "Listo: app/web/static/estilos.css"
