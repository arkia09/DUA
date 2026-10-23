/* Hidden fun: the staff record, secrets, and small surprises.
   Everything here is cosmetic. It runs in the visitor's browser only, stores one small record in localStorage
   (offices visited and secrets found), and never sends anything to the server. Text is always set with textContent. */
(function () {
  "use strict";
  const $ = (sel, root) => (root || document).querySelector(sel);
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  const pick = list => list[Math.floor(Math.random() * list.length)];
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const OFFICES = {
    briefing: "Morning Docket Office",
    pending: "Bureau of Pending Affairs",
    correspondence: "Office of Correspondence Avoidance",
    documents: "Commission for Unnecessarily Complicated Documents",
    tribunal: "Tribunal for Minor Inconveniences",
  };
  // `hint` is shown while a secret is still classified; `story` once it is found.
  const SECRETS = [
    {id: "lost", name: "The Lost Page", hint: "Ask this Department for something it does not have.",
     story: "You requested a page that does not exist, and were issued a permit for it."},
    {id: "break", name: "The Break Room", hint: "Even the rules for robots mention a room that robots may not enter.",
     story: "You found where the sloth goes when he is not at his desk."},
    {id: "complaints", name: "The Complaints Department", hint: "It is open. It would like you to know that it is open.",
     story: "You joined the queue. You are still in it."},
    {id: "lunch", name: "Lunch Break", hint: "Pester the clerk on your staff badge. Repeatedly.",
     story: "You pestered the Sloth Officer until he went to lunch."},
    {id: "drill", name: "Emergency Efficiency Drill", hint: "An old command from an older era. Up, up, and so on.",
     story: "You called a drill. Nobody was interested, but the stamps were very enthusiastic."},
    {id: "walk", name: "The Long Walk", hint: "Say his name. With your keyboard, not your voice.",
     story: "You summoned the Sloth Officer for a walk at his own pace."},
    {id: "button", name: "The Button", hint: "At the bottom of every page there is a button that asks nothing of you.",
     story: "You pressed the button you were asked not to press."},
    {id: "return", name: "Welcome Back", hint: "Leave this tab for a little while. We will notice.",
     story: "You left, and came back. We had not moved on."},
  ];
  const LEVELS = [
    [0, "Visitor"], [3, "Intern"], [6, "Junior Clerk"], [9, "Senior Clerk"], [12, "Deputy Undersecretary of Nothing"],
  ];
  const TOTAL = Object.keys(OFFICES).length + SECRETS.length;
  const KEY = "dua.record.v1";
  const SECRET_IDS = SECRETS.map(s => s.id);

  /* ---------- the staff record (in memory, mirrored to localStorage when it works) ---------- */
  let record = {visited: [], secrets: {}};
  try {
    const saved = JSON.parse(localStorage.getItem(KEY));
    if (saved && typeof saved === "object") {
      record.visited = Array.isArray(saved.visited) ? saved.visited.filter(x => x in OFFICES) : [];
      if (saved.secrets && typeof saved.secrets === "object") {
        SECRET_IDS.forEach(id => { if (saved.secrets[id]) record.secrets[id] = saved.secrets[id]; });
      }
    }
  } catch (e) { /* private window or blocked storage: the record simply lasts as long as this page */ }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(record)); } catch (e) { /* fine */ } }

  const score = () => record.visited.length + Object.keys(record.secrets).length;
  function level() {
    let idx = 0;
    LEVELS.forEach((l, i) => { if (score() >= l[0]) idx = i; });
    return {n: idx + 1, name: LEVELS[idx][1]};
  }

  /* ---------- toast and mascot helpers ---------- */
  let toasts = null;
  function toast(msg) {
    if (!toasts) {
      toasts = el("div", "toasts");
      toasts.setAttribute("role", "status");
      toasts.setAttribute("aria-live", "polite");
      document.body.append(toasts);
    }
    const t = el("p", "toast", msg);
    toasts.append(t);
    setTimeout(() => t.remove(), 7000);
  }
  function bubbleSay(text, ms) {
    const bubble = $("#bubble");
    if (!bubble) return null;
    bubble.textContent = text;
    bubble.hidden = false;
    setTimeout(() => { if (bubble.textContent === text) bubble.hidden = true; }, ms || 8000);
    return bubble;
  }

  function changed(message) {
    const before = window.__duaLevel;
    const now = level();
    window.__duaLevel = now.n;
    save();
    renderRecord();
    renderClearance();
    return before !== undefined && now.n > before ? message + " Promoted: you are now " + now.name + "." : message;
  }
  function unlock(id) {
    if (!SECRET_IDS.includes(id) || record.secrets[id]) return false;
    record.secrets[id] = Date.now();
    const s = SECRETS.find(x => x.id === id);
    const found = Object.keys(record.secrets).length;
    toast(changed("Secret found: " + s.name + " (" + found + " of " + SECRETS.length + ")."));
    return true;
  }
  function visit(slug) {
    if (!(slug in OFFICES) || record.visited.includes(slug)) return;
    record.visited.push(slug);
    toast(changed("New office visited: " + OFFICES[slug] + "."));
  }

  /* ---------- clearance link in the masthead + the record on the front desk ---------- */
  function renderClearance() {
    const a = $("#clearance");
    if (!a) return;
    a.hidden = false;
    a.textContent = " Clearance: " + level().name + " (" + score() + "/" + TOTAL + ")";
  }
  function renderRecord() {
    const box = $("#recordBody");
    if (!box) return;
    const lv = level(), found = Object.keys(record.secrets).length;
    const frag = document.createDocumentFragment();
    const head = el("p", "rank");
    head.append(el("strong", "", "Clearance level " + lv.n + " of " + LEVELS.length + ": " + lv.name));
    frag.append(head);
    const bar = el("div", "meter");
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", score() + " of " + TOTAL + " items completed");
    const fill = el("span", "meter-fill");
    fill.style.width = Math.round(100 * score() / TOTAL) + "%";
    bar.append(fill);
    frag.append(bar);
    frag.append(el("p", "meta", "Offices visited: " + record.visited.length + " of " + Object.keys(OFFICES).length +
      ". Secrets found: " + found + " of " + SECRETS.length + ". Kept only in this browser."));

    const offices = el("ul", "checklist");
    Object.entries(OFFICES).forEach(([slug, name]) => {
      const done = record.visited.includes(slug);
      const li = el("li", done ? "done" : "");
      li.append(el("span", "tick", done ? "Visited" : "Not yet"));
      if (done) li.append(document.createTextNode(" " + name));
      else {
        const a = el("a", "", name);
        a.href = "/" + slug + "/";
        li.append(document.createTextNode(" "), a);
      }
      offices.append(li);
    });
    frag.append(el("h3", "sec", "Offices"), offices);

    const secrets = el("ul", "checklist");
    SECRETS.forEach(s => {
      const done = !!record.secrets[s.id];
      const li = el("li", done ? "done" : "classified");
      li.append(el("span", "tick", done ? "Found" : "Classified"));
      li.append(document.createTextNode(" " + (done ? s.name + ": " + s.story : "Hint: " + s.hint)));
      secrets.append(li);
    });
    frag.append(el("h3", "sec", "Hidden things"), secrets);
    if (found === SECRETS.length && record.visited.length === Object.keys(OFFICES).length) {
      frag.append(el("p", "warn", "Every office visited, every secret found. The Department has nothing left to show you, and has been instructed to look busy."));
    }
    const reset = el("button", "small", "Erase my record");
    reset.type = "button";
    reset.addEventListener("click", () => {
      record = {visited: [], secrets: {}};
      window.__duaLevel = level().n;
      save();
      renderRecord();
      renderClearance();
      toast("Your record has been erased. The Department has no memory of you, which is mutual.");
    });
    frag.append(reset);
    box.replaceChildren(frag);
  }

  /* ---------- the sloth badge: annoy him enough and he goes to lunch ---------- */
  (function sloth() {
    const btn = $("#slothBtn"), svg = $("#sloth"), status = $("#slothStatus");
    if (!btn || !svg) return;
    const resting = status ? status.textContent : "";
    let clicks = 0, onLunch = false, lastClick = 0;
    const LINES = {
      3: "Please stop. That is my face.",
      5: "I am filing a form about you. It will take a while.",
      7: "This is being noted. Slowly.",
      9: "One more and I am going to lunch. I mean it. Gently.",
    };
    btn.addEventListener("click", () => {
      if (onLunch) { bubbleSay("Shh. I am at lunch.", 3000); return; }
      const now = Date.now();
      clicks = now - lastClick > 6000 ? 1 : clicks + 1;     // pauses reset the count
      lastClick = now;
      if (LINES[clicks]) bubbleSay(LINES[clicks], 6000);
      if (clicks >= 10) lunch();
    });
    function lunch() {
      onLunch = true;
      clicks = 0;
      svg.classList.add("asleep");
      if (status) status.textContent = "At lunch (do not disturb)";
      const zzz = el("span", "zzz", "Zzz");
      zzz.setAttribute("aria-hidden", "true");
      $(".idcard", btn).append(zzz);
      const bubble = bubbleSay("I have gone to lunch. If you must find me, I am in the break room.", 15000);
      if (bubble) {
        const a = el("a", "", " Open the door.");
        a.href = "/break-room/";
        bubble.append(a);
      }
      unlock("lunch");
      setTimeout(() => {
        onLunch = false;
        svg.classList.remove("asleep");
        if (status) status.textContent = resting;
        zzz.remove();
        bubbleSay("I am back. I did not enjoy it.", 4000);
      }, 20000);
    }
  })();

  /* ---------- keyboard secrets (ignored while the visitor is typing in a form) ---------- */
  const KONAMI = ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"];
  let kpos = 0, typed = "";
  document.addEventListener("keydown", ev => {
    const t = ev.target;
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    const k = ev.key.length === 1 ? ev.key.toLowerCase() : ev.key;
    kpos = k === KONAMI[kpos] ? kpos + 1 : (k === KONAMI[0] ? 1 : 0);
    if (kpos === KONAMI.length) { kpos = 0; drill(); }
    if (ev.key.length === 1) {
      typed = (typed + k).slice(-5);
      if (typed === "sloth") { typed = ""; walk(); }
    }
  });

  function drill() {
    const banner = el("div", "banner", "EMERGENCY EFFICIENCY DRILL. All staff must work faster. ...Drill cancelled: nobody was interested.");
    banner.setAttribute("role", "status");
    document.body.append(banner);
    setTimeout(() => banner.remove(), 7000);
    if (!reduceMotion) {
      const words = ["APPROVED", "DENIED", "PENDING", "DEFERRED", "FILED", "LATER", "NOTED", "MAYBE"];
      for (let i = 0; i < 24; i++) {
        const s = el("span", "stamp stamp-fall", pick(words));
        s.setAttribute("aria-hidden", "true");
        s.style.left = Math.floor(Math.random() * 90) + "%";
        s.style.animationDelay = (Math.random() * 2).toFixed(2) + "s";
        s.style.animationDuration = (2.5 + Math.random() * 2).toFixed(2) + "s";
        document.body.append(s);
        setTimeout(() => s.remove(), 6500);
      }
    }
    unlock("drill");
  }

  function walk() {
    const src = $("#sloth");
    if (reduceMotion || !src) {
      toast("A sloth has walked past, slowly. You would have to imagine it.");
    } else {
      const w = el("div", "walker");
      w.setAttribute("aria-hidden", "true");
      const copy = src.cloneNode(true);
      copy.removeAttribute("id");
      copy.classList.remove("idphoto");
      w.append(copy, el("span", "walker-say", "Do not rush."));
      w.addEventListener("animationend", () => w.remove());
      document.body.append(w);
      setTimeout(() => w.remove(), 30000);
    }
    unlock("walk");
  }

  /* ---------- the tab notices when you leave ---------- */
  (function tab() {
    const original = document.title;
    const NAGS = ["Come back. We were mid-sentence.", "The paperwork is lonely.", "We noticed you left.", "The sloth is waiting. He has time."];
    let leftAt = 0;
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        leftAt = Date.now();
        document.title = pick(NAGS);
      } else {
        document.title = original;
        if (leftAt && Date.now() - leftAt > 3000) unlock("return");
        leftAt = 0;
      }
    });
  })();

  /* ---------- the button at the bottom of every page ---------- */
  (function button() {
    const b = $("#dnc"), msg = $("#dncMsg");
    if (!b) return;
    let n = 0;
    const LATER = ["Click count: NUM. A form has been filed for each.", "NUM clicks. The Department is not sure what you want.",
                   "Please consider a hobby. NUM clicks recorded."];
    b.addEventListener("click", () => {
      n++;
      msg.replaceChildren();
      if (n === 1) msg.textContent = "Thank you for pressing. Your press has been filed and will be ignored.";
      else if (n === 2) msg.textContent = "Please stop. Each press requires a form.";
      else if (n === 3) {
        msg.append(document.createTextNode("Fine. Your persistence is noted. If you wish to complain about this, the "));
        const a = el("a", "", "Complaints Department");
        a.href = "/complaints/";
        msg.append(a, document.createTextNode(" is open."));
        unlock("button");
      } else msg.textContent = pick(LATER).replace("NUM", String(n));
    });
  })();

  /* ---------- hidden pages ---------- */
  function initComplaints() {
    const pos = $("#queuePos"), note = $("#queueNote"), form = $("#complaintForm"), out = $("#complaintOut");
    if (!pos) return;
    let n = 4812;
    setInterval(() => {
      if (Math.random() < 0.3) {
        n += 1 + Math.floor(Math.random() * 3);
        note.textContent = pick(["A colleague has joined the queue ahead of you.", "The queue has been reorganised. You are now further back.",
                                 "Estimated wait revised: approximately four fiscal years."]);
      } else n -= 1;
      n = Math.max(n, 4700);
      pos.textContent = n.toLocaleString("en-US");
    }, 2500);
    const REASONS = [
      "Dismissed. The complaint was found to be a complaint.",
      "Dismissed on the grounds that the Department is, regrettably, not responsible for anything.",
      "Dismissed. A reply will be mailed in three to five fiscal years.",
      "Dismissed, with sympathy, which is the only thing we have in stock.",
      "Referred to the Department of Complaints About This Department, which has been closed since Tuesday.",
      "Dismissed pending an investigation, which has been dismissed.",
    ];
    form.addEventListener("submit", ev => {
      ev.preventDefault();
      const ticket = "C-" + String(1000 + Math.floor(Math.random() * 9000));
      const box = el("section", "sheet");
      box.append(el("h2", "", "Complaint " + ticket + " received"),
                 el("p", "", "Status: " + pick(REASONS)),
                 el("p", "meta", "Your complaint was not sent anywhere. It has been read by nobody, and is now filed in this browser tab, which will forget it shortly."));
      out.replaceChildren(box);
      $("#complaint").value = "";
    });
  }

  function initBreakRoom() {
    const log = $("#breakLog");
    if (!log) return;
    const say = t => { log.textContent = t; };
    let coffee = 0, wake = 0, fridge = 0;
    const COFFEE = ["He declines. Slowly. It takes about a minute.", "He accepts the cup, looks at it, and puts it down for later.",
                    "The coffee has gone cold. So has the sloth's interest, which was already low.", "He says, \"Not now.\" He says it like a long vowel."];
    const WAKE = ["He is not asleep. He is resting his eyes in a thorough and committed way.", "One eye opens. It closes again, as though it were never open.",
                  "\"I was listening,\" he says. He was not.", "He has resigned. Then un-resigned. Nothing has changed."];
    const FRIDGE = ["One yogurt. The label reads: DO NOT TOUCH, DEPARTMENT AUDIT.", "A single lettuce, filed under Pending.",
                    "A note: \"Whoever took my lunch, I forgive you. Slowly.\"", "The fridge is full of forms. Several are cold."];
    $("#coffee").addEventListener("click", () => say(COFFEE[coffee++ % COFFEE.length]));
    $("#wake").addEventListener("click", () => say(WAKE[wake++ % WAKE.length]));
    $("#fridge").addEventListener("click", () => say(FRIDGE[fridge++ % FRIDGE.length]));
  }

  /* ---------- boot ---------- */
  window.__duaLevel = level().n;
  const unlockId = document.body.dataset.unlock;
  visit(location.pathname.split("/")[1]);
  if (unlockId) unlock(unlockId);
  renderRecord();
  renderClearance();
  const page = document.body.dataset.page;
  if (page === "complaints") initComplaints();
  if (page === "break-room") initBreakRoom();

  if (window.console && console.log) {
    console.log("%cDepartment of Unnecessary Affairs", "font:bold 16px Georgia;color:#7a1f2b");
    console.log("If you are reading this, you may be overqualified. Some officers read robots.txt. Some press the button at the bottom of the page.");
  }
})();
