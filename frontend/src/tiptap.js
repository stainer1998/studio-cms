// Isla de texto enriquecido (RF-11): convierte cada <textarea data-rich> en un editor Tiptap.
// El textarea sigue siendo el campo del formulario; sin JS se edita el HTML directamente.
// El servidor sanitiza con nh3, así que aquí solo se ofrecen las marcas de su lista blanca.
import { Editor } from "@tiptap/core";
import Image from "@tiptap/extension-image";
import StarterKit from "@tiptap/starter-kit";

const BUTTONS = [
  { label: "Negrita", text: "B", run: (c) => c.toggleBold(), active: "bold" },
  { label: "Cursiva", text: "I", run: (c) => c.toggleItalic(), active: "italic" },
  { label: "Título", text: "H2", run: (c) => c.toggleHeading({ level: 2 }), active: ["heading", { level: 2 }] },
  { label: "Subtítulo", text: "H3", run: (c) => c.toggleHeading({ level: 3 }), active: ["heading", { level: 3 }] },
  { label: "Lista", text: "•", run: (c) => c.toggleBulletList(), active: "bulletList" },
  { label: "Lista numerada", text: "1.", run: (c) => c.toggleOrderedList(), active: "orderedList" },
  { label: "Cita", text: "“", run: (c) => c.toggleBlockquote(), active: "blockquote" },
  { label: "Enlace", text: "🔗", run: link, active: "link" },
  { label: "Imagen", text: "🖼", run: image },
];

function link(chain, editor) {
  const previous = editor.getAttributes("link").href || "";
  const href = window.prompt("Dirección del enlace (vacío para quitarlo)", previous);
  if (href === null) return chain;
  return href ? chain.extendMarkRange("link").setLink({ href }) : chain.extendMarkRange("link").unsetLink();
}

function image(chain) {
  // ponytail: imagen por URL; el selector de la biblioteca de Medios llega en H3.
  const src = window.prompt("Dirección de la imagen");
  if (!src) return chain;
  const alt = window.prompt("Texto alternativo (describe la imagen)") || "";
  return chain.setImage({ src, alt });
}

function mount(textarea) {
  const wrapper = document.createElement("div");
  wrapper.className = "rich";
  const toolbar = document.createElement("div");
  toolbar.className = "rich-toolbar";
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "Formato de texto");
  const area = document.createElement("div");
  wrapper.append(toolbar, area);
  textarea.after(wrapper);
  textarea.hidden = true;

  const label = document.querySelector(`label[for="${textarea.id}"]`);
  const editor = new Editor({
    element: area,
    injectCSS: false, // la CSP del Studio no permite estilos en línea; están en studio.css
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3, 4] },
        code: false,
        codeBlock: false,
        strike: false,
        underline: false,
        horizontalRule: false,
        link: { openOnClick: false, autolink: true, defaultProtocol: "https" },
      }),
      Image,
    ],
    content: textarea.value,
    editorProps: {
      attributes: {
        class: "rich-content",
        role: "textbox",
        "aria-multiline": "true",
        ...(label ? { "aria-label": label.textContent.trim() } : {}),
        ...Object.fromEntries(
          ["aria-describedby", "aria-invalid", "aria-required"]
            .filter((a) => textarea.hasAttribute(a))
            .map((a) => [a, textarea.getAttribute(a)]),
        ),
      },
    },
    onUpdate: () => {
      textarea.value = editor.isEmpty ? "" : editor.getHTML();
    },
  });
  if (label) label.addEventListener("click", () => editor.commands.focus());

  const buttons = BUTTONS.map((b) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-icon";
    button.textContent = b.text;
    button.setAttribute("aria-label", b.label);
    button.title = b.label;
    button.addEventListener("click", () => b.run(editor.chain().focus(), editor).run());
    toolbar.append(button);
    return [button, b];
  });
  const refresh = () => {
    for (const [button, b] of buttons) {
      if (b.active) {
        const [name, attrs] = [].concat(b.active);
        button.setAttribute("aria-pressed", String(editor.isActive(name, attrs)));
      }
    }
  };
  editor.on("selectionUpdate", refresh);
  editor.on("transaction", refresh);
  refresh();
}

document.querySelectorAll("textarea[data-rich]").forEach(mount);
