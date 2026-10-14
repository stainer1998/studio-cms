// Prueba de concepto (rama poc/grapesjs-jinja): bloque «Lista de entradas» de GrapesJS que
// exporta un {% for %} sobre entradas() y se muestra en el lienzo renderizado por el mismo
// motor de plantillas del Studio (POST al servidor), igual que la vista previa.
import grapesjs from "grapesjs";
import "grapesjs/dist/css/grapes.min.css";

const cfg = document.currentScript.dataset;
const MODELS = JSON.parse(cfg.models);
const status = (text) => (document.getElementById("v-status").textContent = text);
const datos = () => document.getElementById("v-datos").value;

async function renderFragment(source) {
  const started = performance.now();
  const response = await fetch(cfg.fragment, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrf },
    body: JSON.stringify({ source, datos: datos() }),
  });
  const html = await response.text();
  status(`Bloque renderizado por el servidor en ${Math.round(performance.now() - started)} ms.`);
  return html;
}

const fieldsOf = (key) => MODELS.find((m) => m.key === key)?.fields || [];
const options = (items) => [{ id: "", name: "—" }, ...items];

// Jinja del contenido de la lista. Solo usa claves que vienen de los modelos del sitio.
function listJinja(p) {
  if (!p.modelo) return "<p>Elige un modelo en Propiedades.</p>";
  const fields = fieldsOf(p.modelo);
  const known = (k) => fields.some((f) => f.key === k);
  const args = [JSON.stringify(p.modelo)];
  if (known(p.filtro)) args.push(`${p.filtro}=True`);
  const orderKey = p.orden.replace(/^-/, "");
  if (known(orderKey)) args.push(`orden=${JSON.stringify(p.orden)}`);
  const limit = parseInt(p.limite, 10);
  if (limit > 0) args.push(`limite=${limit}`);
  const title = known(p.titulo) ? p.titulo : "slug";
  const second = fields.find((f) => f.key === p.secundario);
  const secondExpr = second && (second.type === "number" ? `p.${second.key} | moneda` : `p.${second.key}`);
  return [
    `{% for p in entradas(${args.join(", ")}) %}`,
    `<article class="cms-lista__item">`,
    `<h3>{{ p.${title} }}</h3>`,
    secondExpr ? `<p>{{ ${secondExpr} }}</p>` : "",
    `<a href="{{ url_entrada(p) }}">Ver detalle</a>`,
    `</article>`,
    `{% endfor %}`,
  ].filter(Boolean).join("\n");
}

const PROPS = ["modelo", "filtro", "orden", "limite", "titulo", "secundario"];

function listPlugin(editor) {
  editor.Components.addType("cms-lista", {
    model: {
      defaults: {
        tagName: "section",
        name: "Lista de entradas",
        attributes: { class: "cms-lista" },
        droppable: false,
        editable: false,
        modelo: MODELS[0]?.key || "",
        filtro: "",
        orden: "",
        limite: 3,
        titulo: "",
        secundario: "",
        traits: [
          { type: "select", name: "modelo", label: "Modelo", changeProp: true, options: MODELS.map((m) => ({ id: m.key, name: m.name })) },
          { type: "select", name: "filtro", label: "Solo si (booleano)", changeProp: true, options: [] },
          { type: "select", name: "orden", label: "Orden", changeProp: true, options: [] },
          { type: "number", name: "limite", label: "Límite", changeProp: true, min: 1, max: 50 },
          { type: "select", name: "titulo", label: "Campo del título", changeProp: true, options: [] },
          { type: "select", name: "secundario", label: "Campo secundario", changeProp: true, options: [] },
        ],
      },
      init() {
        this.refreshOptions();
        this.on("change:modelo", this.refreshOptions);
        this.on(PROPS.map((p) => `change:${p}`).join(" "), () => this.trigger("cms:changed"));
      },
      refreshOptions() {
        const fields = fieldsOf(this.get("modelo"));
        const pick = (pred) => fields.filter(pred).map((f) => ({ id: f.key, name: f.title }));
        this.getTrait("filtro").set("options", options(pick((f) => f.type === "bool")));
        this.getTrait("orden").set("options", options(fields.flatMap((f) => [
          { id: f.key, name: `${f.title} ↑` },
          { id: `-${f.key}`, name: `${f.title} ↓` },
        ])));
        this.getTrait("titulo").set("options", options(pick((f) => ["text", "slug"].includes(f.type))));
        this.getTrait("secundario").set("options", options(pick((f) => ["text", "number", "date"].includes(f.type))));
      },
      jinja() {
        return listJinja(Object.fromEntries(PROPS.map((p) => [p, String(this.get(p) ?? "")])));
      },
      toHTML() {
        return `<section class="cms-lista">\n${this.jinja()}\n</section>`;
      },
    },
    view: {
      init() {
        this.seq = 0;
        this.listenTo(this.model, "cms:changed", this.refresh);
      },
      onRender() {
        this.refresh();
      },
      refresh() {
        // Varios cambios seguidos (por ejemplo, set() con seis propiedades) se agrupan en una
        // sola petición, y una respuesta vieja nunca reemplaza a una más nueva.
        clearTimeout(this.timer);
        this.timer = setTimeout(async () => {
          const seq = ++this.seq;
          const html = await renderFragment(this.model.jinja());
          if (seq === this.seq) this.el.innerHTML = html;
        }, 150);
      },
    },
  });

  editor.Blocks.add("cms-lista", {
    label: "Lista de entradas",
    category: "Dinámicos",
    content: { type: "cms-lista" },
  });
  editor.Blocks.add("texto", {
    label: "Texto",
    category: "Básicos",
    content: { type: "text", tagName: "p", content: "Escribe aquí un párrafo." },
  });
  editor.Blocks.add("titulo", {
    label: "Título",
    category: "Básicos",
    content: { type: "text", tagName: "h2", content: "Título de la sección" },
  });
}

const editor = grapesjs.init({
  container: "#v-editor",
  height: "70vh",
  fromElement: false,
  // Por defecto GrapesJS carga Font Awesome desde un CDN y envía telemetría a app.grapesjs.com.
  cssIcons: "",
  telemetry: false,
  storageManager: { type: "local", autosave: true, stepsBeforeSave: 1, options: { local: { key: cfg.key } } },
  panels: { defaults: [] },
  blockManager: { appendTo: "#v-blocks" },
  traitManager: { appendTo: "#v-traits" },
  selectorManager: { componentFirst: true },
  undoManager: { maximumStackLength: 100 },
  deviceManager: {
    devices: [
      { id: "Escritorio", name: "Escritorio", width: "" },
      { id: "Tableta", name: "Tableta", width: "768px" },
      { id: "Móvil", name: "Móvil", width: "390px" },
    ],
  },
  plugins: [listPlugin],
});
window.studioEditor = editor; // para las pruebas con Playwright

document.getElementById("v-datos").addEventListener("change", () =>
  editor.getWrapper().find("section.cms-lista").forEach((c) => c.trigger("cms:changed")),
);
document.getElementById("v-undo").addEventListener("click", () => editor.UndoManager.undo());
document.getElementById("v-redo").addEventListener("click", () => editor.UndoManager.redo());
document.querySelectorAll("[data-device]").forEach((button) =>
  button.addEventListener("click", () => {
    editor.setDevice(button.dataset.device);
    document.querySelectorAll("[data-device]").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
  }),
);

// El código de la plantilla: HTML y Jinja de los componentes más su CSS (sin interpretar como Jinja).
export function exportSource() {
  const html = editor.getHtml().replace(/^<body[^>]*>|<\/body>$/g, "").trim();
  const css = editor.getCss({ avoidProtected: true }).trim();
  return css ? `<style>{% raw %}${css}{% endraw %}</style>\n${html}\n` : `${html}\n`;
}
window.studioExportSource = exportSource;

document.getElementById("v-save").addEventListener("click", async () => {
  const response = await fetch(cfg.save, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrf },
    body: JSON.stringify({ source: exportSource() }),
  });
  const { errors } = await response.json();
  status(errors.length ? `No se guardó: ${errors.map((e) => e.message).join(" · ")}` : "Guardado: la plantilla quedó en modo visual.");
});
