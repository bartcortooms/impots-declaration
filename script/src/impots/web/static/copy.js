/* Copy-to-clipboard for tax declaration values.
 *
 * For every .form-cell.source / .form-cell.computed, wraps the cell in a
 * .cell-with-copy container and adds a small ⧉ button. Wrapping (vs. just
 * appending the button next to the cell) keeps each pair as a single grid
 * item so CSS grid layouts don't get pushed out of alignment.
 */
(function () {
  "use strict";

  const NUMERIC_RE = /^[\s\d.,+\-€%]+$/;

  function cleanValue(text) {
    text = text.trim();
    if (NUMERIC_RE.test(text)) {
      // Strip thousand-separator whitespace from numeric values.
      return text.replace(/\s/g, "");
    }
    return text;
  }

  function showCopied(button) {
    const original = button.textContent;
    button.textContent = "✓";
    button.classList.add("copied");
    setTimeout(() => {
      button.textContent = original;
      button.classList.remove("copied");
    }, 1200);
  }

  async function handleCopyClick(event) {
    const button = event.currentTarget;
    const cell = button.parentElement.querySelector(".form-cell");
    if (!cell) return;
    const raw = cell.dataset.copy || cell.textContent;
    const value = cleanValue(raw);
    try {
      await navigator.clipboard.writeText(value);
      showCopied(button);
    } catch (err) {
      // Fallback: select the cell text so the user can copy manually.
      const range = document.createRange();
      range.selectNodeContents(cell);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      button.textContent = "?";
      setTimeout(() => { button.textContent = "⧉"; }, 1500);
    }
  }

  function addButtons() {
    const selector = ".form-cell.source, .form-cell.computed";
    document.querySelectorAll(selector).forEach((cell) => {
      if (!cell.textContent.trim()) return;
      // Don't wrap twice
      if (cell.parentElement.classList.contains("cell-with-copy")) return;

      const wrapper = document.createElement("span");
      wrapper.className = "cell-with-copy";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-btn";
      btn.title = "Copier la valeur";
      btn.textContent = "⧉";
      btn.addEventListener("click", handleCopyClick);

      // Insert wrapper in cell's place, move cell inside wrapper, append button.
      cell.parentNode.insertBefore(wrapper, cell);
      wrapper.appendChild(cell);
      wrapper.appendChild(btn);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", addButtons);
  } else {
    addButtons();
  }
})();
