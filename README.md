# Studio CMS

CMS propio en Flask de VF Digital para construir sitios de clientes. Este repositorio contiene la **etapa 1: Studio de uso personal**, que permite crear un sitio completo y exportarlo como sitio estático en un archivo ZIP.

**Estado:** hitos H1 a H4 terminados (base, contenido, medios y motor de plantillas); sigue la prueba de concepto de GrapesJS con Jinja2 y luego H5 (rutas y vista previa). Los comandos para trabajar están en [CLAUDE.md](CLAUDE.md#comandos).

## Documentación

| Archivo | Contenido |
| --- | --- |
| [docs/etapa-1.md](docs/etapa-1.md) | Alcance, requerimientos con criterios de aceptación, modelo de datos y plan por hitos de la etapa 1. |
| [docs/requerimientos.md](docs/requerimientos.md) | Requerimientos y especificación técnica del sistema completo (etapas 1 a 4). |
| [docs/prototipo/](docs/prototipo/README.md) | Pantallas de referencia de la interfaz. |
| [CLAUDE.md](CLAUDE.md) | Instrucciones de trabajo para Claude Code. |

## Stack

Python 3.12 · Flask · PostgreSQL 16 · Redis y RQ · Jinja2 + HTMX · Monaco Editor · GrapesJS · Tiptap · Docker Compose y Caddy.

## Plan de la etapa 1

| Hito | Contenido |
| --- | --- |
| H1 | Base: proyecto, Docker Compose, acceso con doble factor, sitios y auditoría |
| H2 | Modelos y contenido |
| H3 | Medios |
| H4 | Motor de plantillas y editor de código |
| H5 | Rutas y vista previa |
| H6 | Diseños base y estilos del sitio |
| H7 | Editor visual con GrapesJS |
| H8 | Constructor de bloques |
| H9 | Exportación estática y cierre |

## Trabajar con Claude Code

Abre el repositorio en Claude Code y comienza cada hito en modo de planificación:

```text
Lee CLAUDE.md y docs/etapa-1.md. Vamos a implementar solo el hito H1 (Base).
Propón un plan con la estructura del proyecto, los modelos y las pruebas,
y espera mi aprobación antes de escribir código.
```

Al terminar un hito, revisa sus criterios de aceptación en `docs/etapa-1.md`, confirma los cambios y recién entonces pasa al siguiente.

## Ramas

`main` siempre funciona y no recibe commits directos. Cada hito o cambio se trabaja en su propia rama y entra a `main` por pull request:

| Prefijo | Uso | Ejemplo |
| --- | --- | --- |
| `hito/` | Un hito del plan | `hito/h3-medios` |
| `fix/` | Corrección de un error | `fix/slug-duplicado` |
| `docs/` | Solo documentación | `docs/readme-ramas` |

Antes de abrir el pull request, las pruebas y `ruff check` deben pasar.
