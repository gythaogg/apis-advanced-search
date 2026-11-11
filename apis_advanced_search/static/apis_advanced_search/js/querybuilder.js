(function () {
  "use strict";

  const state = {
    model: null,
    fields: [],
    tree: null,
    queryUrl: null,
    csrfToken: "",
  };

  let app, modelSelect, builderRoot, resultsEl, searchBtn;
  let idCounter = 0;

  function nextId(prefix) {
    idCounter += 1;
    return `${prefix}-${idCounter}`;
  }

  // Negating an entire group is only ever offered on a nested group (see
  // renderGroup) - negating a fresh top-level query has nothing complex to
  // invert yet, so the control would just be clutter there.
  function excludeToggle(node) {
    const wrap = el("div", "form-check form-check-inline mb-0");
    const checkboxId = nextId("qb-exclude");
    const checkbox = el("input", "form-check-input");
    checkbox.type = "checkbox";
    checkbox.id = checkboxId;
    checkbox.checked = !!node.negate;
    checkbox.addEventListener("change", () => {
      node.negate = checkbox.checked;
    });
    const label = el("label", "form-check-label small");
    label.setAttribute("for", checkboxId);
    label.textContent = "Exclude matches from this group";
    wrap.append(checkbox, label);
    return wrap;
  }

  function emptyGroup() {
    return { type: "group", operator: "AND", negate: false, children: [] };
  }

  function lookupOptionFor(fieldInfo, lookupValue) {
    return fieldInfo.lookups.find((l) => l.value === lookupValue) || fieldInfo.lookups[0];
  }

  function newCondition() {
    const field = state.fields[0];
    const option = field.lookups[0];
    return {
      type: "condition",
      field: field.name,
      lookup: option.value,
      value: option.multi ? [] : null,
    };
  }

  // A group with no conditions has nothing to combine, so every group we
  // create for the user - the root on model selection, or a nested one from
  // "+ Add group" - starts with one condition already in it.
  function newGroupWithCondition() {
    const group = emptyGroup();
    group.children.push(newCondition());
    return group;
  }

  function fieldInfoFor(name) {
    return state.fields.find((f) => f.name === name) || state.fields[0];
  }

  function el(tag, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  }

  function button(text, className, onClick) {
    const btn = el("button", className);
    btn.type = "button";
    btn.textContent = text;
    btn.addEventListener("click", onClick);
    return btn;
  }

  // Turns a plain <select> into a type-to-filter combo box, for selects
  // whose option list can get long (which model, which field) - unlike
  // the FK/M2M widgets, this has no `ajax` config, so select2 just filters
  // the options already in the DOM instead of hitting an endpoint. select2
  // fires the native "change" event on selection either way, so existing
  // change listeners on the underlying <select> keep working unchanged.
  function makeSearchable(select, select2Options) {
    if (!window.jQuery) return;
    window.jQuery(select).select2(Object.assign({ theme: "bootstrap-5", width: "auto" }, select2Options));
  }

  // select2 only notifies of a selection through jQuery's event system, not
  // a real native DOM event - a plain addEventListener("change", ...) on a
  // select2-enhanced <select> never fires. Any select that might be passed
  // through makeSearchable needs its change handler bound this same way,
  // falling back to a native listener only for the (select2-less) case
  // where jQuery itself isn't available.
  function onSelectChange(select, handler) {
    if (window.jQuery) {
      window.jQuery(select).on("change", handler);
    } else {
      select.addEventListener("change", handler);
    }
  }

  // --- scalar (single-value) input helpers, shared by the plain single-value
  // widget and the entry field of the multi-value chip list below -------

  function scalarInputElement(fieldInfo) {
    if (fieldInfo.type === "number") {
      const input = el("input", "form-control form-control-sm w-auto");
      input.type = "number";
      return input;
    }
    if (fieldInfo.type === "date") {
      const input = el("input", "form-control form-control-sm w-auto");
      input.type = "date";
      return input;
    }
    if (fieldInfo.type === "datetime") {
      const input = el("input", "form-control form-control-sm w-auto");
      input.type = "datetime-local";
      return input;
    }
    const input = el("input", "form-control form-control-sm w-auto");
    input.type = "text";
    return input;
  }

  function readScalarInputValue(fieldInfo, input) {
    if (input.value === "") return null;
    return fieldInfo.type === "number" ? Number(input.value) : input.value;
  }

  function setScalarInputValue(input, value) {
    if (value !== null && value !== undefined) input.value = value;
  }

  // Plain single-value widget: number/date/datetime/text input, or the
  // Yes/No select for booleans. Used whenever the chosen lookup is not
  // multi-value (see lookups.py - this is every ordering comparison, plus
  // the whole boolean type).
  function buildScalarInput(fieldInfo, currentValue, onChange) {
    if (fieldInfo.type === "boolean") {
      const select = el("select", "form-select form-select-sm w-auto");
      [["true", "Yes"], ["false", "No"]].forEach(([value, label]) => {
        const option = el("option");
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
      });
      select.value = currentValue === false ? "false" : "true";
      onChange(select.value === "true");
      select.addEventListener("change", () => onChange(select.value === "true"));
      return select;
    }

    const input = scalarInputElement(fieldInfo);
    setScalarInputValue(input, currentValue);
    input.addEventListener("input", () => onChange(readScalarInputValue(fieldInfo, input)));
    return input;
  }

  // Multi-value chip list for plain (non-relational) fields: existing
  // values shown as removable chips, plus one small entry field that
  // commits on Enter or "+ Add value" rather than on every keystroke -
  // unlike the scalar widget, a half-typed value shouldn't become a chip.
  function buildChipListInput(fieldInfo, currentValues, onChange) {
    const wrap = el("div", "d-flex align-items-center gap-2 flex-wrap");
    const values = Array.isArray(currentValues) ? currentValues.slice() : [];

    const chipsEl = el("span", "d-flex align-items-center gap-1 flex-wrap");

    function renderChips() {
      chipsEl.innerHTML = "";
      values.forEach((value, index) => {
        const chip = el("span", "badge rounded-pill text-bg-secondary d-flex align-items-center gap-1");
        chip.textContent = value;
        const removeBtn = el("button", "btn-close btn-close-white");
        removeBtn.type = "button";
        removeBtn.style.fontSize = "0.55em";
        removeBtn.setAttribute("aria-label", "Remove value");
        removeBtn.addEventListener("click", () => {
          values.splice(index, 1);
          renderChips();
          onChange(values.slice());
        });
        chip.append(removeBtn);
        chipsEl.appendChild(chip);
      });
    }
    renderChips();

    const entry = scalarInputElement(fieldInfo);

    function commitEntry() {
      const value = readScalarInputValue(fieldInfo, entry);
      if (value === null || value === "") return;
      values.push(value);
      entry.value = "";
      renderChips();
      onChange(values.slice());
    }

    entry.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        commitEntry();
      }
    });
    // Covers the common case of typing one value and going straight to
    // Search (or clicking anywhere else) without pressing Enter or "+ Add
    // value" first - any click elsewhere blurs this field before that
    // click's own handler runs, so this is enough to never lose a typed
    // value the user never explicitly "added".
    entry.addEventListener("blur", commitEntry);

    const addBtn = button("+ Add value", "btn btn-sm btn-outline-secondary", commitEntry);

    wrap.append(chipsEl, entry, addBtn);
    return wrap;
  }

  // FK/M2M widget: select2 reusing apis_core's own autocomplete endpoint.
  // `multiple` switches it between a single pick and a chip-style
  // multi-select - select2 handles the chip UI itself in that case, so no
  // custom chip list is needed here the way it is for plain fields above.
  function buildRelationInput(fieldInfo, multiple, currentValue, currentLabel, onChange) {
    const select = el("select", "form-select form-select-sm");
    if (multiple) select.multiple = true;

    const values = multiple ? (Array.isArray(currentValue) ? currentValue : []) : currentValue ? [currentValue] : [];
    const labels = multiple ? (Array.isArray(currentLabel) ? currentLabel : []) : currentLabel ? [currentLabel] : [];
    values.forEach((value, index) => {
      const option = el("option");
      option.value = value;
      // Without a label, select2 has nothing to display for a preselected
      // option - it would render blank even though the underlying id is
      // correct. Fall back to the raw id only if a label wasn't captured.
      option.textContent = labels[index] || value;
      option.selected = true;
      select.appendChild(option);
    });

    // select2 needs the element attached to the DOM before it can be initialized.
    requestAnimationFrame(() => {
      if (!window.jQuery) return;
      const $select = window.jQuery(select);
      $select.select2({
        theme: "bootstrap-5", // matches the select2-bootstrap-5-theme CSS apis_core already loads
        width: multiple ? "100%" : "auto",
        placeholder: "Start typing…",
        allowClear: !multiple,
        multiple: multiple,
        ajax: {
          url: fieldInfo.autocomplete_url,
          dataType: "json",
          delay: 250,
          data: (params) => ({ q: params.term, page: params.page }),
          processResults: (data) => data,
        },
      });
      // select2's own "data" always reflects the full current selection,
      // for both single and multi mode, so one "change" handler covers
      // picking, removing a chip, and clearing.
      $select.on("change", () => {
        const picked = $select.select2("data") || [];
        if (multiple) {
          onChange(picked.map((d) => d.id), picked.map((d) => d.text));
        } else {
          const first = picked[0];
          onChange(first ? first.id : null, first ? first.text : null);
        }
      });
    });
    return select;
  }

  function buildValueInput(fieldInfo, lookupOption, currentValue, currentLabel, onChange) {
    if (fieldInfo.type === "fk" || fieldInfo.type === "m2m") {
      return buildRelationInput(fieldInfo, lookupOption.multi, currentValue, currentLabel, onChange);
    }
    if (lookupOption.multi) {
      return buildChipListInput(fieldInfo, currentValue, onChange);
    }
    return buildScalarInput(fieldInfo, currentValue, onChange);
  }

  function renderCondition(node, container, onRemove) {
    container.innerHTML = "";
    const row = el("div", "d-flex align-items-center gap-2 flex-wrap");

    if (!node.field) node.field = state.fields[0].name;
    let currentField = fieldInfoFor(node.field);
    if (!node.lookup) node.lookup = currentField.lookups[0].value;

    const fieldSelect = el("select", "form-select form-select-sm w-auto");
    state.fields.forEach((f) => {
      const option = el("option");
      option.value = f.name;
      option.textContent = f.label;
      if (f.name === node.field) option.selected = true;
      fieldSelect.appendChild(option);
    });
    // select2 needs the element attached to the DOM before it can be
    // initialized - it isn't yet at this point, so defer like the FK/M2M
    // widgets do.
    requestAnimationFrame(() => makeSearchable(fieldSelect));

    const lookupSelect = el("select", "form-select form-select-sm w-auto");
    const valueContainer = el("span");

    function populateLookups() {
      lookupSelect.innerHTML = "";
      currentField.lookups.forEach((lookup) => {
        const option = el("option");
        option.value = lookup.value;
        option.textContent = lookup.label;
        if (lookup.value === node.lookup) option.selected = true;
        lookupSelect.appendChild(option);
      });
    }

    function renderValueWidget() {
      valueContainer.innerHTML = "";
      // "empty" / "not_empty" have no value to enter at all.
      if (node.lookup === "empty" || node.lookup === "not_empty") return;
      const option = lookupOptionFor(currentField, node.lookup);
      valueContainer.appendChild(
        buildValueInput(currentField, option, node.value, node.valueLabel, (val, label) => {
          node.value = val;
          if (label !== undefined) node.valueLabel = label;
        })
      );
    }

    populateLookups();
    renderValueWidget();

    onSelectChange(fieldSelect, () => {
      node.field = fieldSelect.value;
      currentField = fieldInfoFor(node.field);
      const option = currentField.lookups[0];
      node.lookup = option.value;
      node.value = option.multi ? [] : null;
      node.valueLabel = option.multi ? [] : null;
      populateLookups();
      renderValueWidget();
    });

    lookupSelect.addEventListener("change", () => {
      node.lookup = lookupSelect.value;
      // A lookup switch can change the value's shape (e.g. a multi-value
      // "contains" to a single-value "<"), so start the value over rather
      // than risk handing a stale array/scalar to the wrong widget.
      const option = lookupOptionFor(currentField, node.lookup);
      node.value = option.multi ? [] : null;
      node.valueLabel = option.multi ? [] : null;
      renderValueWidget();
    });

    const removeBtn = button("✕", "btn btn-sm btn-outline-danger", onRemove);

    row.append(fieldSelect, lookupSelect, valueContainer, removeBtn);
    container.appendChild(row);
  }

  // The inline AND/OR shown between each pair of children. A group has one
  // operator for all its children, so every connector reflects and edits
  // that same value - changing any one of them re-renders the whole group,
  // which makes all the other connectors flip to match. That's deliberate:
  // it teaches "one operator for the whole group" by direct manipulation
  // rather than by disabling every connector but the first.
  function connectorRow(node, container, opts) {
    const row = el("div", "d-flex");
    const select = el("select", "form-select form-select-sm w-auto");
    ["AND", "OR"].forEach((op) => {
      const option = el("option");
      option.value = op;
      option.textContent = op;
      if (node.operator === op) option.selected = true;
      select.appendChild(option);
    });
    select.addEventListener("change", () => {
      node.operator = select.value;
      renderGroup(node, container, opts);
    });
    row.appendChild(select);
    return row;
  }

  function renderGroup(node, container, opts) {
    opts = opts || {};
    container.innerHTML = "";

    const box = el("div", opts.isRoot ? "card mb-2 bg-light" : "card mb-2");
    const body = el("div", "card-body");

    const header = el("div", "d-flex align-items-center gap-2 flex-wrap mb-2");
    // Excluding an entire fresh top-level query is rarely meaningful - the
    // toggle only earns its place once there's a nested group (built via
    // "+ Add group") to apply it to.
    if (!opts.isRoot) {
      header.append(excludeToggle(node));
    }
    if (!opts.isRoot && opts.onRemove) {
      header.appendChild(button("Remove group", "btn btn-sm btn-outline-danger ms-auto", opts.onRemove));
    }
    if (header.children.length) body.appendChild(header);

    const childrenContainer = el("div", "d-flex flex-column gap-2 ps-3 border-start");
    node.children.forEach((child, index) => {
      if (index > 0) {
        childrenContainer.appendChild(connectorRow(node, container, opts));
      }
      const row = el("div");
      const onRemove = () => {
        node.children.splice(index, 1);
        renderGroup(node, container, opts);
      };
      if (child.type === "group") {
        renderGroup(child, row, { onRemove });
      } else {
        renderCondition(child, row, onRemove);
      }
      childrenContainer.appendChild(row);
    });
    body.appendChild(childrenContainer);

    // Add-condition/add-group sit after the last condition rather than up in
    // the header, so they read as "add another one here". Add group is
    // visually de-emphasized (link style) since nesting groups is a more
    // advanced move than just adding another condition.
    const addRow = el("div", "d-flex align-items-center gap-2 mt-2");
    const addConditionBtn = button("+ Add condition", "btn btn-sm btn-outline-primary", () => {
      node.children.push(newCondition());
      renderGroup(node, container, opts);
    });
    const addGroupBtn = button("+ Add group", "btn btn-sm btn-link text-muted", () => {
      node.children.push(newGroupWithCondition());
      renderGroup(node, container, opts);
    });
    addRow.append(addConditionBtn, addGroupBtn);
    body.appendChild(addRow);

    box.appendChild(body);
    container.appendChild(box);
  }

  function escapeHtml(str) {
    const div = el("div");
    div.textContent = str;
    return div.innerHTML;
  }

  async function fetchJSON(url, options) {
    const response = await fetch(url, options);
    let data = null;
    try {
      data = await response.json();
    } catch (err) {
      data = null;
    }
    if (!response.ok) {
      const message = (data && data.error) || `Request failed (${response.status})`;
      throw new Error(message);
    }
    return data;
  }

  function buildUrl(template, modelLabel) {
    const [appLabel, modelName] = modelLabel.split(".");
    return template.replace("__app__", appLabel).replace("__model__", modelName);
  }

  async function onModelChange(modelLabel) {
    state.model = modelLabel;
    state.queryUrl = buildUrl(app.dataset.queryUrlTemplate, modelLabel);
    const fieldsUrl = buildUrl(app.dataset.fieldsUrlTemplate, modelLabel);

    state.fields = await fetchJSON(fieldsUrl);
    state.tree = newGroupWithCondition();
    renderGroup(state.tree, builderRoot, { isRoot: true });
    resultsEl.innerHTML = "";
    searchBtn.disabled = false;
  }

  function renderResults(data, page) {
    resultsEl.innerHTML = "";

    const summary = el("p");
    summary.textContent = `${data.count} result${data.count === 1 ? "" : "s"}`;
    resultsEl.appendChild(summary);

    if (data.results.length) {
      const table = el("table", "table table-sm table-striped");
      const tbody = el("tbody");
      data.results.forEach((result) => {
        const tr = el("tr");
        const td = el("td");
        if (result.url) {
          const a = el("a");
          a.href = result.url;
          a.textContent = result.label;
          td.appendChild(a);
        } else {
          td.textContent = result.label;
        }
        tr.appendChild(td);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      resultsEl.appendChild(table);
    }

    const totalPages = Math.max(Math.ceil(data.count / data.page_size), 1);
    if (totalPages > 1) {
      const nav = el("div", "d-flex align-items-center gap-2 mt-3");
      const prev = button("‹ Prev", "btn btn-sm btn-outline-secondary", () => runSearch(page - 1));
      prev.disabled = page <= 1;
      const next = button("Next ›", "btn btn-sm btn-outline-secondary", () => runSearch(page + 1));
      next.disabled = page >= totalPages;
      const label = el("span");
      label.textContent = `Page ${page} of ${totalPages}`;
      nav.append(prev, label, next);
      resultsEl.appendChild(nav);
    }
  }

  async function runSearch(page) {
    page = page || 1;
    resultsEl.innerHTML = "<p>Searching…</p>";
    try {
      const data = await fetchJSON(state.queryUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": state.csrfToken,
        },
        body: JSON.stringify({ query: state.tree, page: page }),
      });
      renderResults(data, page);
    } catch (err) {
      resultsEl.innerHTML = `<div class="alert alert-danger">${escapeHtml(err.message)}</div>`;
    }
  }

  async function loadModels() {
    const models = await fetchJSON(app.dataset.modelsUrl);
    modelSelect.innerHTML = "";

    // select2's placeholder support expects a plain empty-value option
    // rather than a disabled one - it's what represents "nothing chosen".
    const placeholder = el("option");
    placeholder.value = "";
    placeholder.textContent = "Select model…";
    modelSelect.appendChild(placeholder);

    // Grouping by kind communicates entity-vs-relation on its own, so
    // there's no need for a "(relation)" suffix on every option.
    const entityGroup = el("optgroup");
    entityGroup.label = "Entities";
    const relationGroup = el("optgroup");
    relationGroup.label = "Relations";

    models.forEach((model) => {
      const option = el("option");
      option.value = model.label;
      option.textContent = model.verbose_name;
      (model.kind === "relation" ? relationGroup : entityGroup).appendChild(option);
    });

    if (entityGroup.children.length) modelSelect.appendChild(entityGroup);
    if (relationGroup.children.length) modelSelect.appendChild(relationGroup);

    // select2's own "auto" width doesn't measure option text the way a
    // plain native <select> does, so it has to be sized by hand - wide
    // enough for the longest registered model name to fit on one line.
    // "ch" approximates a character's width, with some padding for the
    // dropdown arrow and inner spacing.
    const longestLabel = Math.max(placeholder.textContent.length, ...models.map((m) => m.verbose_name.length));

    // Already attached to the document from page load, so no need to
    // defer this one to a later frame the way the dynamically-created
    // field selects have to be.
    makeSearchable(modelSelect, { placeholder: "Select model…", width: `${longestLabel + 4}ch` });
  }

  document.addEventListener("DOMContentLoaded", () => {
    app = document.getElementById("qb-app");
    if (!app) return;

    state.csrfToken = app.dataset.csrfToken;
    modelSelect = document.getElementById("qb-model-select");
    builderRoot = document.getElementById("qb-builder-root");
    resultsEl = document.getElementById("qb-results");
    searchBtn = document.getElementById("qb-search-btn");
    searchBtn.disabled = true;

    onSelectChange(modelSelect, () => {
      if (!modelSelect.value) return;
      onModelChange(modelSelect.value);
    });
    searchBtn.addEventListener("click", () => runSearch(1));

    loadModels();
  });
})();
