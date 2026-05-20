/**
 * StreamShield ingest widget — captura IP (servidor) + fingerprint (navegador).
 * Uso:
 * <script src="https://TU-FRONTEND/streamshield-widget.js" async
 *   data-stream-key="..."
 *   data-api-url="https://TU-API"
 *   data-interval="60"
 *   data-username="opcional_twitch_login"></script>
 */
(function () {
  "use strict";

  var script = document.currentScript;
  if (!script) return;

  var streamKey = script.getAttribute("data-stream-key");
  var apiUrl = (script.getAttribute("data-api-url") || "").replace(/\/$/, "");
  var intervalSec = parseInt(script.getAttribute("data-interval") || "60", 10);
  var username = script.getAttribute("data-username") || "";
  var userId = script.getAttribute("data-user-id") || "";

  if (!streamKey || !apiUrl) {
    console.warn("[StreamShield] Falta data-stream-key o data-api-url");
    return;
  }

  function simpleHash(str) {
    var h = 0;
    for (var i = 0; i < str.length; i++) {
      h = (h << 5) - h + str.charCodeAt(i);
      h |= 0;
    }
    return (h >>> 0).toString(16);
  }

  function canvasFingerprint() {
    try {
      var c = document.createElement("canvas");
      c.width = 200;
      c.height = 50;
      var ctx = c.getContext("2d");
      if (!ctx) return "";
      ctx.textBaseline = "top";
      ctx.font = "14px Arial";
      ctx.fillStyle = "#0f0";
      ctx.fillRect(0, 0, 200, 50);
      ctx.fillStyle = "#069";
      ctx.fillText("StreamShield", 2, 15);
      return simpleHash(c.toDataURL());
    } catch (e) {
      return "";
    }
  }

  function webglFingerprint() {
    try {
      var c = document.createElement("canvas");
      var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!gl) return "";
      var dbg = gl.getExtension("WEBGL_debug_renderer_info");
      var vendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : "";
      var renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "";
      return simpleHash(String(vendor) + "|" + String(renderer));
    } catch (e) {
      return "";
    }
  }

  function randomNonce() {
    var arr = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) {
      window.crypto.getRandomValues(arr);
    } else {
      for (var i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256);
    }
    return Array.from(arr, function (b) {
      return b.toString(16).padStart(2, "0");
    }).join("");
  }

  function collectFingerprint() {
    return {
      screen: window.screen ? window.screen.width + "x" + window.screen.height : "",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
      language: navigator.language || "",
      platform: navigator.platform || "",
      canvas_hash: canvasFingerprint(),
      webgl_hash: webglFingerprint(),
      user_agent: (navigator.userAgent || "").slice(0, 512),
      plugins_count: navigator.plugins ? navigator.plugins.length : 0,
      hardware_concurrency: navigator.hardwareConcurrency || 0,
      webdriver: !!navigator.webdriver,
    };
  }

  function ping() {
    var body = {
      stream_key: streamKey,
      event_type: "viewer_pulse",
      platform_username: username || null,
      platform_user_id: userId || null,
      fingerprint: collectFingerprint(),
      metadata: {
        widget_version: "1.1",
        page_url: window.location.href,
        timestamp: new Date().toISOString(),
      },
    };

    var payload = JSON.stringify(body);
    var headers = {
      "Content-Type": "application/json",
      "X-SS-Nonce": randomNonce(),
      "X-SS-Timestamp": String(Date.now()),
    };

    fetch(apiUrl + "/api/v1/widget/ping", {
      method: "POST",
      headers: headers,
      body: payload,
      mode: "cors",
      keepalive: true,
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data && data.ok && data.is_proxy) {
          console.info("[StreamShield] Proxy/VPN detectado, risk=" + data.risk_score);
        }
      })
      .catch(function () {
        /* silencioso en overlay */
      });
  }

  ping();
  if (intervalSec > 0) {
    setInterval(ping, Math.max(intervalSec, 30) * 1000);
  }

  window.StreamShield = {
    ping: ping,
    setUsername: function (u) {
      username = u || "";
    },
  };
})();
