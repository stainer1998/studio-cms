// Isla del editor de plantillas (RF-17): Monaco con Jinja2 sobre HTML, autocompletado de las
// funciones y filtros del CMS, errores marcados en su línea y vista previa en vivo.
// El <textarea data-monaco> sigue siendo el campo del formulario; sin JS se edita ahí mismo.
import * as monaco from "monaco-editor/editor/editor.api";
import "monaco-editor/features/register.all";
import { conf, language } from "monaco-editor/languages/definitions/twig/twig";

const script = document.currentScript;
// Worker desde el propio Studio: con getWorkerUrl Monaco lo envuelve en un blob: que la CSP bloquea.
self.MonacoEnvironment = { getWorker: () => new Worker(script.dataset.worker) };

// Partimos de la definición de Twig: misma sintaxis de etiquetas que Jinja2 y resalta el HTML.
monaco.languages.register({ id: "jinja", extensions: [".html"] });
// Sin cierre automático de {% %}, {{ }} y {# #}: al escribir la etiqueta completa a mano
// los cierres se acumulaban al final de la línea (` %} %} }}`).
monaco.languages.setLanguageConfiguration("jinja", {
  ...conf,
  autoClosingPairs: conf.autoClosingPairs.filter((pair) => !pair.open.startsWith("{")),
});
monaco.languages.setMonarchTokensProvider("jinja", language);

const DOCS = {
  entradas: ["entradas(${1:\"modelo\"}${2:, limite=6})", "entradas(modelo, **filtros, orden=None, limite=None): entradas listas para exportar. Filtros por igualdad (destacado=True); orden=\"-precio\" invierte."],
  entrada: ["entrada(${1:\"modelo\"}, ${2:slug})", "entrada(modelo, slug): una entrada lista para exportar, o None."],
  url_entrada: ["url_entrada(${1:p})", "url_entrada(entrada): URL de la entrada según las rutas del sitio."],
  media_url: ["media_url(${1:p.foto}, ${2:\"mediana\"})", "media_url(medio, variante=\"mediana\"): URL del archivo. Variantes: miniatura, mediana, grande, original."],
  moneda: ["moneda", "Pesos chilenos sin decimales: 3500 → $3.500"],
  fecha: ["fecha${1:(\"largo\")}", "Fecha: 13-10-2026, o con \"largo\": 13 de octubre de 2026"],
};

function registerCompletions(cms) {
  const { CompletionItemKind: Kind, CompletionItemInsertTextRule: Rule } = monaco.languages;
  monaco.languages.registerCompletionItemProvider("jinja", {
    triggerCharacters: ["|", "(", '"', "'", " "],
    provideCompletionItems(model, position) {
      const line = model.getLineContent(position.lineNumber).slice(0, position.column - 1);
      const word = model.getWordUntilPosition(position);
      const range = new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn);
      const item = (name, kind) => ({
        label: name,
        kind,
        insertText: DOCS[name][0],
        insertTextRules: Rule.InsertAsSnippet,
        documentation: DOCS[name][1],
        range,
      });
      // Dentro de entradas(" o entrada(" se sugieren los modelos del sitio.
      if (/entradas?\(\s*["'][\w-]*$/.test(line)) {
        return { suggestions: cms.models.map((m) => ({ label: m, kind: Kind.Class, insertText: m, range })) };
      }
      if (/\|\s*\w*$/.test(line)) {
        return { suggestions: cms.filters.map((f) => item(f, Kind.Function)) };
      }
      if (/(\{\{|\{%)[^}]*$/.test(line)) {
        return { suggestions: cms.functions.map((f) => item(f, Kind.Function)) };
      }
      return { suggestions: [] };
    },
  });
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function mount(textarea) {
  const form = textarea.form;
  const csrf = form.querySelector('input[name="csrf_token"]').value;
  const readOnly = textarea.readOnly;
  const status = document.getElementById("t-errors");
  const previewForm = document.getElementById("p-form");
  const previewSource = document.getElementById("p-source");

  const container = document.createElement("div");
  container.className = "monaco-host";
  textarea.after(container);
  textarea.hidden = true;

  const editor = monaco.editor.create(container, {
    value: textarea.value,
    language: "jinja",
    readOnly,
    readOnlyMessage: { value: "Plantilla en modo visual: el código generado es de solo lectura." },
    automaticLayout: true,
    fixedOverflowWidgets: true, // sugerencias y ayudas no quedan recortadas por la tarjeta
    minimap: { enabled: false },
    fontSize: 13,
    tabSize: 2,
    wordWrap: "on",
    scrollBeyondLastLine: false,
    ariaLabel: document.querySelector(`label[for="${textarea.id}"]`)?.textContent.trim(),
  });
  const model = editor.getModel();

  const showErrors = (errors) => {
    monaco.editor.setModelMarkers(
      model,
      "jinja",
      errors.map((e) => {
        const line = Math.min(e.line || 1, model.getLineCount());
        return {
          severity: monaco.MarkerSeverity.Error,
          message: e.message,
          startLineNumber: line,
          endLineNumber: line,
          startColumn: 1,
          endColumn: model.getLineMaxColumn(line),
        };
      }),
    );
    status.textContent = errors.length ? errors.map((e) => e.message).join(" · ") : "Sin errores";
    status.classList.toggle("error", errors.length > 0);
  };

  const validate = debounce(async () => {
    const response = await fetch(textarea.dataset.validate, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ source: model.getValue(), path: textarea.dataset.path }),
    });
    if (response.ok) showErrors((await response.json()).errors);
  }, 400);

  const refreshPreview = debounce(() => previewForm.requestSubmit(), 800);

  editor.onDidChangeModelContent(() => {
    textarea.value = model.getValue();
    previewSource.value = textarea.value;
    validate();
    refreshPreview();
  });
  // Ctrl+S guarda, como en cualquier editor.
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
    if (!readOnly) form.requestSubmit();
  });
  document.getElementById("p-datos")?.addEventListener("change", () => previewForm.requestSubmit());
  previewForm.requestSubmit();
  if (!readOnly) validate();
}

const textarea = document.querySelector("textarea[data-monaco]");
if (textarea) {
  registerCompletions(JSON.parse(textarea.dataset.cms));
  mount(textarea);
}
