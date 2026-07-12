// Scroll reveal: top-level page blocks below the fold fade up as they enter
// the viewport. The pre-hidden state is applied here (not in the stylesheet),
// so without JS everything stays visible; above-the-fold blocks are skipped
// so nothing flickers at load.
(function () {
  if (typeof IntersectionObserver !== "function") return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const blocks = document.querySelectorAll(".page-shell > *, .shell > *");
  if (!blocks.length) return;

  const io = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add("revealed");
        io.unobserve(entry.target);
      }
    }
  }, { rootMargin: "0px 0px -10% 0px", threshold: 0.02 });

  for (const block of blocks) {
    if (block.getBoundingClientRect().top < window.innerHeight * 0.9) continue;
    block.classList.add("reveal-pending");
    io.observe(block);
  }
})();
