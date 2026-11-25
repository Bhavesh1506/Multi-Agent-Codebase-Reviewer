"use strict";
const $ = (id) => document.getElementById(id);
const canvas = $("map"),
  ctx = canvas.getContext("2d");
const roles = {
  scope_analyst: ["Scope analyst", "#1a7169", "Diff dock"],
  contract_auditor: ["Contract auditor", "#815085", "Watchtower"],
  concurrency_guard: ["Concurrency guard", "#a6532c", "Watchtower"],
  test_gap_finder: ["Test gap finder", "#466ca3", "Test sanctuary"],
  critic_synthesizer: ["Critic", "#83681f", "Verdict beacon"],
};
const agents = Object.keys(roles);
function demo() {
  const events = [];
  const files = [
    "api/orders.py",
    "ingestion/symbols.py",
    "agents/guard.py",
    "tests/test_orders.py",
  ];
  function emit(event, status, agent = "", path = "", extra = {}) {
    const seq = events.length + 1;
    events.push({
      event,
      status,
      agent,
      path,
      island: path.split("/")[0] || "Demo repo",
      repo: "Demo repo",
      seq,
      run_id: "demo",
      timestamp: new Date(1700000000000 + seq * 1050).toISOString(),
      ...extra,
    });
  }
  emit("run_started", "running");
  files.forEach((p, i) =>
    emit("stage_changed", "touched", "", p, {
      symbols: [
        ["submit_order", "lookup"],
        ["map_symbols"],
        ["check_lock"],
        ["test_checkout"],
      ][i],
    }),
  );
  const flags = [];
  agents.slice(0, 4).forEach((a, i) => {
    const p = files[[1, 0, 2, 3][i]];
    emit("agent_moved", "analyzing", a, p, { paths: [p] });
    emit("agent_step", "analyzing", a, p, { step: 1 });
    if (i === 2) {
      emit("stage_changed", "retrying", a, p, { detail: "Model timeout" });
    }
    emit("agent_step", "completed", a, p, {
      step: 1,
      prompt_tokens: 160 + i * 15,
      completion_tokens: 40 + i * 5,
      latency_seconds: 0.24 + i * 0.16,
    });
    if (i === 1 || i === 2) {
      const f = {
        title: i === 1 ? "Response field renamed" : "Possible lock gap",
        line: i === 1 ? 18 : 32,
        confidence: i === 1 ? 0.91 : 0.58,
        severity: i === 1 ? "high" : "medium",
        explanation:
          i === 1
            ? "Existing clients still read the original field."
            : "The lock may be released before the update.",
        evidence: [
          i === 1
            ? "The response now uses order_ref."
            : "The update occurs after the lock block.",
        ],
        finding_id: a + "/0",
      };
      flags.push([a, p, f]);
      emit("finding_raised", "flagged", a, p, f);
    }
    emit("stage_changed", "completed", a, p);
  });
  emit("agent_moved", "analyzing", agents[4]);
  const [a, p, f] = flags[1];
  emit("finding_filtered", "filtered", a, p, {
    ...f,
    reviewer: agents[4],
    detail: "Below confidence threshold",
  });
  const [keptAgent, keptPath, keptFinding] = flags[0];
  emit("finding_kept", "kept", keptAgent, keptPath, {
    ...keptFinding,
    reviewer: agents[4],
    detail:
      "On a changed line, meets the confidence threshold, and includes evidence.",
  });
  emit("stage_changed", "completed", agents[4]);
  emit("run_completed", "completed", "", "", { findings: 1 });
  return events;
}
let source = "demo",
  run = "",
  events = [],
  pos = 0,
  cursor = 0,
  revision = 0,
  due = 0,
  paused = false;
let selection = "hub",
  stage = "Ready",
  repo = "",
  islands,
  villagers,
  markers,
  hitboxes = [];
function clearState() {
  pos = 0;
  stage = "Ready";
  repo = "";
  islands = new Map();
  villagers = new Map(
    agents.map((a) => [a, { status: "idle", island: null, steps: new Map() }]),
  );
  markers = new Map();
}
function reset(data = []) {
  events = data;
  due = 0;
  selection = "hub";
  clearState();
  renderPanel();
}
function apply(e) {
  repo = e.repo;
  if (e.path && !islands.has(e.island)) {
    islands.set(e.island, { status: "Touched" });
  }
  const villager = villagers.get(e.agent);
  if (e.event === "agent_moved" && villager) {
    villager.status = "analyzing";
    villager.island = e.path ? e.island : null;
    if (e.path) islands.get(e.island).status = "In review";
  }
  if (e.event === "stage_changed" && villager) {
    villager.status = e.status;
  }
  if (e.event === "agent_step" && villager) {
    villager.steps.set(e.step, e);
    if (e.status === "analyzing") villager.status = e.status;
  }
  if (e.event === "finding_raised") {
    markers.set(e.finding_id, e);
    if (villager) {
      villager.status = "flagged";
      villager.island = e.island;
    }
  }
  if (e.event === "finding_filtered" || e.event === "finding_kept") {
    markers.set(e.finding_id, { ...markers.get(e.finding_id), ...e });
    if (e.event === "finding_filtered" && villager)
      villager.status = "filtered";
  }
  if (e.event.startsWith("run_")) stage = e.status;
}
function pausePlayback(value) {
  paused = value;
  $("pause").textContent = paused ? "Resume" : "Pause";
}
function seek(index) {
  pausePlayback(true);
  const target = Math.max(0, Math.min(events.length, index));
  if (target < pos) {
    clearState();
    // Reconstructed characters start at their historical positions.
    snapPositions = true;
  }
  while (pos < target) apply(events[pos++]);
  renderPanel();
}
let snapPositions = false;

function usageText(steps) {
  const completed = steps.filter((e) => Number.isFinite(e.latency_seconds));
  if (!completed.length) return "Usage unavailable";
  const tokens = completed.filter(
    (e) =>
      Number.isFinite(e.prompt_tokens) && Number.isFinite(e.completion_tokens),
  );
  const total = tokens.reduce(
    (sum, e) => sum + e.prompt_tokens + e.completion_tokens,
    0,
  );
  const seconds = completed.reduce((sum, e) => sum + e.latency_seconds, 0);
  return (
    (tokens.length
      ? total.toLocaleString() + " tokens"
      : "Tokens unavailable") +
    " · " +
    seconds.toFixed(2) +
    " s"
  );
}
function updateReadouts() {
  $("timeline").max = events.length;
  $("timeline").value = pos;
  $("back").disabled = pos === 0;
  $("next").disabled = pos === events.length;
  $("progress").textContent = pos + " / " + events.length + " events";
  const current = events[pos - 1];
  $("metrics").textContent =
    current && Number.isFinite(current.total_tokens)
      ? current.total_tokens.toLocaleString() +
        " tokens · " +
        current.latency_seconds.toFixed(2) +
        " s wall time"
      : usageText(
          Array.from(villagers.values()).flatMap((v) =>
            Array.from(v.steps.values()),
          ),
        );
}
function el(tag, text) {
  const n = document.createElement(tag);
  n.textContent = text;
  return n;
}
function findingLabel(e) {
  if (e.status === "filtered") return "× Filtered";
  if (e.status === "kept") return "◆ Kept";
  return "◇ Raised";
}
function choose(key) {
  selection = key;
  renderPanel();
}
function renderPanel() {
  const select = $("entity");
  select.replaceChildren();
  function option(key, name) {
    select.add(new Option(name, key));
  }
  option("hub", "Verdict beacon");
  for (const a of agents) option("a:" + a, roles[a][0]);
  for (const i of islands.keys()) option("i:" + i, i);
  for (const [id, finding] of markers) option("f:" + id, finding.title);
  if (![...select.options].some((item) => item.value === selection))
    selection = "hub";
  select.value = selection;
  const log = events.slice(0, pos);
  const key = selection.slice(2);
  const land = selection.startsWith("i:");
  const agent = selection.startsWith("a:");
  const finding = selection.startsWith("f:") ? markers.get(key) : null;
  const relevant = (e) => {
    if (finding) return e.finding_id === key;
    if (land) return e.island === key && e.path;
    if (agent) return e.agent === key || e.reviewer === key;
    return true;
  };
  const details = $("details");
  const activeFinding = document.activeElement?.dataset.finding;
  details.replaceChildren();
  function list(title, values) {
    details.append(el("h3", title));
    const ul = el("ul", "");
    for (const value of values.length ? values : ["None yet"]) {
      const li = el("li", "");
      li.append(value);
      ul.append(li);
    }
    details.append(ul);
  }
  const relatedFindings = Array.from(markers.values()).filter(relevant);
  if (agent) {
    const v = villagers.get(key);
    details.append(el("p", roles[key][2] + " · " + v.status));
    details.append(el("p", v.island || "Verdict beacon"));
    list(
      "Agent steps",
      Array.from(v.steps.values()).map(
        (e) => "Step " + e.step + " · " + e.status + " · " + usageText([e]),
      ),
    );
  } else if (land) {
    const pending = relatedFindings.filter(
      (e) => e.status === "flagged",
    ).length;
    const kept = relatedFindings.filter((e) => e.status === "kept").length;
    const filtered = relatedFindings.filter(
      (e) => e.status === "filtered",
    ).length;
    const concluded = ["completed", "degraded", "failed"].includes(stage);
    details.append(
      el(
        "p",
        key + " · " + (concluded ? "Run " + stage : islands.get(key).status),
      ),
    );
    details.append(
      el(
        "p",
        kept + " kept · " + pending + " raised · " + filtered + " filtered",
      ),
    );
    if (kept || pending) {
      const order = ["low", "medium", "high", "critical"];
      const highest = Math.max(
        ...relatedFindings
          .filter((e) => e.status !== "filtered")
          .map((e) => order.indexOf(e.severity)),
      );
      details.append(
        el(
          "p",
          "Highest reported severity · " + (order[highest] || "Unavailable"),
        ),
      );
    }
  } else if (!finding) {
    details.append(el("p", (repo || "Verdict beacon") + " · " + stage));
  }
  if (finding) {
    details.append(el("h3", finding.title));
    list("Finding details", [
      "File · " + finding.path,
      "Line · " + (finding.line ?? "Unavailable"),
      "Confidence · " +
        (Number.isFinite(finding.confidence)
          ? (finding.confidence * 100).toFixed(1).replace(/\.0$/, "") + "%"
          : "Unavailable"),
      "Severity · " + (finding.severity ?? "Not reported"),
      "Decision · " + findingLabel(finding),
    ]);
    const reason =
      finding.detail ||
      (finding.status === "flagged"
        ? "The specialist raised this finding. This event has no critic decision."
        : "This recording has no decision reason.");
    details.append(el("h3", "Critic’s reasoning"), el("p", reason));
    if (finding.explanation)
      details.append(
        el("h3", "Specialist’s explanation"),
        el("p", finding.explanation),
      );
    list(
      "Evidence",
      Array.isArray(finding.evidence) ? finding.evidence.map(String) : [],
    );
  } else {
    const paths = new Set();
    for (const e of log.filter(relevant)) {
      if (e.path) paths.add(e.path);
      if (agent) for (const p of e.paths || []) paths.add(p);
    }
    list("Touched files", Array.from(paths));
    list(
      "Changed symbols",
      Array.from(
        new Set(
          log.filter((e) => paths.has(e.path)).flatMap((e) => e.symbols || []),
        ),
      ),
    );
    list(
      "Findings",
      relatedFindings.map((e) => {
        const button = el("button", findingLabel(e) + " · " + e.title);
        button.className = "finding-link";
        button.dataset.finding = e.finding_id;
        button.onclick = () => {
          choose("f:" + e.finding_id);
          $("entity").focus();
        };
        return button;
      }),
    );
    if (activeFinding)
      Array.from(details.querySelectorAll(".finding-link"))
        .find((button) => button.dataset.finding === activeFinding)
        ?.focus();
  }
  list(
    "Recent events",
    log
      .filter(relevant)
      .slice(-8)
      .reverse()
      .map(
        (e) =>
          e.timestamp.slice(11, 19) +
          " · " +
          (e.agent ? roles[e.agent]?.[0] || e.agent : e.event) +
          " · " +
          e.status +
          (e.detail ? " · " + e.detail : ""),
      ),
  );
  $("crew").replaceChildren();
  for (const [a, v] of villagers) {
    const b = el("button", roles[a][0]);
    b.style.setProperty("--color", roles[a][1]);
    b.append(
      el("small", v.status),
      el("small", usageText(Array.from(v.steps.values()))),
    );
    b.onclick = () => choose("a:" + a);
    $("crew").append(b);
  }
  updateReadouts();
  $("status").textContent =
    (source === "demo" ? "Demo" : source === "file" ? "Recording" : "Live") +
    " · " +
    stage;
}
function shape(points, fill, stroke) {
  ctx.beginPath();
  points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.stroke();
  }
}
function label(value, x, y, size = 12, color = "#25473e") {
  ctx.font = size + "px system-ui";
  ctx.textAlign = "center";
  ctx.fillStyle = color;
  ctx.fillText(value, x, y);
}
function frame(now) {
  if (!paused && pos < events.length && now >= due) {
    const e = events[pos++];
    apply(e);
    renderPanel();
    const next = events[pos];
    const gap = next
      ? Date.parse(next.timestamp) - Date.parse(e.timestamp)
      : 450;
    due =
      now +
      Math.max(380, Math.min(1800, gap || 380)) / Number($("speed").value);
  }
  const width = Math.max(340, canvas.parentElement.clientWidth),
    cols = Math.max(1, Math.floor(width / 220));
  const height = 150 + Math.max(1, Math.ceil(islands.size / cols)) * 155;
  const dpr = window.devicePixelRatio || 1;
  if (
    canvas.width !== Math.round(width * dpr) ||
    canvas.height !== Math.round(height * dpr)
  ) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#cce7e3";
  ctx.fillRect(0, 0, width, height);
  for (let y = 16; y < height; y += 32)
    for (let x = y % 64; x < width; x += 60) {
      ctx.strokeStyle = "#b3d5cc";
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.quadraticCurveTo(x + 4, y + 3, x + 10, y);
      ctx.stroke();
    }
  const hub = { x: width / 2, y: 65 };
  const coords = new Map();
  hitboxes = [];
  function land(x, y, name, hubLand, active, filtered) {
    ctx.save();
    ctx.translate(x, y);
    const rim = [
      [-89, -4],
      [-69, -28],
      [-32, -36],
      [16, -33],
      [48, -25],
      [80, -16],
      [87, 4],
      [61, 24],
      [17, 31],
      [-42, 28],
      [-78, 15],
    ];
    shape(
      rim.map(([u, v]) => [u, v + 6]),
      "#80b8aa",
    );
    shape(
      rim,
      "#e2c997",
      selection === (hubLand ? "hub" : "i:" + name) ? "#386e66" : null,
    );
    shape(
      rim.map(([u, v]) => [u * 0.91, v * 0.83 - 2]),
      hubLand ? "#9ebca0" : active ? "#dbc48b" : "#a9c78d",
    );
    if (hubLand) {
      shape(
        [
          [-6, 0],
          [-3, -19],
          [3, -19],
          [6, 0],
        ],
        "#f0e2bc",
      );
      ctx.fillStyle = "#e49a42";
      ctx.fillRect(-4, -23, 8, 5);
    } else {
      // Dock, watchtower and sanctuary occupy distinct posts on each island.
      ctx.fillStyle = "#785e43";
      ctx.fillRect(-66, -2, 23, 5);
      for (let n = 0; n < 4; n++) ctx.fillRect(-66 + 6 * n, 2, 2, 5);
      ctx.fillStyle = "#808578";
      ctx.fillRect(-10, -17, 12, 15);
      shape(
        [
          [-13, -17],
          [-4, -26],
          [6, -17],
        ],
        "#855b42",
      );
      ctx.fillStyle = "#fff4cf";
      ctx.fillRect(34, -12, 11, 12);
      shape(
        [
          [31, -12],
          [40, -19],
          [48, -12],
        ],
        "#5b8069",
      );
      shape(
        [
          [38, -3],
          [45, -18],
          [51, -3],
        ],
        "#58896e",
      );
      if (active) label("◆ " + active, 60, -14, 13, "#a63d31");
      if (filtered) label("× " + filtered, -50, -17, 13, "#4b5753");
    }
    label(name.length > 24 ? name.slice(0, 22) + "…" : name, 0, 51, 14);
    ctx.restore();
    hitboxes.push({ x, y, w: 96, h: 52, key: hubLand ? "hub" : "i:" + name });
  }
  land(hub.x, hub.y, "Verdict beacon", true, 0, 0);
  let i = 0;
  for (const name of islands.keys()) {
    const x = (((i % cols) + 0.5) * width) / cols,
      y = 195 + Math.floor(i / cols) * 155;
    i++;
    coords.set(name, { x, y });
    const marks = Array.from(markers.values()).filter((m) => m.island === name);
    land(
      x,
      y,
      name,
      false,
      marks.filter((m) => m.status !== "filtered").length,
      marks.filter((m) => m.status === "filtered").length,
    );
    const visible = marks.slice(-5);
    visible.forEach((finding, index) => {
      const pinX = x + (index - (visible.length - 1) / 2) * 31;
      const pinY = y + 69;
      const filtered = finding.status === "filtered";
      ctx.fillStyle =
        selection === "f:" + finding.finding_id ? "#fcf3cf" : "#f7faf4";
      ctx.fillRect(pinX - 15, pinY - 13, 30, 17);
      label(
        (filtered ? "×" : "◆") + (finding.line ?? "?"),
        pinX,
        pinY,
        10,
        filtered ? "#526963" : "#8b392c",
      );
      hitboxes.push({
        x: pinX,
        y: pinY - 5,
        w: 15,
        h: 9,
        key: "f:" + finding.finding_id,
      });
    });
  }
  agents.forEach((a, idx) => {
    const v = villagers.get(a),
      dest = coords.get(v.island) || hub,
      dx =
        dest.x + (dest === hub ? (idx - 2) * 23 : [-50, -16, 7, 40, 62][idx]),
      dy = dest.y + 10;
    if (snapPositions) {
      v.x = dx;
      v.y = dy;
    }
    v.x ??= hub.x + (idx - 2) * 23;
    v.y ??= hub.y + 10;
    const walking = Math.hypot(dx - v.x, dy - v.y) > 2;
    v.x += (dx - v.x) * 0.13;
    v.y += (dy - v.y) * 0.13;
    const x = Math.round(v.x),
      y = Math.round(v.y) + (walking ? Math.round(Math.sin(now / 60) * 2) : 0);
    ctx.fillStyle = "#314b45";
    ctx.fillRect(x - 4, y + 1, 3, 5);
    ctx.fillRect(x + 1, y + 1, 3, 5);
    ctx.fillStyle = roles[a][1];
    ctx.fillRect(x - 6, y - 7, 12, 10);
    ctx.fillStyle = "#f4cb9e";
    ctx.fillRect(x - 4, y - 13, 8, 7);
    shape(
      [
        [x - 7, y - 12],
        [x, y - 21],
        [x + 7, y - 12],
      ],
      roles[a][1],
    );
    if (selection === "a:" + a) {
      ctx.strokeStyle = "#304e40";
      ctx.strokeRect(x - 10, y - 24, 20, 33);
    }
    if (["retrying", "degraded", "filtered", "flagged"].includes(v.status))
      label(
        { retrying: "↻", degraded: "!", filtered: "×", flagged: "◆" }[v.status],
        x,
        y - 24,
        14,
        "#923d27",
      );
    hitboxes.push({ x, y: y - 7, w: 11, h: 16, key: "a:" + a });
  });
  snapPositions = false;
  requestAnimationFrame(frame);
}
canvas.onclick = (e) => {
  const r = canvas.getBoundingClientRect(),
    x = e.clientX - r.left,
    y = e.clientY - r.top;
  const hit = hitboxes
    .slice()
    .reverse()
    .find((b) => Math.abs(b.x - x) < b.w && Math.abs(b.y - y) < b.h);
  if (hit) choose(hit.key);
};
$("entity").onchange = (e) => choose(e.target.value);
$("speed").onchange = () => {
  due = 0;
};
$("pause").onclick = () => {
  paused = !paused;
  $("pause").textContent = paused ? "Resume" : "Pause";
};
$("timeline").oninput = (e) => seek(Number(e.target.value));
$("back").onclick = () => seek(pos - 1);
$("next").onclick = () => seek(pos + 1);
$("restart").onclick = () => {
  paused = false;
  $("pause").textContent = "Pause";
  reset(events);
};
function switchRun(id) {
  revision++;
  run = id;
  cursor = 0;
  reset();
}
$("source").onchange = () => {
  source = $("source").value;
  switchRun("");
  paused = false;
  $("pause").textContent = "Pause";
  $("file").hidden = source !== "file";
  $("runs").hidden = source !== "live";
  if (source === "demo") reset(demo());
  if (source === "live") {
    followLatest = true;
    poll();
  }
};
$("runs").onchange = () => {
  followLatest = !$("runs").value;
  switchRun($("runs").value);
  poll();
};
$("file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const version = ++revision;
  try {
    const data = (await file.text())
      .trim()
      .split(/\r?\n/)
      .map((line) => JSON.parse(line));
    if (
      !data.every(
        (e) =>
          e &&
          typeof e.event === "string" &&
          typeof e.timestamp === "string" &&
          typeof e.path === "string" &&
          typeof e.island === "string" &&
          e.run_id === data[0].run_id &&
          (!e.symbols || Array.isArray(e.symbols)) &&
          (!e.paths || Array.isArray(e.paths)),
      )
    )
      throw Error("Invalid recording");
    if (version === revision) reset(data);
  } catch {
    if (version === revision)
      $("status").textContent = "Could not read this JSONL run";
  }
};
let polling = false,
  followLatest = true;
async function get(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw Error(r.status);
  return r.json();
}
async function poll() {
  if (source !== "live" || polling) return;
  polling = true;
  const version = revision;
  try {
    const ids = await get("/islands-data/runs");
    if (version !== revision) return;
    $("runs").replaceChildren(
      new Option("Latest run", ""),
      ...ids.map((id) => new Option(id.slice(0, 8), id)),
    );
    if (!ids.length) {
      $("status").textContent = "Waiting for a recorded run";
      return;
    }
    if (!ids.includes(run) || (followLatest && ids[0] !== run)) {
      run = ids[0];
      cursor = 0;
      reset();
    }
    $("runs").value = followLatest ? "" : run;
    const data = await get("/islands-data/runs/" + run + "?cursor=" + cursor);
    if (version !== revision) return;
    cursor = data.cursor;
    events.push(...data.events);
    updateReadouts();
  } catch {
    if (version === revision)
      $("status").textContent = "Journal unavailable · reconnecting";
  } finally {
    polling = false;
  }
}
reset(demo());
setInterval(poll, 850);
requestAnimationFrame(frame);
