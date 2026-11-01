/* TV-Fähigkeitstest (SPEC §11.2). Bewusst ES5: läuft auch dort, wo moderne Syntax scheitert. */
(function () {
  "use strict";

  var FONT = '32px "Atkinson Hyperlegible Next"';
  var report = { ua: navigator.userAgent, startedAt: new Date().toISOString(), media: {} };
  var logEl = document.getElementById("log");
  var stepEl = document.getElementById("step");
  var mediaEl = document.getElementById("media");
  var started = false;
  var reportId = null;
  // Manche TV-Browser (z. B. Opera-basierte) bewegen mit den Pfeiltasten einen Mauszeiger,
  // statt Tastenereignisse an die Seite zu geben. Das wird hier mitgezählt.
  var pointer = { moves: 0, clicks: 0 };
  report.pointer = pointer;
  document.addEventListener("mousemove", function () { if (started) pointer.moves += 1; }, true);
  document.addEventListener("click", function () { if (started) pointer.clicks += 1; }, true);

  function setStep(text) {
    stepEl.innerHTML = "";
    stepEl.appendChild(document.createTextNode(text));
  }

  function log(label, ok, detail) {
    var li = document.createElement("li");
    var mark = ok === true ? "\u2713 " : ok === false ? "\u2717 " : "\u2022 ";
    li.className = ok === true ? "ok" : ok === false ? "fail" : "info";
    li.appendChild(document.createTextNode(mark + label + (detail ? " \u2013 " + detail : "")));
    logEl.appendChild(li);
    window.scrollTo(0, document.body.scrollHeight);
  }

  function request(method, url, body, done) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.timeout = 20000;
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      var data = null;
      try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
      done(xhr.status, data);
    };
    xhr.ontimeout = function () { done(0, null); };
    xhr.send(body ? JSON.stringify(body) : null);
  }

  function syntaxOk(source) {
    try { new Function(source); return true; } catch (e) { return false; }
  }

  function once(fn) {
    var called = false;
    return function () {
      if (called) return;
      called = true;
      fn.apply(null, arguments);
    };
  }

  // ---------------------------------------------------------------- Schritte

  function basics(next) {
    report.screen = {
      width: screen.width, height: screen.height,
      innerWidth: window.innerWidth, innerHeight: window.innerHeight,
      dpr: window.devicePixelRatio || 1
    };
    log("Bildschirm", null, report.screen.innerWidth + "\u00d7" + report.screen.innerHeight +
      " (DPR " + report.screen.dpr + ")");
    log("Browser", null, navigator.userAgent);
    next();
  }

  function jsFeatures(next) {
    report.js = {
      es2017: syntaxOk("async function f(){ await 1; }"),
      es2020: syntaxOk("var a = {}; var b = a?.x ?? 1;"),
      fetch: typeof window.fetch === "function",
      promise: typeof window.Promise === "function"
    };
    log("JavaScript ES2017", report.js.es2017);
    log("JavaScript ES2020", report.js.es2020);
    log("fetch und Promise", report.js.fetch && report.js.promise);
    next();
  }

  function cssFeatures(next) {
    var supports = window.CSS && typeof window.CSS.supports === "function";
    report.css = {
      flex: supports ? window.CSS.supports("display", "flex") : false,
      grid: supports ? window.CSS.supports("display", "grid") : false
    };
    log("CSS Flexbox", report.css.flex);
    log("CSS Grid", report.css.grid);
    next();
  }

  function websocketTest(next) {
    if (!window.WebSocket) {
      report.websocket = { ok: false, detail: "nicht vorhanden" };
      log("WebSocket", false, "nicht vorhanden");
      return next();
    }
    var startedAt = new Date().getTime();
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    var socket;
    var finish = once(function (ok, detail) {
      clearTimeout(timer);
      try { socket.close(); } catch (e) { /* egal */ }
      report.websocket = { ok: ok, detail: detail };
      log("WebSocket", ok, detail);
      next();
    });
    var timer = setTimeout(function () { finish(false, "Zeitüberschreitung"); }, 6000);
    try {
      socket = new WebSocket(proto + location.host + "/ws/echo");
    } catch (e) {
      return finish(false, String(e));
    }
    socket.onopen = function () { socket.send("ping"); };
    socket.onmessage = function (ev) {
      finish(ev.data === "ping", (new Date().getTime() - startedAt) + " ms");
    };
    socket.onerror = function () { finish(false, "Verbindungsfehler"); };
  }

  function fontTest(next) {
    var finish = once(function (ok, detail) {
      report.font = { ok: ok, detail: detail };
      log("Webfont", ok, detail);
      next();
    });
    if (!document.fonts || !document.fonts.load) return finish(false, "document.fonts fehlt");
    setTimeout(function () { finish(false, "Zeitüberschreitung"); }, 6000);
    document.fonts.load(FONT).then(function () {
      finish(document.fonts.check(FONT), "");
    }, function () { finish(false, "Laden fehlgeschlagen"); });
  }

  function mediaInfo(next) {
    setStep("Hole Testvideos von der Tagesschau …");
    request("GET", "/api/tv-check/media", null, function (status, data) {
      report.mediaUrls = data || {};
      if (status !== 200 || !data) log("Testvideos", false, "Server antwortet nicht (" + status + ")");
      else if (data.error) log("Testvideos", false, data.error);
      else log("Testvideos gefunden", true, (data.mp4 ? "MP4 " : "") + (data.hls ? "HLS" : ""));
      next();
    });
  }

  function playTest(url, label, done) {
    var video = document.createElement("video");
    video.muted = true;
    video.setAttribute("muted", "");
    video.setAttribute("playsinline", "");
    mediaEl.appendChild(video);
    var finish = once(function (ok, detail) {
      clearTimeout(timer);
      try { video.pause(); } catch (e) { /* egal */ }
      if (video.parentNode) video.parentNode.removeChild(video);
      log(label, ok, detail);
      done(ok, detail);
    });
    var timer = setTimeout(function () { finish(false, "spielt nicht innerhalb von 20 s"); }, 20000);
    video.addEventListener("playing", function () { finish(true, "spielt"); });
    video.addEventListener("timeupdate", function () {
      if (video.currentTime > 0.2) finish(true, "spielt");
    });
    video.addEventListener("error", function () {
      finish(false, "Fehlercode " + (video.error ? video.error.code : "?"));
    });
    video.src = url;
    var promise = video.play();
    if (promise && typeof promise.then === "function") {
      promise.then(null, function (err) { log(label + " (play)", null, String(err)); });
    }
  }

  function mp4Test(next) {
    var probe = document.createElement("video");
    var can = probe.canPlayType ? probe.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"') : "";
    var url = report.mediaUrls && report.mediaUrls.mp4;
    report.media.mp4 = { canPlayType: can, ok: false, tested: !!url };
    if (!url) {
      log("MP4", null, "nicht getestet: kein Testvideo verfügbar");
      return next();
    }
    setStep("Teste MP4-Wiedergabe …");
    playTest(url, "MP4-Wiedergabe", function (ok, detail) {
      report.media.mp4.ok = ok;
      report.media.mp4.detail = detail;
      next();
    });
  }

  function hlsTest(next) {
    var probe = document.createElement("video");
    var native = probe.canPlayType ? probe.canPlayType("application/vnd.apple.mpegurl") : "";
    var mse = !!(window.MediaSource && window.MediaSource.isTypeSupported &&
      window.MediaSource.isTypeSupported('video/mp4; codecs="avc1.42E01E,mp4a.40.2"'));
    var url = report.mediaUrls && report.mediaUrls.hls;
    report.media.mse = mse;
    report.media.hls_native = { canPlayType: native, ok: false, tested: !!(native && url) };
    log("MediaSource (für hls.js)", mse);
    if (!native || !url) {
      log("HLS nativ", native ? null : false, native ? "nicht getestet: kein Testvideo" : "nicht unterstützt");
      return hlsJsTest(mse, url, next);
    }
    setStep("Teste HLS-Livestream …");
    playTest(url, "HLS nativ", function (ok, detail) {
      report.media.hls_native.ok = ok;
      report.media.hls_native.detail = detail;
      hlsJsTest(mse, url, next);
    });
  }

  // Livestream über hls.js, so wie ihn der tagesschau-Block abspielt (decisions.md Nr. 38)
  function hlsJsTest(mse, url, next) {
    report.media.hls_js = { ok: false, tested: false };
    if (!mse || !url) {
      log("HLS über hls.js", null, !url ? "nicht getestet: kein Testvideo" : "ohne MediaSource nicht möglich");
      return next();
    }
    setStep("Teste Livestream über hls.js …");
    var script = document.createElement("script");
    var finished = false;
    function done(ok, detail) {
      if (finished) return;
      finished = true;
      report.media.hls_js.tested = true;
      report.media.hls_js.ok = ok;
      report.media.hls_js.detail = detail;
      if (!ok) log("HLS über hls.js", false, detail);
      next();
    }
    script.onerror = function () { done(false, "hls.js nicht geladen"); };
    script.onload = function () {
      var Hls = window.Hls;
      if (!Hls || !Hls.isSupported()) return done(false, "hls.js: nicht unterstützt");
      report.media.hls_js.version = Hls.version;
      var video = document.createElement("video");
      var hls = new Hls({ maxBufferLength: 10 });
      video.muted = true;
      video.setAttribute("muted", "");
      video.setAttribute("playsinline", "");
      mediaEl.appendChild(video);
      var timer = setTimeout(function () { finish(false, "spielt nicht innerhalb von 20 s"); }, 20000);
      function finish(ok, detail) {
        clearTimeout(timer);
        try { hls.destroy(); } catch (e) { /* egal */ }
        if (video.parentNode) video.parentNode.removeChild(video);
        if (ok) log("HLS über hls.js " + Hls.version, true, detail);
        done(ok, detail);
      }
      hls.on(Hls.Events.ERROR, function (event, data) {
        if (data && data.fatal) finish(false, "Fehler " + data.details);
      });
      video.addEventListener("timeupdate", function () {
        if (video.currentTime > 0.2) finish(true, "spielt");
      });
      hls.loadSource(url);
      hls.attachMedia(video);
      var p = video.play();
      if (p && typeof p.then === "function") p.then(null, function () { /* timeupdate entscheidet */ });
    };
    script.src = "/shared/vendor/hls-1.7.3.min.js";
    document.head.appendChild(script);
  }

  function youtubeTest(next) {
    setStep("Teste YouTube-Einbettung …");
    var videoId = (report.mediaUrls && report.mediaUrls.youtube_id) || "jNQXAC9IVRw";
    var player = null;
    var finish = once(function (ok, detail) {
      clearTimeout(timer);
      try { if (player && player.destroy) player.destroy(); } catch (e) { /* egal */ }
      report.youtube = { ok: ok, detail: detail };
      log("YouTube-Einbettung", ok, detail);
      next();
    });
    var timer = setTimeout(function () { finish(false, "spielt nicht innerhalb von 25 s"); }, 25000);
    window.onYouTubeIframeAPIReady = function () {
      try {
        player = new window.YT.Player("yt", {
          width: 480, height: 270, videoId: videoId,
          playerVars: { autoplay: 1, mute: 1, playsinline: 1, rel: 0 },
          events: {
            onReady: function (e) { e.target.mute(); e.target.playVideo(); },
            onStateChange: function (e) { if (e.data === 1) finish(true, "spielt"); },
            onError: function (e) { finish(false, "Fehlercode " + e.data); }
          }
        });
      } catch (e) {
        finish(false, String(e));
      }
    };
    var script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    script.onerror = function () { finish(false, "Player-Skript nicht ladbar"); };
    document.body.appendChild(script);
  }

  function fpsTest(next) {
    setStep("Messe Grafikleistung …");
    var box = document.getElementById("box");
    box.style.display = "block";
    var raf = window.requestAnimationFrame || window.webkitRequestAnimationFrame ||
      function (cb) { return setTimeout(function () { cb(new Date().getTime()); }, 16); };
    var frames = 0;
    var start = null;
    function step(ts) {
      if (start === null) start = ts;
      frames += 1;
      var elapsed = ts - start;
      var offset = Math.sin(elapsed / 300) * 300;
      box.style.webkitTransform = "translateX(" + offset + "px)";
      box.style.transform = "translateX(" + offset + "px)";
      if (elapsed < 3000) {
        raf(step);
      } else {
        box.style.display = "none";
        report.fps = Math.round((frames * 1000) / elapsed);
        log("Grafik", report.fps >= 30, report.fps + " Bilder/s");
        next();
      }
    }
    raf(step);
  }

  function submitReport(next) {
    setStep("Sende Bericht …");
    request("POST", "/api/tv-check", report, function (status, data) {
      if (status === 200 && data) {
        reportId = data.id;
        showVerdict(data.verdict);
      } else {
        log("Bericht senden", false, "Status " + status);
      }
      next();
    });
  }

  function keyPhase(labels, done) {
    var keys = [];
    var index = 0;
    var timer = null;
    // Kurz unempfindlich, damit das Loslassen der Start-Taste nicht als erste Antwort zählt.
    var armedAt = new Date().getTime() + 600;
    try {
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
      window.focus();
    } catch (e) { /* egal */ }
    function finish() {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("keyup", onKeyUp, true);
      done(keys);
    }
    function ask() {
      if (index >= labels.length) return finish();
      setStep("Tastentest: Bitte \u201e" + labels[index] + "\u201c drücken (12 s).");
      timer = setTimeout(function () {
        keys.push({ label: labels[index], missed: true });
        log("Taste " + labels[index], false, "nicht erkannt");
        index += 1;
        ask();
      }, 12000);
    }
    function record(e, via) {
      if (index >= labels.length || new Date().getTime() < armedAt) return;
      if (e.preventDefault) e.preventDefault();
      clearTimeout(timer);
      keys.push({ label: labels[index], key: e.key || null, keyCode: e.keyCode, via: via });
      log("Taste " + labels[index], true, via + ": key=" + (e.key || "?") + ", keyCode=" + e.keyCode);
      index += 1;
      ask();
    }
    function onKey(e) { record(e, "keydown"); }
    // Falls ein Browser nur keyup liefert, zählt auch das.
    function onKeyUp(e) {
      var last = keys.length ? keys[keys.length - 1] : null;
      if (last && !last.missed && last.keyCode === e.keyCode) return;
      record(e, "keyup");
    }
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("keyup", onKeyUp, true);
    ask();
  }

  function keysMain(next) {
    keyPhase(["Pfeil hoch", "Pfeil runter", "Pfeil links", "Pfeil rechts", "OK"], function (keys) {
      report.keys = keys;
      next();
    });
  }

  function keysBack(next) {
    // In der eigenen TV-App öffnet „Zurück“ das App-Menü und erreicht die Seite absichtlich nicht.
    if (navigator.userAgent.indexOf("AbendausgabeTV") !== -1) {
      log("Taste Zurück", null, "in der App belegt (Menü), nicht getestet");
      return sendKeys(next);
    }
    keyPhase(["Zurück"], function (keys) {
      report.keys = (report.keys || []).concat(keys);
      sendKeys(next);
    });
  }

  function sendKeys(next) {
    if (reportId === null) return next();
    var body = { keys: report.keys, pointer: pointer };
    request("POST", "/api/tv-check/" + reportId + "/keys", body, function (status, data) {
      if (status === 200 && data) showVerdict(data.verdict);
      next();
    });
  }

  function showVerdict(verdict) {
    if (!verdict) return;
    var old = document.getElementById("verdict");
    if (old) old.parentNode.removeChild(old);
    var el = document.createElement("div");
    el.id = "verdict";
    el.className = "verdict";
    el.appendChild(document.createTextNode("Ergebnis " + verdict.code + ": " + verdict.label));
    stepEl.parentNode.insertBefore(el, stepEl.nextSibling);
    for (var i = 0; i < (verdict.notes || []).length; i++) log("Hinweis", null, verdict.notes[i]);
  }

  var steps = [basics, keysMain, jsFeatures, cssFeatures, websocketTest, fontTest, mediaInfo,
    mp4Test, hlsTest, youtubeTest, fpsTest, submitReport, keysBack];
  var position = 0;

  function next() {
    if (position >= steps.length) {
      setStep("Fertig. Das Ergebnis ist gespeichert; Details unter /admin/tvcheck.html.");
      return;
    }
    var fn = steps[position];
    position += 1;
    try {
      fn(next);
    } catch (e) {
      log("Schritt fehlgeschlagen", false, String(e));
      next();
    }
  }

  function start(e) {
    if (started) return;
    if (e && e.type === "keydown" && e.keyCode !== 13) return;
    started = true;
    report.startedVia = e ? (e.type === "keydown" ? "keydown:" + e.keyCode : e.type) : "?";
    document.removeEventListener("keydown", start);
    document.removeEventListener("click", start);
    next();
  }
  document.addEventListener("keydown", start);
  document.addEventListener("click", start);
})();
