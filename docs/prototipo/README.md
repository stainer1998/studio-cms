# Prototipo de la interfaz del Studio

Estas pantallas son una **referencia de diseño y comportamiento**, no código para reutilizar. Están escritas en un formato propio de los artefactos de diseño de Claude (etiquetas `<x-dc>`, `<sc-for>`, `<sc-if>` y una clase `DCLogic`) que depende de un runtime (`support.js`) que no está incluido. No se abren correctamente en un navegador por sí solas.

Versión navegable en línea: [Studio CMS – Interfaz](https://claude.ai/artifact/HodLJRjZN5nKdiibmrQq1t) (requiere sesión en claude.ai).

## Cómo usarlas al implementar

- Toma de cada archivo la **estructura de la pantalla, los textos, los campos, los estados y la paleta de colores**; están en el HTML y en los estilos en línea.
- Toma del bloque `<script type="text/x-dc">` el **comportamiento esperado**: qué cambia al hacer clic, qué se valida y qué datos de ejemplo se muestran.
- Reimplementa todo con el stack del proyecto: plantillas Jinja2 + HTMX para el panel, Monaco Editor para el editor de código y GrapesJS para el editor visual, los diseños base y los bloques.
- No copies el formato `x-dc` ni la clase `DCLogic` al código del proyecto.

## Pantallas

| Archivo | Pantalla | Etapa | Notas |
| --- | --- | --- | --- |
| `Main.dc.html` | Panel | 1 | Resumen del sitio activo y actividad reciente. La columna de publicación es de la etapa 2. |
| `Contenido.dc.html` | Contenido | 1 | Lista de entradas por modelo y formulario generado desde el modelo. |
| `Medios.dc.html` | Medios | 1 | Biblioteca, carga por arrastre, variantes WebP y uso del archivo. |
| `Modelos.dc.html` | Constructor de modelos | 1 | Campos, edición de campo y esquema JSON generado. |
| `Plantilla-codigo.dc.html` | Plantillas por código | 1 | Árbol de plantillas, editor y vista previa (en el proyecto: Monaco). |
| `Plantilla-visual.dc.html` | Editor visual | 1 y 2 | Lienzo, bloques, capas e inspector son etapa 1 (en el proyecto: GrapesJS). La sección libre, las guías y la alineación son etapa 2. |
| `Disenos-base.dc.html` | Diseños base | 1 | Regiones, propiedades por región, código generado y tema del sitio. |
| `Bloques.dc.html` | Constructor de bloques | 1 | Lista de bloques, propiedades, plantilla y formulario de creación con validación. |
| `Rutas.dc.html` | Rutas | 1 | Patrones de URL, tipos, plantillas y SEO. |
| `Publicacion.dc.html` | Publicación | 2 | Solo referencia; en la etapa 1 se reemplaza por la exportación en ZIP. |
| `Usuarios.dc.html` | Usuarios y roles | 2 | Solo referencia; en la etapa 1 hay un único administrador. |

## Diferencias con la etapa 1

- El selector de sitio y la navegación lateral agrupada (Contenido, Construcción, Administración) se mantienen.
- En la sección Administración, «Publicación» se reemplaza por «Exportación» (vista previa del sitio, generación del ZIP e historial). No hay pantalla de exportación en el prototipo; sigue el estilo de `Publicacion.dc.html`.
- «Usuarios» se reduce a la cuenta del administrador: datos, contraseña, doble factor y códigos de recuperación.
- Los datos de ejemplo (Panadería Los Aromos y sus productos) sirven como sitio de prueba y como datos semilla.
