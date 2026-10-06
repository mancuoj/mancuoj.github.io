(function () {
  "use strict";

  var root = document.documentElement;

  function currentTheme() {
    return root.getAttribute("data-theme") || "light";
  }

  function utterancesName(theme) {
    return theme === "dark" ? "github-dark" : "github-light";
  }

  function utterancesTheme(theme) {
    var frame = document.querySelector("iframe.utterances-frame");
    if (!frame || !frame.contentWindow) return;
    frame.contentWindow.postMessage(
      { type: "set-theme", theme: utterancesName(theme) },
      "https://utteranc.es"
    );
  }

  /* --- 主题切换 --------------------------------------------------------- */
  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("theme", next);
      } catch (e) {}
      utterancesTheme(next);
    });
  }

  /* --- 评论: 点击后加载, 带加载态与淡入 --------------------------------- */
  var box = document.getElementById("comments");
  var btn = document.getElementById("load-comments");
  if (box && btn) {
    btn.addEventListener("click", function () {
      btn.remove();

      var loader = document.createElement("div");
      loader.className = "comments-loading";
      loader.innerHTML = '<span class="spinner" aria-hidden="true"></span><span>加载评论…</span>';
      box.classList.add("is-loading");
      box.appendChild(loader);

      var s = document.createElement("script");
      s.src = "https://utteranc.es/client.js";
      s.setAttribute("repo", btn.dataset.repo);
      s.setAttribute("issue-number", btn.dataset.issue);
      s.setAttribute("theme", utterancesName(currentTheme()));
      s.setAttribute("crossorigin", "anonymous");
      s.async = true;
      s.onerror = function () {
        box.classList.remove("is-loading");
        loader.remove();
        var fail = document.createElement("p");
        fail.className = "comments-fail";
        fail.textContent = "评论加载失败，请刷新页面重试。";
        box.appendChild(fail);
      };
      box.appendChild(s);

      /* 等 utterances 的 iframe 出现，撤掉加载态（内容本身会淡入） */
      var tries = 0;
      var timer = setInterval(function () {
        if (box.querySelector("iframe.utterances-frame")) {
          clearInterval(timer);
          box.classList.remove("is-loading");
          loader.remove();
        } else if (++tries > 130) {
          clearInterval(timer);
        }
      }, 150);
    });
  }

  /* --- 标签页: 标签过滤 + 搜索 ----------------------------------------- */
  var filterRoot = document.getElementById("tag-filter");
  var list = document.getElementById("tagged-posts");
  if (filterRoot && list) {
    var items = Array.prototype.slice.call(list.querySelectorAll(".post-item"));
    var search = document.getElementById("search");
    var empty = document.getElementById("empty");
    var activeTag = "*";

    var apply = function () {
      var q = search ? search.value.trim().toLowerCase() : "";
      var shown = 0;
      items.forEach(function (li) {
        var tags = " " + (li.dataset.tags || "") + " ";
        var okTag = activeTag === "*" || tags.indexOf(" " + activeTag + " ") !== -1;
        var okText = !q || (li.dataset.text || "").indexOf(q) !== -1;
        var show = okTag && okText;
        li.hidden = !show;
        if (show) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
    };

    filterRoot.addEventListener("click", function (e) {
      var chip = e.target.closest(".chip");
      if (!chip) return;
      activeTag = chip.dataset.tag;
      filterRoot.querySelectorAll(".chip").forEach(function (c) {
        c.classList.toggle("is-active", c === chip);
      });
      apply();
    });

    if (search) search.addEventListener("input", apply);

    if (location.hash) {
      var slug = decodeURIComponent(location.hash.slice(1));
      var target = filterRoot.querySelector('.chip[data-tag="' + CSS.escape(slug) + '"]');
      if (target) target.click();
    }
  }
})();
