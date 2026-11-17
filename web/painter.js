// Copyright (C) 2026 Kuan Qian
// SPDX-License-Identifier: GPL-3.0-only

"use strict";

// Player portraits use the same 32 x 32 grid as the character art in
// game/images. A portrait travels as 1024 hex digits, one palette index per
// cell, so the server can validate it without decoding an image.
const Portrait = (() => {
  const SIZE = 32;
  const BACKGROUND = 1;
  const PALETTE = [
    "#1b1719", "#f4f1ea", "#9a9a9a", "#4a4a52",
    "#6b3a2a", "#a9683c", "#e0a878", "#f6d3b0",
    "#c8323c", "#f08a3c", "#f4d03c", "#4caf50",
    "#1f6f4a", "#3f8fd8", "#2a3f8f", "#9a4fb8",
  ];
  const NAMES = [
    "Black", "White", "Grey", "Dark grey",
    "Brown", "Tan", "Peach", "Cream",
    "Red", "Orange", "Yellow", "Green",
    "Dark green", "Blue", "Navy", "Purple",
  ];

  const valid = (value) => typeof value === "string" && /^[0-9a-f]{1024}$/.test(value);
  const parse = (value) => valid(value)
    ? Array.from(value, (digit) => parseInt(digit, 16))
    : new Array(SIZE * SIZE).fill(BACKGROUND);
  const serialize = (cells) => cells.map((cell) => cell.toString(16)).join("");

  function draw(canvas, cells) {
    const context = canvas.getContext("2d");
    for (let index = 0; index < cells.length; index += 1) {
      context.fillStyle = PALETTE[cells[index]];
      context.fillRect(index % SIZE, Math.floor(index / SIZE), 1, 1);
    }
  }

  const urls = new Map();
  function toDataURL(value) {
    if (!valid(value)) return null;
    if (!urls.has(value)) {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = SIZE;
      draw(canvas, parse(value));
      urls.set(value, canvas.toDataURL("image/png"));
    }
    return urls.get(value);
  }

  // Builds the editor inside `root`. `onChange` receives the serialized
  // portrait, or null once the player clears it.
  function createPainter(root, { value = null, onChange = () => {} } = {}) {
    let cells = parse(value);
    let painted = valid(value);
    let colour = 0;
    let tool = "pencil";
    let stroke = null; // last cell of the stroke in progress
    const undoStack = [];

    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = SIZE;
    canvas.className = "painter-canvas";
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "Portrait canvas, 32 by 32 pixels");

    const side = document.createElement("div");
    side.className = "painter-side";
    const tools = document.createElement("div");
    tools.className = "painter-tools";
    const palette = document.createElement("div");
    palette.className = "painter-palette";
    side.append(tools, palette);
    root.classList.add("painter");
    root.replaceChildren(canvas, side);

    const toolButtons = {};
    function addButton(label, onClick) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", onClick);
      tools.append(button);
      return button;
    }
    function setTool(name) {
      tool = name;
      for (const [key, button] of Object.entries(toolButtons)) button.setAttribute("aria-pressed", String(key === name));
    }
    toolButtons.pencil = addButton("Pencil", () => setTool("pencil"));
    toolButtons.fill = addButton("Fill", () => setTool("fill"));
    const undoButton = addButton("Undo", () => {
      const previous = undoStack.pop();
      if (!previous) return;
      ({ cells, painted } = previous);
      commit();
    });
    const clearButton = addButton("Clear", () => {
      remember();
      cells = parse(null);
      painted = false;
      commit();
    });

    const swatches = PALETTE.map((hex, index) => {
      const swatch = document.createElement("button");
      swatch.type = "button";
      swatch.className = "swatch";
      swatch.style.background = hex;
      swatch.title = NAMES[index];
      swatch.setAttribute("aria-label", NAMES[index]);
      swatch.addEventListener("click", () => setColour(index));
      palette.append(swatch);
      return swatch;
    });
    function setColour(index) {
      colour = index;
      swatches.forEach((swatch, at) => swatch.setAttribute("aria-pressed", String(at === index)));
    }

    function remember() {
      undoStack.push({ cells: cells.slice(), painted });
      if (undoStack.length > 50) undoStack.shift();
    }
    function commit() {
      draw(canvas, cells);
      undoButton.disabled = undoStack.length === 0;
      clearButton.disabled = !painted;
      onChange(painted ? serialize(cells) : null);
    }

    function cellAt(event) {
      const box = canvas.getBoundingClientRect();
      const x = Math.floor(((event.clientX - box.left) / box.width) * SIZE);
      const y = Math.floor(((event.clientY - box.top) / box.height) * SIZE);
      return { x: Math.min(SIZE - 1, Math.max(0, x)), y: Math.min(SIZE - 1, Math.max(0, y)) };
    }
    function plot(x, y) {
      cells[y * SIZE + x] = colour;
      const context = canvas.getContext("2d");
      context.fillStyle = PALETTE[colour];
      context.fillRect(x, y, 1, 1);
    }
    // Pointer samples arrive sparsely on fast strokes, so join them up.
    function line(from, to) {
      let { x, y } = from;
      const dx = Math.abs(to.x - x), dy = -Math.abs(to.y - y);
      const sx = x < to.x ? 1 : -1, sy = y < to.y ? 1 : -1;
      let error = dx + dy;
      for (;;) {
        plot(x, y);
        if (x === to.x && y === to.y) break;
        const twice = 2 * error;
        if (twice >= dy) { error += dy; x += sx; }
        if (twice <= dx) { error += dx; y += sy; }
      }
    }
    function flood(start) {
      const target = cells[start.y * SIZE + start.x];
      if (target === colour) return;
      const queue = [start];
      while (queue.length) {
        const { x, y } = queue.pop();
        if (x < 0 || y < 0 || x >= SIZE || y >= SIZE || cells[y * SIZE + x] !== target) continue;
        cells[y * SIZE + x] = colour;
        queue.push({ x: x + 1, y }, { x: x - 1, y }, { x, y: y + 1 }, { x, y: y - 1 });
      }
    }

    canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      remember();
      painted = true;
      const cell = cellAt(event);
      if (tool === "fill") {
        flood(cell);
        commit();
        return;
      }
      canvas.setPointerCapture(event.pointerId);
      stroke = cell;
      plot(cell.x, cell.y);
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!stroke) return;
      const cell = cellAt(event);
      line(stroke, cell);
      stroke = cell;
    });
    const finish = () => {
      if (!stroke) return;
      stroke = null;
      commit();
    };
    canvas.addEventListener("pointerup", finish);
    canvas.addEventListener("pointercancel", finish);

    setTool("pencil");
    setColour(0);
    draw(canvas, cells);
    undoButton.disabled = true;
    clearButton.disabled = !painted;

    return { get value() { return painted ? serialize(cells) : null; } };
  }

  return { SIZE, toDataURL, createPainter };
})();
