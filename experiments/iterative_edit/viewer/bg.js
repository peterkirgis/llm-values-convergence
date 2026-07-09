// Background drift field: inlines bg-collage.svg into #bg and rolls the
// trajectories out left-to-right as the reader scrolls. Each path's
// data-delay staggers its start so the leading edge feathers.
(function () {
  const host = document.getElementById("bg");
  if (!host || typeof fetch !== "function") return;

  fetch("bg-collage.svg")
    .then((res) => (res.ok ? res.text() : Promise.reject(new Error(res.status))))
    .then((text) => {
      host.innerHTML = text;
      const svg = host.querySelector("svg");
      if (!svg) return;

      // With reduced motion (or no scroll range) leave the field fully drawn.
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

      const paths = Array.from(svg.querySelectorAll(".drift")).map((el) => ({
        el,
        length: el.getTotalLength(),
        delay: Number(el.dataset.delay) || 0,
      }));
      for (const p of paths) {
        p.el.style.strokeDasharray = p.length;
        p.el.style.strokeDashoffset = p.length;
      }

      const forced = new URLSearchParams(location.search).get("bgf");
      let ticking = false;
      function update() {
        ticking = false;
        const doc = document.documentElement;
        const range = doc.scrollHeight - doc.clientHeight;
        const f = forced !== null ? Number(forced)
          : range > 0 ? Math.min(1, doc.scrollTop / range) : 1;
        // Head start: the field is already partially inked at load, so it
        // shows beneath the hero right away, and finishes by ~80% scroll.
        const eff = 0.15 + 0.85 * f;
        for (const p of paths) {
          const t = Math.min(1, Math.max(0, (eff - p.delay) / 0.6));
          p.el.style.strokeDashoffset = p.length * (1 - t);
        }
      }
      function onScroll() {
        if (!ticking) {
          ticking = true;
          requestAnimationFrame(update);
        }
      }
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll, { passive: true });
      update();
    })
    .catch(() => {
      /* no background — the plain ground is fine */
    });
})();
