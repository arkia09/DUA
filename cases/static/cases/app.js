(function () {
  "use strict";
  const $ = (sel, root) => (root || document).querySelector(sel);

  /* ---------- tiny DOM helpers (textContent only: model output is untrusted) ---------- */
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function row(dl, term, value) {
    if (!value) return;
    dl.append(el("dt", "", term), el("dd", "", value));
  }
  const pick = list => list[Math.floor(Math.random() * list.length)];

  /* ---------- the Sloth Officer (top-right staff ID badge) ---------- */
  const mascot = (() => {
    const svg = $("#sloth"), bubble = $("#bubble"), btn = $("#slothBtn");
    let timer = null;
    const IDLE = [
      "Take a number. I will attend to you shortly. Possibly tomorrow.",
      "I am not asleep. I am conducting a very long blink.",
      "Everything urgent is, on inspection, optional.",
      "Please do not rush the sloth.",
      "Efficiency is just panic with a clipboard.",
    ];
    function say(text, ms) {
      bubble.textContent = text;
      bubble.hidden = false;
      clearTimeout(timer);
      if (ms !== 0) timer = setTimeout(() => { bubble.hidden = true; }, ms || 8000);
    }
    btn.addEventListener("click", () => { bubble.hidden ? say(pick(IDLE)) : (bubble.hidden = true); });
    const status = $("#slothStatus"), RESTING = status ? status.textContent : "";
    return { say, reviewing(on) {
      svg.classList.toggle("reviewing", on);
      if (status) status.textContent = on ? "Reviewing (slowly)" : RESTING;
    } };
  })();

  /* ---------- shared components ---------- */
  function officialNotice(label, text) {
    if (!text) return null;
    const n = el("aside", "notice");
    n.append(el("small", "", label + " — for entertainment purposes only"), document.createTextNode(text));
    return n;
  }
  function questionsBox(qs, title) {
    if (!qs || !qs.length) return null;
    const q = el("div", "questions");
    q.append(el("strong", "", title || "The Bureau cannot proceed without knowing:"));
    const ul = el("ul");
    qs.forEach(x => ul.append(el("li", "", x)));
    q.append(ul);
    return q;
  }
  function copyButton(getText) {
    const b = el("button", "small", "Copy");
    b.type = "button";
    b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(getText()); b.textContent = "Copied"; }
      catch (e) { b.textContent = "Copy failed"; }
      setTimeout(() => { b.textContent = "Copy"; }, 1500);
    });
    return b;
  }
  /* Django's CSRF token, sent with every POST (the older endpoints ignore it; upload and shred require it) */
  function csrfToken() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function post(url, {json, form} = {}) {
    const headers = {"X-CSRFToken": csrfToken()};
    if (json !== undefined) headers["Content-Type"] = "application/json";
    return fetch(url, {method: "POST", headers, body: json !== undefined ? JSON.stringify(json) : form});
  }
  function bulletList(items) {
    const ul = el("ul");
    items.forEach(x => ul.append(el("li", "", x)));
    return ul;
  }
  function sourceQuote(quote, label) {
    const p = el("p", "src");
    p.append(el("small", "", (label || "Source in your document") + ": "), document.createTextNode("“" + quote + "”"));
    return p;
  }
  function section(parent, title, node) {
    parent.append(el("h3", "sec", title), node);
  }

  const DONE_LINES = [
    "Closed. Nobody is more surprised than this Bureau.",
    "Filed under Accomplished. A rare category.",
    "Done. The Bureau will pretend it expected this.",
    "Stamped complete. The Sloth Officer is moved, slowly.",
  ];
  const LABELS = {do_now: "Do now", schedule: "Schedule", delegate: "Delegate", defer: "Deferred", deny: "Denied"};
  const EXCUSED = ["defer", "deny"];
  const FALLBACK_CLAUSE = "you mention it again";

  /* Procrastination permit: issued for every deferred or denied task */
  function permit(c, t, i, clause) {
    const box = el("div", "permit");
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "Procrastination permit");
    box.append(
      el("div", "permit-kicker", "Department of Unnecessary Affairs"),
      el("div", "permit-title", t.verdict === "deny" ? "Permit to Ignore" : "Permit to Postpone"),
      el("div", "permit-no", "No. PTI-" + c.number + "-" + (i + 1)));
    const dl = el("dl");
    row(dl, "Granted to:", "The Applicant");
    row(dl, "In respect of:", t.title);
    row(dl, "Valid until:", clause || FALLBACK_CLAUSE);
    box.append(dl, el("div", "permit-sign", "Issued by the Sloth Officer, eventually."),
               el("div", "permit-seal", "Approved (slowly)"));
    return box;
  }

  /* ---------- case renderers ---------- */
  function renderPending(c, frag, hooks) {
    const r = c.result, plan = el("section", "sheet");
    plan.append(el("h2", "", "Case " + c.number + " — Action Plan"));
    if (r.notice.summary_line) plan.append(el("p", "smug", r.notice.summary_line));
    const next = el("p", "next");
    next.append(el("strong", "", "Start here (under 5 minutes): "), document.createTextNode(r.plan.smallest_next_action));
    plan.append(next);
    const progressEl = el("p", "progress"), done = new Set(c.done_tasks || []);
    plan.append(progressEl);

    const active = [], excused = [];
    r.plan.tasks.forEach((t, i) => (EXCUSED.includes(t.verdict) ? excused : active).push([t, i]));
    const excuses = r.notice.task_excuses || r.notice.task_remarks || [];   // task_remarks: older cases
    const permits = r.notice.task_permits || [];

    function addTask(t, i, n) {
      const isExcused = EXCUSED.includes(t.verdict);
      const box = el("div", "task" + (isExcused ? " excused" : ""));
      const h = el("h3");
      const closed = el("span", "stamp v-done", "Closed");
      closed.hidden = !done.has(i);
      h.append(el("span", "stamp v-" + t.verdict, LABELS[t.verdict] || t.verdict), el("span", "badge " + t.urgency, t.urgency),
               closed, el("span", "ttl", n + ". " + t.title));
      box.append(h);
      if (t.verdict !== "deny") {
        const tick = el("label", "tick"), cb = el("input"), note = el("p", "done-note", DONE_LINES[i % DONE_LINES.length]);
        cb.type = "checkbox";
        cb.checked = done.has(i);
        note.hidden = !cb.checked;
        box.classList.toggle("done", cb.checked);
        tick.append(cb, document.createTextNode(" Mark as done"));
        cb.addEventListener("change", async () => {
          const want = cb.checked;
          cb.disabled = true;
          try {
            const res = await post("/api/cases/" + encodeURIComponent(c.number) + "/tasks/" + i + "/", {json: {done: want}});
            if (!res.ok) throw new Error();
            if (want) done.add(i); else done.delete(i);
            box.classList.toggle("done", want);
            note.hidden = closed.hidden = !want;
            updateProgress();
            if (want) mascot.say(DONE_LINES[i % DONE_LINES.length]);
          } catch (e) {
            cb.checked = !want;
            mascot.say("The stamp pad is dry. Your tick was not recorded.");
          } finally { cb.disabled = false; }
        });
        box.append(tick, note);
      }
      if (excuses[i]) {
        const q = el("blockquote", "excuse");
        q.append(el("small", "", "Official excuse (fictional; do not submit to your teacher)"),
                 document.createTextNode("“" + excuses[i] + "”"));
        box.append(q);
      }
      box.append(el("div", "serious", "On a serious note…"));
      const dl = el("dl");
      row(dl, "Next step (under 5 minutes)", t.next_step);
      row(dl, "Deadline (as you stated)", t.deadline);
      row(dl, "Minimum effort to be done", t.minimum_effort);
      row(dl, "Why it ranks here", t.reason);
      row(dl, "Do these first", (t.depends_on || []).join("; "));
      box.append(dl);
      if (isExcused) box.append(permit(c, t, i, permits[i]));
      plan.append(box);
    }
    active.forEach(([t, i], k) => addTask(t, i, k + 1));
    if (excused.length) {
      plan.append(el("h3", "", "Officially excused (you may skip these)"));
      excused.forEach(([t, i], k) => addTask(t, i, k + 1));
    }
    const q = questionsBox(r.plan.clarifying_questions);
    if (q) plan.append(q);

    const carry = el("button", "small", "Carry unfinished tasks into a new plan");
    carry.type = "button";
    carry.title = "Files a new case with everything not yet done, and plans it again";
    carry.addEventListener("click", () => hooks.carry && hooks.carry(c.number));
    const tickable = r.plan.tasks.filter(t => t.verdict !== "deny").length;
    function updateProgress() {
      const left = r.plan.tasks.filter((t, i) => t.verdict !== "deny" && !done.has(i)).length;
      progressEl.textContent = "Done: " + (tickable - left) + " of " + tickable + " tasks (denied tasks need no ticking).";
      carry.disabled = left === 0;
    }
    updateProgress();
    if (tickable) {
      const act = el("div", "actions");
      act.append(carry, el("span", "meta", "Tomorrow? This files the open tasks as a fresh case and re-plans them. It takes as long as any new plan."));
      plan.append(act);
    }
    frag.append(plan);
    const n = officialNotice("Official notice", r.notice.official_notice);
    if (n) frag.append(n);

    const k = excused.length;
    mascot.say(k ? "I have excused " + k + (k === 1 ? " task" : " tasks") + ". Do not thank me. Do not rush."
                 : "Regrettably, all of this must be done. I will supervise from here, slowly.");
  }

  function renderCorrespondence(c, frag) {
    const r = c.result, d = r.draft, sheet = el("section", "sheet");
    sheet.append(el("h2", "", "Case " + c.number + " — Your Message"));
    if (c.options && c.options.tone) sheet.append(el("p", "meta", "Tone: " + c.options.tone +
      (c.options.incoming ? " · Reply to the message you pasted" : "")));
    const full = (subject, body) => (subject ? "Subject: " + subject + "\n\n" : "") + body;
    if (d.subject) sheet.append(el("div", "", "Subject: " + d.subject));
    sheet.append(el("pre", "draft", d.body), copyButton(() => full(d.subject, d.body)));
    if (d.placeholders && d.placeholders.length) {
      sheet.append(el("p", "fill", "Fill in before sending: " + d.placeholders.join(" ")));
    }
    (d.alternatives || []).forEach(a => {
      const det = el("details");
      det.append(el("summary", "", "Alternative: " + a.label), el("pre", "draft", a.body), copyButton(() => full(d.subject, a.body)));
      sheet.append(det);
    });
    if (d.incoming_questions && d.incoming_questions.length) {
      const box = el("div");
      d.incoming_questions.forEach(x => {
        const b = el("div", "claim reply-q");
        b.append(el("span", "stamp " + (x.answered ? "v-done" : "v-need"), x.answered ? "Answered in draft" : "Needs your input"),
                 el("div", "", x.question), sourceQuote(x.quote, "Their words"));
        box.append(b);
      });
      section(sheet, "Questions in the message you received", box);
      sheet.append(el("p", "meta", "Answered or not is the AI's own judgement. Check that your draft covers each one." +
        (d.dropped_incoming_questions ? " " + d.dropped_incoming_questions + " item(s) were removed because they could not be matched to the message." : "")));
    }
    const q = questionsBox(d.clarifying_questions);
    if (q) sheet.append(q);
    frag.append(sheet);
    const n = officialNotice("Internal memorandum", r.notice.official_memo);
    if (n) frag.append(n);
    mascot.say("Memorandum prepared. You may now send it, or reconsider everything. Both are valid.");
  }

  /* ---------- Commission for Unnecessarily Complicated Documents ---------- */
  function renderDocuments(c, frag) {
    const r = c.result.review, n = c.result.notice || {}, s = r.stats || {};
    const sheet = el("section", "sheet");
    sheet.append(el("h2", "", "Case " + c.number + " — Document Review"));
    const o = c.options || {};
    sheet.append(el("p", "meta", (o.filename ? "File: " + o.filename : "Pasted text") +
      (o.pages ? " · " + o.pages + (o.pages === 1 ? " page" : " pages") : "") +
      (o.words ? " · " + o.words + " words" : "") + " · The full text was not saved."));

    if (r.looks_like_instructions) {
      sheet.append(el("p", "warn", "This document contains text that looks like instructions aimed at an AI. It was treated as ordinary text and was not obeyed."));
    }

    sheet.append(el("h3", "sec", "In plain language"), el("p", "", r.summary));
    if (r.key_points && r.key_points.length) section(sheet, "Key points", bulletList(r.key_points));

    const claims = (title, items, build, none) => {
      const box = el("div");
      if (!items || !items.length) box.append(el("p", "meta", none));
      else items.forEach(x => box.append(build(x)));
      section(sheet, title, box);
    };
    claims("Deadlines stated in the document", r.deadlines, d => {
      const b = el("div", "claim");
      b.append(el("strong", "", d.when + ": "), document.createTextNode(d.what), sourceQuote(d.source_quote));
      return b;
    }, "No deadline could be traced to the text of the document.");
    claims("What you are asked to do", r.action_items, a => {
      const b = el("div", "claim");
      b.append(document.createTextNode(a.item), sourceQuote(a.source_quote));
      return b;
    }, "No action items could be traced to the text of the document.");
    claims("Requirements and conditions", r.requirements, a => {
      const b = el("div", "claim");
      b.append(document.createTextNode(a.item), sourceQuote(a.source_quote));
      return b;
    }, "No requirements could be traced to the text of the document.");

    if (r.unclear_or_missing && r.unclear_or_missing.length) {
      const q = questionsBox(r.unclear_or_missing, "Unclear, ambiguous or missing:");
      sheet.append(q);
    }
    if (r.dropped_claims) {
      sheet.append(el("p", "meta", r.dropped_claims + (r.dropped_claims === 1 ? " item was" : " items were") +
        " removed because the AI could not point to matching words in your document."));
    }

    /* computed numbers (real) next to the model's label (a joke) */
    sheet.append(el("h3", "sec", "Complexity rating"));
    const stats = el("div", "stats");
    [["Words", s.words], ["Sentences", s.sentences], ["Avg sentence", s.avg_sentence_words + " words"],
     ["Longest sentence", s.longest_sentence_words + " words"],
     ["Reading ease", s.reading_ease + " / 100 (" + s.reading_level + ")"]].forEach(([k, v]) => {
      const d = el("div", "stat");
      d.append(el("b", "", String(v)), el("span", "", k));
      stats.append(d);
    });
    sheet.append(stats);
    if (n.complexity_label) {
      const rating = el("div", "rating");
      rating.append(el("span", "stamp", n.complexity_label), el("span", "meta", "Official rating (fictional). The numbers above are real, and approximate for non-English text."));
      sheet.append(rating);
    }
    sheet.append(el("p", "meta", "AI-generated summary. It is not legal, medical or financial advice. Check the quoted source before relying on any point."));
    frag.append(sheet);
    const ack = officialNotice("Official acknowledgment", n.acknowledgment);
    if (ack) frag.append(ack);

    const nd = (r.deadlines || []).length;
    mascot.say(nd ? "I have found " + nd + (nd === 1 ? " deadline" : " deadlines") + ". I have not hurried toward them."
                  : "No stated deadlines. I find this restful, but please read the unclear parts.");
  }

  /* ---------- Morning Docket Office ---------- */
  function renderBriefing(c, frag) {
    const r = c.result.docket, n = c.result.notice || {}, sheet = el("section", "sheet"), o = c.options || {};
    sheet.append(el("h2", "", "Case " + c.number + " — Today's Docket"));
    sheet.append(el("p", "meta", (o.filename ? "File: " + o.filename : "Pasted notes") +
      (o.pages ? " · " + o.pages + (o.pages === 1 ? " page" : " pages") : "") +
      (o.words ? " · " + o.words + " words" : "") + " · The full text was not saved."));
    if (r.one_liner) sheet.append(el("p", "smug", r.one_liner));

    const today = el("div");
    r.top.forEach((t, i) => {
      const b = el("div", "docket-item"), h = el("h4", "", (i + 1) + ". " + t.title);
      if (t.deadline) h.append(document.createTextNode(" "), el("span", "badge high", "deadline: " + t.deadline));
      const dl = el("dl");
      row(dl, "Why today", t.why);
      row(dl, "Next step (under 5 minutes)", t.next_step);
      b.append(h, dl, sourceQuote(t.quote, "Your words"));
      today.append(b);
    });
    section(sheet, "Today", today);

    if (r.heads_up && r.heads_up.length) {
      const ul = el("ul", "docket-list");
      r.heads_up.forEach(h => {
        const li = el("li");
        li.append(el("strong", "", h.title), document.createTextNode(h.when ? " (" + h.when + ")" : ""), sourceQuote(h.quote, "Your words"));
        ul.append(li);
      });
      section(sheet, "Coming up", ul);
    }
    if (r.can_wait && r.can_wait.length) {
      const ul = el("ul", "docket-list");
      r.can_wait.forEach(w => {
        const li = el("li");
        li.append(el("strong", "", w.title), document.createTextNode(": " + w.why), sourceQuote(w.quote, "Your words"));
        ul.append(li);
      });
      section(sheet, "Can wait (you are officially permitted to ignore these today)", ul);
    }
    const q = questionsBox(r.clarifying_questions, "The Office would like to know:");
    if (q) sheet.append(q);
    if (r.dropped_items) {
      sheet.append(el("p", "meta", r.dropped_items + (r.dropped_items === 1 ? " item was" : " items were") +
        " removed because the AI could not point to matching words in your notes."));
    }
    sheet.append(el("p", "meta", "AI-generated. Check the quoted words before relying on any item."));
    frag.append(sheet);
    const note = officialNotice("Notice of Daily Obligations", n.notice);
    if (note) frag.append(note);
    const k = r.top.length;
    mascot.say("Today's docket: " + k + (k === 1 ? " item" : " items") + ". The rest may wait. I will not be hurrying them.");
  }

  /* ---------- Tribunal for Minor Inconveniences ---------- */
  const APPEALS = [
    "Your appeal has been received and heard by the same judge. It is dismissed, with sympathy.",
    "The appeal was considered at length by the judge who made the original ruling. The ruling stands.",
    "Appeal denied. The judge notes that he found your arguments very persuasive the first time, too.",
    "After careful reflection, in a chair, the court affirms its own decision. Costs: one sigh.",
  ];
  let appealCount = 0;

  function renderTribunal(c, frag) {
    const r = c.result.ruling, n = c.result.notice || {};
    if (r.crisis) {
      const box = el("section", "sheet");
      box.append(el("h2", "", "Case " + c.number + " — Not for this Tribunal"), el("p", "venue", n.serious_notice));
      frag.append(box);
      mascot.say("I have put the stamp down. Please talk to someone.");
      return;
    }
    const sheet = el("section", "sheet");
    sheet.append(el("h2", "", "Case " + c.number + " — Ruling"));
    if (r.serious) sheet.append(el("p", "venue", n.serious_notice));

    const rec = el("p", "next");
    const lead = r.serious ? "Where the considerations lean (not a ruling): "
               : r.provisional ? "Provisional recommendation (no preferences given): " : "Recommended: ";
    rec.append(el("strong", "", lead), document.createTextNode(r.recommended_option));
    sheet.append(rec, el("p", "", r.reasoning));
    if (r.grounded) {
      sheet.append(el("p", "meta", "Based on what you said matters: " + r.preferences_used.map(x => "“" + x + "”").join(", ")));
    } else if (!r.provisional) {
      sheet.append(el("p", "warn", "The Tribunal could not tie this reasoning to the preferences you stated. Treat the recommendation with care."));
    }

    const grid = el("div", "compare");
    r.options.forEach(opt => {
      const card = el("div", "opt" + (opt.name === r.recommended_option ? " pick" : ""));
      if (opt.name === r.recommended_option) card.append(el("span", "stamp", r.serious ? "Leans this way" : "Recommended"));
      card.append(el("h4", "", opt.name), el("h5", "", "Pros"), bulletList(opt.pros), el("h5", "", "Cons"), bulletList(opt.cons));
      grid.append(card);
    });
    sheet.append(grid);
    const q = questionsBox(r.clarifying_questions, "The Tribunal would like to know:");
    if (q) sheet.append(q);
    frag.append(sheet);

    if (!r.serious && (n.case_title || n.verdict)) {
      const j = el("aside", "notice judgment");
      j.append(el("small", "", "Judgment — for entertainment purposes only"));
      if (n.case_title) j.append(el("h3", "", n.case_title));
      if (n.findings) j.append(el("p", "", n.findings));
      if (n.verdict) j.append(el("p", "", "Verdict: " + n.verdict));
      if (n.sentence) j.append(el("p", "", "Sentence: " + n.sentence));
      if (n.appeal_procedure) j.append(el("p", "", "Appeals: " + n.appeal_procedure));
      const result = el("p", "appeal-result");
      result.setAttribute("role", "status");
      const b = el("button", "small", "Lodge an appeal");
      b.type = "button";
      b.addEventListener("click", () => {
        result.textContent = APPEALS[appealCount++ % APPEALS.length];
        mascot.say("The appeal has been heard. By the same judge. It went as you would expect.");
      });
      j.append(b, result);
      frag.append(j);
    }
    mascot.say(r.serious ? "This one matters more than a Tribunal. Please consider the considerations."
                         : "The court has ruled. You may appeal. It will not help.");
  }

  /* hooks: {retry(number), shred(number)} supplied by the page */
  function renderCase(out, c, notice, hooks) {
    hooks = hooks || {};
    const frag = document.createDocumentFragment();
    try {
      if (c.status === "failed") {
        const box = el("div", "sheet error");
        box.append(el("p", "", (notice ? notice + " " : "") + "Case " + c.number + " could not be completed."));
        if (c.department === "documents") {
          // The office does not keep the document, so it cannot be reviewed again from the record.
          box.append(el("p", "", "This office does not keep your document, so please submit it again."));
        } else {
          const b = el("button", "small", "Send back for review");
          b.type = "button";
          b.addEventListener("click", () => hooks.retry && hooks.retry(c.number));
          box.append(b);
        }
        frag.append(box);
        mascot.say("The review has been postponed. By me. Retry when you feel ready.");
      } else if (c.result && c.result.plan) renderPending(c, frag, hooks);
      else if (c.result && c.result.draft) renderCorrespondence(c, frag);
      else if (c.result && c.result.review) renderDocuments(c, frag);
      else if (c.result && c.result.ruling) renderTribunal(c, frag);
      else if (c.result && c.result.docket) renderBriefing(c, frag);
      else frag.append(el("div", "sheet", "Case " + c.number + " is on file, but its record is in an older format and cannot be displayed."));
    } catch (e) {
      frag.append(el("div", "sheet error", "Case " + c.number + " is on file, but its record could not be displayed."));
    }
    if (c.number) {
      const p = el("p", "permalink");
      if (document.body.dataset.page !== "case") {
        const a = el("a", "", "Permanent link to case " + c.number);
        a.href = "/files/" + encodeURIComponent(c.number) + "/";
        p.append(a, document.createTextNode(" · "));
      }
      const canExport = c.status === "resolved" && c.result && !(c.result.ruling && c.result.ruling.crisis);
      if (canExport) {
        const base = "/api/cases/" + encodeURIComponent(c.number) + "/export/";
        const md = el("a", "", "Download Markdown");
        md.href = base + "md/";
        md.setAttribute("download", "");
        p.append(md, document.createTextNode(" · "));
        if (c.department === "pending") {
          const ics = el("a", "", "Download to-do list (.ics)");
          ics.href = base + "ics/";
          ics.setAttribute("download", "");
          p.append(ics, document.createTextNode(" · "));
        }
      }
      const sh = el("button", "small", "Shred this case");
      sh.type = "button";
      sh.title = "Permanently delete this case from this installation";
      sh.addEventListener("click", () => {
        if (window.confirm("Shred case " + c.number + "? It will be permanently deleted.") && hooks.shred) hooks.shred(c.number);
      });
      p.append(sh);
      frag.append(p);
    }
    out.replaceChildren(frag);
  }

  /* ---------- history ---------- */
  const DEPT_NAMES = {briefing: "Morning Docket Office", pending: "Bureau of Pending Affairs", correspondence: "Office of Correspondence Avoidance",
                      documents: "Commission for Unnecessarily Complicated Documents", tribunal: "Tribunal for Minor Inconveniences"};

  async function loadHistory(onSelect) {
    const list = $("#histList"), empty = $("#histEmpty");
    if (!list) return;
    try {
      const res = await fetch("/api/cases/");
      const data = await res.json();
      const dept = list.dataset.department, limit = parseInt(list.dataset.limit || "50", 10);
      const cases = data.cases.filter(c => !dept || c.department === dept).slice(0, limit);
      list.replaceChildren();
      empty.hidden = cases.length > 0;
      cases.forEach(c => {
        const li = el("li");
        const b = list.dataset.links || !onSelect ? el("a", "row") : el("button", "row");
        if (b.tagName === "A") b.href = "/files/" + encodeURIComponent(c.number) + "/";
        else { b.type = "button"; b.addEventListener("click", () => onSelect(c)); }
        const title = el("div");
        title.append(el("strong", "", c.number + " "), document.createTextNode((DEPT_NAMES[c.department] || c.department) + " — "),
                     el("span", "st-" + c.status, c.status.replace("_", " ")));
        b.append(title, el("div", "meta", new Date(c.created_at).toLocaleString() + " · " + c.statement.slice(0, 70) + (c.statement.length > 70 ? "…" : "")));
        li.append(b);
        list.append(li);
      });
    } catch (e) { /* history is a convenience; stay quiet */ }
  }

  /* ---------- department page: form, loading, submit, retry ---------- */
  const LOADING = [
    "The Sloth Officer has been notified. He is finishing a yawn.",
    "Your file is being processed at the speed of dignity.",
    "Stamping things. Slowly. With feeling.",
    "Consulting the Department of Meetings About Meetings.",
    "Please remain seated. Do not rush the sloth.",
    "Your request is being reviewed by someone who is in no hurry whatsoever.",
  ];

  function initDepartment() {
    const config = JSON.parse($("#page-config").textContent);
    const form = $("#form"), ta = $("#statement"), btn = $("#submit"), out = $("#out"), counter = $("#counter"),
          tone = $("#tone"), examples = $("#examples"), prefs = $("#preferences"),
          file = $("#file"), clearFile = $("#clearFile"), fileNote = $("#fileNote"),
          incoming = $("#incoming"), promptLabel = $("#prompt");
    let ticker = null;

    function showMessage(msg, isError) { out.replaceChildren(el("div", isError ? "sheet error" : "sheet", msg)); }
    const hooks = {retry: number => send("/api/cases/" + encodeURIComponent(number) + "/retry/"), shred,
                   carry: number => send("/api/cases/" + encodeURIComponent(number) + "/carry-over/")};
    const show = (c, notice) => renderCase(out, c, notice, hooks);

    function startLoading() {
      const t0 = Date.now();
      let i = 0, n = 0;
      const box = el("div", "sheet"), line = el("p", "", ""), secs = el("p", "meta", "");
      box.append(line, secs);
      out.replaceChildren(box);
      const tick = () => {
        if (n++ % 4 === 0) line.textContent = LOADING[i++ % LOADING.length];   // new line every 4 seconds
        secs.textContent = "Elapsed: " + Math.floor((Date.now() - t0) / 1000) + "s. The Department regrets nothing.";
      };
      tick();
      ticker = setInterval(tick, 1000);
      mascot.reviewing(true);
      mascot.say("Reviewing your case. Slowly. Thoroughly. Mostly slowly.", 0);
    }
    function stopLoading() { clearInterval(ticker); mascot.reviewing(false); }

    async function send(url, request) {
      btn.disabled = true;
      startLoading();
      try {
        const res = await post(url, request);
        const data = await res.json().catch(() => ({}));
        stopLoading();
        if (res.ok) show(data.case);
        else if (data.case) {
          show(data.case, data.notice);
          out.prepend(el("div", "sheet error", data.error || "Something went wrong."));
        } else { showMessage(data.error || "Something went wrong.", true); mascot.say("Something has gone wrong. I blame the intern."); }
      } catch (e) {
        stopLoading();
        showMessage("The server could not be reached.", true);
      } finally {
        btn.disabled = false;
        loadHistory(show);
      }
    }

    async function shred(number) {
      try {
        const res = await post("/api/cases/" + encodeURIComponent(number) + "/shred/");
        if (!res.ok) throw new Error();
        showMessage("Case " + number + " has been shredded. The Department has no memory of it, which is its natural state.");
        mascot.say("Shredded. I did not even look at it. Much.");
      } catch (e) { showMessage("The shredder jammed. The case was not deleted.", true); }
      loadHistory(show);
    }

    /* ---- optional file upload (documents office). The server re-checks everything. ---- */
    function syncFile() {
      const f = file && file.files[0];
      ta.disabled = !!f;
      ta.required = !f;
      if (clearFile) clearFile.hidden = !f;
      if (!file) return;
      if (!f) { fileNote.textContent = ""; return; }
      const ext = (f.name.split(".").pop() || "").toLowerCase();
      if (!["txt", "md", "pdf"].includes(ext)) {
        fileNote.textContent = "Only .txt, .md and .pdf files are accepted. Please remove this file or choose another.";
      } else if (ext === "pdf" && f.size > config.maxPdfBytes) {
        fileNote.textContent = "That file is too large (maximum " + Math.floor(config.maxPdfBytes / 1000000) + " MB for a PDF).";
      } else if (ext !== "pdf" && f.size > config.maxUploadBytes) {
        fileNote.textContent = "That file is too large (maximum " + Math.floor(config.maxUploadBytes / 1000) + " KB).";
      } else {
        fileNote.textContent = "Using " + f.name + " (" + f.size + " bytes). Pasted text is ignored while a file is chosen.";
      }
    }
    if (file) {
      file.addEventListener("change", syncFile);
      clearFile.addEventListener("click", () => { file.value = ""; syncFile(); ta.focus(); });
    }

    ta.addEventListener("input", () => { counter.textContent = ta.value.length + " / " + config.maxChars; });
    if (incoming) {   // with a pasted message, notes on how to reply become optional
      const sync = () => {
        const has = incoming.value.trim().length > 0;
        ta.required = !has;
        promptLabel.textContent = has ? promptLabel.dataset.withIncoming : promptLabel.dataset.plain;
      };
      incoming.addEventListener("input", sync);
      sync();
    }
    ta.dispatchEvent(new Event("input"));
    (config.examples || []).forEach(ex => {
      const text = typeof ex === "string" ? ex : ex.text;
      const b = el("button", "", "Try: " + (text.length > 42 ? text.slice(0, 42) + "…" : text));
      b.type = "button";
      b.title = text;
      b.addEventListener("click", () => {
        if (file) { file.value = ""; syncFile(); }
        if (incoming) { incoming.value = (typeof ex === "object" && ex.incoming) || ""; incoming.dispatchEvent(new Event("input")); }
        ta.value = text;
        if (prefs) prefs.value = (typeof ex === "object" && ex.preferences) || "";
        ta.dispatchEvent(new Event("input"));
        ta.focus();
      });
      examples.append(b);
    });
    [ta, prefs, incoming].forEach(box => box && box.addEventListener("keydown", ev => {
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); form.requestSubmit(); }
    }));
    form.addEventListener("submit", ev => {
      ev.preventDefault();
      const f = file && file.files[0];
      if (f) {
        const bad = fileNote.textContent.startsWith("Only") || fileNote.textContent.startsWith("That file is too large");
        if (bad) { file.focus(); return; }
        const fd = new FormData();
        fd.append("file", f);
        fd.append("department", config.department);
        send("/api/requests/upload/", {form: fd});
        return;
      }
      const body = {department: config.department, statement: ta.value};
      if (config.tone && tone) body.options = {tone: tone.value};
      if (incoming && incoming.value.trim()) body.options.incoming = incoming.value;
      if (prefs) body.options = {preferences: prefs.value};
      send("/api/requests/", {json: body});
    });
    loadHistory(show);
    const GREETING = {
      briefing: "Morning Docket. Hand over the pile. I will tell you which three things deserve to ruin your morning.",
      pending: "Bureau of Pending Affairs. Tell me everything. I will decide what you may ignore.",
      correspondence: "Correspondence Avoidance. Tell me what you need to say. I will say it for you.",
      documents: "Commission for Unnecessarily Complicated Documents. Hand it over. I will read it. Eventually.",
      tribunal: "The Tribunal is in session. Small problems only. Please stand, or do not. I will not notice.",
    };
    setTimeout(() => mascot.say(GREETING[config.department] || "Welcome."), 600);
  }

  /* ---------- case permalink page ---------- */
  async function initCase() {
    const out = $("#out"), number = out.dataset.case;
    async function load(url, opts) {
      try {
        const res = await fetch(url, opts);
        const data = await res.json();
        if (data.case) renderCase(out, data.case, data.notice, hooks);
        else out.replaceChildren(el("div", "sheet error", data.error || "Case not found."));
      } catch (e) { out.replaceChildren(el("div", "sheet error", "The server could not be reached.")); }
    }
    const hooks = {
      retry: n => {
        out.replaceChildren(el("div", "sheet", "Sending back for review…"));
        load("/api/cases/" + encodeURIComponent(n) + "/retry/", {method: "POST", headers: {"X-CSRFToken": csrfToken()}});
      },
      carry: async n => {
        out.replaceChildren(el("div", "sheet", "Filing the unfinished tasks as a new case. This can take a little while."));
        try {
          const res = await post("/api/cases/" + encodeURIComponent(n) + "/carry-over/");
          const data = await res.json().catch(() => ({}));
          if (data.case && data.case.number) { window.location.href = "/files/" + encodeURIComponent(data.case.number) + "/"; return; }
          out.replaceChildren(el("div", "sheet error", data.error || "Something went wrong."));
        } catch (e) { out.replaceChildren(el("div", "sheet error", "The server could not be reached.")); }
      },
      shred: async n => {
        try {
          const res = await post("/api/cases/" + encodeURIComponent(n) + "/shred/");
          if (!res.ok) throw new Error();
          out.replaceChildren(el("div", "sheet", "Case " + n + " has been shredded. This page will now be unable to find it, as intended."));
        } catch (e) { out.replaceChildren(el("div", "sheet error", "The shredder jammed. The case was not deleted.")); }
      },
    };
    load("/api/cases/" + encodeURIComponent(number) + "/");
  }

  /* ---------- boot ---------- */
  const page = document.body.dataset.page;
  if (page === "department" && $("#page-config")) initDepartment();
  else if (page === "case") initCase();
  else if (page === "home") {
    loadHistory(null);
    setTimeout(() => mascot.say("Welcome to the Department. Take a seat. I will be with you in a while."), 600);
  } else if (page === "files") loadHistory(null);
  else if (page === "department") setTimeout(() => mascot.say("This office is closed. I was told to say it is temporary."), 600);
})();
