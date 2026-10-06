(function () {
  "use strict";

  var root = document.documentElement;

  function currentTheme() {
    return root.getAttribute("data-theme") || "light";
  }

  function utterancesTheme(theme) {
    var frame = document.querySelector("iframe.utterances-frame");
    if (!frame || !frame.contentWindow) return;
    frame.contentWindow.postMessage(
      {
        type: "set-theme",
        theme: theme === "dark" ? "github-dark" : "github-light",
      },
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
      /* 若评论脚本尚未执行, 直接改它的 theme 属性, 让 client.js 按新主题初始化 */
      var uttScript = document.querySelector('script[src*="utteranc.es/client.js"]');
      if (uttScript) {
        uttScript.setAttribute("theme", next === "dark" ? "github-dark" : "github-light");
      }
      utterancesTheme(next);
    });
  }

  /* 评论 iframe: onload 时子页面已挂好监听, 顺势补发主题,
     兜住"评论还没加载出来就切了主题"的情况。 */
  var syncTimer = setInterval(function () {
    var frame = document.querySelector("iframe.utterances-frame");
    if (!frame) return;
    clearInterval(syncTimer);
    var send = function () {
      utterancesTheme(currentTheme());
    };
    frame.addEventListener("load", send);
    send();
  }, 200);

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
      var btn = e.target.closest(".chip");
      if (!btn) return;
      activeTag = btn.dataset.tag;
      filterRoot.querySelectorAll(".chip").forEach(function (c) {
        c.classList.toggle("is-active", c === btn);
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
