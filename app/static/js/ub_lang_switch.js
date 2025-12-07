(function () {
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  function ensureStyle() {
    if (document.getElementById("ub-lang-style")) return;
    var style = document.createElement("style");
    style.id = "ub-lang-style";
    style.textContent = [
      ".ub-lang-switch { display: flex; align-items: center; height: 50px; gap: 12px; padding: 0 6px; }",
      ".ub-lang-option { background: transparent; border: none; padding: 0 6px 6px; margin: 0; font-size: 15px; font-weight: 700; letter-spacing: 0.5px; line-height: 20px; color: inherit; text-transform: uppercase; }",
      ".ub-lang-option.active { color: var(--cw-primary, #0f6958); border-bottom: 2px solid currentColor; }",
      ".ub-lang-option:focus { outline: none; box-shadow: none; }",
      ".ub-profile-disabled { pointer-events: none; cursor: default; color: #777; }"
    ].join("\n");
    document.head.appendChild(style);
  }

  function getConfig() {
    var el = document.getElementById("ub-config");
    if (!el) return null;
    return {
      isAdmin: el.dataset.isAdmin === "1",
      isAnonymous: el.dataset.isAnon === "1",
      switchUrl: el.dataset.switchUrl || "/language/switch",
      activeLang: (el.dataset.activeLang || "en").toLowerCase(),
      loginUrl: el.dataset.loginUrl || "/login",
      loginLabel: el.dataset.loginLabel || "Login"
    };
  }

  function disableProfileLink(cfg) {
    if (cfg.isAdmin) return;
    var profileLink = document.getElementById("top_user");
    if (profileLink) {
      if (cfg.isAnonymous) {
        var labelSpan = profileLink.querySelector(".hidden-sm");
        if (labelSpan) {
          labelSpan.textContent = cfg.loginLabel;
        } else {
          profileLink.textContent = cfg.loginLabel;
        }
        profileLink.setAttribute("href", cfg.loginUrl);
        profileLink.classList.remove("ub-profile-disabled");
        profileLink.removeAttribute("aria-disabled");
      } else {
        profileLink.removeAttribute("href");
        profileLink.classList.add("ub-profile-disabled");
        profileLink.setAttribute("aria-disabled", "true");
      }
    }
    var profileToggle = document.querySelector(".profileDrop");
    if (profileToggle) {
      if (cfg.isAnonymous) {
        profileToggle.setAttribute("data-toggle", "dropdown");
        profileToggle.style.cursor = "pointer";
      } else {
        profileToggle.removeAttribute("data-toggle");
        profileToggle.style.cursor = "default";
      }
    }
  }

  function hideTasksLink(cfg) {
    if (cfg.isAdmin) return;
    var tasks = document.getElementById("top_tasks");
    if (tasks && tasks.parentNode) {
      tasks.parentNode.remove();
    }
  }

  function findInsertionTarget(nav) {
    var children = Array.prototype.slice.call(nav.children || []);

    function findById(id) {
      for (var i = 0; i < children.length; i++) {
        var child = children[i];
        if (child && child.querySelector && child.querySelector(id)) {
          return child;
        }
      }
      return null;
    }

    var logoutLi = findById("#logout");
    if (logoutLi) return logoutLi;

    var loginLi = findById("#login");
    if (loginLi) return loginLi;

    return children.length ? children[children.length - 1] : null;
  }

  function renderLanguageSwitch(cfg) {
    var nav = document.getElementById("main-nav");
    if (!nav || document.getElementById("ub-lang-switch")) return;

    var li = document.createElement("li");
    li.id = "ub-lang-switch";
    li.className = "ub-lang-switch navbar-text";

    var options = [
      { code: "lv", label: "LAT" },
      { code: "ru", label: "RUS" },
      { code: "en", label: "ENG" }
    ];

    var buttons = options.map(function (opt) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ub-lang-option" + (opt.code === cfg.activeLang ? " active" : "");
      btn.dataset.lang = opt.code;
      btn.textContent = opt.label;
      return btn;
    });

    buttons.forEach(function (btn) { li.appendChild(btn); });

    var anchor = findInsertionTarget(nav);
    if (anchor && anchor.parentElement === nav) {
      nav.insertBefore(li, anchor);
    } else {
      nav.appendChild(li);
    }

    li.addEventListener("click", function (event) {
      var target = event.target.closest("button");
      if (!target || !target.dataset.lang) return;
      var lang = target.dataset.lang;
      if (!lang || lang === cfg.activeLang) return;
      switchLanguage(cfg, lang);
    });
  }

  function switchLanguage(cfg, lang) {
    try {
      var payload = JSON.stringify({ language: lang });
      fetch(cfg.switchUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        credentials: "same-origin"
      })
        .then(function (resp) {
          if (!resp.ok) throw new Error("switch_failed");
          return resp.json();
        })
        .then(function () {
          window.location.reload();
        })
        .catch(function () {
          window.location.reload();
        });
    } catch (err) {
      window.location.reload();
    }
  }

  function init() {
    var cfg = getConfig();
    if (!cfg) return;
    ensureStyle();
    hideTasksLink(cfg);
    disableProfileLink(cfg);
    renderLanguageSwitch(cfg);
  }

  ready(init);
})();
