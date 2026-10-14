# Studio CMS

CMS propio en Flask para construir sitios de clientes de VF Digital. Este repositorio implementa **solo la etapa 1: el Studio de uso personal**. Con él, un único administrador construye un sitio completo (modelos, contenido, plantillas y diseño visual) y lo exporta como sitio estático en un ZIP que sube a mano al hosting del cliente.

## Fuentes de verdad

Lee estos archivos antes de planificar cualquier trabajo:

1. `docs/etapa-1.md`: alcance, requerimientos con criterios de aceptación, modelo de datos y plan por hitos. **Manda sobre todo lo demás.**
2. `docs/requerimientos.md`: visión completa del sistema (etapas 1 a 4). Úsalo para entender el contexto y no cerrar puertas a etapas futuras, pero no implementes nada que no esté en `docs/etapa-1.md`.
3. `docs/prototipo/`: pantallas de referencia de diseño y comportamiento. Lee `docs/prototipo/README.md` antes de usarlas. **No copies su formato (`x-dc`, `DCLogic`) al código.**

Si encuentras una contradicción entre estos archivos, o un requerimiento que no se puede cumplir tal como está escrito, detente y pregunta antes de decidir.

## Forma de trabajo

- Se trabaja **un hito a la vez**, en el orden de la sección 8 de `docs/etapa-1.md` (H1 a H9). No adelantes trabajo de hitos posteriores.
- Antes de escribir código de un hito, propone un plan (archivos, modelos, migraciones, pruebas) y espera aprobación.
- Un hito está terminado cuando su entregable verificable funciona y se cumplen los criterios de aceptación de sus requerimientos (RF), con pruebas que los cubren.
- Al cerrar un hito, marca sus criterios en `docs/etapa-1.md` (`- [x]`) y resume lo hecho y lo pendiente.
- Antes de H7 (editor visual) se hace una prueba de concepto de GrapesJS con Jinja2: un bloque de lista que genere un `for` válido y se vea igual en el editor y en la vista previa.
- Commits pequeños, en español, con el hito y el RF cuando aplique: `H2: formulario generado desde el modelo (RF-10)`.

## Stack (decidido, no cambiar sin consultar)

| Capa | Tecnología |
| --- | --- |
| Backend | Python 3.12, Flask con Blueprints y patrón `create_app()` |
| Base de datos | PostgreSQL 16 con Flask-SQLAlchemy y Flask-Migrate (Alembic); contenido dinámico en JSONB |
| Autenticación | Flask-Login, Argon2 (`argon2-cffi`), TOTP con `pyotp` |
| Seguridad | Flask-WTF (CSRF), Flask-Limiter, `nh3` para sanitizar HTML |
| Validación de contenido | `jsonschema` contra el esquema de cada modelo |
| Tareas en segundo plano | RQ con Redis |
| Imágenes | Pillow (variantes WebP de 320, 800 y 1600 px) |
| Plantillas de sitios | Jinja2 con `SandboxedEnvironment` y cargador desde la base de datos |
| Interfaz del Studio | Plantillas Jinja2 + HTMX; JavaScript solo en «islas» |
| Editor de código | Monaco Editor con un lenguaje Jinja2 propio (partir de Twig) |
| Editor visual | GrapesJS con componentes y plugins propios |
| Texto enriquecido | Tiptap |
| Despliegue | Docker Compose: Flask + Gunicorn, PostgreSQL, Redis, trabajador RQ y Caddy |

Monaco, GrapesJS y Tiptap se instalan con npm en `frontend/` y se compilan con esbuild a `app/static/dist/`. Se sirven desde el propio Studio (sin CDN) y se cargan solo en las pantallas que los usan.

## Estructura del proyecto

```text
studio-cms/
  app/
    __init__.py          # create_app()
    config.py
    extensions.py        # db, migrate, login_manager, csrf, limiter
    core/                # modelo base con site_id, filtro por sitio, auditoría, sitio activo
    auth/                # inicio de sesión, doble factor, códigos de recuperación, cuenta
    sites/               # sitios y selector de sitio activo
    content/             # modelos (content_types), entradas y versiones
    media/               # carga, validación, variantes y usos
    templating/          # cargador, sandbox, funciones y filtros del CMS, versiones
    visual/              # GrapesJS: plantillas visuales, diseños base, bloques y tema
    routing/             # rutas, SEO y resolución de URL
    preview/             # vista previa del sitio completo
    export/              # generación estática y ZIP
    templates/           # plantillas Jinja2 del panel del Studio (no de los sitios)
    static/
  frontend/              # fuentes JS de las islas (Monaco, GrapesJS, Tiptap) y package.json
  migrations/
  tests/
  docs/
  docker-compose.yml
  Dockerfile
  Caddyfile
  .env.example
  pyproject.toml
```

## Reglas que no se negocian

- **Aislamiento por sitio.** Toda tabla de contenido tiene `site_id`. El filtro por sitio se aplica automáticamente en la capa de consultas (por ejemplo, con un evento `do_orm_execute` o una clase de consulta base), nunca a mano en cada vista. Cada módulo incluye una prueba que intenta leer datos de otro sitio y falla.
- **Plantillas de sitios siempre en sandbox.** Nunca uses `Environment` normal para plantillas guardadas en la base de datos. Las funciones disponibles en ellas se exponen de forma explícita.
- **Un solo motor de renderizado** para el editor, la vista previa y la exportación. Lo que se ve en la vista previa es exactamente lo que se exporta.
- **HTML enriquecido sanitizado** con `nh3` y lista blanca antes de guardarse.
- **Archivos validados por su contenido real**, no por la extensión.
- **Secretos solo en variables de entorno.** Nada de credenciales en el código ni en el repositorio; mantén `.env.example` al día.
- **Tareas pesadas en RQ** (variantes de imagen y exportación); ninguna petición HTTP las ejecuta en línea.
- No agregues dependencias fuera del stack sin consultar.

## Funciones y filtros disponibles en las plantillas de sitios

Los nombres van en español porque los escribe el administrador en sus plantillas:

- `entradas(modelo, **filtros, orden=None, limite=None)`: lista de entradas listas para exportar.
- `entrada(modelo, slug)`: una entrada.
- `url_entrada(entrada)`: URL según las rutas del sitio.
- `media_url(media, variante="mediana")`: URL de un archivo o de una de sus variantes.
- Filtros `moneda` (pesos chilenos, sin decimales y con separador de miles) y `fecha`.

Monaco debe autocompletar estos nombres.

## Convenciones

- Código, identificadores, tablas y columnas en inglés (como en el modelo de datos de `docs/etapa-1.md`).
- Interfaz, mensajes al usuario, documentación y commits en español neutro.
- Formato y lint con `ruff`; pruebas con `pytest` contra un PostgreSQL real (servicio de Docker Compose), no SQLite.
- Las pantallas del panel siguen la estructura, los textos y la paleta del prototipo, con HTMX para las interacciones (formularios parciales, listas filtradas, confirmaciones).
- Accesibilidad básica: etiquetas en todos los campos, foco visible y controles usables con teclado.

## Comandos

Copia `.env.example` a `.env` y completa los valores. Fuera de Docker, los comandos leen `.env` con `uv run --env-file .env`.

```bash
docker compose up -d db redis                        # PostgreSQL y Redis (también crean la base studio_test)
uv sync                                              # dependencias de Python
uv run --env-file .env flask --app app db upgrade    # aplicar migraciones
uv run --env-file .env flask --app app db migrate -m "mensaje"   # nueva migración tras cambiar modelos
uv run --env-file .env flask --app app crear-admin   # administrador: imprime secreto TOTP, URI y códigos
uv run --env-file .env flask --app app regenerar-codigos         # nuevos códigos de recuperación
uv run --env-file .env flask --app app run --debug   # Studio en http://localhost:5000 (SESSION_COOKIE_SECURE=false)
uv run --env-file .env rq worker                     # trabajador RQ
uv run --env-file .env pytest                        # pruebas (usa TEST_DATABASE_URL; la base de desarrollo debe estar migrada)
uv run ruff check . && uv run ruff format .          # lint y formato
docker compose up -d --build                         # stack completo con Caddy en https://localhost
docker compose exec web flask --app app crear-admin  # administrador dentro del stack
```

Islas JS (Tiptap; luego Monaco y GrapesJS), compiladas con esbuild a `app/static/dist/` (no versionado; el `Dockerfile` las compila solo):

```bash
cd frontend && npm ci && npm run build             # o `npm run watch` mientras se desarrolla
```

## Fuera de alcance en este repositorio por ahora

Publicación automática, formularios, editores cliente e invitaciones, vista previa compartible, secciones libres y guías, Runtime, API REST y extensiones. Si una tarea parece requerir algo de esto, pregunta antes.
