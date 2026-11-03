/* TV-Bühne der Abendausgabe. ES2017, ohne Build-Schritt (decisions.md). */
(function () {
  "use strict";

  const DESIGN_WIDTH = 1920;
  const main = document.getElementById("main");
  const rundownEl = document.getElementById("rundown");
  const remainingEl = document.getElementById("remaining");
  const statusEl = document.getElementById("status");
  const nextBtn = document.getElementById("next");

  let ws = null;
  let retry = 0;
  let state = null;
  let screenKey = "";
  let deadlineAt = null;
  let player = null; // { video, hls, ended, failed } des laufenden Videoblocks

  function scale() {
    const width = window.innerWidth || document.documentElement.clientWidth || DESIGN_WIDTH;
    document.documentElement.style.fontSize = (width / DESIGN_WIDTH) * 16 + "px";
  }
  window.addEventListener("resize", scale);
  scale();

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmt(n) {
    const rounded = Number(Number(n).toPrecision(3));
    return rounded.toLocaleString("de-DE", { maximumFractionDigits: 2 });
  }

  function fmtAxis(n) {
    if (n >= 1e9) return fmt(n / 1e9) + " Mrd.";
    if (n >= 1e6) return fmt(n / 1e6) + " Mio.";
    return fmt(n);
  }

  // ------------------------------------------------------------ Verbindung

  function connect() {
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws/tv");
    ws.onopen = function () {
      retry = 0;
      statusEl.textContent = "";
    };
    ws.onmessage = function (event) {
      try {
        state = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      render();
    };
    ws.onclose = function () {
      statusEl.textContent = "Verbindung getrennt. Verbinde neu …";
      retry = Math.min(retry + 1, 5);
      setTimeout(connect, 500 * Math.pow(2, retry));
    };
  }

  function send(message) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(message));
  }

  // Tasten im Video (decisions.md Nr. 55): OK Pause, ◀ ▶ spulen, ▼ weiter, ▲ Ton.
  // Ein versehentliches OK soll die Nachrichten nicht überspringen.
  const KEYS = {
    ok: [13], up: [38], down: [40], left: [37], right: [39],
    rewind: [89, 227], forward: [90, 228], playPause: [179, 85], next: [176, 87],
  };
  const KEY_NAMES = {
    Enter: "ok", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
    MediaRewind: "rewind", MediaFastForward: "forward", MediaPlayPause: "playPause",
    MediaTrackNext: "next",
  };

  function keyOf(event) {
    if (KEY_NAMES[event.key]) return KEY_NAMES[event.key];
    for (const name in KEYS) if (KEYS[name].indexOf(event.keyCode) >= 0) return name;
    return "";
  }

  document.addEventListener("keydown", function (event) {
    const key = keyOf(event);
    if (player && key) {
      event.preventDefault();
      showChrome();
      if (key === "up") toggleSound();
      else if (key === "left" || key === "rewind") seek(-SEEK_BACK_S);
      else if (key === "right" || key === "forward") {
        if (player.ended || player.failed) send({ type: "ok" });
        else seek(SEEK_FORWARD_S);
      } else if (key === "down" || key === "next") send({ type: "ok" });
      else if (key === "playPause") togglePlay();
      else if (key === "ok") {
        if (player.ended || player.failed) send({ type: "ok" });
        else togglePlay();
      }
      return;
    }
    if (document.getElementById("embed") && key) {
      event.preventDefault();
      const el = document.getElementById("vid-screen");
      if (el) el.classList.add("chrome-on");
      if (key === "ok" || key === "down" || key === "right" || key === "next") send({ type: "ok" });
      return;
    }
    if (key === "ok") {
      event.preventDefault();
      send({ type: "ok" });
    }
  });
  // Klick statt Taste: für TV-Browser im Cursor-Modus (Tastenereignisse kommen dort nicht an).
  nextBtn.addEventListener("click", function (event) {
    event.preventDefault();
    send({ type: "ok" });
  });

  // ------------------------------------------------------------ Darstellung

  function peopleList(members, mode) {
    const items = members
      .filter(function (m) { return m.present; })
      .map(function (m) {
        const waiting = mode === "ask" && !m.answered;
        const tick = mode === "ask" && m.answered ? '<span class="tick">✓</span>' : "";
        return (
          '<li class="' + (waiting ? "waiting" : "") + '">' +
          '<span class="dot" style="background:' + esc(m.color) + '"></span>' +
          esc(m.name) + tick + "</li>"
        );
      });
    return '<ul class="people">' + items.join("") + "</ul>";
  }

  function renderSide() {
    const index = state.phase === "lobby" ? -1 : state.block_index;
    let remaining = 0;
    rundownEl.innerHTML = state.rundown
      .map(function (b, i) {
        let cls = "";
        if (state.phase === "ended" || i < index) cls = "done";
        else if (i === index) cls = "current";
        if (i > index && state.phase !== "ended") remaining += b.est_minutes || 0;
        const minutes = b.est_minutes ? '<span class="min">' + b.est_minutes + " min</span>" : "";
        return '<li class="' + cls + '">' + esc(b.title) + minutes + "</li>";
      })
      .join("");
    if (state.phase === "ended") remainingEl.textContent = "Fertig.";
    else if (remaining === 0) remainingEl.textContent = "Gleich Sendeschluss.";
    else remainingEl.textContent = "Noch etwa " + remaining + " Minuten.";
  }

  function renderLobby() {
    const anyone = state.members.some(function (m) { return m.present; });
    const joinUrl = location.origin + "/c/";
    const date = new Date().toLocaleDateString("de-DE", {
      weekday: "long", day: "numeric", month: "long",
    });
    return (
      '<div class="lobby screen"><div class="lobby-text">' +
      '<p class="kicker">' + esc(date) + "</p>" +
      "<h1>Abendausgabe</h1>" +
      '<p class="lead">' + (anyone ? "Dabei:" : "Noch niemand eingecheckt.") + "</p>" +
      peopleList(state.members, "lobby") +
      '<p class="hint">' +
      (anyone ? "Start mit „Weiter“ oder am Handy." : "Mit dem Handy einchecken.") +
      "</p></div>" +
      '<figure class="qr"><img alt="QR-Code zum Einchecken" src="/api/qr.svg?data=' +
      encodeURIComponent(joinUrl) + '"><figcaption>' + esc(location.host) + "/c/</figcaption></figure>" +
      "</div>"
    );
  }

  function renderInfo(block) {
    const credit = block.credit ? '<p class="credit">' + esc(block.credit) + "</p>" : "";
    if (block.media) {
      return (
        '<div class="screen"><p class="kicker">' + esc(block.title) + "</p>" +
        withMedia(block, '<p class="lead">' + esc(block.body || "") + "</p>" + credit) + "</div>"
      );
    }
    return (
      '<div class="screen"><h1>' + esc(block.title) + "</h1>" +
      '<p class="lead">' + esc(block.body || "") + "</p>" + credit +
      "</div>"
    );
  }

  // Mitbringsel aus offiziellen Playern (decisions.md Nr. 56). Der fremde Player bekommt
  // keinen Fokus, damit die Fernbedienung bei der Seite bleibt.
  function renderEmbed(block) {
    const credit = block.credit ? '<p class="vid-source">' + esc(block.credit) + "</p>" : "";
    return (
      '<div class="video-screen chrome-on embed-screen' + (block.vertical ? " vertical" : "") +
      '" id="vid-screen"><iframe id="embed" src="' + esc(block.src) + '" tabindex="-1" ' +
      'allow="autoplay; encrypted-media; picture-in-picture; fullscreen" ' +
      'referrerpolicy="strict-origin-when-cross-origin" title="' + esc(block.caption || block.title) + '"></iframe>' +
      '<div class="vid-top"><p class="kicker">' + esc(block.title) + " · " + esc(block.attribution || "") + "</p>" +
      (block.caption ? '<p class="vid-source">' + esc(block.caption) + "</p>" : "") + credit + "</div>" +
      '<div class="vid-bottom"><span class="vid-hint">OK oder ▼: Weiter</span></div></div>'
    );
  }

  let embedTimer = null;

  function startEmbed() {
    clearTimeout(embedTimer);
    embedTimer = setTimeout(function () {
      const el = document.getElementById("vid-screen");
      if (el) el.classList.remove("chrome-on");
    }, 6000);
    // Fokus bei der Seite halten, auch wenn der Player ihn an sich zieht
    window.addEventListener("blur", refocus);
  }

  function refocus() {
    if (!document.getElementById("embed")) {
      window.removeEventListener("blur", refocus);
      return;
    }
    setTimeout(function () { window.focus(); }, 50);
  }

  function optionList(block) {
    const letters = "ABCDEFGH";
    return (
      '<ul class="options">' +
      block.options
        .map(function (o, i) {
          return '<li><span class="letter">' + letters[i] + "</span>" + esc(o) + "</li>";
        })
        .join("") +
      "</ul>"
    );
  }

  // Bild und Originalschlagzeile (Weltblick): links das Bild, rechts Text und Antworten.
  function withMedia(block, inner) {
    if (!block.media || block.media.kind !== "image") return inner;
    if (block.media.large) {
      return '<div class="media-big"><img src="' + esc(block.media.src) + '" alt=""></div>' + inner;
    }
    const lang = block.caption_lang ? ' lang="' + esc(block.caption_lang) + '"' : "";
    return (
      '<div class="media-split"><div class="media-pic"><img src="' + esc(block.media.src) +
      '" alt="" referrerpolicy="no-referrer"></div><div class="media-text">' +
      (block.caption ? '<p class="caption" dir="auto"' + lang + ">" + esc(block.caption) + "</p>" : "") +
      inner + "</div></div>"
    );
  }

  function renderAsk(block) {
    const body =
      block.type === "choice"
        ? optionList(block)
        : '<p class="lead">Schätzt auf dem Handy, in ' + esc(block.unit) + ".</p>";
    return (
      '<div class="screen"><p class="kicker">' + esc(block.title) + "</p>" +
      withMedia(block, '<h1 class="' + (block.media ? "q-small" : "") + '">' + esc(block.question) + "</h1>" + body) +
      peopleList(state.members, "ask") +
      '<p class="countdown" id="countdown"></p></div>'
    );
  }

  function estimateAxis(block, answers) {
    const W = 1000;
    const H = 260;
    const pad = 40;
    const lo = Number(block.min);
    const hi = Number(block.max);
    const useLog = block.log !== false;
    function x(v) {
      const t = useLog
        ? (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))
        : (v - lo) / (hi - lo);
      return pad + Math.max(0, Math.min(1, t)) * (W - 2 * pad);
    }
    let svg =
      '<svg class="axis" viewBox="0 0 ' + W + " " + H + '" role="img">' +
      '<line x1="' + pad + '" y1="150" x2="' + (W - pad) + '" y2="150" stroke="#2e4560" stroke-width="3"/>';
    const ticks = [];
    if (useLog) {
      for (let p = Math.ceil(Math.log10(lo)); p <= Math.floor(Math.log10(hi)); p++) {
        ticks.push(Math.pow(10, p));
      }
    } else {
      for (let i = 0; i <= 4; i++) ticks.push(lo + ((hi - lo) * i) / 4);
    }
    ticks.forEach(function (t) {
      svg +=
        '<line x1="' + x(t) + '" y1="142" x2="' + x(t) + '" y2="158" stroke="#2e4560" stroke-width="3"/>' +
        '<text x="' + x(t) + '" y="192" font-size="26" text-anchor="middle">' + esc(fmtAxis(t)) + "</text>";
    });
    answers.forEach(function (a, i) {
      const y = i % 2 === 0 ? 112 : 70;
      svg +=
        '<g class="pin" style="transition-delay:' + i * 350 + 'ms">' +
        '<line x1="' + x(a.value) + '" y1="' + (y + 10) + '" x2="' + x(a.value) + '" y2="150" stroke="' + esc(a.color) + '" stroke-width="3"/>' +
        '<circle cx="' + x(a.value) + '" cy="' + y + '" r="11" fill="' + esc(a.color) + '"/>' +
        '<text x="' + x(a.value) + '" y="' + (y - 18) + '" font-size="26" text-anchor="middle" style="fill:' + esc(a.color) + '">' + esc(a.name) + "</text>" +
        "</g>";
    });
    const tx = x(Number(block.truth));
    svg +=
      '<g class="truth" style="transition-delay:' + (answers.length * 350 + 500) + 'ms">' +
      '<line x1="' + tx + '" y1="20" x2="' + tx + '" y2="165" stroke="#ffffff" stroke-width="4"/>' +
      '<text x="' + tx + '" y="238" font-size="32" font-weight="700" text-anchor="middle" style="fill:#ffffff">' +
      esc(Number(block.truth).toLocaleString("de-DE") + " " + block.unit) + "</text></g>";
    return svg + "</svg>";
  }

  function resultList(answers) {
    return (
      '<ul class="results">' +
      answers
        .map(function (a) {
          return (
            '<li><span class="dot" style="background:' + esc(a.color) + '"></span>' +
            esc(a.name) + ": " + a.points + "</li>"
          );
        })
        .join("") +
      "</ul>"
    );
  }

  function renderReveal(block, reveal) {
    const answers = reveal.answers;
    let body = "";
    if (block.type === "estimate") {
      body = estimateAxis(block, answers) + resultList(answers);
    } else {
      const letters = "ABCDEFGH";
      body =
        '<ul class="options choice-result">' +
        block.options
          .map(function (option, i) {
            const pickers = answers
              .filter(function (a) { return a.value === i; })
              .map(function (a, j) {
                return (
                  '<span class="pin" style="transition-delay:' + j * 250 + 'ms">' +
                  '<span class="dot" style="background:' + esc(a.color) + '"></span></span>'
                );
              })
              .join("");
            const mark =
              i === block.correct
                ? '<span class="truth correct-mark" style="transition-delay:' +
                  (answers.length * 250 + 500) + 'ms">✓ richtig</span>'
                : "";
            return '<li><span class="letter">' + letters[i] + "</span>" + esc(option) + " " + pickers + mark + "</li>";
          })
          .join("") +
        "</ul>";
    }
    const label = block.source_label != null ? block.source_label : "Quelle: ";
    const source = block.source ? '<p class="source">' + esc(label + block.source) + "</p>" : "";
    return (
      '<div class="screen" id="reveal"><p class="kicker">Auflösung</p>' +
      withMedia(block, '<h1 class="' + (block.media ? "q-small" : "") + '">' + esc(block.question) + "</h1>" + body + source) +
      "</div>"
    );
  }

  function renderEnded() {
    const scores = (state.scores || [])
      .map(function (row) {
        return (
          '<li><span class="dot" style="background:' + esc(row.color) + '"></span>' +
          esc(row.name) + '<span class="pts">' + row.points + " Punkte</span></li>"
        );
      })
      .join("");
    return (
      '<div class="ended screen"><h1>Sendeschluss</h1>' +
      '<p class="lead">Das war die Abendausgabe.</p>' +
      (scores ? '<ul class="scores">' + scores + "</ul>" : "") +
      '<p class="hint">Der Fernseher gehört jetzt euch: Netflix, Prime oder aus.</p></div>'
    );
  }

  // ------------------------------------------------------------ Video

  let hlsLoading = null;

  function loadHls() {
    if (window.Hls) return Promise.resolve(window.Hls);
    if (hlsLoading) return hlsLoading;
    hlsLoading = new Promise(function (resolve, reject) {
      const script = document.createElement("script");
      script.src = "/shared/vendor/hls-1.7.3.min.js";
      script.onload = function () { resolve(window.Hls); };
      script.onerror = function () { hlsLoading = null; reject(new Error("hls.js nicht geladen")); };
      document.head.appendChild(script);
    });
    return hlsLoading;
  }

  // Vollbild: Titel und Bedienhinweis blenden nach einigen Sekunden aus und kommen
  // bei jeder Taste, bei Pause und am Ende zurück. Die Quelle bleibt oben links klein sichtbar.
  function renderVideo(block) {
    const source = block.attribution ? "Quelle: " + esc(block.attribution) : "";
    return (
      '<div class="video-screen chrome-on" id="vid-screen">' +
      '<video id="vid" playsinline preload="auto"></video>' +
      '<div class="vid-top"><p class="kicker" id="vid-title">' + esc(block.title) + "</p>" +
      '<p id="vid-source" class="vid-source">' + source + "</p>" +
      (block.credit ? '<p class="vid-source">' + esc(block.credit) + "</p>" : "") + "</div>" +
      '<p id="vid-msg" class="vid-msg">Lädt …</p>' +
      '<p id="vid-flash" class="vid-flash"></p>' +
      '<div class="vid-progress"><span id="vid-time" class="vid-time"></span>' +
      '<div class="vid-track"><div id="vid-bar" class="vid-bar"></div></div></div>' +
      (block.caption
        ? '<p class="vid-caption" dir="auto"' + (block.caption_lang ? ' lang="' + esc(block.caption_lang) + '"' : "") + ">" +
          esc(block.caption) + "</p>"
        : "") +
      '<div class="vid-bottom"><span id="vid-hint" class="vid-hint">' +
      hintText(!!block.muted, "") + "</span></div>" +
      "</div>"
    );
  }

  let chromeTimer = null;

  function showChrome() {
    const el = document.getElementById("vid-screen");
    if (!el) return;
    el.classList.add("chrome-on");
    nextBtn.hidden = false;
    clearTimeout(chromeTimer);
    chromeTimer = setTimeout(function () {
      if (!player || player.video.paused || player.ended || player.failed) return;
      el.classList.remove("chrome-on");
      nextBtn.hidden = true;
    }, 5000);
  }

  function report(status, extra) {
    const msg = { type: "media", block: state && state.block ? state.block.id : "", status: status };
    if (extra) for (const k in extra) msg[k] = extra[k];
    send(msg);
  }

  function setMsg(text) {
    const el = document.getElementById("vid-msg");
    if (!el) return;
    el.textContent = text || "";
    el.style.opacity = text ? "1" : "0";
    if (text) showChrome();
  }

  // Zeitpunkt der Sendung, der gerade läuft (ms), für Livestreams mit Anfang und Ende.
  function positionDate() {
    if (!player) return null;
    if (player.hls && player.hls.playingDate) return player.hls.playingDate.getTime();
    if (player.dateOffset != null) return player.video.currentTime * 1000 + player.dateOffset;
    return null;
  }

  function stopPlayer() {
    if (!player) return;
    clearTimeout(chromeTimer);
    if (player.hls) player.hls.destroy();
    try { player.video.pause(); } catch (e) { /* schon weg */ }
    player.video.removeAttribute("src");
    player = null;
  }

  const SEEK_BACK_S = 15;
  const SEEK_FORWARD_S = 30;

  function hintText(muted, mode) {
    return (mode ? mode + " · " : "") + (muted ? "▲ Ton an · " : "") +
      "OK: Pause · ◀ ▶ Spulen · ▼ Weiter";
  }

  function toggleSound() {
    player.video.muted = !player.video.muted;
    const hint = document.getElementById("vid-hint");
    if (hint) hint.textContent = hintText(player.video.muted, player.endAt ? "Zeitversetzt" : "");
    flash(player.video.muted ? "Ton aus" : "Ton an");
  }

  function flash(text) {
    const el = document.getElementById("vid-flash");
    if (!el) return;
    el.textContent = text;
    el.classList.add("on");
    clearTimeout(flash.timer);
    flash.timer = setTimeout(function () { el.classList.remove("on"); }, 900);
  }

  // Spielbereich in Sekunden: bei zeitversetzter Sendung ab Sendebeginn, sonst die Datei
  function bounds() {
    const v = player.video;
    let lo = 0;
    let hi = isFinite(v.duration) ? v.duration - 1 : v.currentTime;
    if (v.seekable && v.seekable.length) {
      lo = v.seekable.start(0);
      hi = v.seekable.end(v.seekable.length - 1) - 3; // nicht ganz an die Live-Kante
    }
    const at = positionDate();
    if (player.startAt && at != null) {
      lo = Math.max(lo, v.currentTime - (at - player.startAt * 1000) / 1000);
    }
    return [lo, Math.max(lo, hi)];
  }

  function seek(delta) {
    const v = player.video;
    const range = bounds();
    v.currentTime = Math.max(range[0], Math.min(v.currentTime + delta, range[1]));
    flash((delta > 0 ? "+" : "−") + Math.abs(delta) + " s");
    updateTime();
  }

  function mmss(sec) {
    sec = Math.max(0, Math.floor(sec));
    return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
  }

  function updateTime() {
    const el = document.getElementById("vid-time");
    if (!el || !player) return;
    const v = player.video;
    const at = positionDate();
    let now = v.currentTime;
    let total = isFinite(v.duration) ? v.duration : 0;
    if (player.startAt && at != null) {
      now = (at - player.startAt * 1000) / 1000;
      total = player.endAt ? player.endAt - player.startAt : 0;
    }
    el.textContent = total ? mmss(now) + " / " + mmss(total) : "";
    const bar = document.getElementById("vid-bar");
    if (bar) bar.style.transform = "scaleX(" + (total ? Math.min(1, now / total) : 0) + ")";
  }

  function togglePlay() {
    if (!player) return;
    if (player.video.paused) {
      const p = player.video.play();
      if (p && p.catch) p.catch(function () { setMsg("Abspielen nicht möglich. Weiter mit ▶."); });
    } else {
      player.video.pause();
    }
  }

  function playFile(video, src) {
    video.src = src;
    return "mp4";
  }

  // Nativ (ohne Sprung an den Anfang): Position über seekable schätzen.
  function playHlsNative(video, media) {
    video.src = media.src;
    video.addEventListener("loadedmetadata", function once() {
      video.removeEventListener("loadedmetadata", once);
      if (!player || player.video !== video || !video.seekable.length) return;
      const edge = video.seekable.end(video.seekable.length - 1);
      let target = edge;
      if (media.start_at) {
        target = Math.max(video.seekable.start(0), edge - (Date.now() / 1000 - media.start_at));
        video.currentTime = target;
        player.dateOffset = media.start_at * 1000 - target * 1000;
      } else {
        player.dateOffset = Date.now() - edge * 1000;
      }
    });
    return "hls-nativ";
  }

  function playHls(media) {
    const video = player.video;
    const mine = player;
    const native = video.canPlayType("application/vnd.apple.mpegurl");
    // hls.js zuerst: Der eingebaute Player meldete am Fernseher und im Desktop-Chrome
    // Fehler 4 (decisions.md Nr. 53). Nativ nur, wenn hls.js fehlt oder MSE nicht geht.
    return loadHls().catch(function () { return null; }).then(function (Hls) {
      if (mine !== player) return "abgebrochen";
      if (!Hls || !Hls.isSupported()) {
        if (native) return playHlsNative(video, media);
        throw new Error("HLS wird hier nicht unterstützt");
      }
      const hls = new Hls({ maxBufferLength: 30, subtitleDisplay: false });
      player.hls = hls;
      if (media.start_at) {
        // Erste Playlist abwarten, dann an den Sendebeginn springen (Sendezeit je Segment).
        hls.once(Hls.Events.LEVEL_LOADED, function (_e, data) {
          const frags = (data && data.details && data.details.fragments) || [];
          const first = frags[0];
          let pos = -1;
          if (first && first.programDateTime) {
            pos = Math.max(first.start, first.start + (media.start_at * 1000 - first.programDateTime) / 1000);
          }
          hls.stopLoad();
          hls.startLoad(pos);
        });
      }
      hls.on(Hls.Events.ERROR, function (_e, data) {
        if (!data || !data.fatal) return;
        report("error", { via: "hls.js", error: String(data.details || data.type) });
        hls.destroy();
        player.hls = null;
        if (media.fallback_src) {
          setMsg("Livestream gestört, zeige die letzte Kurzfassung.");
          player.endAt = null;
          playFile(video, media.fallback_src);
          video.play().catch(function () {});
        } else {
          player.failed = true;
          setMsg("Livestream gestört. Weiter mit OK.");
        }
      });
      hls.loadSource(media.src);
      hls.attachMedia(video);
      return "hls.js";
    });
  }

  function startVideo(block) {
    const video = document.getElementById("vid");
    if (!video) return;
    player = {
      video: video, hls: null, ended: false, failed: false, endAt: null, startAt: null, dateOffset: null,
    };
    video.muted = !!block.muted;
    if (block.poster) video.poster = block.poster;
    if (block.vertical) video.classList.add("vertical");
    const mine = player;
    let via = "";

    video.addEventListener("playing", function () {
      setMsg("");
      showChrome();
      report("playing", { via: via });
    });
    video.addEventListener("pause", function () {
      if (!mine.ended && mine === player) setMsg("Pause. OK spielt weiter.");
    });
    video.addEventListener("ended", function () {
      mine.ended = true;
      setMsg("Ende. Weiter mit OK.");
      report("ended", { via: via });
    });
    // Livestream: am Ende der Sendung anhalten, statt ins nächste Programm zu laufen.
    video.addEventListener("seeking", function () {
      if (mine !== player || !mine.ended) return;
      mine.ended = false; // zurückgespult: Das Ende gilt nicht mehr
      setMsg("");
    });
    video.addEventListener("timeupdate", function () {
      if (mine === player) updateTime();
      if (mine !== player || mine.ended || !mine.endAt) return;
      const at = positionDate();
      if (at == null || at < mine.endAt * 1000) return;
      mine.ended = true;
      video.pause();
      setMsg("Ende der Sendung. Weiter mit OK.");
      report("ended", { via: via });
    });
    video.addEventListener("error", function () {
      if (mine !== player || mine.hls) return; // hls.js meldet selbst
      mine.failed = true;
      setMsg("Video lässt sich nicht abspielen. Weiter mit OK.");
      report("error", { via: via, error: String(video.error && video.error.code) });
    });

    function begin(media) {
      if (mine !== player) return;
      const title = document.getElementById("vid-title");
      if (title && media.title) title.textContent = media.title;
      const src = document.getElementById("vid-source");
      if (src && media.attribution) src.textContent = "Quelle: " + media.attribution;
      const hint = document.getElementById("vid-hint");
      if (hint && media.end_at) {
        hint.textContent = hintText(player.video.muted, media.live ? "Live" : "Zeitversetzt");
      }
      mine.endAt = media.end_at || null;
      mine.startAt = media.start_at || null;
      const ready = media.format === "hls" ? playHls(media) : Promise.resolve(playFile(video, media.src));
      ready
        .then(function (how) {
          via = how;
          const p = video.play();
          if (p && p.catch) p.catch(function () { setMsg("OK drücken zum Abspielen."); });
        })
        .catch(function (err) {
          report("error", { via: "hls", error: String(err && err.message) });
          if (media.fallback_src) {
            via = "mp4-rückfall";
            playFile(video, media.fallback_src);
            video.play().catch(function () { setMsg("OK drücken zum Abspielen."); });
          } else {
            mine.failed = true;
            setMsg("Livestream geht auf diesem Gerät nicht. Weiter mit OK.");
          }
        });
    }

    if (block.media) {
      fetch("/api/media/" + encodeURIComponent(block.media))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data && data.media) begin(data.media);
          else {
            mine.failed = true;
            setMsg(((data && data.error) || "Heute nicht verfügbar.") + " Weiter mit OK.");
          }
        })
        .catch(function () {
          mine.failed = true;
          setMsg("Server nicht erreichbar. Weiter mit OK.");
        });
    } else {
      begin({ format: block.format || "mp4", src: block.src, title: block.title, attribution: block.attribution });
    }
  }

  function updateCountdown() {
    const el = document.getElementById("countdown");
    if (!el || deadlineAt === null) return;
    const seconds = Math.max(0, Math.ceil((deadlineAt - Date.now()) / 1000));
    el.textContent = "Noch " + seconds + " Sekunden";
  }
  setInterval(updateCountdown, 250);

  function render() {
    if (!state) return;
    renderSide();
    const anyone = state.members.some(function (m) { return m.present; });
    nextBtn.hidden = state.phase === "ended" || (state.phase === "lobby" && !anyone);
    deadlineAt = state.seconds_left == null ? null : Date.now() + state.seconds_left * 1000;
    const block = state.block;
    let html = "";
    let key = state.phase + ":" + state.block_index + ":" + state.block_phase;
    const isVideo = state.block_phase === "show" && block && block.type === "video";
    const isEmbed = state.block_phase === "show" && block && block.type === "embed";
    if (isEmbed && key === screenKey && document.getElementById("embed")) return;
    if (isVideo && key === screenKey && player) {
      // Laufendes Video nicht neu aufbauen, nur die Seitenleiste aktualisieren.
      return;
    }
    stopPlayer();
    document.body.classList.toggle("video-mode", !!(isVideo || isEmbed));
    if (state.phase === "lobby") html = renderLobby();
    else if (state.phase === "ended") html = renderEnded();
    else if (isVideo) html = renderVideo(block);
    else if (isEmbed) html = renderEmbed(block);
    else if (state.block_phase === "show") html = renderInfo(block);
    else if (state.block_phase === "ask") html = renderAsk(block);
    else if (state.block_phase === "reveal") html = renderReveal(block, state.reveal);

    const isNewScreen = key !== screenKey;
    screenKey = key;
    main.innerHTML = html;
    if (!isNewScreen && main.firstElementChild) {
      main.firstElementChild.style.webkitAnimation = "none";
      main.firstElementChild.style.animation = "none";
    }
    updateCountdown();
    if (isVideo) {
      startVideo(block);
      showChrome();
    }
    if (isEmbed) startEmbed();

    const reveal = document.getElementById("reveal");
    if (reveal) {
      if (isNewScreen) {
        // Zwei Frames warten, damit die Übergänge sicher starten.
        requestAnimationFrame(function () {
          requestAnimationFrame(function () { reveal.classList.add("in"); });
        });
      } else {
        reveal.classList.add("in");
      }
    }
  }

  connect();
})();
