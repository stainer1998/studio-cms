// Isla de Medios: subida por arrastrar y soltar (RF-13) y selector de imágenes, que usan
// los campos imagen de las entradas y el botón de imagen de Tiptap (window.studioPickImage).
const PICKER_URL = document.currentScript.dataset.picker;

const dropzone = document.querySelector("[data-dropzone]");
if (dropzone) {
  const input = dropzone.querySelector('input[type="file"]');
  input.addEventListener("change", () => input.files.length && dropzone.requestSubmit());
  for (const type of ["dragenter", "dragover"]) {
    dropzone.addEventListener(type, (e) => {
      e.preventDefault();
      dropzone.classList.add("is-over");
    });
  }
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-over"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-over");
    input.files = e.dataTransfer.files;
    dropzone.requestSubmit();
  });
}

// La etiqueta «Subir archivos» de la cabecera también responde al teclado.
document.querySelectorAll("[data-file-trigger]").forEach((label) => {
  label.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      document.getElementById(label.htmlFor).click();
    }
  });
});

// Abre el selector y resuelve con {pickId, alt, src, thumb} o null si se cierra sin elegir.
window.studioPickImage = async function () {
  let dialog = document.getElementById("media-picker");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "media-picker";
    dialog.className = "picker card";
    dialog.setAttribute("aria-labelledby", "media-picker-title");
    document.body.append(dialog);
  }
  const response = await fetch(PICKER_URL, { headers: { "HX-Request": "true" } });
  dialog.innerHTML =
    '<div class="card-head"><h2 id="media-picker-title">Elegir imagen</h2>' +
    '<button type="button" class="btn" data-close>Cerrar</button></div>' +
    (await response.text());
  window.htmx?.process(dialog);
  dialog.showModal();
  return new Promise((resolve) => {
    const onClick = (e) => {
      const card = e.target.closest("[data-pick-id]");
      if (card) {
        resolve({ ...card.dataset });
        dialog.close();
      } else if (e.target.closest("[data-close]")) {
        dialog.close();
      }
    };
    dialog.addEventListener("click", onClick);
    dialog.addEventListener(
      "close",
      () => {
        dialog.removeEventListener("click", onClick);
        resolve(null);
      },
      { once: true },
    );
  });
};

document.querySelectorAll("[data-image-field]").forEach((field) => {
  const input = field.querySelector('input[type="hidden"]');
  const preview = field.querySelector("[data-preview]");
  const clear = field.querySelector("[data-clear]");
  field.querySelector("[data-pick]").addEventListener("click", async () => {
    const media = await window.studioPickImage();
    if (!media) return;
    input.value = media.pickId;
    const img = document.createElement("img");
    img.src = media.thumb;
    img.alt = media.alt;
    preview.replaceChildren(img);
    clear.hidden = false;
  });
  clear.addEventListener("click", () => {
    input.value = "";
    preview.textContent = "Sin imagen";
    clear.hidden = true;
  });
});
