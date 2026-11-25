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
    if (i === 2)
      emit("stage_changed", "retrying", a, p, { detail: "Model timeout" });
    if (i === 1 || i === 2) {
      const f = {
        title: i === 1 ? "Response field renamed" : "Possible lock gap",
        line: i === 1 ? 18 : 32,
        confidence: i === 1 ? 0.91 : 0.58,
        finding_id: a + "/0",
      };
      flags.push([a, p, f]);
      emit("finding_raised", "flagged", a, p, f);
    }
    emit("stage_changed", "completed", a, p);
  });
  emit("agent_moved", "analyzing", agents[4]);
  const [a, p, f] = flags[1];
  emit("finding_filtered", "filtered", a, p, { ...f, reviewer: agents[4] });
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
function reset(data = []) {
  events = data;
  pos = 0;
  due = 0;
  selection = "hub";
  stage = "Ready";
  repo = "";
  islands = new Map();
  villagers = new Map(agents.map((a) => [a, { status: "idle", island: null }]));
  markers = new Map();
  renderPanel();
}
function apply(e) {
  repo = e.repo;
  if (e.path && !islands.has(e.island))
    islands.set(e.island, { files: new Set(), symbols: new Set() });
  if (e.path) {
    const land = islands.get(e.island);
    land.files.add(e.path);
    for (const s of e.symbols || []) land.symbols.add(s);
  }
  const who = e.reviewer || e.agent;
  if (villagers.has(who)) {
    const v = villagers.get(who);
    v.status = e.status;
    v.island = e.path ? e.island : null;
  }
  if (e.event === "finding_raised" || e.event === "finding_filtered")
    markers.set(e.finding_id, e);
  if (e.event.startsWith("run_")) stage = e.status;
  renderPanel();
}
function el(tag, text) {
  const n = document.createElement(tag);
  n.textContent = text;
  return n;
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
  option("hub", "Review hub");
  for (const a of agents) option("a:" + a, roles[a][0]);
  for (const i of islands.keys()) option("i:" + i, i);
  select.value = selection;
  const log = events.slice(0, pos);
  const key = selection.slice(2),
    land = selection.startsWith("i:"),
    agent = selection.startsWith("a:");
  const relevant = (e) =>
    land
      ? e.island === key && e.path
      : agent
        ? e.agent === key || e.reviewer === key
        : true;
  const details = $("details");
  details.replaceChildren();
  function list(title, values) {
    details.append(el("h3", title));
    const ul = el("ul", "");
    for (const value of values.length ? values : ["None yet"])
      ul.append(el("li", value));
    details.append(ul);
  }
  if (agent)
    details.append(el("p", roles[key][2] + " · " + villagers.get(key).status));
  if (!land && !agent)
    details.append(el("p", (repo || "Review hub") + " · " + stage));
  const paths = new Set();
  for (const e of log.filter(relevant)) {
    if (e.path) paths.add(e.path);
    if (agent) for (const p of e.paths || []) paths.add(p);
  }
  list("Touched files", Array.from(paths));
  const symbols = new Set(
    log.filter((e) => paths.has(e.path)).flatMap((e) => e.symbols || []),
  );
  list("Changed symbols", Array.from(symbols));
  list(
    "Findings",
    Array.from(markers.values())
      .filter(relevant)
      .map(
        (e) =>
          (e.status === "filtered" ? "× Filtered" : "◆ Raised") +
          " · " +
          e.title +
          " · " +
          e.path +
          ":" +
          e.line +
          " · " +
          e.confidence +
          (e.detail ? " · " + e.detail : "") +
          (e.explanation ? " — " + e.explanation : ""),
      ),
  );
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
    b.append(el("small", v.status));
    b.onclick = () => choose("a:" + a);
    $("crew").append(b);
  }
  $("progress").textContent = pos + " / " + events.length + " events";
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
    const latest = marks[marks.length - 1];
    if (latest) {
      const filtered = latest.status === "filtered";
      const title = String(latest.title);
      label(
        (filtered ? "× " : "◆ ") +
          (title.length > 20 ? title.slice(0, 18) + "…" : title) +
          " · L" +
          (latest.line ?? "?"),
        x,
        y + 68,
        11,
        filtered ? "#526963" : "#8b392c",
      );
    }
  }
  agents.forEach((a, idx) => {
    const v = villagers.get(a),
      dest = coords.get(v.island) || hub,
      dx =
        dest.x + (dest === hub ? (idx - 2) * 23 : [-50, -16, 7, 40, 62][idx]),
      dy = dest.y + 10;
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
