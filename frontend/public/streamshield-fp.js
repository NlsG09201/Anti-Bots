/**
 * StreamShield Advanced Fingerprint Collector v2
 * Expone window.StreamShieldFP.collect() → payload para API
 */
(function (global) {
  "use strict";

  var SESSION_KEY = "ss_fp_session_id";

  function simpleHash(str) {
    var h = 0;
    for (var i = 0; i < str.length; i++) {
      h = (h << 5) - h + str.charCodeAt(i);
      h |= 0;
    }
    return (h >>> 0).toString(16);
  }

  function getSessionId() {
    try {
      var existing = sessionStorage.getItem(SESSION_KEY);
      if (existing) return existing;
      var id =
        (global.crypto && global.crypto.randomUUID && global.crypto.randomUUID()) ||
        "ss-" + Date.now() + "-" + Math.random().toString(16).slice(2);
      sessionStorage.setItem(SESSION_KEY, id);
      return id;
    } catch (e) {
      return "ss-anon-" + Date.now();
    }
  }

  function canvasFingerprint() {
    try {
      var c = document.createElement("canvas");
      c.width = 240;
      c.height = 60;
      var ctx = c.getContext("2d");
      if (!ctx) return { hash: "", duplicate: "" };
      ctx.textBaseline = "top";
      ctx.font = "14px 'Arial'";
      ctx.fillStyle = "#f60";
      ctx.fillRect(0, 0, 240, 60);
      ctx.fillStyle = "#069";
      ctx.fillText("StreamShield FP", 4, 8);
      ctx.strokeStyle = "rgba(102, 204, 0, 0.7)";
      ctx.strokeText("StreamShield FP", 4, 8);
      var a = simpleHash(c.toDataURL());
      ctx.fillStyle = "#963";
      ctx.fillText("probe-2", 8, 24);
      var b = simpleHash(c.toDataURL());
      return { hash: a, duplicate: b, noise_detected: a !== b };
    } catch (e) {
      return { hash: "", duplicate: "", noise_detected: false };
    }
  }

  function webglInfo() {
    try {
      var c = document.createElement("canvas");
      var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!gl) return { hash: "", vendor: "", renderer: "" };
      var dbg = gl.getExtension("WEBGL_debug_renderer_info");
      var vendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : "";
      var renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "";
      return {
        hash: simpleHash(String(vendor) + "|" + String(renderer)),
        vendor: String(vendor),
        renderer: String(renderer),
      };
    } catch (e) {
      return { hash: "", vendor: "", renderer: "" };
    }
  }

  function audioFingerprint() {
    return new Promise(function (resolve) {
      try {
        var AC = global.OfflineAudioContext || global.webkitOfflineAudioContext;
        if (!AC) {
          resolve("");
          return;
        }
        var ctx = new AC(1, 44100, 44100);
        var osc = ctx.createOscillator();
        osc.type = "triangle";
        osc.frequency.value = 10000;
        var comp = ctx.createDynamicsCompressor();
        osc.connect(comp);
        comp.connect(ctx.destination);
        osc.start(0);
        ctx.startRendering();
        ctx.oncomplete = function (ev) {
          try {
            var buf = ev.renderedBuffer.getChannelData(0).slice(4500, 5000);
            var sum = 0;
            for (var i = 0; i < buf.length; i++) sum += Math.abs(buf[i]);
            resolve(simpleHash(String(sum)));
          } catch (e2) {
            resolve("");
          }
        };
      } catch (e) {
        resolve("");
      }
    });
  }

  function detectAutomation() {
    var hints = {};
    try {
      hints.chrome_headless = !!navigator.webdriver;
      hints.missing_chrome_runtime = typeof global.chrome === "undefined";
      if (global.navigator.permissions && global.navigator.permissions.query) {
        global.navigator.permissions
          .query({ name: "notifications" })
          .then(function (p) {
            hints.permissions_anomaly =
              p.state === "denied" && Notification.permission === "default";
          })
          .catch(function () {});
      }
    } catch (e) {}
    return {
      webdriver: !!navigator.webdriver,
      selenium: !!global._selenium || !!global.callSelenium || !!document.__selenium_unwrapped,
      puppeteer: !!global.__puppeteer_evaluation_script__ || !!global._WEBDRIVER_ELEM_CACHE,
      playwright: !!global.__playwright || !!global.__pw_manual,
      headless_hints: hints,
    };
  }

  function gatherWebRTC(timeoutMs) {
    return new Promise(function (resolve) {
      var result = {
        local_ips: [],
        public_ip: null,
        mdns_host: null,
        failed: false,
      };
      if (!global.RTCPeerConnection) {
        result.failed = true;
        resolve(result);
        return;
      }
      var done = false;
      var finish = function () {
        if (done) return;
        done = true;
        resolve(result);
      };
      setTimeout(finish, timeoutMs || 2500);
      try {
        var pc = new RTCPeerConnection({
          iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
        });
        pc.createDataChannel("ss");
        pc.onicecandidate = function (ev) {
          if (!ev.candidate || !ev.candidate.candidate) return;
          var cand = ev.candidate.candidate;
          var ipMatch = cand.match(/([0-9]{1,3}(\.[0-9]{1,3}){3})/);
          if (ipMatch && result.local_ips.indexOf(ipMatch[1]) === -1) {
            result.local_ips.push(ipMatch[1]);
          }
          if (cand.indexOf(".local") > -1) {
            result.mdns_host = cand.split(" ")[4] || cand;
          }
        };
        pc.createOffer().then(function (offer) {
          return pc.setLocalDescription(offer);
        });
      } catch (e) {
        result.failed = true;
        finish();
      }
    });
  }

  function getUserAgentData() {
    return new Promise(function (resolve) {
      if (!navigator.userAgentData || !navigator.userAgentData.getHighEntropyValues) {
        resolve(null);
        return;
      }
      navigator.userAgentData
        .getHighEntropyValues(["platform", "platformVersion", "architecture", "brands"])
        .then(function (v) {
          resolve({
            brands: v.brands,
            platform: v.platform,
            platformVersion: v.platformVersion,
            architecture: v.architecture,
          });
        })
        .catch(function () {
          resolve(null);
        });
    });
  }

  function collect() {
    return Promise.all([audioFingerprint(), gatherWebRTC(2500), getUserAgentData()]).then(
      function (parts) {
        var audioHash = parts[0];
        var webrtc = parts[1];
        var uad = parts[2];
        var canvas = canvasFingerprint();
        var webgl = webglInfo();
        var auto = detectAutomation();
        var langs = navigator.languages ? Array.prototype.slice.call(navigator.languages) : [];

        return {
          session_id: getSessionId(),
          user_agent: (navigator.userAgent || "").slice(0, 512),
          user_agent_data: uad,
          platform: navigator.platform || "",
          language: navigator.language || "",
          languages: langs,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
          timezone_offset_minutes: new Date().getTimezoneOffset(),
          screen_resolution: global.screen
            ? global.screen.width + "x" + global.screen.height
            : "",
          color_depth: global.screen ? global.screen.colorDepth : null,
          device_memory: navigator.deviceMemory,
          hardware_concurrency: navigator.hardwareConcurrency || 0,
          canvas_hash: canvas.hash,
          canvas_duplicate_hash: canvas.duplicate,
          canvas_noise_detected: canvas.noise_detected,
          canvas_noise_expected: true,
          webgl_hash: webgl.hash,
          webgl_vendor: webgl.vendor,
          webgl_renderer: webgl.renderer,
          audio_hash: audioHash,
          webrtc_local_ips: webrtc.local_ips,
          webrtc_public_ip: webrtc.public_ip,
          webrtc_mdns_host: webrtc.mdns_host,
          webrtc_failed: webrtc.failed,
          webdriver: auto.webdriver,
          selenium: auto.selenium,
          puppeteer: auto.puppeteer,
          playwright: auto.playwright,
          headless_hints: auto.headless_hints,
          plugins_count: navigator.plugins ? navigator.plugins.length : 0,
          outer_dimensions_zero:
            global.outerWidth === 0 && global.outerHeight === 0,
          touch_support: "ontouchstart" in global || navigator.maxTouchPoints > 0,
        };
      },
    );
  }

  global.StreamShieldFP = { collect: collect, version: "2.0.0" };
})(typeof window !== "undefined" ? window : globalThis);
