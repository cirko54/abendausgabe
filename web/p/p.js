/* Profilfragebogen (SPEC §4.1). Alles freiwillig; Sichtbarkeit wählt die Person selbst. */
(function () {
  "use strict";

  const app = document.getElementById("app");
  const DAYS = [["mo", "Mo"], ["di", "Di"], ["mi", "Mi"], ["do", "Do"], ["fr", "Fr"], ["sa", "Sa"], ["so", "So"]];
  let schema = null;
  let me = null;
  const rankState = {};

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  async function api(method, url, body) {
    const response = await fetch(url, {
      method: method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
    });
    let data = {};
    try { data = await response.json(); } catch (e) { data = {}; }
    if (!response.ok) {
      const error = new Error((data && data.detail) || "Fehler " + response.status);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function fieldHtml(f, value) {
    const hint = f.hint ? '<p class="hint">' + esc(f.hint) + "</p>" : "";
    const id = "f_" + f.id;
    if (f.type === "text") {
      return '<label for="' + id + '">' + esc(f.label) + "</label>" + hint +
        '<input type="text" id="' + id + '" value="' + esc(value || "") + '">';
    }
    if (f.type === "textarea") {
      return '<label for="' + id + '">' + esc(f.label) + "</label>" + hint +
        '<textarea id="' + id + '">' + esc(value || "") + "</textarea>";
    }
    if (f.type === "links") {
      return '<label for="' + id + '">' + esc(f.label) + "</label>" + hint +
        '<textarea id="' + id + '">' + esc((value || []).join("\n")) + "</textarea>";
    }
    if (f.type === "tags") {
      return '<label for="' + id + '">' + esc(f.label) + "</label>" + hint +
        '<input type="text" id="' + id + '" value="' + esc((value || []).join(", ")) + '">';
    }
    if (f.type === "slider") {
      const v = value == null ? Math.round((f.min + f.max) / 2) : value;
      return '<label for="' + id + '">' + esc(f.label) + "</label>" + hint +
        '<input type="range" id="' + id + '" min="' + f.min + '" max="' + f.max + '" value="' + v + '">' +
        '<div class="range-labels"><span>' + esc(f.min_label || f.min) + "</span><span>" +
        esc(f.max_label || f.max) + "</span></div>";
    }
    if (f.type === "rank") {
      const order = (value && value.length ? value : []).concat(
        f.options.filter(function (o) { return !(value || []).includes(o); })
      );
      rankState[f.id] = order;
      return '<fieldset><legend>' + esc(f.label) + "</legend>" + hint +
        '<ol class="rank" id="' + id + '"></ol></fieldset>';
    }
    if (f.type === "weekdays") {
      const selected = value || [];
      return '<fieldset><legend>' + esc(f.label) + "</legend>" + hint + '<div class="days">' +
        DAYS.map(function (d) {
          return '<label><input type="checkbox" name="' + id + '" value="' + d[0] + '"' +
            (selected.includes(d[0]) ? " checked" : "") + ">" + d[1] + "</label>";
        }).join("") + "</div></fieldset>";
    }
    return "";
  }

  function drawRank(fieldId) {
    const list = document.getElementById("f_" + fieldId);
    const order = rankState[fieldId];
    list.innerHTML = order.map(function (o, i) {
      return "<li><span>" + (i + 1) + ". " + esc(o) + "</span>" +
        '<button type="button" data-up="' + i + '" aria-label="nach oben">↑</button>' +
        '<button type="button" data-down="' + i + '" aria-label="nach unten">↓</button></li>';
    }).join("");
    list.querySelectorAll("button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const up = btn.getAttribute("data-up");
        const i = Number(up !== null ? up : btn.getAttribute("data-down"));
        const j = up !== null ? i - 1 : i + 1;
        if (j < 0 || j >= order.length) return;
        const tmp = order[i]; order[i] = order[j]; order[j] = tmp;
        drawRank(fieldId);
      });
    });
  }

  function collect() {
    const answers = {};
    schema.fields.forEach(function (f) {
      const el = document.getElementById("f_" + f.id);
      if (f.type === "text" || f.type === "textarea") answers[f.id] = el.value.trim();
      else if (f.type === "links") answers[f.id] = el.value.split("\n").map(function (s) { return s.trim(); }).filter(Boolean);
      else if (f.type === "tags") answers[f.id] = el.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
      else if (f.type === "slider") answers[f.id] = Number(el.value);
      else if (f.type === "rank") answers[f.id] = rankState[f.id].slice();
      else if (f.type === "weekdays") {
        answers[f.id] = Array.prototype.slice.call(document.querySelectorAll('input[name="f_' + f.id + '"]:checked'))
          .map(function (c) { return c.value; });
      }
    });
    return answers;
  }

  async function save() {
    const status = document.getElementById("status");
    const checked = document.querySelector('input[name="visibility"]:checked');
    try {
      const saved = await api("POST", "/api/profile", {
        answers: collect(),
        visibility: checked ? checked.value : "self",
      });
      status.textContent = "Gespeichert (Version " + saved.version + ").";
    } catch (e) {
      status.textContent = e.message;
    }
  }

  async function init() {
    try {
      me = await api("GET", "/api/me");
    } catch (e) {
      app.innerHTML = '<div class="body"><h1>Erst anmelden</h1><p class="muted">Melde dich zuerst am Handy an.</p>' +
        '<a class="big primary" href="/c/">Zur Anmeldung</a></div>';
      return;
    }
    if (me.role === "guest") {
      app.innerHTML = '<div class="body"><h1>Gäste haben kein Profil.</h1><a class="big" href="/c/">Zurück</a></div>';
      return;
    }
    schema = await api("GET", "/api/profile/schema");
    const current = await api("GET", "/api/profile/me");
    const answers = current.answers || {};
    const vis = schema.visibility;
    const defaultVis = current.visibility || (me.role === "admin" ? vis.default_admin : vis.default_member);
    app.innerHTML =
      '<div class="top"><span class="dot" style="background:' + esc(me.color) + '"></span>' + esc(me.name) +
      '<a href="/c/" style="margin-left:auto;color:inherit">Zurück</a></div>' +
      '<div class="form"><h1>Dein Profil</h1><p class="muted">' + esc(schema.intro) + "</p>" +
      schema.fields.map(function (f) {
        return '<div class="field">' + fieldHtml(f, answers[f.id]) + "</div>";
      }).join("") +
      '<div class="field"><fieldset class="radio"><legend>' + esc(vis.label) + "</legend>" +
      vis.options.map(function (o) {
        return '<label><input type="radio" name="visibility" value="' + esc(o.id) + '"' +
          (o.id === defaultVis ? " checked" : "") + ">" + esc(o.label) + "</label>";
      }).join("") +
      "</fieldset></div>" +
      '<button id="save" class="big primary">Speichern</button><p id="status" class="toast"></p></div>';
    schema.fields.forEach(function (f) { if (f.type === "rank") drawRank(f.id); });
    document.getElementById("save").addEventListener("click", save);
  }

  init();
})();
