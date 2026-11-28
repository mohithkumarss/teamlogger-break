// ZenMetrics website. Downloads always go through GitHub (the releases page opens
// in a new tab and we ask for a star); the live countdown in the mockups; screen
// tabs; light/dark; current-section highlight; scroll reveals. No dependencies.
(() => {
  "use strict";
  const REPO = "vyaca-corp/zenmetrics";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const cache = {
    get(k) { try { const c = JSON.parse(sessionStorage.getItem(k) || "null"); return c && Date.now() - c.t < 600000 ? c.v : null; } catch (e) { return null; } },
    set(k, v) { try { sessionStorage.setItem(k, JSON.stringify({ t: Date.now(), v })); } catch (e) { /* storage blocked */ } },
  };
  async function gh(path, key) {
    const hit = cache.get(key);
    if (hit) return hit;
    const res = await fetch(`https://api.github.com/repos/${REPO}${path}`, { headers: { Accept: "application/vnd.github+json" } });
    if (!res.ok) throw new Error(`GitHub ${res.status}`);
    const v = await res.json();
    cache.set(key, v);
    return v;
  }

  // ---------------------------------------------------------------- which system?
  function detectOS() {
    const p = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    const ua = navigator.userAgent || "";
    if (/android|iphone|ipad|ipod/i.test(ua)) return "mobile";
    if (/mac/i.test(p) || /Mac OS X/.test(ua)) return "mac";
    if (/win/i.test(p) || /Windows/.test(ua)) return "win";
    if (/linux|x11|cros/i.test(p) || /Linux|X11/.test(ua)) return "linux";
    return "unknown";
  }
  const OS = detectOS();
  const OS_NAME = { mac: "macOS", win: "Windows", linux: "Linux" };
  const OS_FILE = { mac: "dmg", win: "exe", linux: "deb" };
  if (OS in OS_NAME) {
    const label = $("[data-download-label]");
    if (label) label.textContent = `Download for ${OS_NAME[OS]}`;
    const row = $(`.which li[data-os="${OS}"]`);
    if (row) { row.classList.add("yours"); row.parentElement.prepend(row); }
  }

  // ---------------------------------------------------------------- release file names (shown, never linked)
  const KIND = [["exe", /setup\.exe$/i], ["msi", /\.msi$/i], ["dmg", /\.dmg$/i], ["deb", /\.deb$/i], ["rpm", /\.rpm$/i], ["appimage", /\.AppImage$/i]];
  const files = {};
  let releasePage = `https://github.com/${REPO}/releases/latest`;
  gh("/releases/latest", "zm-rel").then((r) => {
    if (r.html_url) releasePage = r.html_url;
    for (const a of r.assets || []) {
      const k = KIND.find(([, re]) => re.test(a.name));
      if (k && !files[k[0]]) files[k[0]] = a.name;
    }
    for (const el of $$("[data-file]")) if (files[el.dataset.file]) el.textContent = files[el.dataset.file];
    const v = (r.tag_name || "").replace(/^v/, "");
    const when = r.published_at ? new Date(r.published_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
    const line = $("[data-release-line]");
    if (line && v) line.textContent = `Latest: v${v}${when ? ` · ${when}` : ""} · needs the TeamLogger desktop app on the same computer.`;
  }).catch(() => { /* the generic names stay */ });

  // ---------------------------------------------------------------- stars (shown once there are a few)
  gh("", "zm-repo").then((r) => {
    const n = r.stargazers_count || 0;
    if (n < 5) return;
    const text = n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n);
    for (const el of $$(".star-count")) { el.textContent = text; el.hidden = false; }
  }).catch(() => { /* no count */ });

  // ---------------------------------------------------------------- download: ask for a star first, then the download page
  // Every download button opens this prompt instead of leaving the page. Its two buttons are
  // real links (new tab), so nothing can be blocked as a pop-up:
  //   Star on GitHub        -> the repo (then the prompt says thanks)
  //   Continue to download  -> the release page, with the right file for that system named here
  const ask = $("#star-ask");
  const askStar = $("[data-ask-star]"), askGo = $("[data-ask-continue]");
  const fileName = (os) => {
    const want = OS_FILE[os];
    return (want && files[want]) || ({ dmg: "the .dmg file", exe: "the -setup.exe installer", deb: "the .deb (or .rpm / .AppImage)" }[want] || "the file for your system");
  };
  function openAsk(os) {
    ask.classList.remove("starred");
    $("[data-ask-title]").textContent = "Before you download — a quick star?";
    $("[data-ask-text]").textContent = "ZenMetrics is free. A star on GitHub is the best way to help other TeamLogger users find it. It takes a second.";
    $("[data-ask-continue-label]").textContent = os in OS_NAME ? `Continue to download for ${OS_NAME[os]}` : "Continue to download";
    askStar.className = "btn primary";
    askGo.className = "btn soft";
    askGo.href = releasePage;
    $("[data-file-for-os]").textContent = fileName(os);
    ask.showModal();
  }
  if (ask && typeof ask.showModal === "function") {
    for (const a of $$("[data-download]")) {
      a.addEventListener("click", (e) => {
        e.preventDefault();                    // no direct download, no leaving the page yet
        openAsk(a.dataset.for || OS);
      });
    }
    askStar.addEventListener("click", () => {  // the link opens the repo; the prompt turns into a thank-you
      ask.classList.add("starred");
      $("[data-ask-title]").textContent = "Thank you!";
      $("[data-ask-text]").textContent = "That really helps. Now grab ZenMetrics:";
      askStar.className = "btn soft";
      askGo.className = "btn primary";
    });
    askGo.addEventListener("click", () => setTimeout(() => ask.close(), 120));
    ask.addEventListener("click", (e) => { if (e.target === ask) ask.close(); });  // click outside
  }

  // ---------------------------------------------------------------- live countdown in the mockups
  const clocks = $$("[data-clock]"), bars = $$("[data-bar]"), arcs = $$("[data-arc]"), dials = $$("[data-dial]");
  const START = 47 * 60 + 12, STRETCH = 110 * 60;
  const t0 = Date.now();
  const fmt = (s) => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}`;
  };
  function tick() {
    const left = START - (Math.floor((Date.now() - t0) / 1000) % (START - 60)); // a demo: never reaches zero
    const frac = 1 - left / STRETCH;
    const text = fmt(left);
    clocks.forEach((el) => (el.textContent = text));
    bars.forEach((el) => (el.style.width = `${(frac * 100).toFixed(2)}%`));
    arcs.forEach((el) => (el.style.strokeDashoffset = String(54.04 * (1 - frac))));
    dials.forEach((el) => (el.style.strokeDasharray = `${(frac * 100).toFixed(2)} 100`));
  }
  tick();
  if (!reduced) (function loop() { setTimeout(() => { tick(); loop(); }, 1000 - (Date.now() % 1000) + 10); })();

  // ---------------------------------------------------------------- screens
  const captions = {
    today: "Your next break, your day on one line, and this week’s numbers.",
    stats: "Hours per day, a month calendar, and every day’s timeline.",
    setup: "Seven short steps — and nothing happens without your consent.",
  };
  for (const tab of $$(".tabs [role=tab]")) {
    tab.addEventListener("click", () => {
      const k = tab.dataset.shot;
      $$(".tabs [role=tab]").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      $$(".shot").forEach((s) => s.classList.toggle("is-active", s.dataset.shot === k));
      $("[data-shot-title]").textContent = tab.textContent;
      $("[data-shot-caption]").textContent = captions[k];
    });
  }

  // ---------------------------------------------------------------- light / dark
  $("#theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("zm-theme", root.dataset.theme); } catch (e) { /* ignore */ }
  });

  // ---------------------------------------------------------------- header: shadow + current section
  const nav = $(".nav");
  const links = $$(".nav-links a");
  const sections = links.map((a) => $(a.getAttribute("href")));
  function onScroll() {
    nav.classList.toggle("scrolled", scrollY > 8);
    const y = scrollY + innerHeight * 0.35;
    let current = -1;
    sections.forEach((s, i) => { if (s && s.offsetTop <= y && s.offsetTop + s.offsetHeight > y) current = i; });
    links.forEach((a, i) => a.classList.toggle("on", i === current));
  }
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // ---------------------------------------------------------------- reveals
  const items = $$(".reveal");
  if (reduced || !("IntersectionObserver" in window)) {
    items.forEach((el) => el.classList.add("in"));
  } else {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        const sibs = [...e.target.parentElement.children].filter((c) => c.classList.contains("reveal"));
        e.target.style.transitionDelay = `${Math.min(sibs.indexOf(e.target), 5) * 70}ms`;
        e.target.classList.add("in");
        io.unobserve(e.target);
      }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.06 });
    items.forEach((el) => io.observe(el));
  }

  $("#year").textContent = String(new Date().getFullYear());
})();
