// Small DOM toolkit: element builder, icons, toasts, tooltips, number tweens, dialogs.

type Child = Node | string | number | null | undefined | false;
type Attrs = Record<string, unknown> & { class?: string; on?: Record<string, (e: Event) => void> };

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: Child[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "on") for (const [ev, fn] of Object.entries(v as Record<string, EventListener>)) el.addEventListener(ev, fn);
    else if (k === "class") el.className = String(v);
    else if (k in el && typeof v !== "string") (el as unknown as Record<string, unknown>)[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  append(el, children);
  return el;
}

export function append(el: Element, children: Child[]) {
  for (const c of children) if (c != null && c !== false) el.append(c instanceof Node ? c : String(c));
}

export function clear(el: Element, ...children: Child[]) {
  el.replaceChildren();
  append(el, children);
}

const ICONS: Record<string, string> = {
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  hourglass: '<path d="M6 3h12M6 21h12M7 3c0 5 10 5 10 9s-10 4-10 9M17 3c0 5-10 5-10 9s10 4 10 9"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  alarm: '<circle cx="12" cy="13" r="7"/><path d="M12 10v3l2 1.5M5 4 2.5 6.5M19 4l2.5 2.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
  prev: '<path d="m15 18-6-6 6-6"/>',
  next: '<path d="m9 18 6-6-6-6"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2.5"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  theme: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  coffee: '<path d="M4 9h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM17 10h1.5a2.5 2.5 0 0 1 0 5H17M8 3v3M12 3v3"/>',
  lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
  up: '<path d="m18 15-6-6-6 6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
};

export function icon(name: keyof typeof ICONS | string): SVGSVGElement {
  const t = document.createElement("template");
  t.innerHTML = `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] ?? ""}</svg>`;
  return t.content.firstChild as SVGSVGElement;
}

export function iconButton(name: string, label: string, onClick: () => void, cls = "btn icon-round"): HTMLButtonElement {
  return h("button", { class: cls, title: label, "aria-label": label, on: { click: onClick } }, icon(name));
}

// ---------------------------------------------------------------- toast
const toasts = h("div", { class: "toasts", role: "status", "aria-live": "polite" });
document.body.append(toasts);

/** A short message at the bottom; with `action`, a button (e.g. Undo) and a longer stay. */
export function toast(msg: string, action?: { label: string; run: () => void }) {
  const t = h("div", { class: "toast" }, msg);
  const close = () => {
    t.classList.add("out");
    setTimeout(() => t.remove(), 240);
  };
  if (action)
    t.append(h("button", { class: "toast-action", on: { click: () => { close(); action.run(); } } }, action.label));
  toasts.append(t);
  setTimeout(close, action ? 6000 : 3000);
}

export function errorToast(e: unknown) {
  toast(typeof e === "string" ? e : e instanceof Error ? e.message : String(e));
}

// ---------------------------------------------------------------- tooltip ([data-tip] anywhere, incl. SVG)
const tip = h("div", { class: "tip", hidden: true });
document.body.append(tip);
document.addEventListener("pointermove", (e) => {
  const target = (e.target as Element | null)?.closest?.("[data-tip]");
  const text = target?.getAttribute("data-tip");
  if (!text) {
    tip.hidden = true;
    return;
  }
  tip.textContent = text;
  tip.hidden = false;
  const w = tip.offsetWidth / 2 + 8;
  tip.style.left = `${Math.min(Math.max(e.clientX, w), window.innerWidth - w)}px`;
  tip.style.top = `${e.clientY}px`;
});
document.addEventListener("pointerleave", () => (tip.hidden = true));

// ---------------------------------------------------------------- number tween
const tweens = new WeakMap<Element, { v: number; raf?: number }>();

/** Animate an element's number from its previous value to `value`. */
export function countTo(el: Element, value: number, fmt: (v: number) => string, ms = 700) {
  const st = tweens.get(el);
  if (st?.raf) cancelAnimationFrame(st.raf);
  const from = st?.v;
  tweens.set(el, { v: value });
  if (from == null || from === value || !el.isConnected || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.textContent = fmt(value);
    return;
  }
  const t0 = performance.now();
  const step = (t: number) => {
    const k = Math.min(1, (t - t0) / ms);
    const e = 1 - (1 - k) ** 3;
    el.textContent = fmt(from + (value - from) * e);
    if (k < 1) tweens.get(el)!.raf = requestAnimationFrame(step);
  };
  tweens.get(el)!.raf = requestAnimationFrame(step);
}

// ---------------------------------------------------------------- dialogs
export interface Sheet { dialog: HTMLDialogElement; body: HTMLDivElement; close: () => void }

/** A modal sheet with a close button; removed from the page when closed. */
export function sheet(opts: { wide?: boolean; onClose?: () => void } = {}): Sheet {
  const dialog = h("dialog", { class: opts.wide ? "wide" : "" });
  const body = h("div", { class: "sheet" });
  const close = () => dialog.close();
  body.append(iconButton("close", "Close", close, "btn quiet close"));
  dialog.append(body);
  dialog.addEventListener("close", () => {
    opts.onClose?.();
    dialog.remove();
  });
  dialog.addEventListener("click", (e) => e.target === dialog && close()); // backdrop
  document.body.append(dialog);
  queueMicrotask(() => dialog.showModal());
  return { dialog, body, close };
}

export function confirmDialog(title: string, body: string, ok: string): Promise<boolean> {
  return new Promise((resolve) => {
    let result = false;
    const s = sheet({ onClose: () => resolve(result) });
    s.body.append(
      h("h2", { class: "dialog-title" }, title),
      h("div", { class: "sub" }, body),
      h("div", { class: "row" },
        h("button", { class: "btn primary", style: "flex:1", on: { click: () => { result = true; s.close(); } } }, ok),
        h("button", { class: "btn soft", on: { click: s.close } }, "Cancel")),
    );
  });
}

export function switchEl(on: boolean, label: string, onChange: (on: boolean) => void): HTMLButtonElement {
  const b = h("button", { class: "switch", role: "switch", "aria-label": label, "aria-checked": String(on), title: label });
  b.addEventListener("click", () => {
    const v = b.getAttribute("aria-checked") !== "true";
    b.setAttribute("aria-checked", String(v));
    onChange(v);
  });
  return b;
}

export const setSwitch = (b: HTMLElement, on: boolean) => b.setAttribute("aria-checked", String(on));
