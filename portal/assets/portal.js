// Shared helpers for every page: requests to the API, messages, dates, icons and the account icon.
// Every page loads this file first, then its own script.
(function () {
  "use strict";

  const ICONS = "/assets/icons.svg";

  function $(id) {
    return document.getElementById(id);
  }

  // POST a JSON body. Throws an Error with .status and the server's message on failure.
  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
      credentials: "same-origin",
    });
    let data = {};
    try { data = await res.json(); } catch (err) { data = {}; }
    if (!res.ok) {
      const error = new Error(data.error || `Request failed (${res.status}).`);
      error.status = res.status;
      throw error;
    }
    return data;
  }

  // GET without throwing. Returns { ok, status, data }.
  async function get(path) {
    try {
      const res = await fetch(path, { credentials: "same-origin" });
      let data = {};
      try { data = await res.json(); } catch (err) { data = {}; }
      return { ok: res.ok, status: res.status, data: data };
    } catch (err) {
      return { ok: false, status: 0, data: { error: "Cannot reach the server. Check that it is running." } };
    }
  }

  // GET that throws on failure, like post().
  async function getJson(path) {
    const result = await get(path);
    if (!result.ok) {
      const error = new Error(result.data.error || `Request failed (${result.status}).`);
      error.status = result.status;
      throw error;
    }
    return result.data;
  }

  // Show a message in an element, or hide it when the message is empty.
  function say(id, message, tone) {
    const box = $(id);
    if (!box) return;
    box.textContent = message || "";
    box.hidden = !message;
    if (tone) {
      box.classList.remove("ok", "err", "info");
      box.classList.add(tone);
    }
  }

  function icon(name, extraClass) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "icon" + (extraClass ? " " + extraClass : ""));
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(ns, "use");
    use.setAttribute("href", `${ICONS}#${name}`);
    svg.appendChild(use);
    return svg;
  }

  // Make an element: el("p", { className: "x" }, "text", child, ...)
  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (key === "className") node.className = value;
      else if (key === "dataset") Object.assign(node.dataset, value);
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else if (value !== undefined && value !== null && value !== false) node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  // Dates from the server are UTC. Show them in this computer's time, as day/month/year and time.
  function when(iso, empty) {
    if (!iso) return empty || "No time limit";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function initials(name) {
    const words = String(name || "").trim().split(/\s+/).filter(Boolean);
    return words.slice(0, 2).map((word) => word[0].toUpperCase()).join("") || "?";
  }

  // The account icon: shows the signed-in person's details. Its Log out button is the only one.
  function setupAccount(name, rows) {
    const area = $("accountArea");
    const button = $("accountButton");
    const panel = $("accountPanel");
    const details = $("accountDetails");
    if (!area || !button || !panel || !details) return;
    button.textContent = initials(name);
    button.title = name || "Your account";
    details.replaceChildren();
    for (const [label, value] of rows) {
      details.append(el("dt", null, label), el("dd", null, value || "Not recorded"));
    }
    area.hidden = false;

    const close = () => {
      panel.hidden = true;
      button.setAttribute("aria-expanded", "false");
    };
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = panel.hidden;
      panel.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", (event) => {
      if (!area.contains(event.target)) close();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });
    $("logoutButton").addEventListener("click", logout);
  }

  async function logout() {
    try { await post("/api/logout", {}); } catch (err) { /* the session ends either way */ }
    window.location.replace("/");
  }

  // Pages for a logged-in citizen call this first. Anyone else is sent to the right place.
  const HOME_FOR = { citizen: "/home", officer: "/officer", worker: "/worker" };

  // Pages for one kind of account call this first. Anyone else is sent to their own page, or to log in.
  async function requireRole(role) {
    const me = await get("/api/me");
    if (me.ok && me.data.role === role) return me.data;
    window.location.replace(me.ok && HOME_FOR[me.data.role] ? HOME_FOR[me.data.role] : "/");
    return new Promise(() => {}); // the page is changing; stop here
  }

  function requireCitizen() {
    return requireRole("citizen");
  }

  function citizenAccountRows(profile) {
    return [
      ["Name", profile.name],
      ["Mobile", profile.mobile],
      ["Address", profile.address],
      ["Zone", profile.zone],
      ["Ward", profile.ward],
    ];
  }

  // The router's message for the citizen, exactly as the router wrote it. Its first line is a banner that says
  // the text is a draft and not an official reply; that line is shown as a notice, and the rest as the message.
  function routerMessage(message) {
    const text = String(message || "");
    const cut = text.indexOf("\n\n");
    const banner = cut === -1 ? "" : text.slice(0, cut);
    const body = cut === -1 ? text : text.slice(cut + 2);
    return [
      banner ? el("p", { className: "router-banner" }, banner) : null,
      el("pre", { className: "router-message" }, body),
    ];
  }

  // The router's timeline as steps: each office, its time limit, and where the complaint is now.
  function routerProgress(progress) {
    if (!progress || !Array.isArray(progress.steps) || !progress.steps.length) return null;
    const words = { done: "Done", current: "Now", upcoming: "Next", skipped: "Not needed" };
    const marks = { done: "\u2713", current: "\u25cf", upcoming: "", skipped: "\u2013" };
    const steps = progress.steps.map((step) => el("li", { className: `rs ${step.state}` },
      el("span", { className: "rs-mark", "aria-hidden": "true" }, marks[step.state] || ""),
      el("div", { className: "rs-body" },
        el("strong", null, step.office),
        el("span", { className: "rs-time" }, `Time limit: ${step.time_limit}`),
        step.deadline ? el("span", { className: "rs-deadline" }, `Counting down to ${when(step.deadline)}`) : null),
      el("span", { className: "rs-state" }, words[step.state] || "")));
    return el("div", { className: "router-progress" },
      progress.label ? el("p", { className: "rp-head" }, el("strong", null, progress.label),
        progress.repair_time ? ` \u2013 charter repair time ${progress.repair_time}` : "") : null,
      el("ol", { className: "router-steps" }, ...steps),
      progress.after_last_level ? el("p", { className: "muted" }, progress.after_last_level) : null,
      progress.note ? el("p", { className: "muted" }, progress.note) : null);
  }

  window.Portal = {
    $, post, get, getJson, say, icon, el, when, initials, routerMessage, routerProgress,
    setupAccount, logout, requireCitizen, requireRole, citizenAccountRows, HOME_FOR,
    // The status a citizen sees: a green Resolved once an officer or worker has resolved it.
    citizenPill(item) {
      if (item.status === "closed" || item.status === "awaiting_confirmation") return el("span", { className: "pill resolved side" }, "Resolved");
      if (item.work_status === "allotted") return el("span", { className: "pill allotted side" }, "Allotted \u00b7 Work in progress");
      if (item.rejected_before) return el("span", { className: "pill notdone side" }, "Rejected \u00b7 In progress");
      return el("span", { className: "pill registered side" }, "Registered");
    },
  };
})();
