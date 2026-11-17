// Copyright (C) 2026 Kuan Qian
// SPDX-License-Identifier: GPL-3.0-only

"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  banner: $("banner"),
  screens: { start: $("start"), lobby: $("lobby"), game: $("game") },
  startTitle: $("start-title"),
  startError: $("start-error"),
  name: $("name"),
  painter: $("painter"),
  joinForm: $("join-form"),
  joinCode: $("join-code"),
  createButton: $("create-button"),
  lobbyCode: $("lobby-code"),
  inviteLink: $("invite-link"),
  copyLink: $("copy-link"),
  lobbyPlayers: $("lobby-players"),
  lobbyStart: $("lobby-start"),
  gameTitle: $("game-title"),
  channels: $("channels"),
  roomCode: $("room-code"),
  gamePlayers: $("game-players"),
  endButtons: document.querySelectorAll(".end-button"),
  leaveButtons: document.querySelectorAll(".leave-button"),
  channelName: $("channel-name"),
  messages: $("messages"),
  typing: $("typing"),
  composer: $("composer"),
  composerInput: $("composer-input"),
};

const store = {
  get(key) {
    try { return localStorage.getItem(`verbage.${key}`); } catch { return null; }
  },
  set(key, value) {
    try {
      if (value === null) localStorage.removeItem(`verbage.${key}`);
      else localStorage.setItem(`verbage.${key}`, value);
    } catch { /* private mode: the game still works, it just cannot resume */ }
  },
  json(key) {
    try { return JSON.parse(this.get(key)); } catch { return null; }
  },
};

const state = {
  title: "Verbage",
  room: null, // { code, you, state, players: Map(id -> { id, name, portrait, online }) }
  channels: new Map(), // name -> { name, items, unread, awaiting, typingUntil, button }
  active: null,
};

// A code from an invite link (?room=ABCD) wins over a remembered seat elsewhere.
let inviteCode = (new URLSearchParams(location.search).get("room") || "").toUpperCase();

const running = () => Boolean(state.room && state.room.state === "running");

// ---- connection -----------------------------------------------------------

let socket = null;
let retryDelay = 500;
let bannerTimer = null;

function connect() {
  const url = new URL("ws", document.baseURI);
  url.search = "";
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(url);
  socket.addEventListener("open", () => {
    retryDelay = 500;
    clearTimeout(bannerTimer);
    showBanner(null);
    const seat = store.json("seat");
    const resume = seat && (!inviteCode || inviteCode === seat.room);
    send({ type: "hello", room: resume ? seat.room : null, token: resume ? seat.token : null });
  });
  socket.addEventListener("message", (event) => handle(JSON.parse(event.data)));
  socket.addEventListener("close", () => {
    clearTimeout(bannerTimer);
    bannerTimer = setTimeout(() => showBanner("Reconnecting…"), 1000);
    setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 5000);
  });
}

function send(message) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

function showBanner(text) {
  els.banner.hidden = !text;
  els.banner.textContent = text || "";
}

function showScreen(name) {
  for (const [key, screen] of Object.entries(els.screens)) screen.hidden = key !== name;
}

// ---- server events ----------------------------------------------------------

function handle(event) {
  switch (event.type) {
    case "welcome": return onWelcome(event);
    case "error": return onError(event.message);
    case "players": return onPlayers(event.players);
    case "status": return onStatus(event);
    case "channel": return void ensureChannel(event.channel);
    case "remove_channel": return removeChannel(event.channel);
    case "item": return onItem(event.channel, event.item);
    case "update": return onUpdate(event.channel, event.id, event.patch);
    case "clear": return onClear(event.channel);
    case "awaiting": return onAwaiting(event.channel, event.value);
    case "typing": return onTyping(event.channel, event.seconds);
  }
}

function resetChannels() {
  state.channels.clear();
  state.active = null;
  els.channels.replaceChildren();
  els.messages.replaceChildren();
}

function onWelcome(event) {
  state.title = event.title;
  els.startTitle.textContent = event.title;
  els.gameTitle.textContent = event.title;
  const keep = state.active;
  resetChannels();

  if (!event.room) {
    state.room = null;
    store.set("seat", null);
    els.joinCode.value = inviteCode;
    if (!inviteCode) history.replaceState(null, "", location.pathname);
    showError(event.notice || null);
    showScreen("start");
    updateTitle();
    return;
  }

  const room = event.room;
  inviteCode = "";
  store.set("seat", JSON.stringify({ room: room.code, token: room.token }));
  history.replaceState(null, "", `?room=${room.code}`);
  state.room = { code: room.code, you: room.you, state: room.state, players: new Map() };
  els.lobbyCode.textContent = room.code;
  els.roomCode.textContent = room.code;
  els.inviteLink.value = location.href;
  for (const data of room.channels) {
    const channel = ensureChannel(data.name);
    channel.items = data.items.map(stampDeadline);
    channel.awaiting = data.awaiting_input;
  }
  onPlayers(room.players);
  showScreen(room.state === "lobby" ? "lobby" : "game");
  selectChannel(state.channels.has(keep) ? keep : firstChannel());
  renderStatus();
}

function showError(message) {
  els.startError.textContent = message || "";
  els.startError.hidden = !message;
}

function onError(message) {
  if (state.room) {
    showBanner(message);
    setTimeout(() => showBanner(null), 4000);
  } else {
    showError(message);
  }
}

function onPlayers(players) {
  if (!state.room) return;
  state.room.players = new Map(players.map((player) => [player.id, player]));
  for (const list of [els.lobbyPlayers, els.gamePlayers]) {
    list.replaceChildren(...players.map((player) => {
      const row = document.createElement("li");
      row.classList.toggle("offline", !player.online);
      const name = el("span", "name");
      name.textContent = player.name;
      row.append(avatarFor(player.name, Portrait.toDataURL(player.portrait)), name);
      if (player.id === state.room.you) row.append(el("span", "tag", "you"));
      else if (!player.online) row.append(el("span", "tag", "away"));
      return row;
    }));
  }
}

function onStatus(event) {
  if (!state.room) return;
  state.room.state = event.state;
  if (event.reset) resetChannels();
  showScreen("game");
  renderStatus();
}

// The server sends seconds remaining; pin that to this browser's clock.
function stampDeadline(item) {
  if (typeof item.remaining === "number") item.deadline = performance.now() + item.remaining * 1000;
  return item;
}

function ensureChannel(name) {
  let channel = state.channels.get(name);
  if (channel) return channel;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "channel";
  button.addEventListener("click", () => selectChannel(name));
  channel = { name, items: [], unread: 0, awaiting: false, typingUntil: 0, button };
  state.channels.set(name, channel);
  els.channels.append(button);
  refreshSidebar();
  if (!state.active && state.room) selectChannel(name);
  return channel;
}

function removeChannel(name) {
  const channel = state.channels.get(name);
  if (!channel) return;
  channel.button.remove();
  state.channels.delete(name);
  if (state.active === name) {
    state.active = null;
    selectChannel(firstChannel());
  }
  refreshSidebar();
}

function firstChannel() {
  return state.channels.keys().next().value ?? null;
}

function onItem(name, item) {
  const channel = ensureChannel(name);
  stampDeadline(item);
  channel.items.push(item);
  channel.typingUntil = 0;
  const mine = item.kind === "player" && item.player === state.room.you;
  if (name === state.active) {
    const stick = nearBottom();
    els.messages.append(renderItem(item, channel.items[channel.items.length - 2]));
    if (stick || mine) scrollToBottom();
    renderTyping();
  } else if (!mine) {
    channel.unread += 1;
  }
  refreshSidebar();
}

function onUpdate(name, id, patch) {
  const channel = state.channels.get(name);
  const index = channel ? channel.items.findIndex((item) => item.id === id) : -1;
  if (index < 0) return;
  const item = Object.assign(channel.items[index], patch);
  if (name === state.active) {
    const node = els.messages.querySelector(`[data-id="${id}"]`);
    if (node) node.replaceWith(renderItem(item, channel.items[index - 1]));
  }
  refreshSidebar();
}

function onClear(name) {
  const channel = state.channels.get(name);
  if (!channel) return;
  channel.items = [];
  channel.unread = 0;
  if (name === state.active) els.messages.replaceChildren();
  refreshSidebar();
}

function onAwaiting(name, value) {
  const channel = ensureChannel(name);
  channel.awaiting = value;
  if (name === state.active) renderComposer();
  refreshSidebar();
}

function onTyping(name, seconds) {
  const channel = ensureChannel(name);
  channel.typingUntil = performance.now() + seconds * 1000 + 300;
  setTimeout(renderTyping, seconds * 1000 + 350);
  renderTyping();
}

// ---- rendering ----------------------------------------------------------------

function selectChannel(name) {
  if (!name || !state.channels.has(name)) {
    els.channelName.textContent = "";
    renderComposer();
    return;
  }
  state.active = name;
  const channel = state.channels.get(name);
  channel.unread = 0;
  els.channelName.textContent = name;
  els.messages.replaceChildren(...channel.items.map((item, index) => renderItem(item, channel.items[index - 1])));
  scrollToBottom();
  renderComposer();
  renderTyping();
  refreshSidebar();
}

const pickedByMe = (item) => item.picks.some((pick) => pick.player === state.room.you);

// True when the story cannot move on in this channel until this player acts.
function needsAction(channel) {
  if (!running()) return false;
  return channel.awaiting || channel.items.some((item) =>
    item.open && (item.kind === "button" || (item.kind === "menu" && !pickedByMe(item))));
}

function refreshSidebar() {
  let unreadTotal = 0;
  for (const channel of state.channels.values()) {
    unreadTotal += channel.unread;
    const label = el("span", "label");
    label.textContent = channel.name;
    const parts = [label];
    if (needsAction(channel)) {
      const dot = el("span", "waiting");
      dot.title = "Waiting for a player";
      parts.push(dot);
    }
    if (channel.unread) parts.push(el("span", "count", channel.unread > 99 ? "99+" : String(channel.unread)));
    channel.button.replaceChildren(...parts);
    channel.button.classList.toggle("active", channel.name === state.active);
    channel.button.classList.toggle("unread", channel.unread > 0);
    if (channel.name === state.active) channel.button.setAttribute("aria-current", "page");
    else channel.button.removeAttribute("aria-current");
  }
  updateTitle(unreadTotal);
}

function updateTitle(unread = 0) {
  document.title = unread ? `(${unread}) ${state.title}` : state.title;
}

function renderStatus() {
  for (const button of els.endButtons) {
    button.textContent = running() ? "End game" : "Play again";
    button.classList.toggle("primary", !running());
    button.classList.toggle("quiet", running());
  }
  renderTyping();
  // Open buttons and menus must stop looking clickable once the game is over.
  selectChannel(state.active);
  refreshSidebar();
}

function renderComposer() {
  const channel = state.channels.get(state.active);
  const awaiting = Boolean(running() && channel && channel.awaiting);
  const usable = running() && Boolean(channel);
  els.composer.classList.toggle("awaiting", awaiting);
  els.composerInput.disabled = !usable;
  els.composer.querySelector("button").disabled = !usable;
  els.composerInput.placeholder = !running()
    ? "The game has ended"
    : !channel
      ? "The story is about to begin…"
      : awaiting
        ? "The story is waiting for a reply…"
        : `Message #${state.active}`;
  if (awaiting && matchMedia("(pointer: fine)").matches) els.composerInput.focus();
}

function renderTyping() {
  const channel = state.channels.get(state.active);
  els.typing.classList.toggle("on", Boolean(running() && channel && channel.typingUntil > performance.now()));
}

function nearBottom() {
  const box = els.messages;
  return box.scrollHeight - box.scrollTop - box.clientHeight < 120;
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.append(...richText(text));
  return node;
}

// Discord-style inline markup: **bold**, *italic*, `code`. Builds DOM nodes, so
// script and player text is never parsed as HTML.
function richText(text) {
  const nodes = [];
  const pattern = /\*\*([^*]+)\*\*|\*([^*\n]+)\*|`([^`\n]+)`/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const tag = match[1] !== undefined ? "strong" : match[2] !== undefined ? "em" : "code";
    const node = document.createElement(tag);
    node.textContent = match[1] ?? match[2] ?? match[3];
    nodes.push(node);
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

// An avatar is a picture when there is one, otherwise the name's first letter.
function avatarFor(name, url, pixelated = true) {
  let avatar;
  if (url) {
    avatar = document.createElement("img");
    avatar.src = url;
    avatar.alt = "";
    if (pixelated) avatar.classList.add("pixel");
  } else {
    avatar = document.createElement("span");
    avatar.textContent = (name || "?").trim().charAt(0).toUpperCase();
  }
  avatar.classList.add("avatar");
  return avatar;
}

function renderItem(item, previous) {
  const node = renderItemBody(item, previous);
  node.dataset.id = item.id;
  return node;
}

function renderItemBody(item, previous) {
  switch (item.kind) {
    case "dialogue":
    case "player": return renderSpeech(item, previous);
    case "narration": return el("p", "narration text", item.text);
    case "prompt": return el("p", "prompt text", item.text);
    case "notice": return el("p", "notice text", item.text);
    case "image": return renderImage(item);
    case "link": return renderLink(item);
    case "button": return renderButton(item);
    case "menu": return renderMenu(item);
    default: return el("div");
  }
}

function renderSpeech(item, previous) {
  const node = el("div", `msg ${item.kind}`);
  const sameSpeaker = previous && previous.kind === item.kind && previous.speaker === item.speaker
    && previous.character === item.character && previous.player === item.player;
  if (sameSpeaker) node.classList.add("grouped");
  if (item.color) node.style.setProperty("--c", item.color);

  let avatar;
  if (item.kind === "player") {
    // Players who left the room keep their name but lose their portrait.
    const player = state.room.players.get(item.player);
    avatar = avatarFor(item.speaker, player ? Portrait.toDataURL(player.portrait) : null);
  } else {
    avatar = avatarFor(item.speaker, item.avatar, false);
  }
  const speaker = el("div", "speaker");
  speaker.textContent = item.speaker;
  node.append(avatar, speaker, el("div", "body text", item.text));
  return node;
}

function renderImage(item) {
  const figure = el("figure", "image");
  const image = document.createElement("img");
  image.alt = item.caption || "";
  const stick = nearBottom();
  image.addEventListener("load", () => { if (stick) scrollToBottom(); });
  image.src = item.url;
  figure.append(image);
  if (item.caption) figure.append(el("figcaption", "text", item.caption));
  return figure;
}

function renderLink(item) {
  const node = el("div", "controls");
  const button = el("button", "", `${item.text} →`);
  button.type = "button";
  button.addEventListener("click", () => selectChannel(item.target));
  node.append(button);
  return node;
}

const live = (item) => item.open && running();

function renderTimer(item) {
  if (!live(item) || item.deadline === undefined) return [];
  const remaining = (item.deadline - performance.now()) / 1000;
  if (remaining <= 0) return [];
  const bar = el("span", "timer");
  bar.style.animationDuration = `${remaining}s`;
  return [bar];
}

function renderButton(item) {
  const node = el("div", "controls");
  const button = el("button", "primary", item.text);
  button.type = "button";
  button.disabled = !live(item);
  button.addEventListener("click", () => send({ type: "button", id: item.id }));
  node.append(button, ...renderTimer(item));
  if (item.clicked_by) {
    const who = el("span", "pickers");
    who.textContent = item.clicked_by;
    node.append(who);
  }
  return node;
}

function renderMenu(item) {
  const node = el("div", "controls");
  const answered = pickedByMe(item);
  for (const choice of item.choices) {
    const button = el("button", "", choice.text);
    button.type = "button";
    button.disabled = !live(item) || answered;
    const pickers = item.picks.filter((pick) => pick.index === choice.index).map((pick) => pick.user);
    if (pickers.length) {
      button.classList.add("picked");
      const who = el("span", "pickers");
      who.textContent = pickers.join(", ");
      button.append(who);
    }
    button.addEventListener("click", () => send({ type: "menu", id: item.id, index: choice.index }));
    node.append(button);
  }
  if (!answered) node.append(...renderTimer(item));
  return node;
}

// ---- landing page ---------------------------------------------------------------

els.name.value = store.get("name") || "";
els.name.addEventListener("input", () => store.set("name", els.name.value.trim() || null));
const painter = Portrait.createPainter(els.painter, {
  value: store.get("portrait"),
  onChange: (value) => store.set("portrait", value),
});

function profile() {
  const name = els.name.value.trim();
  if (!name) {
    showError("Enter a name first.");
    els.name.focus();
    return null;
  }
  showError(null);
  return { name, portrait: painter.value };
}

els.createButton.addEventListener("click", () => {
  const who = profile();
  if (who) send({ type: "create", ...who });
});

els.joinForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const code = els.joinCode.value.trim().toUpperCase();
  if (code.length !== 4) {
    showError("Enter the 4-letter room code.");
    els.joinCode.focus();
    return;
  }
  const who = profile();
  if (who) send({ type: "join", room: code, ...who });
});

// ---- room actions -----------------------------------------------------------------

els.copyLink.addEventListener("click", async () => {
  els.inviteLink.select();
  try {
    // Only available on https and localhost; otherwise the link stays selected.
    await navigator.clipboard.writeText(els.inviteLink.value);
    els.copyLink.textContent = "Copied";
    setTimeout(() => { els.copyLink.textContent = "Copy"; }, 1500);
  } catch { /* the selection is the fallback */ }
});

els.lobbyStart.addEventListener("click", () => send({ type: "start" }));

els.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = els.composerInput.value.trim();
  if (!text || !state.active) return;
  send({ type: "say", channel: state.active, text });
  els.composerInput.value = "";
});

for (const button of els.endButtons) {
  button.addEventListener("click", () => {
    if (!state.room) return;
    if (!running()) send({ type: "start" });
    else if (confirm("End the game for everyone in the room?")) send({ type: "stop" });
  });
}

for (const button of els.leaveButtons) {
  button.addEventListener("click", () => {
    if (!state.room) return;
    if (state.room.state === "lobby" || confirm("Leave this room?")) {
      history.replaceState(null, "", location.pathname);
      send({ type: "leave" });
    }
  });
}

connect();
