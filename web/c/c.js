/* Handy-Controller der Abendausgabe. ES2017, ohne Build-Schritt. */
(function () {
  "use strict";

  const app = document.getElementById("app");
  const SLIDER_STEPS = 1000;

  let me = null;
  let state = null;
  let ws = null;
  let retry = 0;
  let rest = false;
  let renderKey = "";
  let sliderPos = SLIDER_STEPS / 2;
  let sliderTouched = false;
  let toastTimer = null;
  // Morgen danach (decisions.md Nr. 45): { card, rating, answer, result } oder null
  let morning = null;

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmt(n) {
    return Number(Number(n).toPrecision(3)).toLocaleString("de-DE", { maximumFractionDigits: 2 });
  }

  async function api(method, url, body) {
    const response = await fetch(url, {
      method: method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
    });
    let data = {};
    try {
      data = await response.json();
    } catch (e) {
      data = {};
    }
    if (!response.ok) {
      const error = new Error((data && data.detail) || "Fehler " + response.status);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  // ------------------------------------------------------------- Anmeldung

  async function showChooser() {
    rest = false;
    document.body.classList.remove("rest");
    let data;
    try {
      data = await api("GET", "/api/people");
    } catch (e) {
      app.innerHTML = '<div class="body"><p class="error">' + esc(e.message) + "</p></div>";
      return;
    }
    const buttons = data.people
      .map(function (p) {
        return (
          '<button class="big person" data-id="' + esc(p.id) + '" data-claimed="' + (p.claimed ? 1 : 0) +
          '"><span class="dot" style="background:' + esc(p.color) + '"></span>' + esc(p.name) + "</button>"
        );
      })
      .join("");
    app.innerHTML =
      '<div class="body"><h1>Wer bist du?</h1>' + buttons +
      '<button class="big person" data-id="gast"><span class="dot" style="background:' +
      esc(data.guest_color) + '"></span>Gast</button></div>';
    app.querySelectorAll("button[data-id]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const id = btn.getAttribute("data-id");
        if (id === "gast") register("gast", null);
        else showPin(id, btn.textContent, btn.getAttribute("data-claimed") === "1");
      });
    });
  }

  function showPin(personId, name, claimed) {
    const text = claimed
      ? "Gib deine PIN ein."
      : "Lege eine PIN fest (4 bis 8 Ziffern). Damit kann niemand sonst unter deinem Namen auftreten.";
    app.innerHTML =
      '<div class="body"><h1>' + esc(name) + '</h1><p class="muted">' + esc(text) + "</p>" +
      '<input id="pin" type="password" inputmode="numeric" pattern="[0-9]*" autocomplete="off" maxlength="8">' +
      '<p id="err" class="error"></p>' +
      '<button id="go" class="big primary">Anmelden</button>' +
      '<button id="back" class="big">Zurück</button></div>';
    const input = document.getElementById("pin");
    input.focus();
    document.getElementById("go").addEventListener("click", function () {
      register(personId, input.value);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") register(personId, input.value);
    });
    document.getElementById("back").addEventListener("click", showChooser);
  }

  async function register(personId, pin) {
    try {
      me = await api("POST", "/api/devices", { person_id: personId, pin: pin });
      connect();
      loadMorning();
    } catch (e) {
      const err = document.getElementById("err");
      if (err) err.textContent = e.message;
      else alert(e.message);
    }
  }

  // ------------------------------------------------------------ Verbindung

  function connect() {
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws/c");
    ws.onopen = function () {
      retry = 0;
    };
    ws.onmessage = function (event) {
      try {
        state = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      render();
    };
    ws.onclose = function (event) {
      ws = null;
      if (event.code === 4401) {
        me = null;
        showChooser();
        return;
      }
      retry = Math.min(retry + 1, 5);
      setTimeout(function () {
        if (!ws && me) connect();
      }, 500 * Math.pow(2, retry));
    };
  }

  // Aufgewacht oder zurück im Browser: Verbindung sofort erneuern.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible" || !me) return;
    if (!ws) connect();
    if (!morning) loadMorning();
  });

  function send(message) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(message));
  }

  function toast(text) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = text;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.textContent = ""; }, 2000);
  }

  // --------------------------------------------------------- Morgen danach

  async function loadMorning() {
    if (!me || me.role === "guest") return;
    try {
      const data = await api("GET", "/api/morning");
      morning = data.card ? { card: data.card, rating: null, answer: null, result: null } : null;
    } catch (e) {
      morning = null;
    }
    renderKey = "";
    render();
  }

  function morningVisible() {
    return !!morning && (!state || state.phase !== "block");
  }

  function morningHtml() {
    const card = morning.card;
    const q = card.question;
    if (morning.result) {
      const r = morning.result.question;
      let html = "<h1>Danke.</h1>";
      if (r) {
        html += r.correct
          ? '<p class="value">Richtig.</p>'
          : '<p class="muted">Nicht ganz. Richtig ist:</p><p class="value small-value">' + esc(r.answer) + "</p>";
        if (r.source) html += '<p class="muted">Quelle: ' + esc(r.source) + "</p>";
      }
      return html + '<button class="big primary" data-morning="done">Fertig</button>';
    }
    let html =
      '<p class="muted">Morgen danach · ' + esc(card.day) + "</p>" +
      "<h1>Wie war die Abendausgabe gestern?</h1>" +
      '<div class="stars">' +
      [1, 2, 3, 4, 5].map(function (n) {
        return '<button class="star' + (morning.rating === n ? " on" : "") + '" data-rating="' + n + '">' + n + "</button>";
      }).join("") +
      '</div><div class="range-labels"><span>gar nicht</span><span>sehr</span></div>';
    if (q) {
      html += '<h2 class="recall">' + esc(q.question) + "</h2>" +
        q.options.map(function (o, i) {
          return '<button class="big' + (morning.answer === i ? " picked" : "") + '" data-recall="' + i + '">' + esc(o) + "</button>";
        }).join("");
    }
    const ready = morning.rating && (!q || morning.answer !== null);
    return html +
      '<button class="big primary" data-morning="send"' + (ready ? "" : " disabled") + ">Absenden</button>" +
      '<p id="err" class="error"></p>' +
      '<button class="small" data-morning="later">Später</button>';
  }

  async function sendMorning() {
    try {
      morning.result = await api("POST", "/api/morning", {
        session_id: morning.card.session_id,
        rating: morning.rating,
        answer: morning.answer,
      });
      draw();
    } catch (e) {
      const err = document.getElementById("err");
      if (err) err.textContent = e.message;
    }
  }

  function bindMorning() {
    app.querySelectorAll("[data-rating]").forEach(function (el) {
      el.addEventListener("click", function () {
        morning.rating = Number(el.getAttribute("data-rating"));
        draw();
      });
    });
    app.querySelectorAll("[data-recall]").forEach(function (el) {
      el.addEventListener("click", function () {
        morning.answer = Number(el.getAttribute("data-recall"));
        draw();
      });
    });
    app.querySelectorAll("[data-morning]").forEach(function (el) {
      el.addEventListener("click", function () {
        const act = el.getAttribute("data-morning");
        if (act === "send") sendMorning();
        else {
          morning = null; // „Später“: abends beim Einchecken kommt die Karte wieder
          renderKey = "";
          render();
        }
      });
    });
  }

  // ------------------------------------------------------------ Darstellung

  function sliderValue(block, pos) {
    const t = pos / SLIDER_STEPS;
    const lo = Number(block.min);
    const hi = Number(block.max);
    if (block.log === false) return lo + t * (hi - lo);
    return Math.pow(10, Math.log10(lo) + t * (Math.log10(hi) - Math.log10(lo)));
  }

  function roundSig(n) {
    return Number(Number(n).toPrecision(3));
  }

  function bodyHtml() {
    const you = state.you || {};
    const isAdmin = me.role === "admin";
    const block = state.block;
    if (!you.present) {
      return (
        '<h1>Guten Abend, ' + esc(me.name) + "</h1>" +
        '<button class="big primary" data-act="checkin">Ich bin dabei</button>'
      );
    }
    if (state.phase === "lobby") {
      return (
        "<h1>Du bist eingecheckt.</h1>" +
        '<p class="muted">Die Sendung startet mit OK auf der Fernbedienung.</p>' +
        (isAdmin ? '<button class="big primary" data-act="advance">Sendung starten</button>' : "")
      );
    }
    if (state.phase === "ended") {
      return (
        "<h1>Sendeschluss.</h1>" +
        '<p class="muted">Deine Punkte heute: ' + (you.total || 0) + "</p>" +
        (isAdmin ? '<button class="big" data-act="advance">Neue Testsendung</button>' : "")
      );
    }
    if (state.block_phase === "ask" && !you.answered) {
      if (block.type === "choice") {
        return (
          "<h1>" + esc(block.question) + "</h1>" +
          block.options
            .map(function (o, i) {
              return '<button class="big" data-choice="' + i + '">' + esc(o) + "</button>";
            })
            .join("")
        );
      }
      return (
        "<h1>" + esc(block.question) + "</h1>" +
        '<p class="value" id="value"></p>' +
        '<input id="slider" type="range" min="0" max="' + SLIDER_STEPS + '" step="1" value="' + sliderPos + '">' +
        '<button class="big primary" data-act="answer"' + (sliderTouched ? "" : " disabled") +
        ">Antwort senden</button>"
      );
    }
    if (state.block_phase === "ask") {
      return "<h1>Gespeichert.</h1><p class=\"muted\">Handy kann weg. Die Auflösung kommt am Fernseher.</p>";
    }
    if (state.block_phase === "reveal") {
      const points = you.points == null ? "" : "<p class=\"value\">" + you.points + " Punkte</p>";
      return "<h1>Auflösung am Fernseher.</h1>" + points;
    }
    return '<h1>Schau auf den Fernseher.</h1><p class="muted">Handy kann weg.</p>';
  }

  function footHtml() {
    const isAdmin = me.role === "admin";
    const inBlock = state.phase === "block";
    let html = '<div class="foot">';
    if (inBlock) {
      html +=
        '<button class="small" data-signal="too_easy">Zu leicht</button>' +
        '<button class="small" data-signal="too_hard">Zu zäh</button>' +
        '<button class="small" data-act="skip_vote">Überspringen</button>';
    }
    if (state.you && state.you.present) html += '<button class="small" data-act="leave">Bin weg</button>';
    if (isAdmin && inBlock) {
      html +=
        '<button class="small" data-act="advance">Weiter</button>' +
        '<button class="small" data-act="end_now">Sendeschluss jetzt</button>';
    }
    if (me.role !== "guest") html += '<a href="/p/">Profil</a>';
    return html + "</div>";
  }

  function wantsRest() {
    const you = state.you || {};
    if (!you.present || state.phase !== "block") return false;
    if (state.block_phase === "ask") return !!you.answered;
    return true;
  }

  function render() {
    if (!me) return;
    if (!state) {
      if (morningVisible()) draw();
      return;
    }
    const you = state.you || {};
    const key = [
      state.phase, state.block_index, state.block_phase, you.present, you.answered, you.points,
      morningVisible(),
    ].join(":");
    if (key === renderKey) return; // nichts Relevantes geändert: Eingaben nicht zerstören
    const isNewQuestion = state.block_phase === "ask" && !you.answered;
    if (isNewQuestion) {
      rest = false;
      // Kein sichtbarer Startwert: Ein vorgegebener Wert würde als Anker die Schätzung verzerren.
      sliderPos = SLIDER_STEPS / 2;
      sliderTouched = false;
      if (navigator.vibrate) navigator.vibrate(120);
    } else if (wantsRest() && key !== renderKey) {
      rest = true;
    }
    renderKey = key;
    draw();
  }

  function draw() {
    if (rest) {
      document.body.classList.add("rest");
      app.innerHTML = '<p class="rest-text">Handy kann weg.<br>Antippen zum Aufwecken.</p>';
      return;
    }
    document.body.classList.remove("rest");
    const top =
      '<div class="top"><span class="dot" style="background:' + esc(me.color) + '"></span>' +
      esc(me.name) + "</div>";
    if (morningVisible()) {
      app.innerHTML = top + '<div class="body">' + morningHtml() + "</div>";
      bindMorning();
      return;
    }
    app.innerHTML =
      top + '<div class="body">' + bodyHtml() + '<p id="toast" class="toast"></p></div>' +
      (state ? footHtml() : "");
    bind();
  }

  function bind() {
    const slider = document.getElementById("slider");
    const valueEl = document.getElementById("value");
    if (slider && state.block) {
      const sendBtn = app.querySelector('[data-act="answer"]');
      const update = function () {
        sliderPos = Number(slider.value);
        valueEl.textContent = sliderTouched
          ? fmt(sliderValue(state.block, sliderPos)) + " " + state.block.unit
          : "Regler bewegen";
        if (sendBtn) sendBtn.disabled = !sliderTouched;
      };
      slider.addEventListener("input", function () {
        sliderTouched = true;
        update();
      });
      update();
    }
    app.querySelectorAll("[data-act]").forEach(function (el) {
      el.addEventListener("click", function () {
        const act = el.getAttribute("data-act");
        if (act === "answer") {
          send({ type: "answer", value: roundSig(sliderValue(state.block, sliderPos)) });
        } else if (act === "end_now") {
          if (confirm("Sendung jetzt beenden?")) send({ type: "end_now" });
        } else {
          send({ type: act });
          if (act === "skip_vote") toast("Überspringen vorgeschlagen.");
        }
      });
    });
    app.querySelectorAll("[data-choice]").forEach(function (el) {
      el.addEventListener("click", function () {
        send({ type: "answer", value: Number(el.getAttribute("data-choice")) });
      });
    });
    app.querySelectorAll("[data-signal]").forEach(function (el) {
      el.addEventListener("click", function () {
        send({ type: "signal", kind: el.getAttribute("data-signal") });
        toast("Notiert.");
      });
    });
  }

  document.addEventListener("click", function () {
    if (rest) {
      rest = false;
      draw();
    }
  });

  // ------------------------------------------------------------------ Start

  (async function init() {
    try {
      me = await api("GET", "/api/me");
    } catch (e) {
      showChooser();
      return;
    }
    connect();
    loadMorning();
  })();
})();
