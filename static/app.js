(function () {
  "use strict";

  var root = document.documentElement;

  function currentTheme() {
    return root.getAttribute("data-theme") || "light";
  }

  /* --- 主题切换（只在主页 Elsewhere 的文字按钮） ------------------------ */
  var switcher = document.getElementById("theme-switch");
  if (switcher) {
    var syncLabel = function () {
      switcher.textContent = currentTheme() === "dark" ? "Light" : "Dark";
    };
    syncLabel();
    switcher.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("theme", next);
      } catch (e) {}
      syncLabel();
    });
  }

  /* --- 标签页: 标签过滤 ----------------------------------------------- */
  var filterRoot = document.getElementById("tag-filter");
  var list = document.getElementById("tagged-posts");
  if (filterRoot && list) {
    var items = Array.prototype.slice.call(list.querySelectorAll(".post-item"));
    var activeTag = "*";

    var apply = function () {
      items.forEach(function (li) {
        var tags = " " + (li.dataset.tags || "") + " ";
        li.hidden = !(activeTag === "*" || tags.indexOf(" " + activeTag + " ") !== -1);
      });
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

    if (location.hash) {
      var slug = decodeURIComponent(location.hash.slice(1));
      var target = filterRoot.querySelector('.chip[data-tag="' + CSS.escape(slug) + '"]');
      if (target) target.click();
    }
  }
})();
