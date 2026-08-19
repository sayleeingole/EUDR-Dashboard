// Warn before leaving a page with an unsaved narrative (08 §3.4 — replaces
// Streamlit's autosave, which 08a rejected as an audit-log flood).
(function () {
  let dirty = false;
  document.addEventListener("input", function (e) {
    if (e.target.matches("textarea[data-guard-unsaved]")) dirty = true;
  });
  document.addEventListener("submit", function () { dirty = false; });
  window.addEventListener("beforeunload", function (e) {
    if (!dirty) return;
    e.preventDefault();
    e.returnValue = "";
  });
})();

// Evidence queue undo-toast timer.
(function () {
  const toast = document.getElementById("undo-toast");
  if (toast) {
    const timeout = parseInt(toast.dataset.timeout || "5000", 10);
    setTimeout(function () { toast.remove(); }, timeout);
  }
})();

// Excel-style per-column table filtering (any table.data-table[data-filterable],
// e.g. the evidence table). Client-side — every row is already server-rendered.
(function () {
  const table = document.querySelector("table.data-table[data-filterable]");
  if (!table) return;
  const filters = Array.from(table.querySelectorAll(".col-filter"));
  const rows = Array.from(table.querySelectorAll("tbody tr"));
  const empty = document.getElementById("filter-empty");
  function apply() {
    let visible = 0;
    rows.forEach(function (row) {
      const match = filters.every(function (f) {
        const val = f.value.trim().toLowerCase();
        if (!val) return true;
        const cell = (row.dataset[f.dataset.col] || "").toLowerCase();
        return f.tagName === "SELECT"
          ? cell.split(",").map(function (s) { return s.trim(); }).includes(val)
          : cell.includes(val);
      });
      row.style.display = match ? "" : "none";
      if (match) visible++;
    });
    if (empty) empty.style.display = visible === 0 ? "" : "none";
  }
  filters.forEach(function (f) {
    f.addEventListener(f.tagName === "SELECT" ? "change" : "input", apply);
  });
})();

// Evidence split view: filters, bulk-select, J/K nav, pane-swap sync — same
// pattern as the Legal requirements split view below.
(function () {
  const list = document.getElementById("ev-list");
  if (!list) return;
  const filters = Array.from(document.querySelectorAll("#evidence-filters .ev-filter"));
  const rows = Array.from(list.querySelectorAll(".ev-row"));
  const groups = Array.from(list.querySelectorAll(".ev-group"));
  const empty = document.getElementById("ev-filter-empty");

  function apply() {
    let visible = 0;
    rows.forEach(function (row) {
      const match = filters.every(function (f) {
        const val = f.value.trim().toLowerCase();
        if (!val) return true;
        const cell = (row.dataset[f.dataset.col] || "").toLowerCase();
        return f.tagName === "SELECT" ? cell === val : cell.includes(val);
      });
      row.style.display = match ? "" : "none";
      if (match) visible++;
    });
    groups.forEach(function (g) {
      const any = Array.from(g.querySelectorAll(".ev-row")).some(function (r) { return r.style.display !== "none"; });
      g.style.display = any ? "" : "none";
    });
    if (empty) empty.style.display = visible === 0 ? "" : "none";
  }
  filters.forEach(function (f) {
    f.addEventListener(f.tagName === "SELECT" ? "change" : "input", apply);
  });

  // Summary links ("12 from an untrusted source") set the matching filter.
  document.querySelectorAll(".ev-summary-link").forEach(function (link) {
    link.addEventListener("click", function (e) {
      e.preventDefault();
      const flagSel = document.querySelector('.ev-filter[data-col="flag"]');
      const confSel = document.querySelector('.ev-filter[data-col="confidence"]');
      if (link.dataset.filterFlag && flagSel) { flagSel.value = link.dataset.filterFlag; flagSel.dispatchEvent(new Event("change")); }
      if (link.dataset.filterConfidence && confSel) { confSel.value = link.dataset.filterConfidence; confSel.dispatchEvent(new Event("change")); }
    });
  });

  // Bulk-select: enable "Approve selected" only once something is checked;
  // "select all visible" respects the current filters.
  const selectAll = document.getElementById("ev-select-all");
  const approveBtn = document.getElementById("ev-approve-selected");
  function checkboxes() { return Array.from(list.querySelectorAll(".ev-row-select")); }
  function syncApproveBtn() {
    if (approveBtn) approveBtn.disabled = !checkboxes().some(function (c) { return c.checked; });
  }
  list.addEventListener("change", function (e) {
    if (e.target.classList.contains("ev-row-select")) syncApproveBtn();
  });
  if (selectAll) {
    selectAll.addEventListener("change", function () {
      checkboxes().forEach(function (c) {
        if (c.closest(".ev-row").style.display !== "none") c.checked = selectAll.checked;
      });
      syncApproveBtn();
    });
  }

  function visibleRows() {
    return rows.filter(function (r) { return r.style.display !== "none" && r.closest(".ev-group").open; });
  }
  function select(row) {
    rows.forEach(function (r) { r.classList.toggle("selected", r === row); });
    row.scrollIntoView({ block: "nearest" });
  }
  list.addEventListener("click", function (e) {
    if (e.target.closest(".ev-row-check")) return;
    const row = e.target.closest(".ev-row");
    if (row) select(row);
  });
  document.body.addEventListener("htmx:afterSwap", function (e) {
    if (e.detail.target.id !== "ev-pane") return;
    const pane = e.detail.target.querySelector(".ev-pane");
    if (!pane) return;
    const row = document.getElementById("ev-row-" + pane.dataset.id);
    if (row) select(row);
    pane.scrollTop = 0;
  });

  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    if (e.key !== "j" && e.key !== "k") return;
    const vis = visibleRows();
    if (!vis.length) return;
    const cur = vis.findIndex(function (r) { return r.classList.contains("selected"); });
    let next;
    if (e.key === "j") next = vis[Math.min(cur + 1, vis.length - 1)];
    else next = vis[Math.max(cur - 1, 0)];
    if (next && !next.classList.contains("selected")) {
      e.preventDefault();
      next.querySelector(".ev-row-link").click();
    }
  });
})();

// Legal requirements split view: client-side filters over the left list (every
// row is already server-rendered), J/K to walk the list, and keeping the
// selected row highlighted when htmx swaps the reading pane.
(function () {
  const list = document.getElementById("req-list");
  if (!list) return;
  const filters = Array.from(document.querySelectorAll("#legal-filters .req-filter"));
  const rows = Array.from(list.querySelectorAll(".req-row"));
  const groups = Array.from(list.querySelectorAll(".req-group"));
  const empty = document.getElementById("filter-empty");

  function apply() {
    let visible = 0;
    rows.forEach(function (row) {
      const match = filters.every(function (f) {
        const val = f.value.trim().toLowerCase();
        if (!val) return true;
        const cell = (row.dataset[f.dataset.col] || "").toLowerCase();
        return f.tagName === "SELECT"
          ? cell.split(",").map(function (s) { return s.trim(); }).includes(val)
          : cell.includes(val);
      });
      row.style.display = match ? "" : "none";
      if (match) visible++;
    });
    // A group with nothing showing disappears with its header.
    groups.forEach(function (g) {
      const any = Array.from(g.querySelectorAll(".req-row"))
        .some(function (r) { return r.style.display !== "none"; });
      g.style.display = any ? "" : "none";
    });
    if (empty) empty.style.display = visible === 0 ? "" : "none";
  }
  filters.forEach(function (f) {
    f.addEventListener(f.tagName === "SELECT" ? "change" : "input", apply);
  });

  function visibleRows() {
    return rows.filter(function (r) {
      return r.style.display !== "none" && r.closest(".req-group").open;
    });
  }
  function select(row) {
    rows.forEach(function (r) { r.classList.toggle("selected", r === row); });
    row.scrollIntoView({ block: "nearest" });
  }
  // Clicking a row: mark it selected immediately (htmx fills the pane).
  list.addEventListener("click", function (e) {
    const row = e.target.closest(".req-row");
    if (row) select(row);
  });
  // Pane's own Prev/Next links and after a pane swap: sync the highlight.
  document.body.addEventListener("htmx:afterSwap", function (e) {
    if (e.detail.target.id !== "req-pane") return;
    const pane = e.detail.target.querySelector(".req-pane");
    if (!pane) return;
    const row = document.getElementById("req-row-" + pane.dataset.id);
    if (row) select(row);
    // Reset scroll to top of the pane so the reviewer starts at the law.
    pane.scrollTop = 0;
  });

  // J / K move down / up through the visible rows, unless typing in a field.
  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    if (e.key !== "j" && e.key !== "k") return;
    const vis = visibleRows();
    if (!vis.length) return;
    const cur = vis.findIndex(function (r) { return r.classList.contains("selected"); });
    let next;
    if (e.key === "j") next = vis[Math.min(cur + 1, vis.length - 1)];
    else next = vis[Math.max(cur - 1, 0)];
    if (next && !next.classList.contains("selected")) {
      e.preventDefault();
      next.click();
    }
  });
})();

// ---- Column filters on data tables (e.g. evidence table confidence /
// significance dropdowns). Each <select class="col-filter" data-col="X">
// filters rows whose data-X attribute doesn't match; multiple filters AND.
(function () {
  const tables = document.querySelectorAll("table[data-filterable]");
  tables.forEach(function (table) {
    const filters = table.querySelectorAll("select.col-filter");
    if (!filters.length) return;
    function apply() {
      const active = [];
      filters.forEach(function (s) {
        if (s.value) active.push([s.dataset.col, s.value.toLowerCase()]);
      });
      let shown = 0;
      table.querySelectorAll("tbody tr").forEach(function (row) {
        const ok = active.every(function (f) {
          return (row.dataset[f[0]] || "").toLowerCase() === f[1];
        });
        row.style.display = ok ? "" : "none";
        if (!ok) {
          const cb = row.querySelector('input[type="checkbox"]');
          if (cb) cb.checked = false;
        } else shown++;
      });
      const counter = document.querySelector("[data-filter-count]");
      if (counter) counter.textContent = shown;
    }
    filters.forEach(function (s) {
      s.addEventListener("change", apply);
      // Don't let a click on the dropdown trigger column sort handlers.
      s.addEventListener("click", function (e) { e.stopPropagation(); });
    });
  });
})();

// ---- Checklist section edit mode: "Edit" reveals rename boxes, the ×
// remove button, and the add-a-document row for that section only; "Done"
// hides them again. Purely client-side visibility — nothing is saved until
// a rename/remove/add form is actually submitted.
(function () {
  document.querySelectorAll(".checklist-edit-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const block = btn.closest(".checklist-group-block");
      const editing = block.classList.toggle("editing");
      btn.textContent = editing ? btn.dataset.doneLabel : btn.dataset.editLabel;
    });
  });
})();
