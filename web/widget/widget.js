/*!
 * AiWoop Support Widget v1.0
 * Embed on any site:
 *   <script src="https://YOUR-API-HOST/widget/widget.js" defer></script>
 * Optional data-* attributes:
 *   data-api-url, data-title, data-subtitle, data-accent, data-greeting,
 *   data-position ("right" | "left"), data-suggestions ("A|B|C"),
 *   data-brand-name, data-brand-url
 * JS API: window.AiWoopWidget.open() / .close() / .reset() / .ask("text")
 */
(() => {
  "use strict";
  if (window.AiWoopWidget) return;

  const script = document.currentScript;
  const ds = (script && script.dataset) || {};
  const scriptOrigin = script && script.src ? new URL(script.src).origin : location.origin;

  const CONFIG = {
    apiUrl: (ds.apiUrl || scriptOrigin).replace(/\/$/, ""),
    title: ds.title || "Support",
    subtitle: ds.subtitle || "AI assistant · replies instantly",
    accent: ds.accent || "#4F46E5",
    greeting:
      ds.greeting ||
      "Hi! 👋 I can help with orders, shipping, returns and refunds. How can I help you today?",
    position: ds.position === "left" ? "left" : "right",
    suggestions: (ds.suggestions || "Track my order|Start a return|Shipping times|Talk to a human")
      .split("|")
      .map((s) => s.trim())
      .filter(Boolean),
    brandName: ds.brandName || "AiWoop",
    brandUrl: ds.brandUrl || "",
  };

  const MAX_LENGTH = 2000;
  const MAX_STORED_MESSAGES = 50;
  const THREAD_ID_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;
  const STORAGE_KEY = `aiwoop-chat:${CONFIG.apiUrl}`;

  // ---------- Persistence (localStorage may be blocked: never let it break the widget) ----------
  const storage = {
    load() {
      try {
        const data = JSON.parse(localStorage.getItem(STORAGE_KEY));
        if (!data || !Array.isArray(data.messages)) return null;
        if (data.threadId && !THREAD_ID_PATTERN.test(data.threadId)) data.threadId = null;
        return data;
      } catch {
        return null;
      }
    },
    save(value) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
      } catch {
        /* storage unavailable: keep working in memory */
      }
    },
    clear() {
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
    },
  };

  let state = storage.load() || { threadId: null, messages: [] };
  let busy = false;
  let errorEl = null;

  // ---------- Markup ----------
  const icon = (paths) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  const ICONS = {
    chat: icon('<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'),
    close: icon('<path d="M18 6 6 18M6 6l12 12"/>'),
    reset: icon(
      '<path d="M3 12a9 9 0 0 1 15.5-6.3L21 8"/><path d="M21 3v5h-5"/>' +
        '<path d="M21 12a9 9 0 0 1-15.5 6.3L3 16"/><path d="M3 21v-5h5"/>'
    ),
    send: icon('<path d="M12 19V5M5 12l7-7 7 7"/>'),
  };

  const CSS = `
    :host {
      --accent: #4F46E5;
      --surface: #FFFFFF;
      --canvas: #F8F8FA;
      --text: #111827;
      --muted: #6B7280;
      --border: #E5E7EB;
      all: initial;
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
        "Noto Sans Arabic", "Helvetica Neue", Arial, sans-serif;
    }
    *, *::before, *::after { box-sizing: border-box; }
    button { font: inherit; }

    .launcher {
      position: fixed; bottom: 24px; right: 24px; z-index: 2147483000;
      width: 60px; height: 60px; border-radius: 50%; border: none; cursor: pointer;
      background: var(--accent); color: #fff; display: grid; place-items: center;
      box-shadow: 0 10px 30px rgba(17, 24, 39, 0.22);
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .launcher:hover { transform: translateY(-2px) scale(1.04); }
    .launcher:focus-visible { outline: 3px solid color-mix(in srgb, var(--accent) 40%, white); outline-offset: 3px; }
    .launcher svg { width: 26px; height: 26px; }
    .launcher .i-close { display: none; }
    .launcher[aria-expanded="true"] .i-chat { display: none; }
    .launcher[aria-expanded="true"] .i-close { display: block; }

    .panel {
      position: fixed; bottom: 100px; right: 24px; z-index: 2147483000;
      width: 380px; height: min(640px, calc(100vh - 130px));
      display: flex; flex-direction: column; overflow: hidden;
      background: var(--surface); color: var(--text);
      border-radius: 18px; box-shadow: 0 24px 64px rgba(17, 24, 39, 0.24);
      font-size: 14px; line-height: 1.5;
      animation: pop 0.18s ease-out;
    }
    .panel[hidden] { display: none; }
    :host([data-position="left"]) .launcher,
    :host([data-position="left"]) .panel { right: auto; left: 24px; }
    @keyframes pop {
      from { opacity: 0; transform: translateY(12px) scale(0.98); }
      to { opacity: 1; transform: none; }
    }

    .header {
      display: flex; align-items: center; gap: 12px; padding: 16px;
      background: var(--accent); color: #fff;
    }
    .avatar {
      width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0;
      display: grid; place-items: center; font-weight: 600; font-size: 16px;
      background: rgba(255, 255, 255, 0.2);
    }
    .meta { flex: 1; min-width: 0; }
    .title { font-weight: 600; font-size: 15px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .subtitle { display: flex; align-items: center; gap: 6px; font-size: 12px; opacity: 0.9; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #34D399; flex-shrink: 0; }
    .icon-btn {
      width: 32px; height: 32px; border-radius: 8px; border: none; cursor: pointer;
      display: grid; place-items: center; background: transparent; color: #fff; opacity: 0.85;
    }
    .icon-btn:hover { background: rgba(255, 255, 255, 0.16); opacity: 1; }
    .icon-btn:focus-visible { outline: 2px solid #fff; }
    .icon-btn svg { width: 18px; height: 18px; }

    .messages {
      flex: 1; overflow-y: auto; padding: 16px;
      display: flex; flex-direction: column; gap: 10px; background: var(--canvas);
      scroll-behavior: smooth;
    }
    .msg {
      max-width: 85%; padding: 10px 14px; border-radius: 16px;
      white-space: pre-wrap; overflow-wrap: anywhere;
    }
    .msg.user {
      align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 4px;
    }
    .msg.bot {
      align-self: flex-start; background: var(--surface); border: 1px solid var(--border);
      border-bottom-left-radius: 4px;
    }
    .msg.error {
      align-self: center; max-width: 95%; font-size: 13px; text-align: center;
      background: #FEF2F2; color: #B91C1C; border: 1px solid #FECACA;
    }
    .typing { display: inline-flex; gap: 4px; padding: 4px 2px; }
    .typing span {
      width: 6px; height: 6px; border-radius: 50%; background: var(--muted);
      animation: blink 1.2s infinite ease-in-out;
    }
    .typing span:nth-child(2) { animation-delay: 0.15s; }
    .typing span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes blink { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }

    .suggestions { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 16px 12px; background: var(--canvas); }
    .suggestions:empty { display: none; }
    .chip {
      padding: 6px 12px; border-radius: 999px; cursor: pointer; font-size: 13px;
      border: 1px solid var(--accent); background: var(--surface); color: var(--accent);
      transition: background 0.15s ease, color 0.15s ease;
    }
    .chip:hover { background: var(--accent); color: #fff; }

    .composer {
      display: flex; align-items: flex-end; gap: 8px; padding: 12px;
      border-top: 1px solid var(--border); background: var(--surface);
    }
    textarea {
      flex: 1; resize: none; max-height: 120px; padding: 10px 12px; outline: none;
      border: 1px solid var(--border); border-radius: 12px;
      font: inherit; color: inherit; background: var(--surface);
    }
    textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
    }
    .send {
      width: 40px; height: 40px; flex-shrink: 0; border: none; border-radius: 12px; cursor: pointer;
      display: grid; place-items: center; background: var(--accent); color: #fff;
    }
    .send:disabled { opacity: 0.4; cursor: not-allowed; }
    .send svg { width: 18px; height: 18px; }

    .brand { padding: 6px 0 10px; text-align: center; font-size: 11px; color: var(--muted); background: var(--surface); }
    .brand a, .brand strong { color: var(--muted); font-weight: 600; text-decoration: none; }
    .brand a:hover { color: var(--accent); }

    @media (max-width: 480px) {
      .panel { inset: 0; width: 100%; height: 100%; border-radius: 0; }
      .launcher[aria-expanded="true"] { display: none; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { animation: none !important; transition: none !important; }
    }
  `;

  const HTML = `
    <button class="launcher" type="button" aria-label="Open support chat" aria-expanded="false">
      <span class="i-chat">${ICONS.chat}</span><span class="i-close">${ICONS.close}</span>
    </button>
    <section class="panel" role="dialog" aria-label="Support chat" hidden>
      <header class="header">
        <div class="avatar" aria-hidden="true"></div>
        <div class="meta">
          <div class="title"></div>
          <div class="subtitle"><span class="dot"></span><span class="subtitle-text"></span></div>
        </div>
        <button class="icon-btn reset" type="button" aria-label="Start a new conversation"
          title="New conversation">${ICONS.reset}</button>
        <button class="icon-btn close" type="button" aria-label="Close chat">${ICONS.close}</button>
      </header>
      <div class="messages" role="log" aria-live="polite"></div>
      <div class="suggestions"></div>
      <form class="composer">
        <textarea rows="1" placeholder="Type your message…" aria-label="Message"
          maxlength="${MAX_LENGTH}"></textarea>
        <button class="send" type="submit" aria-label="Send message" disabled>${ICONS.send}</button>
      </form>
      <footer class="brand"></footer>
    </section>
  `;

  function mount() {
    const host = document.createElement("div");
    host.id = "aiwoop-support-widget";
    host.setAttribute("data-position", CONFIG.position);
    host.style.setProperty("--accent", CONFIG.accent);
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `<style>${CSS}</style>${HTML}`;
    document.body.appendChild(host);

    const $ = (selector) => shadow.querySelector(selector);
    const ui = {
      launcher: $(".launcher"),
      panel: $(".panel"),
      list: $(".messages"),
      suggestions: $(".suggestions"),
      form: $(".composer"),
      input: $("textarea"),
      send: $(".send"),
    };

    // Static texts via textContent (never innerHTML for configurable values)
    $(".avatar").textContent = CONFIG.title.charAt(0).toUpperCase();
    $(".title").textContent = CONFIG.title;
    $(".subtitle-text").textContent = CONFIG.subtitle;
    const brand = $(".brand");
    brand.append("Powered by ");
    const brandEl = document.createElement(CONFIG.brandUrl ? "a" : "strong");
    brandEl.textContent = CONFIG.brandName;
    if (CONFIG.brandUrl) {
      brandEl.href = CONFIG.brandUrl;
      brandEl.target = "_blank";
      brandEl.rel = "noopener noreferrer";
    }
    brand.append(brandEl);

    // ---------- Rendering ----------
    const scrollToBottom = () => {
      ui.list.scrollTop = ui.list.scrollHeight;
    };

    function addMessage(role, text) {
      const el = document.createElement("div");
      el.className = `msg ${role}`;
      el.dir = "auto"; // Correct alignment for Arabic and other RTL languages
      el.textContent = text; // XSS-safe: model output is never parsed as HTML
      ui.list.appendChild(el);
      scrollToBottom();
      return el;
    }

    function addTypingIndicator() {
      const el = addMessage("bot", "");
      el.setAttribute("aria-label", "Assistant is typing");
      el.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
      return el;
    }

    function renderSuggestions() {
      ui.suggestions.replaceChildren();
      if (state.messages.length) return;
      for (const text of CONFIG.suggestions) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip";
        chip.textContent = text;
        chip.addEventListener("click", () => send(text));
        ui.suggestions.appendChild(chip);
      }
    }

    function render() {
      ui.list.replaceChildren();
      addMessage("bot", CONFIG.greeting);
      for (const message of state.messages) {
        addMessage(message.role === "user" ? "user" : "bot", message.content);
      }
      renderSuggestions();
    }

    function showError(text) {
      clearError();
      errorEl = addMessage("error", text);
    }

    function clearError() {
      if (errorEl) errorEl.remove();
      errorEl = null;
    }

    function persist() {
      state.messages = state.messages.slice(-MAX_STORED_MESSAGES);
      storage.save(state);
    }

    // ---------- Input ----------
    function autosize() {
      ui.input.style.height = "auto";
      ui.input.style.height = `${Math.min(ui.input.scrollHeight, 120)}px`;
    }

    function updateSendButton() {
      ui.send.disabled = busy || !ui.input.value.trim();
    }

    // ---------- Networking (Server-Sent Events over fetch) ----------
    async function* readEvents(response) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) return;
        buffer += decoder.decode(value, { stream: true });
        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const chunk = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const line = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (line) yield JSON.parse(line.slice(6));
        }
      }
    }

    async function send(rawText) {
      const message = String(rawText || "").trim().slice(0, MAX_LENGTH);
      if (!message || busy) return;

      busy = true;
      updateSendButton();
      clearError();
      ui.suggestions.replaceChildren();

      const userEl = addMessage("user", message);
      const botEl = addTypingIndicator();
      let streamed = "";
      let final = null;

      try {
        const body = state.threadId ? { message, thread_id: state.threadId } : { message };
        const response = await fetch(`${CONFIG.apiUrl}/public/v1/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (response.status === 429) {
          throw new Error("You're sending messages too quickly. Please wait a moment and try again.");
        }
        if (!response.ok || !response.body) {
          throw new Error("Something went wrong. Please try again.");
        }

        for await (const event of readEvents(response)) {
          if (event.type === "token") {
            streamed += event.content;
            botEl.textContent = streamed;
            scrollToBottom();
          } else if (event.type === "done") {
            final = event;
          } else if (event.type === "error") {
            throw new Error(event.detail || "Something went wrong. Please try again.");
          }
        }
        if (!final) throw new Error("The connection was interrupted. Please try again.");

        botEl.textContent = final.reply; // Authoritative final text
        state.threadId = final.thread_id;
        state.messages.push({ role: "user", content: message });
        state.messages.push({ role: "assistant", content: final.reply });
        persist();
      } catch (error) {
        userEl.remove();
        botEl.remove();
        ui.input.value = message; // Give the message back so the visitor can retry
        autosize();
        showError(
          error instanceof TypeError
            ? "Can't reach support right now. Check your connection and try again."
            : error.message
        );
        renderSuggestions();
      } finally {
        busy = false;
        updateSendButton();
        ui.input.focus();
      }
    }

    // ---------- Open / close / reset ----------
    const isOpen = () => !ui.panel.hidden;

    function toggle(open = !isOpen()) {
      ui.panel.hidden = !open;
      ui.launcher.setAttribute("aria-expanded", String(open));
      ui.launcher.setAttribute("aria-label", open ? "Close support chat" : "Open support chat");
      if (open) {
        scrollToBottom();
        setTimeout(() => ui.input.focus(), 50);
      }
    }

    function reset() {
      if (busy) return;
      state = { threadId: null, messages: [] };
      storage.clear();
      clearError();
      render();
    }

    // ---------- Events ----------
    ui.launcher.addEventListener("click", () => toggle());
    $(".close").addEventListener("click", () => toggle(false));
    $(".reset").addEventListener("click", reset);

    ui.input.addEventListener("input", () => {
      autosize();
      updateSendButton();
    });
    ui.input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        ui.form.requestSubmit();
      }
    });
    ui.form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (busy) return;
      const text = ui.input.value;
      ui.input.value = "";
      autosize();
      send(text);
    });
    shadow.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && isOpen()) {
        toggle(false);
        ui.launcher.focus();
      }
    });

    render();

    window.AiWoopWidget = {
      open: () => toggle(true),
      close: () => toggle(false),
      reset,
      ask(text) {
        if (busy) return;
        reset();
        toggle(true);
        send(text);
      },
    };
  }

  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount, { once: true });
})();