/*
Copyright (C) 2026 Kuan Qian
SPDX-License-Identifier: GPL-3.0-only

Animated tutorial demos. Each <div class="vb-demo" data-demo="name"> becomes a
script pane beside a mock chat window, and plays the timeline in DEMOS[name]
when it scrolls into view. The line being run is highlighted as its output
appears.
*/

(function () {
  "use strict";

  var ASSETS = (document.currentScript && document.currentScript.src || "").replace(/[^/]*$/, "");
  var REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var ABORT = {};

  var PEOPLE = {
    bot: { name: "Verbage", color: "#f2f3f5", tag: "APP", img: "favicon-64.png", bg: "#5865f2" },
    n: { name: "Narrator", color: "#a48335", tag: "APP", bg: "#a48335" },
    jia: { name: "Jia Li", color: "#b16399", tag: "APP", img: "demo/jiali.png", bg: "#b16399" },
    Alice: { name: "Alice", color: "#f0b232", bg: "#c27c0e", player: true },
    Bob: { name: "Bob", color: "#7ab7ff", bg: "#2f6fb5", player: true },
    Carol: { name: "Carol", color: "#7bd88f", bg: "#2d8a4e", player: true },
  };
  var PLAYER_ORDER = ["Alice", "Bob", "Carol"];

  var KEYWORDS = /^(label|jump|menu|persistent|timeout|if|elif|else|default|define|input|into|case|contains|button|run|show|image|caption|wait|channel|link|to|clear|time|limit|minutes|not|and|or|True|False)$/;

  var RESTAURANT = "data:image/svg+xml," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 40" shape-rendering="crispEdges">' +
    '<rect width="64" height="40" fill="#1b2340"/>' +
    '<g fill="#e8ecff"><rect x="24" y="3" width="1" height="1"/><rect x="33" y="6" width="1" height="1"/><rect x="44" y="2" width="1" height="1"/><rect x="18" y="7" width="1" height="1"/><rect x="61" y="9" width="1" height="1"/></g>' +
    '<rect x="52" y="3" width="4" height="4" fill="#f4e7b0"/><rect x="51" y="4" width="1" height="2" fill="#f4e7b0"/><rect x="56" y="4" width="1" height="2" fill="#f4e7b0"/>' +
    '<rect y="34" width="64" height="6" fill="#24321f"/>' +
    '<rect x="18" y="16" width="30" height="18" fill="#7a2b2b"/>' +
    '<rect x="16" y="11" width="34" height="2" fill="#3b2626"/><rect x="14" y="13" width="38" height="3" fill="#2d1d1d"/>' +
    '<rect x="12" y="12" width="2" height="2" fill="#2d1d1d"/><rect x="52" y="12" width="2" height="2" fill="#2d1d1d"/>' +
    '<rect x="27" y="17" width="12" height="3" fill="#c9a227"/>' +
    '<rect x="21" y="21" width="6" height="5" fill="#f3c76b"/><rect x="39" y="21" width="6" height="5" fill="#f3c76b"/>' +
    '<rect x="24" y="21" width="1" height="5" fill="#7a2b2b"/><rect x="42" y="21" width="1" height="5" fill="#7a2b2b"/>' +
    '<rect x="30" y="22" width="6" height="12" fill="#ffd98a"/><rect x="33" y="22" width="1" height="12" fill="#d9a85a"/>' +
    '<rect x="19" y="16" width="2" height="3" fill="#e0473c"/><rect x="45" y="16" width="2" height="3" fill="#e0473c"/>' +
    '<rect x="29" y="34" width="8" height="6" fill="#8a6a45"/>' +
    '<rect x="6" y="15" width="3" height="19" fill="#4a3423"/>' +
    '<rect x="0" y="7" width="15" height="8" fill="#3f7a3a"/><rect x="2" y="5" width="11" height="2" fill="#3f7a3a"/>' +
    '<g fill="#4f8f45"><rect x="0" y="15" width="1" height="9"/><rect x="2" y="15" width="1" height="13"/><rect x="4" y="15" width="1" height="7"/><rect x="10" y="15" width="1" height="11"/><rect x="12" y="15" width="1" height="8"/><rect x="14" y="15" width="1" height="12"/></g>' +
    "</svg>"
  );

  // ------------------------------------------------------------------
  // Demo timelines. `line` highlights a line of `script` (1-based) before the
  // rest of the step runs. Channels use the names Discord would show.
  // ------------------------------------------------------------------

  var DEMOS = {
    setup: {
      script: 'label setup:\n    "You stand outside a restaurant."',
      channels: ["general"],
      view: "general",
      steps: [
        { slash: "/start", user: "Alice" },
        { reply: "Starting the game.", to: "Alice", cmd: "/start" },
        { line: 1, channel: "game" },
        { view: "game" },
        { line: 2, narrate: "You stand outside a restaurant." },
      ],
    },

    files: {
      file: "Explorer",
      lang: "tree",
      script: "game/\n    main.script\n    characters.script\n    act_1.script\n    images/\n        jiali.png\n        narrator.jpg",
      window: "terminal",
      steps: [
        { line: 1, log: "$ python check.py game", cls: "vb-prompt", wait: 900 },
        { line: 2, log: "# main.script        label setup", cls: "vb-note" },
        { line: 3, log: "# characters.script  define jia, define n", cls: "vb-note" },
        { line: 4, log: "# act_1.script       label begin  ->  act_1.begin", cls: "vb-note" },
        { line: 6, log: '# images/jiali.png   image "jiali"', cls: "vb-note" },
        { line: 7, log: '# images/narrator.jpg image "narrator"', cls: "vb-note" },
        { line: null, log: "Loaded 2 labels, 2 characters, 2 images, and 0 defaults from game.", cls: "vb-ok" },
      ],
    },

    character: {
      script: 'define jia = Character(\n    "Jia Li",\n    color="#b16399",\n    image="jiali",\n)\n\nlabel setup:\n    jia "Welcome. Your table is almost ready."',
      steps: [
        { line: 1, wait: 500 },
        { line: 2, wait: 400 },
        { line: 3, wait: 400 },
        { line: 4, wait: 600 },
        { line: 7, wait: 500 },
        { line: 8, say: "Welcome. Your table is almost ready.", who: "jia" },
      ],
    },

    channels: {
      script: 'label setup:\n    jump entrance\n\nlabel entrance(channel="Entrance"):\n    n "You stand outside a locked door."\n    jump door\n\nlabel door(channel="Entrance"):\n    n "There is a keypad beside the door."',
      steps: [
        { line: 1, wait: 400 },
        { line: 2, wait: 600 },
        { line: 4, channel: "entrance" },
        { view: "entrance" },
        { line: 5, say: "You stand outside a locked door." },
        { line: 6, wait: 600 },
        { line: 8, wait: 400 },
        { line: 9, say: "There is a keypad beside the door." },
      ],
    },

    menu: {
      script: 'label door(channel="Entrance"):\n    n "The keypad glows blue."\n\n    menu:\n        "Enter a code":\n            jump enter_code\n\n        "Walk away":\n            n "You step back from the door."\n\n    n "The night feels colder now."',
      channels: ["entrance"],
      steps: [
        { line: 2, say: "The keypad glows blue." },
        { line: 4, menu: ["Enter a code", "Walk away"], id: "m" },
        { click: "m", option: 1, user: "Alice", disable: true },
        { line: 8, wait: 300 },
        { line: 9, say: "You step back from the door." },
        { line: 11, say: "The night feels colder now." },
      ],
    },

    conditional: {
      script: 'default door_locked = True\n\nlabel door(channel="Entrance"):\n    menu:\n        "Open the door" if not door_locked:\n            n "You enter the restaurant\'s basement."\n\n        "Enter a code" if door_locked:\n            jump enter_code',
      channels: ["entrance"],
      vars: { door_locked: true },
      steps: [
        { line: 1, wait: 500 },
        { line: 4, menu: ["Enter a code"], id: "a" },
        { line: 8, wait: 900 },
        { pill: "Later, the players crack the code" },
        { set: { door_locked: false }, disable: "a", wait: 900 },
        { line: 4, menu: ["Open the door"], id: "b" },
        { line: 5, click: "b", option: 0, user: "Bob", disable: true },
        { line: 6, say: "You enter the restaurant's basement." },
      ],
    },

    branches: {
      script: 'label report(channel="Great Hall"):\n    if clues_found >= 3:\n        n "You have enough evidence to accuse someone."\n        jump accusation\n    elif clues_found > 0:\n        n "You have a theory, but not enough proof."\n    else:\n        n "You are still completely in the dark."',
      channels: ["great-hall"],
      vars: { clues_found: 0 },
      steps: [
        { pill: "Run with clues_found = 0" },
        { line: 2, wait: 500 },
        { line: 5, wait: 500 },
        { line: 7, wait: 300 },
        { line: 8, say: "You are still completely in the dark.", after: 1400 },
        { set: { clues_found: 1 }, pill: "Run with clues_found = 1" },
        { line: 2, wait: 500 },
        { line: 5, wait: 300 },
        { line: 6, say: "You have a theory, but not enough proof.", after: 1400 },
        { set: { clues_found: 3 }, pill: "Run with clues_found = 3" },
        { line: 2, wait: 300 },
        { line: 3, say: "You have enough evidence to accuse someone." },
        { line: 4, wait: 600 },
      ],
    },

    image: {
      script: 'label restaurant_front(channel="Entrance"):\n    show image "restaurant_front":\n        caption "The restaurant waits under the old willow tree."',
      channels: ["entrance"],
      steps: [
        { line: 1, wait: 400 },
        { line: 2, wait: 300 },
        { line: 3, narrate: "The restaurant waits under the old willow tree.", image: RESTAURANT, italic: false },
      ],
    },

    timed: {
      script: 'label overhear(channel="Dining Room"):\n    menu timeout 20:\n        "Interrupt the conversation":\n            n "You clear your throat."\n\n        "Keep listening":\n            n "You stay quiet."\n\n        timeout:\n            n "The moment passes."',
      channels: ["dining-room"],
      steps: [
        { line: 2, menu: ["Interrupt the conversation", "Keep listening"], id: "t", after: 1200 },
        { pill: "20 seconds pass. Nobody clicks." },
        { disable: "t", wait: 600 },
        { line: 9, wait: 400 },
        { line: 10, say: "The moment passes." },
      ],
    },

    input: {
      script: 'default code_entered = ""\ndefault correct_code = "dead beef"\ndefault door_locked = True\n\nlabel enter_code(channel="Entrance"):\n    input "Enter the code on the keypad." into code_entered:\n        case correct_code:\n            n "The lock snaps open."\n            $ door_locked = False\n            jump door\n\n        case _:\n            n "The keypad flashes red."\n            jump door',
      channels: ["entrance"],
      vars: { code_entered: "", door_locked: true },
      steps: [
        { line: 6, notice: "Enter the code on the keypad." },
        { type: "dead beef", user: "Alice" },
        { set: { code_entered: "dead beef" }, wait: 500 },
        { line: 7, wait: 600 },
        { line: 8, say: "The lock snaps open." },
        { line: 9, set: { door_locked: false }, wait: 700 },
        { line: 10, wait: 500 },
      ],
    },

    contains: {
      script: 'default restroom_action = ""\n\nlabel restroom(channel="Restroom"):\n    input "What do you inspect?" into restroom_action:\n        case contains "portrait" or "painting" or "winnie":\n            n "You find a hidden button behind the frame."\n\n        case _:\n            n "You do not find anything unusual."',
      channels: ["restroom"],
      vars: { restroom_action: "" },
      steps: [
        { line: 4, notice: "What do you inspect?" },
        { type: "I look behind the portrait.", user: "Carol" },
        { set: { restroom_action: "I look behind the portrait." }, wait: 400 },
        { line: 5, wait: 800 },
        { line: 6, say: "You find a hidden button behind the frame." },
      ],
    },

    persistent: {
      height: 400,
      script: 'default push_count = 0\n\nlabel heavy_door(channel="Basement"):\n    n "The iron door is too heavy for one person."\n\n    persistent menu:\n        "Push together":\n            $ push_count += 1\n            n "$(username()) throws their shoulder against the door."\n\n            if push_count >= 3:\n                n "With everyone pushing, the door finally opens."\n                jump basement_open\n\n        "Look for another way":\n            n "You search the walls, but find no other passage."\n\nlabel basement_open(channel="Basement"):\n    n "Cold air rolls up from the stairs below."',
      channels: ["basement"],
      vars: { push_count: 0 },
      steps: [
        { line: 4, say: "The iron door is too heavy for one person." },
        { line: 6, menu: ["Push together", "Look for another way"], id: "p" },
        { line: 7, click: "p", option: 0, user: "Alice" },
        { line: 8, set: { push_count: 1 }, wait: 400 },
        { line: 9, say: "Alice throws their shoulder against the door." },
        { line: 11, wait: 400 },
        { line: 7, click: "p", option: 0, user: "Bob" },
        { line: 8, set: { push_count: 2 }, wait: 400 },
        { line: 9, say: "Bob throws their shoulder against the door." },
        { line: 11, wait: 400 },
        { line: 7, click: "p", option: 0, user: "Carol" },
        { line: 8, set: { push_count: 3 }, wait: 400 },
        { line: 9, say: "Carol throws their shoulder against the door." },
        { line: 11, wait: 400 },
        { line: 12, say: "With everyone pushing, the door finally opens." },
        { line: 13, disable: "p", wait: 500 },
        { line: 19, say: "Cold air rolls up from the stairs below." },
      ],
    },

    persistentTimeout: {
      script: 'label closing_door(channel="Basement"):\n    persistent menu timeout 30:\n        "Hold the door":\n            n "$(username()) keeps the door from closing."\n\n        timeout:\n            n "The door slams shut."',
      channels: ["basement"],
      steps: [
        { line: 2, menu: ["Hold the door"], id: "h" },
        { line: 3, click: "h", option: 0, user: "Alice" },
        { line: 4, say: "Alice keeps the door from closing.", after: 1000 },
        { line: 2, pill: "30 seconds pass" },
        { disable: "h", wait: 600 },
        { line: 6, wait: 400 },
        { line: 7, say: "The door slams shut." },
      ],
    },

    run: {
      height: 400,
      script: 'label enter_restaurant(channel="Great Hall"):\n    n "The party splits up to search the restaurant."\n    run (kitchen, restroom, banquet_hall)\n    n "Everyone returns to the Great Hall."\n\nlabel kitchen(channel="Kitchen"):\n    n "The kitchen is hot and noisy."\n    button "Look around"\n    n "You find a burned receipt."\n    channel link "Return to Great Hall" to "Great Hall"\n\nlabel restroom(channel="Restroom"):\n    n "The restroom is quiet."\n    button "Inspect the mirror"\n    n "Someone wrote a number in the fogged glass."\n    channel link "Return to Great Hall" to "Great Hall"\n\nlabel banquet_hall(channel="Banquet Hall"):\n    n "The tables are set for a banquet."\n    button "Check under the table"\n    n "You find a torn envelope."\n    channel link "Return to Great Hall" to "Great Hall"',
      channels: ["great-hall"],
      steps: [
        { line: 2, say: "The party splits up to search the restaurant." },
        { line: 3, channel: ["kitchen", "restroom", "banquet-hall"] },
        { line: 7, say: "The kitchen is hot and noisy.", ch: "kitchen", after: 250 },
        { line: 13, say: "The restroom is quiet.", ch: "restroom", after: 250 },
        { line: 19, say: "The tables are set for a banquet.", ch: "banquet-hall", after: 250 },
        { line: 8, button: "Look around", id: "k", ch: "kitchen", after: 150 },
        { line: 14, button: "Inspect the mirror", id: "r", ch: "restroom", after: 150 },
        { line: 20, button: "Check under the table", id: "b", ch: "banquet-hall" },
        { view: "kitchen" },
        { line: 8, click: "k", option: 0, user: "Alice", disable: true },
        { line: 9, say: "You find a burned receipt.", ch: "kitchen" },
        { line: 10, link: "Return to Great Hall", ch: "kitchen" },
        { view: "restroom" },
        { line: 14, click: "r", option: 0, user: "Bob", disable: true },
        { line: 15, say: "Someone wrote a number in the fogged glass.", ch: "restroom" },
        { line: 16, link: "Return to Great Hall", ch: "restroom" },
        { view: "banquet-hall" },
        { line: 20, click: "b", option: 0, user: "Carol", disable: true },
        { line: 21, say: "You find a torn envelope.", ch: "banquet-hall" },
        { line: 22, link: "Return to Great Hall", id: "l", ch: "banquet-hall" },
        { click: "l", option: 0, user: "Carol" },
        { view: "great-hall" },
        { line: 4, say: "Everyone returns to the Great Hall." },
      ],
    },

    runReturn: {
      script: 'label enter_restaurant(channel="Great Hall"):\n    n "The party splits up to search the restaurant."\n    run (kitchen, restroom, banquet_hall)\n    n "Everyone returns to the Great Hall."',
      channels: ["great-hall", "kitchen", "restroom", "banquet-hall"],
      vars: { waiting_for: "kitchen, restroom, banquet_hall" },
      prefill: [{ say: "The party splits up to search the restaurant." }],
      steps: [
        { line: 3, wait: 900 },
        { pill: "Kitchen scene finishes", unread: "kitchen", set: { waiting_for: "restroom, banquet_hall" }, wait: 1200 },
        { pill: "Restroom scene finishes", unread: "restroom", set: { waiting_for: "banquet_hall" }, wait: 1200 },
        { pill: "Banquet Hall scene finishes", unread: "banquet-hall", set: { waiting_for: "(nothing)" }, wait: 900 },
        { line: 4, say: "Everyone returns to the Great Hall." },
      ],
    },

    button: {
      script: 'default investigator = ""\n\nlabel study(channel="Study"):\n    button "Look around":\n        $ investigator = username()\n        n "$(investigator) notices fresh footprints."',
      channels: ["study"],
      vars: { investigator: "" },
      steps: [
        { line: 4, button: "Look around", id: "s", after: 900 },
        { click: "s", option: 0, user: "Alice", disable: true },
        { line: 5, set: { investigator: "Alice" }, wait: 700 },
        { line: 6, say: "Alice notices fresh footprints." },
      ],
    },

    clear: {
      script: 'label restroom_reset(channel="Restroom"):\n    n "A cleaner sweeps through the room."\n    clear channel "Restroom"\n    n "The restroom is quiet again."',
      channels: ["restroom"],
      prefill: [
        { say: "The restroom is quiet." },
        { notice: "What do you inspect?" },
        { user: "Carol", text: "I look behind the portrait." },
        { say: "You find a hidden button behind the frame." },
      ],
      steps: [
        { line: 2, say: "A cleaner sweeps through the room.", after: 900 },
        { line: 3, clear: "restroom", wait: 900 },
        { line: 4, say: "The restroom is quiet again." },
      ],
    },
  };

  // ------------------------------------------------------------------
  // DOM helpers
  // ------------------------------------------------------------------

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function formatInto(node, text) {
    var parts = String(text).split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/);
    parts.forEach(function (part) {
      if (!part) return;
      if (/^\*\*.+\*\*$/.test(part)) node.appendChild(el("strong", null, part.slice(2, -2)));
      else if (/^\*.+\*$/.test(part)) node.appendChild(el("em", null, part.slice(1, -1)));
      else if (/^`.+`$/.test(part)) node.appendChild(el("code", null, part.slice(1, -1)));
      else node.appendChild(document.createTextNode(part));
    });
  }

  function highlightLine(li, text, lang) {
    if (lang === "tree") {
      var isDir = /\/$/.test(text.trim());
      li.appendChild(el("span", isDir ? "vb-dir" : null, text));
      return;
    }
    var re = /("(?:[^"\\]|\\.)*")|(#.*$)|(\b\d+\b)|([A-Za-z_][A-Za-z0-9_]*)|(\s+)|(.)/g;
    var m;
    while ((m = re.exec(text))) {
      if (m[1]) li.appendChild(el("span", "vb-s", m[1]));
      else if (m[2]) li.appendChild(el("span", "vb-c", m[2]));
      else if (m[3]) li.appendChild(el("span", "vb-n", m[3]));
      else if (m[4]) li.appendChild(KEYWORDS.test(m[4]) ? el("span", "vb-k", m[4]) : document.createTextNode(m[4]));
      else li.appendChild(document.createTextNode(m[0]));
    }
  }

  function pyValue(value) {
    if (value === true) return "True";
    if (value === false) return "False";
    if (typeof value === "string") return value === "(nothing)" ? value : JSON.stringify(value);
    return String(value);
  }

  function clock(offset) {
    var d = new Date(2026, 0, 1, 20, 14 + offset);
    return "Today at " + ((d.getHours() + 11) % 12 + 1) + ":" + String(d.getMinutes()).padStart(2, "0") + " PM";
  }

  function avatar(who) {
    var person = PEOPLE[who];
    var box = el("div", "vb-av");
    box.style.background = person.bg;
    if (person.img) {
      var img = el("img");
      img.src = ASSETS + person.img;
      img.alt = "";
      box.appendChild(img);
    } else {
      box.textContent = person.name.charAt(0);
    }
    return box;
  }

  var CURSOR_SVG =
    '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 1l11 7.5-4.6.9 2.7 5.2-2 1-2.7-5.2L2.9 13.5z" fill="#fff" stroke="#111" stroke-width="1"/></svg>';

  // ------------------------------------------------------------------
  // Demo player
  // ------------------------------------------------------------------

  function Demo(root, spec) {
    this.root = root;
    this.spec = spec;
    this.token = null;
    this.visible = false;
    this.build();
    this.reset();
  }

  Demo.prototype.build = function () {
    var spec = this.spec;
    var root = this.root;
    var self = this;
    root.textContent = "";
    if (spec.height) root.style.setProperty("--vb-h", spec.height + "px");

    var code = el("div", "vb-code");
    var bar = el("div", "vb-code-bar");
    bar.appendChild(el("span", "vb-file", spec.file || "main.script"));
    var replay = el("button", "vb-replay", "Replay");
    replay.type = "button";
    replay.setAttribute("aria-label", "Replay animation");
    replay.addEventListener("click", function () {
      self.play(false);
    });
    bar.appendChild(replay);
    code.appendChild(bar);

    this.lines = [];
    var list = el("ol", "vb-lines");
    spec.script.split("\n").forEach(function (text, i) {
      var li = el("li");
      li.appendChild(el("span", "vb-ln", String(i + 1)));
      var src = el("span", "vb-src");
      highlightLine(src, text, spec.lang);
      li.appendChild(src);
      list.appendChild(li);
      self.lines.push(li);
    });
    this.lineList = list;
    code.appendChild(list);
    this.varBar = el("div", "vb-vars");
    code.appendChild(this.varBar);
    root.appendChild(code);

    var win = el("div", "vb-win");
    win.setAttribute("aria-hidden", "true");
    this.win = win;
    if (spec.window === "terminal") {
      win.classList.add("vb-term");
      var head = el("div", "vb-head", "Terminal");
      win.appendChild(head);
      this.term = el("div", "vb-term-out");
      win.appendChild(this.term);
    } else {
      var side = el("div", "vb-side");
      side.appendChild(el("div", "vb-server", "Story Night"));
      side.appendChild(el("div", "vb-cat", "Dialog Game"));
      this.chanList = el("div");
      side.appendChild(this.chanList);
      win.appendChild(side);

      var main = el("div", "vb-main");
      this.head = el("div", "vb-head");
      main.appendChild(this.head);
      this.log = el("div", "vb-log");
      main.appendChild(this.log);
      this.typing = el("div", "vb-typing");
      main.appendChild(this.typing);
      this.compose = el("div", "vb-compose");
      main.appendChild(this.compose);
      win.appendChild(main);
    }
    root.appendChild(win);
    root.classList.add("vb-ready");
  };

  Demo.prototype.reset = function () {
    var spec = this.spec;
    this.vars = {};
    this.varBar.textContent = "";
    var initial = spec.vars || {};
    for (var key in initial) this.vars[key] = initial[key];
    this.renderVars();
    this.setLine(null, true);
    this.buttons = {};
    this.cursors = {};
    this.clock = 0;
    Array.prototype.slice.call(this.win.querySelectorAll(".vb-cursor")).forEach(function (c) {
      c.remove();
    });
    if (this.term) {
      this.term.textContent = "";
      return;
    }
    this.channels = {};
    this.order = [];
    this.chanList.textContent = "";
    this.log.textContent = "";
    this.typing.textContent = "";
    var first = spec.channels || ["game"];
    for (var i = 0; i < first.length; i++) this.addChannel(first[i], false);
    this.showChannel(spec.view || first[0]);
  };

  Demo.prototype.renderVars = function (changed) {
    var bar = this.varBar;
    bar.textContent = "";
    for (var key in this.vars) {
      var item = el("span", "vb-var");
      item.appendChild(document.createTextNode(key + " = "));
      item.appendChild(el("b", null, pyValue(this.vars[key])));
      if (changed && key in changed) item.classList.add("vb-flash");
      bar.appendChild(item);
    }
  };

  Demo.prototype.setLine = function (n, instant) {
    if (this.activeLine) this.activeLine.classList.remove("vb-on");
    this.activeLine = n ? this.lines[n - 1] : null;
    if (!this.activeLine) return;
    this.activeLine.classList.add("vb-on");
    var list = this.lineList;
    var top = this.activeLine.offsetTop - list.offsetTop - list.clientHeight / 3;
    var target = Math.max(0, top);
    if (instant || REDUCED) list.scrollTop = target;
    else list.scrollTo({ top: target, behavior: "smooth" });
  };

  Demo.prototype.addChannel = function (name, animate) {
    if (this.channels[name]) return this.channels[name];
    var item = el("div", "vb-chan");
    item.appendChild(el("span", "vb-hash", "#"));
    item.appendChild(el("span", null, name));
    if (animate) item.classList.add("vb-new");
    this.chanList.appendChild(item);
    var pane = el("div", "vb-msgs");
    pane.hidden = true;
    this.log.appendChild(pane);
    var channel = { name: name, item: item, pane: pane, last: null };
    this.channels[name] = channel;
    this.order.push(name);
    return channel;
  };

  Demo.prototype.showChannel = function (name) {
    var channel = this.channels[name];
    if (!channel) return;
    for (var key in this.channels) {
      var other = this.channels[key];
      other.pane.hidden = other !== channel;
      other.item.classList.toggle("vb-active", other === channel);
    }
    channel.item.classList.remove("vb-unread");
    this.current = channel;
    this.head.textContent = "";
    this.head.appendChild(el("span", "vb-hash", "#"));
    this.head.appendChild(document.createTextNode(name));
    this.compose.classList.remove("vb-typed");
    this.compose.textContent = "Message #" + name;
    channel.pane.scrollTop = channel.pane.scrollHeight;
  };

  Demo.prototype.channelFor = function (step) {
    return step.ch ? this.addChannel(step.ch, false) : this.current;
  };

  Demo.prototype.scrollDown = function (channel, instant) {
    var pane = channel.pane;
    if (instant || REDUCED) pane.scrollTop = pane.scrollHeight;
    else pane.scrollTo({ top: pane.scrollHeight, behavior: "smooth" });
  };

  Demo.prototype.append = function (channel, who, build, opts) {
    opts = opts || {};
    var person = PEOPLE[who];
    var row = el("div", "vb-msg");
    var grouped = channel.last === who && !opts.reply;
    row.classList.add(grouped ? "vb-cont" : "vb-first");
    row.appendChild(avatar(who));
    var body = el("div", "vb-body");
    if (opts.reply) {
      var reply = el("div", "vb-reply");
      reply.appendChild(document.createTextNode("↳ "));
      reply.appendChild(el("b", null, opts.reply.user));
      reply.appendChild(document.createTextNode(" used "));
      reply.appendChild(el("b", null, opts.reply.cmd));
      body.appendChild(reply);
    }
    var meta = el("div", "vb-meta");
    var name = el("span", "vb-name", person.name);
    name.style.color = person.color;
    meta.appendChild(name);
    if (person.tag) meta.appendChild(el("span", "vb-tag", person.tag));
    meta.appendChild(el("span", "vb-time", clock(this.clock)));
    body.appendChild(meta);
    build(body);
    row.appendChild(body);
    channel.pane.appendChild(row);
    channel.last = who;
    if (channel !== this.current) channel.item.classList.add("vb-unread");
    this.scrollDown(channel, opts.instant);
    return row;
  };

  Demo.prototype.textMessage = function (channel, who, text, opts) {
    opts = opts || {};
    return this.append(channel, who, function (body) {
      if (text) {
        var p = el("div", "vb-text");
        formatInto(p, text);
        body.appendChild(p);
      }
      if (opts.image) {
        var img = el("img", "vb-image");
        img.src = opts.image;
        img.alt = "";
        body.appendChild(img);
      }
      if (opts.buttons) body.appendChild(opts.buttons);
    }, opts);
  };

  Demo.prototype.buttonRow = function (labels, kind, id, animate) {
    var row = el("div", "vb-btns");
    var list = [];
    labels.forEach(function (label) {
      var btn = el("button", "vb-btn", label);
      btn.type = "button";
      btn.tabIndex = -1;
      if (kind) btn.classList.add(kind);
      if (animate) btn.classList.add("vb-new");
      row.appendChild(btn);
      list.push(btn);
    });
    if (id) this.buttons[id] = list;
    return row;
  };

  // ---------- timing ----------

  Demo.prototype.sleep = function (ms, token) {
    if (this.instant) {
      return token === this.token ? Promise.resolve() : Promise.reject(ABORT);
    }
    var self = this;
    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        if (token === self.token) resolve();
        else reject(ABORT);
      }, ms);
    });
  };

  Demo.prototype.showTyping = function (who, channel, token) {
    if (this.instant || channel !== this.current) return this.sleep(120, token);
    var person = PEOPLE[who];
    var typing = this.typing;
    typing.textContent = "";
    var dots = el("span", "vb-dots");
    dots.appendChild(el("i"));
    dots.appendChild(el("i"));
    dots.appendChild(el("i"));
    typing.appendChild(dots);
    var label = el("span");
    label.appendChild(el("b", null, person.name));
    label.appendChild(document.createTextNode(" is typing…"));
    typing.appendChild(label);
    return this.sleep(750, token).then(function () {
      typing.textContent = "";
    });
  };

  Demo.prototype.cursorFor = function (user) {
    if (this.cursors[user]) {
      this.cursors[user].style.opacity = "1";
      return this.cursors[user];
    }
    var cursor = el("div", "vb-cursor");
    cursor.innerHTML = CURSOR_SVG;
    var tag = el("span", null, user);
    tag.style.background = PEOPLE[user].bg;
    cursor.appendChild(tag);
    var index = Math.max(0, PLAYER_ORDER.indexOf(user));
    var x = this.win.clientWidth - 70 - index * 26;
    var y = this.win.clientHeight - 30 - index * 18;
    cursor.style.transition = "none";
    cursor.style.transform = "translate(" + x + "px," + y + "px)";
    cursor.style.opacity = "0";
    this.win.appendChild(cursor);
    void cursor.offsetWidth;
    cursor.style.transition = "";
    cursor.style.opacity = "1";
    this.cursors[user] = cursor;
    return cursor;
  };

  Demo.prototype.clickButton = function (btn, user, token) {
    var self = this;
    if (this.instant) {
      return Promise.resolve();
    }
    var pane = btn.closest(".vb-msgs");
    var paneBox = pane.getBoundingClientRect();
    var btnBox = btn.getBoundingClientRect();
    if (btnBox.top < paneBox.top + 8 || btnBox.bottom > paneBox.bottom - 8) {
      pane.scrollTop += btnBox.top - paneBox.top - pane.clientHeight / 3;
    }
    var cursor = this.cursorFor(user);
    var winBox = this.win.getBoundingClientRect();
    var box = btn.getBoundingClientRect();
    var x = box.left - winBox.left + Math.min(box.width * 0.6, box.width - 10);
    var y = box.top - winBox.top + box.height * 0.55;
    return this.sleep(60, token).then(function () {
      cursor.style.transform = "translate(" + x + "px," + y + "px)";
      return self.sleep(850, token);
    }).then(function () {
      cursor.classList.add("vb-click");
      btn.classList.add("vb-press");
      return self.sleep(220, token);
    }).then(function () {
      cursor.classList.remove("vb-click");
      btn.classList.remove("vb-press");
      return self.sleep(450, token);
    }).then(function () {
      cursor.style.opacity = "0";
    });
  };

  Demo.prototype.typeInto = function (text, token) {
    var compose = this.compose;
    var self = this;
    if (this.instant) return Promise.resolve();
    compose.textContent = "";
    compose.classList.add("vb-typed");
    var i = 0;
    function next() {
      if (i >= text.length) return self.sleep(450, token);
      i += 1;
      compose.textContent = text.slice(0, i);
      return self.sleep(55, token).then(next);
    }
    return this.sleep(300, token).then(next);
  };

  // ---------- one step ----------

  Demo.prototype.step = function (s, token) {
    var self = this;
    var chain = Promise.resolve();
    function then(fn) {
      chain = chain.then(fn);
    }

    if ("line" in s) this.setLine(s.line, this.instant);

    if (s.log != null) {
      then(function () {
        var row = el("div", s.cls || null, s.log);
        self.term.appendChild(row);
        self.term.scrollTop = self.term.scrollHeight;
        return self.sleep(s.wait == null ? 700 : s.wait, token);
      });
      return chain;
    }

    if (s.channel) {
      then(function () {
        var names = [].concat(s.channel);
        var p = Promise.resolve();
        names.forEach(function (name) {
          p = p.then(function () {
            self.addChannel(name, !self.instant);
            return self.sleep(350, token);
          });
        });
        return p.then(function () {
          return self.sleep(500, token);
        });
      });
    }

    if (s.view) {
      then(function () {
        self.showChannel(s.view);
        return self.sleep(700, token);
      });
    }

    if (s.unread) {
      then(function () {
        var channel = self.addChannel(s.unread, false);
        if (channel !== self.current) channel.item.classList.add("vb-unread");
      });
    }

    if (s.pill) {
      then(function () {
        var channel = self.current;
        var pill = el("div", "vb-pill", s.pill);
        channel.pane.appendChild(pill);
        channel.last = null;
        self.scrollDown(channel, self.instant);
        return self.sleep(900, token);
      });
    }

    if (s.set) {
      then(function () {
        for (var key in s.set) self.vars[key] = s.set[key];
        self.renderVars(self.instant ? null : s.set);
      });
    }

    if (s.disable) {
      then(function () {
        (self.buttons[s.disable] || []).forEach(function (btn) {
          btn.classList.add("vb-off");
        });
      });
    }

    if (s.slash) {
      then(function () {
        return self.typeInto(s.slash, token).then(function () {
          self.compose.classList.remove("vb-typed");
          self.compose.textContent = "Message #" + self.current.name;
        });
      });
    }

    if (s.reply) {
      then(function () {
        self.clock += 1;
        self.textMessage(self.current, "bot", s.reply, { reply: { user: s.to, cmd: s.cmd }, instant: self.instant });
        return self.sleep(800, token);
      });
    }

    if (s.type) {
      then(function () {
        var channel = self.current;
        return self.typeInto(s.type, token).then(function () {
          self.compose.classList.remove("vb-typed");
          self.compose.textContent = "Message #" + channel.name;
          self.textMessage(channel, s.user, s.type, { instant: self.instant });
          return self.sleep(600, token);
        });
      });
    }

    if (s.user && s.text) {
      then(function () {
        self.textMessage(self.channelFor(s), s.user, s.text, { instant: self.instant });
      });
    }

    function speak(who, text, opts) {
      then(function () {
        var channel = self.channelFor(s);
        return self.showTyping(who, channel, token).then(function () {
          opts.instant = self.instant;
          self.textMessage(channel, who, text, opts);
          return self.sleep(s.after == null ? 650 : s.after, token);
        });
      });
    }

    if (s.say) speak(s.who || "n", s.say, {});
    if (s.narrate) speak("bot", s.italic === false ? s.narrate : "*" + s.narrate + "*", { image: s.image });
    if (s.notice) speak("bot", s.notice, {});

    if (s.menu || s.button || s.link) {
      then(function () {
        var channel = self.channelFor(s);
        var labels = s.menu || [s.button || s.link];
        var kind = s.button ? "vb-primary" : s.link ? "vb-link" : null;
        var row = self.buttonRow(labels, kind, s.id, !self.instant);
        self.textMessage(channel, "bot", "", { buttons: row, instant: self.instant });
        return self.sleep(s.after == null ? 700 : s.after, token);
      });
    }

    if (s.click) {
      then(function () {
        var btn = (self.buttons[s.click] || [])[s.option || 0];
        if (!btn) return null;
        return self.clickButton(btn, s.user, token).then(function () {
          if (s.disable === true) {
            self.buttons[s.click].forEach(function (b) {
              b.classList.add("vb-off");
            });
          }
          return self.sleep(250, token);
        });
      });
    }

    if (s.clear) {
      then(function () {
        var channel = self.channels[s.clear];
        var rows = Array.prototype.slice.call(channel.pane.children);
        rows.forEach(function (row) {
          row.classList.add("vb-gone");
        });
        return self.sleep(450, token).then(function () {
          channel.pane.textContent = "";
          channel.last = null;
        });
      });
    }

    if (s.wait && !s.log) {
      then(function () {
        return self.sleep(s.wait, token);
      });
    }

    return chain;
  };

  Demo.prototype.play = function (instant) {
    var self = this;
    var token = {};
    this.token = token;
    this.instant = !!instant;
    this.reset();
    var steps = this.spec.steps;
    var chain = Promise.resolve();

    if (this.spec.prefill) {
      chain = chain.then(function () {
        var wasInstant = self.instant;
        self.instant = true;
        var p = Promise.resolve();
        self.spec.prefill.forEach(function (s) {
          p = p.then(function () {
            return self.step(s, token);
          });
        });
        return p.then(function () {
          self.instant = wasInstant;
        });
      });
    }

    chain = chain.then(function () {
      return self.sleep(500, token);
    });
    steps.forEach(function (s) {
      chain = chain.then(function () {
        return self.step(s, token);
      });
    });

    return chain.then(function () {
      for (var key in self.cursors) self.cursors[key].style.opacity = "0";
      if (self.instant) {
        self.instant = false;
        return null;
      }
      return self.sleep(6000, token).then(function () {
        if (self.visible) return self.play(false);
        self.token = null;
        return null;
      });
    }).catch(function (err) {
      if (err !== ABORT) throw err;
    });
  };

  Demo.prototype.stop = function () {
    this.token = null;
  };

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------

  function boot() {
    var nodes = document.querySelectorAll(".vb-demo[data-demo]");
    var demos = [];
    Array.prototype.forEach.call(nodes, function (node) {
      var spec = DEMOS[node.getAttribute("data-demo")];
      if (!spec) return;
      var demo = new Demo(node, spec);
      node._vbDemo = demo;
      demos.push(demo);
    });

    if (REDUCED || !("IntersectionObserver" in window)) {
      demos.forEach(function (demo) {
        demo.play(true);
      });
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var demo = entry.target._vbDemo;
        if (entry.isIntersecting) {
          demo.visible = true;
          if (!demo.token) demo.play(false);
        } else {
          demo.visible = false;
          demo.stop();
        }
      });
    }, { threshold: 0.45 });
    demos.forEach(function (demo) {
      observer.observe(demo.root);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
