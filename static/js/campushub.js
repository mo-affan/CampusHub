/* CampusHub UI behaviour - no external libraries. */
(function () {
  "use strict";

  /* mobile sidebar */
  document.querySelectorAll("[data-toggle-sidebar]").forEach(function (b) {
    b.addEventListener("click", function () { document.body.classList.toggle("sidebar-open"); });
  });
  document.addEventListener("click", function (e) {
    if (document.body.classList.contains("sidebar-open") && !e.target.closest(".sidebar, [data-toggle-sidebar]")) {
      document.body.classList.remove("sidebar-open");
    }
  });

  /* dismiss flash messages */
  document.querySelectorAll(".flash-close").forEach(function (b) {
    b.addEventListener("click", function () { b.closest(".flash").remove(); });
  });

  /* confirmation dialog for forms with data-confirm */
  var dlg = document.getElementById("confirm-dialog");
  var pending = null;
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (dlg && form.dataset.confirm && !form.dataset.confirmed) {
      e.preventDefault();
      e.stopImmediatePropagation();
      pending = form;
      dlg.querySelector("[data-confirm-title]").textContent = form.dataset.confirmTitle || "Please confirm";
      dlg.querySelector("[data-confirm-text]").textContent = form.dataset.confirm;
      var ok = dlg.querySelector("[data-confirm-ok]");
      ok.textContent = form.dataset.confirmOk || "Confirm";
      ok.className = "btn " + (form.dataset.confirmTone === "danger" ? "btn-danger" : "btn-brand");
      dlg.showModal();
    }
  }, true);
  if (dlg) {
    dlg.querySelector("[data-confirm-ok]").addEventListener("click", function () {
      if (pending) { pending.dataset.confirmed = "1"; dlg.close(); pending.requestSubmit(); }
    });
    dlg.querySelector("[data-confirm-cancel]").addEventListener("click", function () { pending = null; dlg.close(); });
  }

  /* loading state on submit (after validation / confirmation) */
  document.addEventListener("submit", function (e) {
    if (e.defaultPrevented) return;
    var btn = e.target.querySelector("button[type=submit]:not([data-no-loading])");
    if (btn) {
      setTimeout(function () {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Working…';
      }, 0);
    }
  });

  /* student / faculty switch inside a form */
  document.querySelectorAll("form").forEach(function (form) {
    var radios = form.querySelectorAll("input[name=user_type]");
    function sync() {
      var v = (form.querySelector("input[name=user_type]:checked") || {}).value || "student";
      form.querySelectorAll(".pick-student").forEach(function (el) { el.hidden = v !== "student"; });
      form.querySelectorAll(".pick-faculty").forEach(function (el) { el.hidden = v !== "faculty"; });
    }
    radios.forEach(function (r) { r.addEventListener("change", sync); });
    if (radios.length) sync();
  });

  /* clickable table rows */
  document.querySelectorAll("tr[data-href]").forEach(function (tr) {
    tr.addEventListener("click", function (e) {
      if (e.target.closest("a, button, form, input, select")) return;
      window.location = tr.dataset.href;
    });
  });

  /* "/" focuses the global search */
  var search = document.getElementById("global-search");
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && search && !/input|textarea|select/i.test(document.activeElement.tagName)) {
      e.preventDefault(); search.focus();
    }
  });

  /* booking form: time validation + live schedule of the chosen facility */
  var bform = document.getElementById("booking-form");
  if (bform) {
    var fac = bform.querySelector("[name=facility_id]"), day = bform.querySelector("[name=date]"),
        st = bform.querySelector("[name=start]"), en = bform.querySelector("[name=end]"),
        err = document.getElementById("time-error"), box = document.getElementById("day-preview"),
        current = [], OPEN = 7 * 60, CLOSE = 21 * 60;
    var mins = function (t) { if (!t) return null; var p = t.split(":"); return +p[0] * 60 + +p[1]; };
    var pct = function (m) { return Math.max(0, Math.min(100, (m - OPEN) / (CLOSE - OPEN) * 100)); };
    var esc = function (s) { var d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; };

    function validTimes() {
      var a = mins(st.value), b = mins(en.value);
      var bad = a !== null && b !== null && b <= a;
      en.classList.toggle("is-invalid", bad);
      err.classList.toggle("show", bad);
      return !bad;
    }
    function render(data) {
      if (!data) { box.innerHTML = '<span class="muted">Choose a facility and date to see its schedule.</span>'; return; }
      var a = mins(st.value), b = mins(en.value), clash = null;
      var blocks = data.bookings.map(function (x) {
        var s = mins(x.start), e = mins(x.end);
        if (a !== null && b !== null && b > a && x.status === "CONFIRMED" && s < b && e > a) clash = x;
        return '<div class="mini-block" style="left:' + pct(s) + '%;width:' + (pct(e) - pct(s)) + '%" title="' +
               esc(x.start + "–" + x.end + " " + x.purpose) + '"></div>';
      }).join("");
      if (a !== null && b !== null && b > a) {
        blocks += '<div class="mini-block chosen' + (clash ? " clash" : "") + '" style="left:' + pct(a) +
                  '%;width:' + (pct(b) - pct(a)) + '%"></div>';
      }
      var list = data.bookings.length ? data.bookings.map(function (x) {
        return '<div class="d-flex justify-content-between gap-2 small"><span><span class="ref">' + esc(x.ref) + "</span> " +
               esc(x.start) + "–" + esc(x.end) + " · " + esc(x.purpose || "") + '</span><span class="muted">' + esc(x.booked_by) + "</span></div>";
      }).join("") : '<div class="small muted">No bookings yet on this day.</div>';
      var status = data.status !== "AVAILABLE"
        ? '<div class="note warning mb-2">This facility is ' + esc(data.status.replace("_", " ").toLowerCase()) +
          '. MySQL will reject new bookings (trigger T1).</div>' : "";
      var clashNote = clash ? '<div class="note danger mt-2">Overlaps ' + esc(clash.ref) + " (" + esc(clash.start) + "–" +
          esc(clash.end) + '). MySQL will reject this booking.</div>' : "";
      box.innerHTML = status + '<div class="d-flex justify-content-between mb-1"><b class="small">' + esc(data.facility) +
        '</b><span class="small muted">capacity ' + data.capacity + '</span></div><div class="mini-track">' + blocks +
        '</div><div class="mini-scale"><span>07:00</span><span>11:00</span><span>14:00</span><span>17:00</span><span>21:00</span></div>' +
        '<div class="mt-2 d-grid gap-1">' + list + "</div>" + clashNote;
    }
    function load() {
      if (!fac.value || !day.value) { current = null; render(null); return; }
      fetch("/api/facilities/" + encodeURIComponent(fac.value) + "/day?date=" + encodeURIComponent(day.value))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { current = d; render(d); })
        .catch(function () { box.innerHTML = '<span class="muted">Schedule preview unavailable.</span>'; });
    }
    [fac, day].forEach(function (el) { el.addEventListener("change", load); });
    [st, en].forEach(function (el) { el.addEventListener("input", function () { validTimes(); if (current) render(current); }); });
    bform.addEventListener("submit", function (e) {
      if (!validTimes()) { e.preventDefault(); en.focus(); }
    });
    load();
  }

  /* sign-in page: label follows the chosen role; show / hide password */
  var roleTabs = document.querySelectorAll(".role-tabs input[name=role]");
  var loginLabel = document.getElementById("login-label");
  var loginInput = document.getElementById("login");
  var hints = { STUDENT: ["Registration number or e-mail", "e.g. 24BCE1101"],
                FACULTY: ["Employee code or e-mail", "e.g. F1001"],
                ADMIN:   ["E-mail", "e.g. karthik.admin@campushub.edu"] };
  function syncRole() {
    var r = (document.querySelector(".role-tabs input[name=role]:checked") || {}).value;
    if (r && hints[r] && loginLabel && loginInput) { loginLabel.textContent = hints[r][0]; loginInput.placeholder = hints[r][1]; }
  }
  roleTabs.forEach(function (r) { r.addEventListener("change", syncRole); });
  syncRole();
  document.querySelectorAll("[data-pw-toggle]").forEach(function (b) {
    b.hidden = false;
    b.addEventListener("click", function () {
      var input = document.getElementById(b.getAttribute("data-pw-toggle"));
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      b.textContent = show ? "Hide" : "Show";
      b.setAttribute("aria-pressed", show ? "true" : "false");
    });
  });

  /* close the profile menu when clicking elsewhere */
  document.addEventListener("click", function (e) {
    document.querySelectorAll("details.profile-menu[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });
})();
