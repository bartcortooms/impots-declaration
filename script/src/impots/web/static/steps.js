/* Multi-step navigation for the declaration report.
 *
 * Top-level steps are configured below, organized into phases for the progress
 * bar. Some steps have sub-steps (each .titre-page or .abt-page child becomes
 * a sub-step). The single ◂ Précédent / Suivant ▸ pair advances through
 * sub-steps first, then to the next top-level step.
 *
 * URL hash:
 *   #step-id            → top-level step (sub-step 0 if present)
 *   #step-id/2          → top-level step, 1-based sub-step
 *
 * Keyboard:
 *   ← / →               → previous / next
 *   1–9, 0              → jump to step 1–9 / 10
 *   ?                   → toggle legend
 *   Esc                 → close legend
 */
(function () {
  "use strict";

  const stepConfig = [
    { id: "rubriques",                short: "Rubriques",   label: "Sélection des rubriques (2042)",                phase: "Préparation" },
    { id: "annexes",                  short: "Annexes",     label: "Sélection des annexes (2047 / 2074 / ABT)",     phase: "Préparation" },
    { id: "form-2047-gateway",        short: "2047 prép.",  label: "2047 — Préparation (Votre déclaration concerne)", phase: "2047" },
    { id: "form-2047",                short: "2047 §200",   label: "2047 — Dividendes (section 200)",               phase: "2047" },
    { id: "form-2074-gateway",        short: "2074 prép.",  label: "2074 — Préparation (Cas suivants)",             phase: "2074" },
    { id: "form-2074",                short: "2074 §510",   label: "2074 — Cessions (cadre 5 § 510)", subSelector: ".titre-page", phase: "2074" },
    { id: "fiche-2074-abt-gateway",   short: "ABT prép.",   label: "2074-ABT — Préparation (Nombre d'opérations)",  phase: "ABT" },
    { id: "fiche-2074-abt",           short: "ABT fiche",   label: "2074-ABT — Fiche par titre", subSelector: ".abt-page", phase: "ABT" },
    { id: "bloc-1133",                short: "Bloc 1133",   label: "2074 — Compensation (cadre 11 bloc 1133)",      phase: "2074" },
    { id: "audit",                    short: "Audit",       label: "Audit & vérifications",                          phase: "Audit" },
  ];

  // Phase order matters for the grouped progress bar.
  const phaseOrder = ["Préparation", "2047", "2074", "ABT", "Audit"];

  function $(s, ctx) { return (ctx || document).querySelector(s); }
  function $$(s, ctx) { return Array.from((ctx || document).querySelectorAll(s)); }

  function getSubElements(step) {
    if (!step.subSelector) return [];
    const root = document.getElementById(step.id);
    return root ? $$(step.subSelector, root) : [];
  }

  function parseHash() {
    const hash = window.location.hash.slice(1);
    if (!hash) return { stepIdx: 0, subIdx: 0 };
    const [id, subStr] = hash.split("/");
    const stepIdx = stepConfig.findIndex(s => s.id === id);
    if (stepIdx < 0) return { stepIdx: 0, subIdx: 0 };
    const subIdx = subStr ? Math.max(0, parseInt(subStr, 10) - 1) : 0;
    return { stepIdx, subIdx };
  }

  function buildHash(stepIdx, subIdx) {
    const step = stepConfig[stepIdx];
    const subs = getSubElements(step);
    if (subs.length > 1 && subIdx > 0) {
      return "#" + step.id + "/" + (subIdx + 1);
    }
    return "#" + step.id;
  }

  function navigate(stepIdx, subIdx, push = true) {
    stepIdx = Math.max(0, Math.min(stepConfig.length - 1, stepIdx));
    const subs = getSubElements(stepConfig[stepIdx]);
    subIdx = Math.max(0, Math.min(Math.max(0, subs.length - 1), subIdx));
    const newHash = buildHash(stepIdx, subIdx);
    if (push) {
      history.pushState({ stepIdx, subIdx }, "", newHash);
    } else {
      history.replaceState({ stepIdx, subIdx }, "", newHash);
    }
    render();
    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  }

  function advanceForward() {
    const { stepIdx, subIdx } = parseHash();
    const subs = getSubElements(stepConfig[stepIdx]);
    if (subs.length && subIdx + 1 < subs.length) {
      navigate(stepIdx, subIdx + 1);
    } else if (stepIdx + 1 < stepConfig.length) {
      navigate(stepIdx + 1, 0);
    }
  }

  function advanceBackward() {
    const { stepIdx, subIdx } = parseHash();
    if (subIdx > 0) {
      navigate(stepIdx, subIdx - 1);
    } else if (stepIdx > 0) {
      const prevSubs = getSubElements(stepConfig[stepIdx - 1]);
      navigate(stepIdx - 1, prevSubs.length ? prevSubs.length - 1 : 0);
    }
  }

  function render() {
    const { stepIdx, subIdx } = parseHash();
    const currentStep = stepConfig[stepIdx];

    stepConfig.forEach((s) => {
      const el = document.getElementById(s.id);
      if (!el) return;
      el.classList.toggle("step-active", s.id === currentStep.id);
    });

    const allSubElements = stepConfig
      .filter(s => s.subSelector)
      .flatMap(s => getSubElements(s));
    allSubElements.forEach(el => {
      el.classList.remove("sub-active");
    });
    const subs = getSubElements(currentStep);
    if (subs.length > 0 && subs[subIdx]) {
      subs.forEach(el => el.classList.add("sub-hidden"));
      subs[subIdx].classList.remove("sub-hidden");
      subs[subIdx].classList.add("sub-active");
    }

    $$(".progress-step").forEach((el) => {
      const i = parseInt(el.dataset.idx, 10);
      el.classList.toggle("active", i === stepIdx);
      el.classList.toggle("done", i < stepIdx);
    });
    $$(".phase-group").forEach((el) => {
      const phase = el.dataset.phase;
      const indices = stepConfig
        .map((s, i) => s.phase === phase ? i : -1)
        .filter(i => i >= 0);
      const isActive = indices.includes(stepIdx);
      const allDone = indices.every(i => i < stepIdx);
      el.classList.toggle("active", isActive);
      el.classList.toggle("done", allDone);
    });

    const isFirst = stepIdx === 0 && subIdx === 0;
    const isLast = stepIdx === stepConfig.length - 1 && (!subs.length || subIdx === subs.length - 1);
    $$(".step-nav").forEach((nav) => {
      const prevBtn = nav.querySelector(".prev");
      const nextBtn = nav.querySelector(".next");
      if (prevBtn) {
        prevBtn.disabled = isFirst;
        prevBtn.querySelector(".target").textContent = prevTargetLabel(stepIdx, subIdx);
      }
      if (nextBtn) {
        nextBtn.disabled = isLast;
        // Hide the Suivant button entirely on the terminal step — there's
        // nothing to advance to, so even a disabled placeholder is confusing.
        nextBtn.style.visibility = isLast ? "hidden" : "";
        nextBtn.querySelector(".target").textContent = nextTargetLabel(stepIdx, subIdx);
      }
      const counter = nav.querySelector(".counter");
      if (counter) {
        let text = `Étape ${stepIdx + 1} / ${stepConfig.length}`;
        if (subs.length > 1) {
          text += `  ·  Titre ${subIdx + 1} / ${subs.length}`;
        }
        counter.textContent = text;
      }
    });

    renderSubIndicator(currentStep, subIdx, subs);
  }

  function prevTargetLabel(stepIdx, subIdx) {
    if (subIdx > 0) return "Titre " + subIdx;
    if (stepIdx > 0) return stepConfig[stepIdx - 1].label;
    return "";
  }

  function nextTargetLabel(stepIdx, subIdx) {
    const subs = getSubElements(stepConfig[stepIdx]);
    if (subs.length && subIdx + 1 < subs.length) return "Titre " + (subIdx + 2);
    if (stepIdx + 1 < stepConfig.length) return stepConfig[stepIdx + 1].label;
    return "";
  }

  function renderSubIndicator(step, subIdx, subs) {
    const root = document.getElementById(step.id);
    if (!root) return;
    let bar = root.querySelector(":scope > .sub-progress");
    if (subs.length <= 1) {
      if (bar) bar.remove();
      return;
    }
    if (!bar) {
      bar = document.createElement("nav");
      bar.className = "sub-progress";
      bar.setAttribute("aria-label", "Sous-étapes par titre");
      const heading = root.querySelector("h2, h3");
      if (heading && heading.nextSibling) {
        heading.parentNode.insertBefore(bar, heading.nextSibling);
      } else {
        root.prepend(bar);
      }
    }
    bar.innerHTML = "";
    const label = document.createElement("span");
    label.className = "sub-progress-label";
    label.textContent = `Titre ${subIdx + 1} / ${subs.length}`;
    bar.appendChild(label);
    subs.forEach((subEl, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sub-step" + (i === subIdx ? " active" : "");
      btn.textContent = "Titre " + (i + 1);
      const summary = subEl.dataset.summary;
      if (summary) btn.title = summary;
      btn.addEventListener("click", () => {
        const { stepIdx } = parseHash();
        navigate(stepIdx, i);
      });
      bar.appendChild(btn);
    });
  }

  function buildProgressBar() {
    const bar = document.createElement("nav");
    bar.className = "progress-bar";
    bar.setAttribute("aria-label", "Étapes de la déclaration");

    phaseOrder.forEach((phaseName) => {
      const group = document.createElement("div");
      group.className = "phase-group";
      group.dataset.phase = phaseName;

      const label = document.createElement("div");
      label.className = "phase-label";
      label.textContent = phaseName;
      group.appendChild(label);

      const stepsRow = document.createElement("div");
      stepsRow.className = "phase-steps";

      stepConfig.forEach((s, i) => {
        if (s.phase !== phaseName) return;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "progress-step";
        btn.dataset.idx = i;
        btn.innerHTML = `<span class="step-num">${i + 1}</span><span class="step-label">${s.short}</span>`;
        btn.title = s.label + " (touche " + ((i + 1) % 10) + ")";
        btn.addEventListener("click", () => navigate(i, 0));
        stepsRow.appendChild(btn);
      });

      group.appendChild(stepsRow);
      bar.appendChild(group);
    });

    return bar;
  }

  function buildStepNav() {
    const nav = document.createElement("div");
    nav.className = "step-nav";
    nav.innerHTML = `
      <button type="button" class="prev">◂ Précédent <span class="target"></span></button>
      <span class="counter"></span>
      <button type="button" class="next"><span class="target"></span> Suivant ▸</button>
    `;
    nav.querySelector(".prev").addEventListener("click", advanceBackward);
    nav.querySelector(".next").addEventListener("click", advanceForward);
    return nav;
  }

  function handleKeyboard(event) {
    // Ignore when typing in an input
    const target = event.target;
    if (target && typeof target.matches === "function" && target.matches("input, textarea, select")) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;

    if (event.key === "ArrowLeft") {
      advanceBackward();
      event.preventDefault();
    } else if (event.key === "ArrowRight") {
      advanceForward();
      event.preventDefault();
    } else if (event.key >= "0" && event.key <= "9") {
      const idx = event.key === "0" ? 9 : parseInt(event.key, 10) - 1;
      if (idx >= 0 && idx < stepConfig.length) {
        navigate(idx, 0);
        event.preventDefault();
      }
    }
  }

  function collapseNonApplicableRows() {
    // On rubriques + annexes pages: hide rows where the user has nothing
    // to do (state-unchecked) behind a small "show non-applicable rows"
    // toggle. Cuts 70-80% of the visible row count.
    document.querySelectorAll(".rubriques-list, .cas-list").forEach((list) => {
      const inactive = list.querySelectorAll(".cas-row.state-unchecked");
      if (inactive.length < 3) return; // not worth collapsing
      inactive.forEach((row) => row.classList.add("collapsed-row"));
      list.classList.add("has-collapsed");

      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "collapse-toggle";
      toggle.innerHTML = `<span class="toggle-arrow">▸</span> Afficher les ${inactive.length} rubriques non applicables`;
      toggle.addEventListener("click", () => {
        const expanded = list.classList.toggle("show-collapsed");
        toggle.querySelector(".toggle-arrow").textContent = expanded ? "▾" : "▸";
        toggle.firstChild.nextSibling.textContent = expanded
          ? ` Masquer les ${inactive.length} rubriques non applicables`
          : ` Afficher les ${inactive.length} rubriques non applicables`;
      });
      list.parentNode.insertBefore(toggle, list);
    });
  }

  function init() {
    const main = $("main");
    if (!main) return;

    main.prepend(buildProgressBar());
    collapseNonApplicableRows();

    stepConfig.forEach((s) => {
      const el = document.getElementById(s.id);
      if (!el) return;
      el.classList.add("step");
      el.appendChild(buildStepNav());
    });

    window.addEventListener("hashchange", () => render());
    window.addEventListener("popstate", () => render());
    document.addEventListener("keydown", handleKeyboard);

    navigate(parseHash().stepIdx, parseHash().subIdx, /*push=*/false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
