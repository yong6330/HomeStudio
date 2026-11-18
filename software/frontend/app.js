// HomeStudio mobile UI. Screens are the Google Stitch export ported 1:1 (views/*.html, Tailwind compiled to app.css).
// This file only routes, fetches the API and fills the Stitch markup (data-k / data-tpl hooks). No build step, no CDN.
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(2, "0");
const num = (n) => Math.round(n || 0).toLocaleString("ko-KR");

async function api(path, opt = {}) {
  const r = await fetch(path, { credentials: "same-origin", signal: (!opt.method || opt.method === "GET") && S.controller ? S.controller.signal : undefined, ...opt, headers: opt.body ? { "Content-Type": "application/json" } : {} });
  let j = null;
  try { j = await r.json(); } catch (e) { if (e.name === "AbortError") throw e; /* empty body */ }
  if (!r.ok) { const e = new Error("HTTP " + r.status); e.status = r.status; e.data = j; throw e; }
  return j;
}
const post = (p, b) => api(p, { method: "POST", body: JSON.stringify(b || {}) });
const del = (p) => api(p, { method: "DELETE" });

// ---------- time (KST) ----------
const KST = 9 * 3600e3;
const kst = (d) => new Date((d ? new Date(d) : new Date()).getTime() + KST); // read with getUTC*
const hhmm = (d) => { const k = kst(d); return pad(k.getUTCHours()) + ":" + pad(k.getUTCMinutes()); };
const hhmmss = (d) => { const k = kst(d); return hhmm(d) + ":" + pad(k.getUTCSeconds()); };
const DOW = "일월화수목금토";
const iso = (k) => k.toISOString().slice(0, 10);
const addDays = (s, n) => iso(new Date(Date.parse(s + "T00:00:00Z") + n * 864e5));
const careStart = () => (S.state && S.state.pet && S.state.pet.care_day_start) || "12:00";
const careHours = () => { const [h, m] = careStart().split(":").map(Number); return h + m / 60; };
const careToday = () => iso(new Date(kst().getTime() - careHours() * 3600e3));
const dateLabel = (s) => { const d = new Date(s + "T00:00:00Z"); return `${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일 (${DOW[d.getUTCDay()]})`; };
const shortLabel = (s) => { const d = new Date(s + "T00:00:00Z"); return `${pad(d.getUTCMonth() + 1)}.${pad(d.getUTCDate())} ${DOW[d.getUTCDay()]}`; };
const ampm = (t) => { const h = +t.split(":")[0]; return h === 12 ? `낮 ${t}` : h < 12 ? `오전 ${t}` : `오후 ${t}`; };
const IFACE = { wired: "유선", wifi: "Wi-Fi", manual: "수동 지정", unbound: "미등록", unknown: "네트워크" };
const careCycle = () => `${careStart()} ~ 익일 ${careStart()}`;
const ago = (d) => { if (!d) return "기록 없음"; const s = Math.max(0, (Date.now() - new Date(d)) / 1e3); return s < 60 ? `${Math.round(s)}초 전` : s < 3600 ? `${Math.round(s / 60)}분 전` : s < 86400 ? `${Math.round(s / 3600)}시간 전` : `${Math.round(s / 86400)}일 전`; };
const dur = (sec) => {
  const total = Math.max(0, Math.round(Number(sec) || 0));
  const minutes = Math.floor(total / 60), seconds = total % 60;
  return minutes ? `${minutes}분${seconds ? ` ${seconds}초` : ""}` : `${seconds}초`;
};
const gb = (b) => (b / 1e9).toFixed(1) + " GB";
const daypart = (h) => h < 6 ? "새벽" : h < 12 ? "오전" : h < 18 ? "낮" : h < 22 ? "저녁" : "밤";
const isNight = (h) => h >= 18 || h < 6;
const eventLighting = (e) => {
  const stored = e.capture_daypart === "day" || e.capture_daypart === "night";
  const night = stored ? e.capture_daypart === "night" : isNight(kst(e.started_at).getUTCHours());
  const source = e.capture_daypart_source || "legacy_timestamp";
  return { night, label: `${night ? "야간" : "주간"} · ${source === "capture_time" ? "저장된 시각 기준" : "기록 시각 기준"}` };
};

// ---------- camera state ----------
const CAM = {
  online: { label: "정상 수집 중", short: "연결 완료", state: "정상 가동", sub: "감지·저장 동작 중", icon: "wifi", dot: "bg-primary", text: "text-primary" },
  privacy: { label: "프라이버시 모드", short: "프라이버시", state: "프라이버시 모드", sub: "감지·저장 일시정지", icon: "lock", dot: "bg-tertiary", text: "text-tertiary" },
  dark: { label: "화면 어두움", short: "화면 어두움", state: "화면 어두움", sub: "밝기 부족 감지", icon: "dark_mode", dot: "bg-tertiary", text: "text-tertiary" },
  offline: { label: "연결 지연", short: "신호 없음", state: "연결 끊김", sub: "스냅샷 수신 지연", icon: "warning", dot: "bg-error", text: "text-error" },
};
function camState(st) {
  const age = st.camera_last_seen ? (Date.now() - new Date(st.camera_last_seen)) / 1e3 : Infinity;
  let mode = st.camera_status in CAM ? st.camera_status : "offline";
  if (mode !== "privacy" && age > 120) mode = "offline"; // service stopped / stale heartbeat
  return { mode, age, ...CAM[mode] };
}
function animalStateLine(st, lastEventEnd) {
  const camera = camState(st);
  if (camera.mode === "offline") return "카메라 연결을 기다리고 있어요";
  if (camera.mode === "privacy") return "프라이버시 모드가 켜져 있어요";
  if (camera.mode === "dark") return "화면이 어두워 모습을 확인하기 어려워요";
  const seenAt = st.activity_seen_at ? Date.parse(st.activity_seen_at) : NaN;
  const fresh = Number.isFinite(seenAt) && Date.now() >= seenAt && Date.now() - seenAt < 45e3;
  if (fresh && st.activity_state === "active") return "지금 활발히 움직이고 있어요";
  if (fresh && st.activity_state === "idle") {
    const eventAt = lastEventEnd ? Date.parse(lastEventEnd) : NaN;
    if (Number.isFinite(eventAt) && Date.now() >= eventAt && Date.now() - eventAt < 10 * 60e3)
      return `잠시 조용해졌어요 · 최근 ${hhmm(lastEventEnd)}에 움직임이 기록됐어요`;
    return "지금은 조용한 시간이에요 · 움직임을 살펴보고 있어요";
  }
  return "지금 모습을 확인하고 있어요";
}
function snapshotIsFresh(st) {
  const seenAt = st.snapshot_seen_at ? Date.parse(st.snapshot_seen_at) : NaN;
  return Number.isFinite(seenAt) && Date.now() >= seenAt && Date.now() - seenAt < 45e3;
}

// ---------- Stitch markup hooks ----------
function bind(data, root = document) {
  for (const el of $$("[data-k]", root)) if (el.dataset.k in data) el.textContent = data[el.dataset.k];
  for (const el of $$("[data-html]", root)) if (el.dataset.html in data) el.innerHTML = data[el.dataset.html];
  for (const el of $$("[data-show]", root)) if (el.dataset.show in data) el.classList.toggle("hidden", !data[el.dataset.show]);
  for (const el of $$("[data-cls]", root)) if (el.dataset.cls in data) el.classList.add(...data[el.dataset.cls].split(" "));
}
// zones (P4 prep): normalized polygons; colors per kind reuse theme tokens
const ZK = { cage: ["케이지", "#e3e2e7", "bg-outline"], wheel: ["쳇바퀴", "#5af0b3", "bg-primary"], food: ["먹이 그릇", "#ffcf96", "bg-tertiary"], water: ["물병", "#cbc6bd", "bg-secondary"],
  hide: ["은신처", "#ffa929", "bg-tertiary-container"], toilet: ["화장실", "#d4c4a8", "bg-tertiary"], custom: ["직접 입력", "#ffb4ab", "bg-error"] };
const inPoly = (x, y, pts) => { let hit = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const [xi, yi] = pts[i], [xj, yj] = pts[j]; if ((yi > y) !== (yj > y) && x < xi + ((y - yi) * (xj - xi)) / (yj - yi)) hit = !hit; } return hit; };
function fill(name, items, each) {
  const t = $(`[data-tpl="${name}"]`);
  if (!t) return;
  for (const it of items) { const n = t.cloneNode(true); n.removeAttribute("data-tpl"); each(n, it); t.before(n); }
  t.remove();
}
const show = (id, on = true) => { const el = document.getElementById(id); if (el) el.classList.toggle("hidden", !on); };
const swap = (el, off, on, cond) => { el.classList.remove(...(cond ? off : on).split(" ")); el.classList.add(...(cond ? on : off).split(" ")); };
function err(id, msg) { show(id, !!msg); const p = $(`#${id} [data-k]`); if (p) p.textContent = msg || ""; }

// 행동 건강 (stereotypy hints): values + baseline wording
const behVal = (it) => it.key === "wheel_sec" ? dur(it.today) : `${it.today}번`;
const OBS_LABEL = { movement_candidate: "이동 후보", wheel_motion_candidate: "쳇바퀴 구역 동작 후보", repeated_path_candidate: "반복 경로 후보" };
const OBS_QUALITY = { global_light_change: "조명 변화", multiple_motion_regions: "여러 움직임 겹침", large_motion_region: "넓은 영역 움직임",
  no_cage_roi: "케이지 영역 미설정", empty_cage_roi: "케이지 영역 확인 필요", insufficient_frames: "확인 가능한 영상이 적음",
  decode_timeout: "영상 처리 지연", decode_failed: "영상 일부 확인 실패", memory_limit: "영상 분석 자원 제한",
  memory_measurement_unavailable: "분석 상태 확인 제한", original_missing_preview_used: "저장 영상으로 확인", source_file_missing: "영상 파일을 찾지 못함" };
const obsTime = (seconds) => { const s = Math.max(0, Math.floor(Number(seconds) || 0)); return `${pad(Math.floor(s / 60))}:${pad(s % 60)}`; };
function observationRows(result, limit = Infinity) {
  const items = Array.isArray(result?.items) ? result.items : (Array.isArray(result?.intervals) ? [result] : []);
  return items.flatMap((item, itemIndex) => (item.intervals || []).map((interval) => ({
    event_id: item.event_id, status: item.status, label: OBS_LABEL[interval.label] || "관찰 구간",
    state: interval.state === "candidate" ? "후보" : "확인하기 어려운 구간",
    time: `${obsTime(interval.start_sec)}–${obsTime(interval.end_sec)}`,
    start_sec: Number(interval.start_sec) || 0, end_sec: Number(interval.end_sec) || 0,
    recency: itemIndex,
    source_time_quality: item.source_time_quality,
    source_label: item.source === "preview" ? "재생용 영상 구간" : "원본 영상 구간",
    quality: [...new Set((item.quality_reasons || []).map((reason) => OBS_QUALITY[reason] || "일부 장면 확인에 제한"))].join(" · ")
  }))).sort((a, b) => (b.end_sec - b.start_sec) - (a.end_sec - a.start_sec) || a.recency - b.recency || b.start_sec - a.start_sec).slice(0, limit);
}
function observationSummary(result, count) {
  const items = Array.isArray(result?.items) ? result.items : (Array.isArray(result?.intervals) ? [result] : []);
  const all = items.flatMap((item) => item.intervals || []);
  const candidates = all.filter((interval) => interval.state === "candidate").length;
  const unknown = all.filter((interval) => interval.state !== "candidate").length;
  const parts = [];
  if (candidates) parts.push(`살펴볼 후보 ${candidates}개`);
  if (unknown) parts.push(`확인이 어려운 구간 ${unknown}개`);
  if (!parts.length) parts.push(`살펴볼 구간 ${count}개`);
  if (Number.isFinite(result?.analyzed_clips)) parts.push(`분석 영상 ${result.analyzed_clips}개`);
  if (Number.isFinite(result?.analyzed_sec)) parts.push(`분석한 구간 ${dur(result.analyzed_sec)}`);
  return parts.join(" · ");
}
function behSub(it, beh) {
  if (beh.status === "learning" || beh.status === "rebuilding") return "비교 준비 중";
  if (beh.status !== "ready") return beh.status === "low_coverage" ? "수집 범위 부족" : beh.status === "early" ? "시간대 비교 대기" : "평소 비교 보류";
  if (it.median == null || !["high", "usual"].includes(it.flag)) return "평소 비교 기준이 부족해 관찰만 기록해요";
  return `평소 ${it.key === "wheel_sec" ? dur(it.median) : it.median + "번"}${it.flag === "high" ? " · 평소보다 많아요" : " · 평소 범위예요"}`;
}
function behLine(beh, date = beh.date || careToday()) {
  if (beh.status !== "ready") { const q = baselineText(beh, dur, { date, live: date === careToday() }); return { beh_title: q.title, beh_text: q.text }; }
  const hi = beh.items.filter((i) => i.flag === "high" && i.median != null && !i.ref_only);
  if (!hi.length && beh.items.some((i) => !i.ref_only && (i.median == null || !["high", "usual"].includes(i.flag)))) return { beh_title: "오늘 행동을 관찰해 기록했어요", beh_text: "평소 비교 기준이 부족한 항목은 비교를 쉬어요." };
  return hi.length ? { beh_title: `${hi.map((i) => i.label).join("·")} 평소보다 많아요`, beh_text: "환경(케이지·은신처·놀이감)을 한번 살펴봐 주세요." }
    : { beh_title: "반복 행동 평소와 비슷해요", beh_text: `쳇바퀴 구역 체류 ${dur(beh.items[0].today)} · 같은 길 왕복 ${beh.items[1].today}번` };
}
function zoneMapBins(tracks, width, height, columns = 16, rows = 9) {
  const bins = new Map();
  for (const item of tracks || []) for (const point of Array.isArray(item?.track) ? item.track : []) {
    if (!Array.isArray(point) || point.length < 3) continue;
    const [t, x, y] = point;
    if (![t, x, y].every((n) => typeof n === "number" && Number.isFinite(n)) || x < 0 || y < 0 || x >= width || y >= height) continue;
    const col = Math.min(columns - 1, Math.floor(x / width * columns)), row = Math.min(rows - 1, Math.floor(y / height * rows));
    const key = `${col}:${row}`, bin = bins.get(key) || { x: (col + .5) * width / columns, y: (row + .5) * height / rows, count: 0 };
    bin.count++; bins.set(key, bin);
  }
  return [...bins.values()];
}
function zoneMapBinRadius(width, height) {
  return Math.min(width / 16, height / 9) * .25;
}
function zoneMapSegments(track, width, height, maxGap = 2.5, maxJump = Math.hypot(width, height) * .18) {
  const segments = []; let points = [], previous = null;
  const flush = () => { if (points.length) segments.push({ points }); points = []; };
  for (const sample of Array.isArray(track) ? track : []) {
    if (!Array.isArray(sample) || sample.length < 3) { flush(); previous = null; continue; }
    const [t, x, y] = sample;
    const valid = [t, x, y].every((n) => typeof n === "number" && Number.isFinite(n)) && x >= 0 && y >= 0 && x < width && y < height;
    if (!valid) { flush(); previous = null; continue; }
    if (previous && (t <= previous.t || t - previous.t > maxGap || Math.hypot(x - previous.x, y - previous.y) > maxJump)) flush();
    points.push({ t: Number(t), x: Number(x), y: Number(y) }); previous = { t: Number(t), x: Number(x), y: Number(y) };
  }
  flush(); return segments;
}
function zoneMapLabelX(center, text, fontSize, width, padding) {
  const halfWidth = Math.min(width / 2, String(text).length * fontSize / 2);
  return Math.max(halfWidth + padding, Math.min(width - halfWidth - padding, center));
}
function zoneMapLabelFont(height, frameWidth, renderedWidth) {
  const base = height / 27, scale = renderedWidth > 0 ? renderedWidth / frameWidth : 0;
  return Math.max(base, scale > 0 ? 10 / scale : base);
}
function renderZoneMap(map, zoneShapes, tracks, width, height, home = false) {
  if (!map) return;
  const root = map.closest(home ? ".hs-home-zones" : ".hs-report-zone-card") || map.parentElement;
  const zoneLayer = $(`[data-map-zones]`, map), densityLayer = $(`[data-map-density]`, map), trackLayer = $(`[data-map-tracks]`, map), labelLayer = $(`[data-map-labels]`, map);
  const mode = $(`[data-map-mode]`, root), clipWrap = $(`[data-map-clip-wrap]`, root), clip = $(`[data-map-clip]`, root);
  if (!zoneLayer || !densityLayer || !trackLayer || !labelLayer) return;
  const w = Number.isFinite(+width) && +width > 0 ? +width : 160, h = Number.isFinite(+height) && +height > 0 ? +height : 90;
  map.setAttribute("viewBox", `0 0 ${w} ${h}`);
  const ns = "http://www.w3.org/2000/svg", svg = (tag, attrs) => { const el = document.createElementNS(ns, tag); for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value)); return el; };
  zoneLayer.replaceChildren(); densityLayer.replaceChildren(); trackLayer.replaceChildren(); labelLayer.replaceChildren();
  for (const zone of zoneShapes || []) {
    if (!Array.isArray(zone.points) || zone.points.length < 3 || zone.points.some((p) => !Array.isArray(p) || !Number.isFinite(+p[0]) || !Number.isFinite(+p[1]) || +p[0] < 0 || +p[0] > 1 || +p[1] < 0 || +p[1] > 1)) continue;
    const cage = zone.kind === "cage";
    const points = zone.points.map(([x, y]) => `${(+x * w).toFixed(1)},${(+y * h).toFixed(1)}`).join(" ");
    zoneLayer.append(svg("polygon", { points, fill: "none", stroke: cage ? "#8c8c91" : "#aaa69f", "stroke-opacity": cage ? ".32" : ".48", "stroke-width": cage ? w / 520 : w / 360 }));
    if (!cage) {
      const center = zone.points.reduce((a, p) => [a[0] + +p[0] / zone.points.length, a[1] + +p[1] / zone.points.length], [0, 0]);
      const labelText = zone.name || "구역", fontSize = zoneMapLabelFont(h, w, map.clientWidth);
      const labelX = zoneMapLabelX(center[0] * w, labelText, fontSize, w, h / 45);
      const label = svg("text", { x: labelX, y: center[1] * h, "text-anchor": "middle", fill: "#f0ede7", "font-size": fontSize, stroke: "#121317", "stroke-width": h / 90, "paint-order": "stroke" });
      label.textContent = labelText; labelLayer.append(label);
    }
  }
  const paint = () => {
    densityLayer.replaceChildren(); trackLayer.replaceChildren();
    const pathMode = mode?.value === "path";
    if (clipWrap) clipWrap.classList.toggle("hidden", !pathMode);
    if (!pathMode) {
      for (const bin of zoneMapBins(tracks, w, h)) {
        const radius = zoneMapBinRadius(w, h);
        densityLayer.append(svg("circle", { cx: bin.x, cy: bin.y, r: radius, fill: "#ffcf96", "fill-opacity": Math.min(.72, .28 + Math.log2(bin.count + 1) * .12) }));
      }
      return;
    }
    const index = Math.max(0, Math.min((tracks || []).length - 1, Number(clip?.value) || 0)), item = tracks?.[index];
    if (!item) return;
    const segments = zoneMapSegments(item.track, w, h);
    for (const segment of segments) {
      const points = segment.points;
      if (points.length > 1) trackLayer.append(svg("polyline", { points: points.map((p) => `${p.x},${p.y}`).join(" "), fill: "none", stroke: "#5af0b3", "stroke-width": Math.max(.7, h / 130), "stroke-linecap": "round", "stroke-linejoin": "round" }));
    }
    const allPoints = segments.flatMap((segment) => segment.points);
    if (allPoints.length) {
      trackLayer.append(svg("circle", { cx: allPoints[0].x, cy: allPoints[0].y, r: h / 45, fill: "#ffcf96", stroke: "#121317", "stroke-width": h / 100 }));
      trackLayer.append(svg("circle", { cx: allPoints.at(-1).x, cy: allPoints.at(-1).y, r: h / 45, fill: "#5af0b3", stroke: "#121317", "stroke-width": h / 100 }));
    }
  };
  if (clip) {
    clip.replaceChildren();
    (tracks || []).forEach((item, index) => { const option = document.createElement("option"); option.value = String(index); option.textContent = `${item.started_at ? hhmm(item.started_at) : "시각 미상"} · 클립 ${index + 1}`; clip.append(option); });
    clip.disabled = !tracks?.length;
  }
  if (mode) mode.onchange = paint;
  if (clip) clip.onchange = paint;
  paint();
}
// ---------- views ----------
const S = { state: null, cache: {}, live: [] };
const UI = "261015base1";
const TIMELINE_RETURN = "hs_timeline_return";
const isOwner = () => { const u = S.state && S.state.user; return !!u && (u.space_role === "owner" || (!u.space_role && u.role === "admin")); };
const canManage = () => { const u = S.state && S.state.user; return !!u && (u.space_role === "owner" || u.space_role === "subadmin" || (!u.space_role && u.role === "admin")); };
const canDeleteEvents = () => !!(S.state && S.state.user);
const ROLE_KO = { owner: "대표 관리자", subadmin: "부관리자", member: "가족" };
async function mount(name, signal) {
  if (!S.cache[name]) S.cache[name] = await (await fetch(`views/${name}.html?v=${UI}`, { signal })).text();
  if (signal.aborted) return;
  const html = S.cache[name];
  const m = html.match(/<!--body class="([^"]*)"-->/);
  document.body.className = m ? m[1] : "";
  document.body.innerHTML = html;
  scrollTo(0, 0);
}
const go = (h) => { if (location.hash === h) route(); else location.hash = h; };
function openSession(id, date, kind = "timeline") {
  let origin;
  try { origin = JSON.parse(sessionStorage.getItem(TIMELINE_RETURN)); } catch (_) { /* stale session state */ }
  const currentId = decodeURIComponent((location.hash.split("/")[1] || "").split("?")[0]);
  if (!location.hash.startsWith("#session/") || !origin || origin.eventId !== currentId)
    origin = { kind, date, scrollY };
  const target = "#session/" + encodeURIComponent(id);
  sessionStorage.setItem(TIMELINE_RETURN, JSON.stringify({ ...origin, eventId: id }));
  if (location.hash.startsWith("#session/")) { history.replaceState(null, "", target); route(); }
  else go(target);
}
function restoreOriginPosition(kind, date) {
  let origin;
  try { origin = JSON.parse(sessionStorage.getItem(TIMELINE_RETURN)); } catch (_) { /* stale session state */ }
  if (origin?.kind === kind && origin.date === date) { sessionStorage.removeItem(TIMELINE_RETURN); scrollTo(0, origin.scrollY); }
}

function TimelineCalendar(selectedDate, signal) {
  const dialog = $("#calendar-dialog"), monthLabel = $("#calendar-month"), daysRoot = $("#calendar-days"), message = $("#calendar-message");
  let [year, month] = selectedDate.split("-").map(Number);
  let recorded = new Set(), loaded = false, loading = false;
  const today = careToday();
  const monthId = () => `${year}-${pad(month)}`;
  const render = () => {
    if (!dialog || !daysRoot) return;
    monthLabel.textContent = `${year}년 ${month}월`;
    const first = new Date(`${monthId()}-01T00:00:00Z`), offset = first.getUTCDay();
    const count = new Date(Date.UTC(year, month, 0)).getUTCDate();
    daysRoot.replaceChildren();
    const cells = Math.ceil((offset + count) / 7) * 7;
    let row;
    for (let i = 0; i < cells; i++) {
      if (i % 7 === 0) { row = document.createElement("div"); row.className = "hs-calendar-weekrow"; row.setAttribute("role", "row"); daysRoot.append(row); }
      const day = i - offset + 1;
      if (day < 1 || day > count) { const blank = document.createElement("span"); blank.setAttribute("role", "gridcell"); blank.setAttribute("aria-hidden", "true"); row.append(blank); continue; }
      const value = `${monthId()}-${pad(day)}`, button = document.createElement("button");
      button.type = "button"; button.className = "hs-calendar-day"; button.dataset.date = value; button.setAttribute("role", "gridcell"); button.textContent = String(day);
      button.setAttribute("aria-label", `${dateLabel(value)}${recorded.has(value) ? ", 기록 있음" : ""}`);
      button.setAttribute("aria-pressed", value === selectedDate ? "true" : "false");
      if (recorded.has(value)) button.classList.add("has-events");
      if (value > today || !loaded || loading) button.disabled = true;
      button.onclick = () => { if (value <= today && loaded && !loading) { dialog.close(); go(`#timeline/${value}`); } };
      row.append(button);
    }
    $("#calendar-next").disabled = monthId() >= today.slice(0, 7);
    $("#calendar-prev").disabled = loading;
  };
  const fetchDates = async () => {
    if (loading) return;
    loading = true; loaded = false; recorded = new Set(); message.textContent = "기록 날짜를 불러오는 중이에요."; $("#calendar-retry").classList.add("hidden"); render();
    try {
      const result = await api("/api/events/dates?care=1", { signal });
      if (signal.aborted || !dialog.isConnected) return;
      recorded = new Set((Array.isArray(result?.dates) ? result.dates : []).filter((value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value && value <= today));
      loaded = true;
      message.textContent = recorded.size ? "점으로 표시된 날짜에 활동 기록이 있어요." : "아직 저장된 활동 기록이 없어요.";
      render();
      $$(".hs-calendar-day", daysRoot).find((button) => button.dataset.date === selectedDate)?.focus();
    } catch (error) {
      if (error.name === "AbortError" || signal.aborted) return;
      loaded = false; message.textContent = "기록 날짜를 불러오지 못했어요. 다시 시도해 주세요."; $("#calendar-retry").classList.remove("hidden"); render();
    } finally { loading = false; render(); }
  };
  this.bind = () => {
    if (!dialog) return;
    $("#open-calendar").onclick = () => { [year, month] = selectedDate.split("-").map(Number); dialog.showModal(); fetchDates(); };
    $("#calendar-close").onclick = () => dialog.close();
    $("#calendar-retry").onclick = fetchDates;
    $("#calendar-prev").onclick = () => { if (loading) return; month--; if (month < 1) { month = 12; year--; } render(); };
    $("#calendar-next").onclick = () => { if (loading || monthId() >= today.slice(0, 7)) return; month++; if (month > 12) { month = 1; year++; } render(); };
    $("#calendar-today").onclick = () => { dialog.close(); go(`#timeline/${today}`); };
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); }, { signal });
    dialog.addEventListener("keydown", (event) => {
      const current = event.target.closest?.(".hs-calendar-day");
      if (!current || !loaded || loading) return;
      const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
      if (!delta) return;
      event.preventDefault();
      const next = addDays(current.dataset.date, delta);
      if (next > today) return;
      [year, month] = next.split("-").map(Number);
      render();
      $$(".hs-calendar-day", daysRoot).find((button) => button.dataset.date === next)?.focus();
    }, { signal });
    render();
  };
}

const PUBLIC = ["welcome", "login", "signup", "invite", "forgot", "pin", "start", "join"];
const SETTINGS = ["password", "pinset", "zones", "family"];
const ONBOARD = ["pet", "schedule", "discover", "camconn", "camera", "done"];  // + zones (also a settings screen)
async function route() {
  (S.live || []).forEach(clearInterval); S.live = [];
  if (S.controller) S.controller.abort();
  const controller = S.controller = new AbortController();
  const [name0, arg] = (location.hash.slice(1) || "home").split("/");
  try { S.state = await api("/api/auth/state"); }
  catch (_) { if (controller.signal.aborted) return; S.state = { has_admin: true, user: null }; }
  if (controller.signal.aborted) return;
  const st = S.state, u = st.user;
  let name = name0;
  if (name === "recording-preview") name = "home";
  if (!u) { if (!PUBLIC.includes(name)) name = "welcome"; }
  else if (!u.verified) name = "verify";
  else if (isOwner() && !st.onboarding_done && !ONBOARD.includes(name) && name !== "zones") name = "pet";
  else if (ONBOARD.includes(name) && !["schedule", "done"].includes(name) && st.onboarding_done && (!isOwner() || !["pet", "discover", "camconn", "camera"].includes(name))) name = "home";
  else if (name === "invite" || name === "join") { /* logged in on an invite link: preview + "로그아웃 후 가입" instead of redirecting */ }
  else if (PUBLIC.includes(name) || name === "verify") name = "home";
  if (name !== name0) { history.replaceState(null, "", "#" + name); }
  const view = VIEWS[name] || VIEWS.home;
  try { await mount(name === "invite" ? "signup" : VIEWS[name] ? name : "home", controller.signal); }
  catch (e) { if (controller.signal.aborted) return; throw e; }
  if (controller.signal.aborted) return;
  bell();
  try { await view(arg); } catch (e) {
    if (controller.signal.aborted || e.name === "AbortError") return;
    if (name === "session") $("#player-status").textContent = "기록을 불러오지 못했어요. 타임라인에서 다시 열어 주세요.";
    if (e.status === 401) return go("#login");
    console.error(e);
  }
}

const VIEWS = {
  // ======== account / onboarding ========
  async welcome() {
    $("#btn-login").onclick = () => go("#login");
    $("#btn-signup").onclick = () => go("#start");
    $("#btn-invite").onclick = () => go("#join");
    $("#btn-pin").onclick = () => go("#pin");
  },

  // Stitch "어떻게 시작할까요?": new home (first admin) or join a family home (invite)
  async start() {
    const has = S.state.has_admin;
    let pick = has ? "join" : "create";
    const ON = { card: "group relative w-full p-5 rounded-[20px] bg-surface-container-low cursor-pointer transition-all duration-200 active:scale-[0.99] select-none shadow-sm",
      radio: "w-6 h-6 rounded-full bg-primary flex items-center justify-center text-on-primary transition-colors shrink-0",
      icon: "w-12 h-12 rounded-2xl bg-primary/15 flex items-center justify-center text-primary shrink-0 transition-colors",
      badge: "inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary/10 text-primary font-label-sm text-label-sm font-semibold" };
    const OFF = { card: "group relative w-full p-5 rounded-[20px] bg-surface-container cursor-pointer transition-all duration-200 active:scale-[0.99] select-none shadow-sm opacity-90 hover:opacity-100",
      radio: "w-6 h-6 rounded-full bg-surface-container-highest flex items-center justify-center text-on-surface-variant transition-colors shrink-0",
      icon: "w-12 h-12 rounded-2xl bg-surface-variant flex items-center justify-center text-secondary shrink-0 transition-colors",
      badge: "inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-variant text-secondary font-label-sm text-label-sm font-semibold" };
    const paint = () => {
      for (const [k, id] of [["create", "create-home"], ["join", "join-home"]]) {
        const c = pick === k ? ON : OFF, kk = k;
        $(`#card-${id}`).className = c.card; $(`#radio-${kk}`).className = c.radio; $(`#icon-container-${kk}`).className = c.icon; $(`#badge-${kk}`).className = c.badge;
        $(`#radio-${kk}`).innerHTML = `<span class="material-symbols-outlined text-[16px]${pick === k ? " font-bold" : " hidden"}">check</span>`;
      }
      $("#submit-cta").innerHTML = `<span>${pick === "create" ? "새 홈 만들기 시작" : "가족 홈 참여하기"}</span><span class="material-symbols-outlined text-[20px]">arrow_forward</span>`;
      err("start-error", pick === "create" && has ? "이 HomeStudio에는 이미 홈이 만들어져 있어요. 가족에게 초대 링크를 받아 '가족 홈 참여하기'로 들어와 주세요." : "");
    };
    $$("[data-pick]").forEach((el) => (el.onclick = () => { pick = el.dataset.pick; paint(); }));
    paint();
    $("#submit-cta").onclick = () => { if (pick === "join") go("#join"); else if (!has) go("#signup"); };
  },

  // Stitch "초대 코드를 입력해 주세요": 8 slots, link autofill, live check + home preview, then signup with the code
  async join(code) {
    const inp = $("#invite-code-input"), slots = $("#code-slots");
    const fromLink = !!code;
    bind({ chip: fromLink ? "초대 링크 확인 중" : "초대 코드 입력" });
    const SLOT = "h-12 rounded-lg bg-surface-container-highest flex items-center justify-center font-headline-sm text-headline-sm text-primary";
    const EMPTY = "h-12 rounded-lg bg-surface-container-low flex items-center justify-center font-headline-sm text-headline-sm text-outline-variant";
    const clean = (v) => v.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
    const draw = () => { const v = inp.value; slots.innerHTML = [...Array(8)].map((_, i) => `<div class="${i < v.length ? SLOT : EMPTY}">${i < v.length ? esc(v[i]) : "·"}</div>`).join(""); };
    let ok = null;
    const check = async () => {
      ok = null; show("preview", false); show("code-ok", false); $("#btn-join").disabled = true; err("join-error");
      if (inp.value.length !== 8) return;
      try {
        const p = await post("/api/auth/invite/check", { code: inp.value });
        ok = inp.value;
        const pet = p.pet_name || "반려동물", w = p.weight_g ? `${p.weight_g}g` : "";
        const age = p.birthday ? Math.max(0, Math.floor((Date.now() - Date.parse(p.birthday)) / (30.44 * 864e5))) : null;
        const extra = [w, age !== null ? `${age}개월` : ""].filter(Boolean).join(", ");
        bind({ chip: fromLink ? "초대 링크 확인됨" : "초대 코드 확인됨", home_name: `${pet}의 HomeStudio`,
          pet_line: `${p.species || "햄스터"} · ${pet}${extra ? ` (${extra})` : ""}`, admin: p.admin ? `${p.admin} (관리자)` : "관리자",
          device: p.cameras ? `${p.camera_name || "HomeStudio 카메라"} ${p.cameras}대` : "카메라 미등록",
          note: `참여 즉시 ${pet}의 활동·쳇바퀴 기록과 알림을 함께 볼 수 있어요.` });
        show("preview"); show("code-ok"); $("#btn-join").disabled = false;
      } catch (e) {
        err("join-error", e.status === 429 ? "확인 시도가 너무 많아요. 10분 후 다시 시도해주세요." : "유효하지 않거나 만료된 코드예요. 관리자에게 새 초대 링크를 요청해 주세요.");
      }
    };
    inp.oninput = () => { inp.value = clean(inp.value); draw(); check(); };
    slots.onclick = () => inp.focus();
    $("#btn-paste").onclick = async () => {
      try { const t = await navigator.clipboard.readText(); inp.value = clean(t.split("/").pop()); bind({ paste_label: "붙여넣기 완료" }); draw(); check(); }
      catch (_) { inp.focus(); bind({ code_hint: "길게 눌러 붙여넣기 하세요" }); }
    };
    $("#btn-nocode").onclick = () => { err("join-error", "가족 관리자에게 HomeStudio 상태 화면 > '가족 초대'에서 초대 링크를 만들어 보내 달라고 요청해 주세요."); };
    $("#btn-join").onclick = () => { if (ok) go(`#invite/${ok}`); };
    if (code) inp.value = clean(decodeURIComponent(code));
    draw(); if (inp.value) check(); else inp.focus();
  },

  async login() {
    bind({ now: hhmm() });
    const email = $("#email"), pw = $("#password");
    email.oninput = () => { const ok = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim()); show("email-ok", ok); show("email-ok-icon", ok); };
    pwToggle();
    $("#btn-forgot").onclick = () => go("#forgot");
    $("#btn-pin").onclick = () => go("#pin");
    $("#btn-signup").onclick = () => go(S.state.has_admin ? "#invite" : "#signup");
    $("#login-form").onsubmit = async (ev) => {
      ev.preventDefault();
      try {
        await post("/api/auth/login", { email: email.value, password: pw.value, remember: $("#rememberMe").checked });
        const next = sessionStorage.getItem("hs_after_login");
        sessionStorage.removeItem("hs_after_login");
        if (next) { history.replaceState(null, "", next); }
        route();
      } catch (e) {
        const d = (e.data && e.data.detail) || {};
        const bad = true;
        swap($("#pw-label"), "text-on-surface-variant", "text-error", bad);
        swap($("#pw-lock"), "text-on-surface-variant", "text-error", bad);
        swap(pw, "bg-surface-container focus:bg-surface-container-high", "bg-error-container/40 shadow-[0_0_16px_rgba(147,0,10,0.25)]", bad);
        show("pw-count", !!d.failures);
        $("#pw-count").textContent = d.failures ? `입력 오류 (${d.failures}/5회)` : "";
        show("login-error");
        $('[data-k="login_error"]').textContent = e.status === 429
          ? `로그인 시도가 너무 많아요. ${Math.ceil((d.locked_sec || 900) / 60)}분 후 다시 시도해주세요.`
          : "이메일 또는 비밀번호가 일치하지 않습니다.";
      }
    };
  },

  async signup() { return signupView(false); },
  async invite(code) { return signupView(true, code); },

  async verify() {
    const admin = isOwner();
    bind({ email: S.state.user.email, step: admin ? "2 / 5 단계" : "2 / 2 단계", cta: admin ? "인증 완료 및 다음 (3/5)" : "인증 완료",
      mail_note: S.state.mail_sender === "log" ? "메일 발송이 아직 설정되지 않아, 인증 코드는 HomeStudio 서버 로그에 기록돼요. (관리자 PC에서 확인)" : "스팸 메일함으로 분류되었을 수 있으니 메일함을 확인해주세요." });
    $("#step-bar").style.width = admin ? "40%" : "100%";
    const inp = $("#authCodeInput"), boxes = $("#code-boxes");
    const BOX = {
      full: "w-12 h-14 rounded-2xl bg-surface-container flex items-center justify-center font-headline-lg text-headline-lg text-on-surface shadow-sm",
      active: "w-12 h-14 rounded-2xl bg-surface-container-high flex items-center justify-center shadow-[0_0_16px_rgba(90,240,179,0.2)] relative",
      empty: "w-12 h-14 rounded-2xl bg-surface-container-low flex items-center justify-center text-outline-variant font-headline-lg text-headline-lg",
    };
    const draw = () => {
      const v = inp.value;
      boxes.innerHTML = [0, 1, 2, 3, 4, 5].map((i) => i < v.length ? `<div class="${BOX.full}">${esc(v[i])}</div>`
        : i === v.length ? `<div class="${BOX.active}"><span class="w-0.5 h-6 bg-primary rounded-full animate-pulse"></span></div>`
        : `<div class="${BOX.empty}"><span class="w-2 h-2 rounded-full bg-outline-variant/60"></span></div>`).join("");
    };
    inp.oninput = () => { inp.value = inp.value.replace(/\D/g, "").slice(0, 6); draw(); err("verify-error"); };
    boxes.onclick = () => inp.focus();
    draw(); inp.focus();
    let until = Date.now() + 600e3;
    const tick = () => { const s = Math.max(0, Math.round((until - Date.now()) / 1e3)); const c = $("#timerClock"); if (!c) return clearInterval(S.timer); c.textContent = `${pad(Math.floor(s / 60))}:${pad(s % 60)}`; };
    clearInterval(S.timer); S.timer = setInterval(tick, 1000); tick();
    $("#resendBtn").onclick = async () => { await post("/api/auth/resend"); until = Date.now() + 600e3; tick(); err("verify-error"); };
    $("#btn-change").onclick = async () => { await post("/api/auth/logout"); go("#signup"); };
    $("#submitCta").onclick = async () => {
      try { await post("/api/auth/verify", { code: inp.value }); clearInterval(S.timer); go(admin ? "#pet" : "#home"); }
      catch (_) { err("verify-error", "인증번호가 맞지 않거나 만료됐어요. 다시 확인해주세요."); }
    };
  },

  async forgot() {
    const email = $("#email");
    let step = 1;
    $("#btn-login").onclick = () => go("#login");
    pwRules($("#reset-password"), $("#reset-confirm"));
    $("#reset-form").onsubmit = async (ev) => {
      ev.preventDefault();
      err("reset-error");
      try {
        if (step === 1) {
          await post("/api/auth/forgot", { email: email.value });
          step = 2; show("email-ok"); show("email-ok-icon");
          $$(".reset-step2").forEach((el) => el.classList.remove("hidden"));
          $("#reset-cta").textContent = "비밀번호 재설정";
          err("reset-error", S.state.mail_sender === "log" ? "메일 발송이 아직 설정되지 않아, 코드는 HomeStudio 서버 로그에 기록돼요." : "");
          $("#reset-code").focus();
        } else {
          await post("/api/auth/reset", { email: email.value, code: $("#reset-code").value, password: $("#reset-password").value, password_confirm: $("#reset-confirm").value });
          go("#login");
        }
      } catch (e) {
        err("reset-error", e.status === 422 ? "비밀번호 규칙과 확인 입력을 다시 확인해주세요." : "코드가 맞지 않거나 만료됐어요.");
      }
    };
  },

  async pin() {
    $("#btn-invite").onclick = () => go("#invite");
    $("#btn-forgot").onclick = () => go("#login");
    $("#btn-login").onclick = () => go("#login");
    if (!S.state.pin_available) {
      bind({ pin_sub: "이 기기에 등록된 PIN이 없어요. 아래 '로그인 후 설정'을 누르면 로그인 뒤 바로 PIN 등록 화면으로 이동해요." });
      $("#btn-login").textContent = "로그인 후 설정";
      $("#btn-login").onclick = () => { sessionStorage.setItem("hs_after_login", "#pinset"); go("#login"); };
      return pinPad(null);
    }
    pinPad(async (pin) => {
      try { await post("/api/auth/pin/unlock", { pin }); route(); }
      catch (e) {
        const d = (e.data && e.data.detail) || {};
        if (e.status === 423) { err("pin-error", "PIN을 5회 틀려 이 기기의 간편 잠금이 해제됐어요. 비밀번호로 로그인해주세요."); setTimeout(() => go("#login"), 1800); }
        else err("pin-error", d.failures ? `PIN이 맞지 않아요. (${d.failures}/${d.max}회)` : "비밀번호로 로그인해주세요.");
        return true;
      }
    });
  },

  async pinset() {
    $("#btn-invite").onclick = () => go("#settings");
    $("#btn-forgot").onclick = () => go("#password");
    $("#btn-login").onclick = () => go("#settings");
    const STEP1 = `${S.state.pin_available ? "이 기기: PIN 등록됨 (새 PIN으로 바뀌어요)" : "이 기기: PIN 미등록"}\n1. 현재 비밀번호 입력. 2. 새 PIN 4~6자리 입력 후 확인. 3. 같은 PIN 한 번 더.`;
    bind({ pin_sub: STEP1 });
    let first = null;
    pinPad(async (pin) => {
      if (!$("#pin-password").value) { err("pin-error", "먼저 위 칸에 현재 비밀번호를 입력해주세요."); $("#pin-password").focus(); return true; }
      if (!/^\d{4,6}$/.test(pin)) { err("pin-error", "PIN은 숫자 4~6자리예요. 4자리 이상 누른 뒤 확인을 눌러주세요."); return true; }
      if (!first) { first = pin; bind({ pin_sub: "확인을 위해 같은 PIN을 한 번 더 입력하고 확인을 눌러주세요." }); err("pin-error"); return true; }
      if (pin !== first) { first = null; bind({ pin_sub: STEP1 }); err("pin-error", "두 PIN이 달라요. 다시 입력해주세요."); return true; }
      try { await post("/api/auth/pin", { password: $("#pin-password").value, pin }); S.state.pin_available = true; bind({ pin_sub: "등록 완료! 다음부터 잠금 화면에서 이 PIN으로 열 수 있어요." }); err("pin-error"); setTimeout(() => go("#settings"), 1400); }
      catch (e) { first = null; bind({ pin_sub: STEP1 }); err("pin-error", e.status === 401 ? "현재 비밀번호가 맞지 않아요. 다시 입력해주세요." : e.status === 422 ? "PIN은 숫자 4~6자리예요." : "등록하지 못했어요. 잠시 후 다시 시도해주세요."); return true; }
    }, 6);
  },

  async password() {
    $("#btn-login").onclick = () => go("#settings");
    pwRules($("#reset-password"), $("#reset-confirm"));
    $("#password-form").onsubmit = async (ev) => {
      ev.preventDefault();
      err("reset-error");
      try {
        await post("/api/auth/password", { current: $("#reset-code").value, password: $("#reset-password").value, password_confirm: $("#reset-confirm").value });
        err("reset-error", "비밀번호가 변경됐어요. 다른 기기는 모두 로그아웃됐어요.");
        setTimeout(() => go("#settings"), 1200);
      } catch (e) {
        err("reset-error", e.status === 401 ? "현재 비밀번호가 맞지 않아요." : "비밀번호 규칙과 확인 입력을 다시 확인해주세요.");
      }
    };
  },

  async pet() {
    const p = S.state.pet || {};
    const name = $("#pet-name-input");
    name.value = p.name && p.name !== "hamster" ? p.name : "";
    const ON = "bg-surface-container-high text-primary shadow-sm", OFF = "bg-surface-container text-on-surface-variant active:bg-surface-container-high";
    let species = p.species || "골든 햄스터", sex = p.sex || null;
    const paint = () => {
      for (const c of $$(".species-chip")) {
        const on = c.dataset.species === species;
        c.setAttribute("aria-checked", on); swap(c, OFF, ON, on);
        const ic = c.querySelector(".material-symbols-outlined");
        ic.textContent = on ? "radio_button_checked" : "radio_button_unchecked"; ic.classList.toggle("text-outline", !on);
        const dot = c.querySelector(".animate-pulse");
        if (on && !dot) c.firstElementChild.outerHTML = `<span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>${esc(c.dataset.species)}</span>`;
        if (!on && dot) c.firstElementChild.outerHTML = `<span>${esc(c.dataset.species)}</span>`;
      }
      for (const b of $$(".sex-btn")) swap(b, "text-on-surface-variant", "bg-surface-container-high text-primary shadow-sm", b.dataset.sex === sex);
      const ok = name.value.trim().length > 0;
      show("name-ok", ok); show("name-ok-icon", ok);
    };
    $$(".species-chip").forEach((c) => (c.onclick = () => { species = c.dataset.species; paint(); }));
    $$(".sex-btn").forEach((b) => (b.onclick = () => { sex = b.dataset.sex; paint(); }));
    name.oninput = paint;
    if (p.birthday) $("#pet-date-input").value = p.birthday;
    const avatar = () => { if ((S.state.pet || {}).has_photo) { $("#pet-avatar").src = "/media/pet.jpg?t=" + Date.now(); bind({ photo_label: "사진 변경" }); } };
    avatar();
    $("#btn-photo").onclick = () => $("#pet-photo").click();
    $("#pet-photo").onchange = async (ev) => {
      const f = ev.target.files[0];
      if (!f) return;
      if (f.size > 2 * 1024 * 1024) return err("pet-error", "사진은 2MB 이하 JPG/PNG만 올릴 수 있어요.");
      const r = await fetch("/api/pet/photo", { method: "POST", credentials: "same-origin", headers: { "Content-Type": f.type }, body: f });
      if (!r.ok) return err("pet-error", "사진은 2MB 이하 JPG/PNG만 올릴 수 있어요.");
      err("pet-error"); S.state.pet = { ...(S.state.pet || {}), has_photo: true }; avatar();
    };
    if (p.weight_g) $("#pet-weight-input").value = p.weight_g;
    paint();
    const settings = !!S.state.onboarding_done;
    if (settings) { $("#onb-progress").classList.add("hidden"); bind({ next_label: "저장", next_icon: "check" }); }
    $("#next-step-btn").onclick = async () => {
      if (!name.value.trim()) return err("pet-error", "반려동물 이름을 입력해주세요.");
      try {
        await post("/api/onboarding/pet", { name: name.value.trim(), species, sex, birthday: $("#pet-date-input").value || null, weight_g: parseFloat($("#pet-weight-input").value) || null });
        go(S.state.onboarding_done ? "#settings" : "#schedule");
      } catch (_) { err("pet-error", "입력값을 확인해주세요. (이름 1~10자)"); }
    };
  },

  async schedule() {
    let h = +careStart().split(":")[0];
    const draw = () => {
      $("#time-display-hour").textContent = `${pad(h)}:00`;
      $("#time-period-tag").textContent = h === 12 ? "낮 / 정오" : h === 0 ? "자정" : h < 6 ? "새벽" : h < 12 ? "오전" : h < 18 ? "오후" : "저녁 / 밤";
      $("#time-until").textContent = `다음 날 ${pad((h + 23) % 24)}:59까지 1일로 집계`;
    };
    $("#btn-time-minus").onclick = () => { h = (h + 23) % 24; draw(); };
    $("#btn-time-plus").onclick = () => { h = (h + 1) % 24; draw(); };
    const q = $("#quiet-toggle"), knob = $("#toggle-circle");
    const setQ = (on) => { q.setAttribute("aria-checked", on); swap(q, "bg-surface-variant", "bg-primary", on); swap(knob, "translate-x-0", "translate-x-5", on); };
    q.onclick = () => setQ(q.getAttribute("aria-checked") !== "true");
    try { setQ((await api("/api/settings/quiet")).enabled); } catch (_) { /* default on */ }
    draw();
    if (S.state.onboarding_done) $("#btn-next span").textContent = "저장하고 돌아가기";
    $("#btn-next").onclick = async () => {
      try { await post("/api/onboarding/schedule", { care_day_start: `${pad(h)}:00` }); await post("/api/settings/quiet", { enabled: q.getAttribute("aria-checked") === "true" }); go(S.state.onboarding_done ? "#settings" : "#discover"); }
      catch (_) { err("schedule-error", "관리자만 변경할 수 있어요."); }
    };
  },

  async camera() {
    const st = await api("/api/status"), c = camState(st);
    $("#cam-img").src = "/media/latest.jpg?t=" + Date.now();
    bind({ cam_badge: c.mode === "privacy" ? "PRIVACY · 렌즈 수납" : c.mode === "online" ? "LIVE · 스냅샷" : c.label,
      cam_spec: `${st.snapshot_fps}fps · ${st.stream_source}`,
      cam_status: { online: "카메라 연결됨 (정상 작동 중)", privacy: "카메라 연결됨 (프라이버시 모드)", dark: "카메라 연결됨 (화면 어두움)" }[c.mode] || "카메라 연결 없음 (서비스 확인 필요)",
      cam_detail: `마지막 수집 ${ago(st.camera_last_seen)} · TVS-W1000` });
    $("#btn-test-angle").onclick = () => open("/media/latest.jpg", "_blank");
    // find the camera on the LAN (WS-Discovery + ARP), verify the model, and bind it by MAC (keeps existing interface labels)
    $("#btn-retry").onclick = () => go("#discover");
    $("#btn-complete").onclick = async () => { await post("/api/onboarding/complete"); go("#done"); };
  },

  // Stitch "네트워크에서 카메라를 찾고 있어요": scan all PC subnets, user picks one camera (no auto-pick)
  async discover() {
    const onb = !S.state.onboarding_done;
    bind({ step: onb ? "새로운 홈 생성 (5/5단계)" : "카메라 다시 찾기" });
    const list = $("#cam-list"), tplA = $('[data-tpl="cam"]'), tplB = $('[data-tpl="camreg"]');
    tplA.remove(); tplB.remove();
    let sel = null, open = true;
    const btn = $("#confirmConnectionBtn");
    $("#btn-help").onclick = () => { open = !open; show("helpDetails", open); $("#helpChevron").style.transform = open ? "rotate(0deg)" : "rotate(-90deg)"; };
    const NET = { wired: ["lan", "유선 LAN 연결됨"], wifi: ["network_wifi", "Wi-Fi 연결됨"], unknown: ["lan", "같은 네트워크"] };
    const scan = async () => {
      sel = null; btn.disabled = true; err("discover-error");
      $$("[data-cam]", list).forEach((n) => n.remove());
      show("radar"); bind({ title: "네트워크에서 카메라를 찾고 있어요", scan: "유선 · Wi-Fi 스캔 중...", found: "", scope: "로컬 탐색 활성화됨" });
      $("#btn-rescan").disabled = true;
      let r;
      try { r = await post("/api/camera/discover"); }
      catch (e) { r = { candidates: [], error: e.status }; }
      $("#btn-rescan").disabled = false;
      const cs = r.candidates.sort((a, b) => a.registered - b.registered);
      bind({ title: cs.length ? "카메라를 찾았어요" : "카메라를 찾지 못했어요", scan: `스캔 완료 (${(r.prefixes || []).map((p) => p + ".x").join(", ") || "-"})`, found: `· ${cs.length}대 발견` });
      for (const c of cs) {
        const n = (c.registered ? tplB : tplA).cloneNode(true);
        n.removeAttribute("data-tpl"); n.dataset.cam = c.ip;
        const [ic, label] = NET[c.iface] || NET.unknown;
        bind({ model: c.model, tag: "신규 감지", addr: `IP ${c.ip}${c.mac ? ` · MAC ${c.mac.toUpperCase().replace(/-/g, ":")}` : ""}`, net_icon: ic, net: label }, n);
        const radio = $("[data-radio]", n);
        radio.className = "w-6 h-6 rounded-full bg-surface-container-high flex items-center justify-center text-outline";
        radio.innerHTML = '<span class="w-2.5 h-2.5 rounded-full bg-surface-variant"></span>';
        n.onclick = () => {
          sel = c; btn.disabled = false;
          bind({ cta: c.registered ? "이 카메라로 다시 연결하기" : "이 카메라 연결하기" });
          for (const o of $$("[data-cam]", list)) {
            const on = o === n, rd = $("[data-radio]", o);
            rd.className = on ? "w-6 h-6 rounded-full bg-primary flex items-center justify-center text-on-primary shadow-sm" : "w-6 h-6 rounded-full bg-surface-container-high flex items-center justify-center text-outline";
            rd.innerHTML = on ? '<span class="material-symbols-outlined text-[16px] font-bold">check</span>' : '<span class="w-2.5 h-2.5 rounded-full bg-surface-variant"></span>';
          }
        };
        list.append(n);
      }
      show("auth-tip", true);
      if (r.auth_error) {
        bind({ auth_title: "카메라 계정 확인이 필요해요", auth_text: "응답한 카메라가 HomeStudio 계정 로그인을 거절했어요. 카메라 관리자 페이지에서 <strong>grok 계정</strong>과 비밀번호를 확인해 주세요. 잠금 방지를 위해 1분 이상 기다린 뒤 다시 찾아요." });
        err("discover-error", "카메라 계정 확인이 필요해요.");
      } else if (r.error === 403) err("discover-error", "관리자만 카메라를 연결할 수 있어요.");
      else if (!cs.length) { open = true; show("helpDetails"); err("discover-error", "카메라를 찾지 못했어요. 아래 체크리스트를 확인하고 다시 찾아 주세요."); }
      if (cs.length === 1) $("[data-cam]", list).click();
    };
    $("#btn-rescan").onclick = scan;
    btn.onclick = async () => {
      if (!sel) return;
      btn.disabled = true;
      btn.innerHTML = '<span class="material-symbols-outlined text-[20px] animate-spin">hourglass_empty</span><span>카메라 확인 중...</span>';
      try {
        await post("/api/camera/bind", { macs: [{ mac: sel.mac, iface: sel.iface === "unknown" ? "unknown" : sel.iface }], model: sel.model });
        go("#camconn");
      } catch (e) {
        btn.innerHTML = '<span data-k="cta">이 카메라 연결하기</span><span class="material-symbols-outlined text-[20px]">arrow_forward</span>'; btn.disabled = false;
        err("discover-error", e.status === 422 ? "이 기기의 MAC 주소를 읽지 못했어요. 다시 찾아 주세요." : "카메라 연결을 확인하지 못했어요. 계정과 네트워크를 확인하고 다시 시도해 주세요.");
      }
    };
    scan();
  },

  // Stitch "카메라가 정상적으로 연결되었어요!": snapshot preview, camera name, connection facts
  async camconn() {
    const [st, info] = await Promise.all([api("/api/status"), api("/api/camera/info")]);
    const c = camState(st), h = kst().getUTCHours();
    $("#cam-img").src = "/media/latest.jpg?t=" + Date.now();
    $("#cam-img").onerror = () => { $("#cam-img").removeAttribute("src"); };
    bind({ badge: c.mode === "offline" ? "연결됨 · 첫 화면 기다리는 중" : "실시간 연결 성공", live: `LIVE · 스냅샷 ${st.snapshot_fps}fps`,
      dp_icon: isNight(h) ? "nightlight" : "wb_sunny", daypart: isNight(h) ? "야간 · 시각 기준" : "주간 · 시각 기준",
      net_icon: info.camera_iface === "wifi" ? "wifi" : "lan", net_short: IFACE[info.camera_iface] || "네트워크", cam_label: c.mode === "offline" ? "화면 수신 대기 중" : c.label,
      net: { wired: "유선 LAN", wifi: "Wi-Fi", manual: "수동 지정" }[info.camera_iface] || "확인 중", ip: info.camera_ip || "-",
      fw: info.firmware || "확인 불가" });
    const name = $("#camera-name-input");
    name.value = info.name || `${(S.state.pet && S.state.pet.name) || "우리 집"} 케이지`;
    $("#btn-clear-name").onclick = () => { name.value = ""; name.focus(); };
    $("#btn-expand-preview").onclick = () => open("/media/latest.jpg", "_blank");
    $("#btn-next-step").onclick = async () => {
      try { await post("/api/camera/name", { name: name.value.trim() }); }
      catch (_) { return err("camconn-error", "카메라 이름은 1~20자로 입력해 주세요."); }
      go("#zones");
    };
  },

  async done() {
    const p = S.state.pet || {};
    const [st, members] = await Promise.all([api("/api/status"), api("/api/members")]);
    bind({ pet_name: p.name || "", pet_detail: p.name ? `(${p.species || "반려동물"}${p.weight_g ? `, ${p.weight_g}g` : ""})` : "", care_cycle: `${ampm(careStart())} ~ 익일 ${careStart()}`,
      cam_short: camState(st).short, family: `가족 ${members.length}명 참여 중` });
    $("#btn-home").onclick = () => go("#home");
    $("#btn-sensors").onclick = () => go("#sensors");
  },

  // ======== dashboard ========
  async home(arg) {
    const routeController = S.controller || new AbortController();
    const date = arg || careToday(), today = date === careToday();
    document.body.classList.add("hs-data-loading");
    const q = (p, d = date) => api(`/api/${p}?date=${d}&care=1`);
    let sum, prev, hours, bl, st, evs, zst, daily, zoneShapes;
    try { [sum, prev, hours, bl, st, evs, zst, daily, zoneShapes] = await Promise.all([q("summary"), q("summary", addDays(date, -1)), q("hourly"), api(`/api/baseline?date=${date}`), api("/api/status"), q("events"), api(`/api/zones/stats?date=${date}&care=1`), api(`/api/reports/daily?date=${date}`).catch((error) => { if (error.name === "AbortError") throw error; return { zones: [], tracks: [] }; }), api("/api/zones")]); }
    catch (error) {
      if (routeController.signal.aborted) return;
      const loader = $(`[data-view-loading="home"]`);
      if (loader) { loader.hidden = false; loader.innerHTML = `<span role="status">홈 기록을 불러오지 못했어요.</span><button type="button" class="hs-calendar-retry" data-view-retry>다시 시도</button>`; loader.querySelector("[data-view-retry]").onclick = () => route(); }
      return;
    }
    if (routeController.signal.aborted) return;
    const loader = $(`[data-view-loading="home"]`);
    const zname = Object.fromEntries(zst.zones.map((z) => [z.id, z.name])), wheel = zst.zones.find((z) => z.kind === "wheel");
    const c = camState(st), p = S.state.pet || {};
    $(".hs-home-columns").classList.toggle("hs-home-historical", !today);
    const reportLink = $(`[data-report-link]`);
    if (reportLink) reportLink.href = today ? "#report" : `#report/${date}`;
    $('[data-day="1"]').disabled = date >= careToday();
    const nowH = +kst().getUTCHours(), last = evs[evs.length - 1];
    const min = (s) => (s < 600 ? Math.round(s / 6) / 10 : Math.round(s / 60));
    const dm = Math.round((sum.active_sec - prev.active_sec) / 60);
    const cmpv = baselineText(bl, min, { date, live: today }), lvl = cmpv.lvl;
    bind({
      pet_name: p.name || "", date_label: dateLabel(date), report_title: today ? "최근 하루 보고서" : `${dateLabel(date)} 하루 보고서`, report_teaser: today ? "지난 돌봄 하루의 활동과 영상을 살펴봐요." : `${dateLabel(date)} 기록 · 활동 ${sum.session_count}회 · ${dur(sum.active_sec)} 움직임`, is_today: today, care_cycle: careCycle(),
      mode_now: { online: "수집 정상", privacy: "프라이버시", dark: "화면 어두움", offline: "연결 지연" }[c.mode] || c.label,
      lag_label: c.mode === "offline" && isFinite(c.age) ? `지연 ${Math.max(1, Math.round(c.age / 60))}분` : "연결 지연",
      moment_title: last ? `${hhmm(last.started_at)}에 움직였어요` : today ? "아직 오늘 활동 기록이 없어요" : "이 날은 활동 기록이 없어요",
      moment_tag: last ? "최근 기록" : "기록 없음",
      moment_text: last ? `${(last.zones || []).length ? last.zones.map((z) => zname[z]).join("·") + " 구역에서 " : ""}${dur(last.duration_sec)} 동안 ${num(last.distance_px)}px 이동했어요. ${today ? "오늘" : "이 날"} ${sum.session_count}번째 활동 구간이에요.` : "움직임이 감지되면 여기에서 요약해 드릴게요.",
      active_min: min(sum.active_sec), delta: `${dm >= 0 ? "+" : ""}${dm}분 (어제)`, delta_icon: dm === 0 ? "remove" : "arrow_upward",
      delta_cls: "text-on-surface-variant",
      sessions: sum.session_count, clips: wheel ? `${wheel.name} ${wheel.visits}회 · ${dur(wheel.dwell_sec)}` : `클립 ${evs.filter((e) => e.clip_path).length}개`, distance: num(sum.distance_px), level: lvl,
      cmp_title: cmpv.title, cmp_text: cmpv.text,
      chart_sub: `${careStart()}부터 익일 ${careStart()} 기준 집계`,
    });
    const comparison = $("#home-comparison");
    show("home-comparison", true);
    if (comparison) comparison.classList.toggle("hs-home-baseline-pending", bl.status !== "ready");
    if (today) {
      let baselineLoading = false;
      S.live.push(setInterval(async () => {
        if (document.hidden || baselineLoading || routeController.signal.aborted) return;
        if (careToday() !== date) { route(); return; }
        baselineLoading = true;
        try {
          const latest = await api(`/api/baseline?date=${date}`, { signal: routeController.signal });
          if (routeController.signal.aborted) return;
          const summary = baselineText(latest, min, { date, live: true });
          bind({ level: summary.lvl, cmp_title: summary.title, cmp_text: summary.text });
          if (comparison) comparison.classList.toggle("hs-home-baseline-pending", latest.status !== "ready");
        } catch (error) { if (error.name === "AbortError") return; }
        finally { baselineLoading = false; }
      }, 60000));
    }
    const homeZones = daily.zones || [], homeTracks = daily.tracks || [];
    const homeMap = $("#home-zone-map"), frameW = daily.frame_size?.width || 160, frameH = daily.frame_size?.height || 90;
    renderZoneMap(homeMap, zoneShapes, homeTracks, frameW, frameH, true);
    const homeMaxDwell = Math.max(1, ...homeZones.map((z) => +z.dwell_sec || 0));
    fill("home-zone", homeZones, (node, zone) => { node.querySelector("[data-home-zone-bar]").style.width = `${Math.max(0, (+zone.dwell_sec || 0) / homeMaxDwell * 100)}%`; bind({ home_zone_name: zone.name || "구역", home_zone_dwell: dur(zone.dwell_sec || 0) }, node); });
    $('[data-k="delta_icon"]').classList.add("hidden");
    $('[data-k="delta"]').textContent = `${dm >= 0 ? "+" : ""}${dm}분 · 어제와 비교`;
    const recent = evs.slice(-3).reverse();
    bind({ records_empty: !recent.length });
    $('[data-records-all]').href = "#timeline/" + date;
    fill("recent-record", recent, (n, e) => {
      n.href = "#session/" + encodeURIComponent(e.event_id);
      bind({ record_time: hhmm(e.started_at), record_detail: `${dur(e.duration_sec)} · ${num(e.distance_px)}px 이동`, record_action: e.clip_path ? "영상 보기" : "기록 보기" }, n);
    });
    // 24 bars, care-day order (Stitch bar classes)
    const max = Math.max(...hours.map((b) => b.active_sec), 1);
    const curIdx = today ? hours.findIndex((b) => b.hour === nowH) : -1;
    const peakIdx = hours.reduce((m, b, i) => (b.active_sec > hours[m].active_sec ? i : m), 0);
    $("#bars").innerHTML = hours.map((b, i) => {
      const hgt = Math.max(3, Math.round((b.active_sec / max) * 92));
      const night = b.hour >= 22 || b.hour <= 2;
      const cls = i === curIdx ? "w-2.5 bg-primary shadow-[0_0_12px_rgba(52,211,153,0.5)]"
        : curIdx >= 0 && i > curIdx ? "w-2 bg-surface-variant/30"
        : b.active_sec > 0 ? (night ? "w-2 bg-tertiary" : "w-2 bg-tertiary-container/70") : "w-2 bg-surface-variant";
      return `<div class="${cls} rounded-t-sm" style="height:${hgt}%;width:8px;flex:0 0 8px" title="${pad(b.hour)}시: ${min(b.active_sec)}분"></div>`;
    }).join("");
    const bi = curIdx >= 0 ? curIdx : peakIdx, bb = hours[bi];
    $("#now-bubble").style.setProperty("--hs-now-position", ((bi + 0.5) / 24) * 100 + "%");
    $("#now-bubble").classList.toggle("hidden", curIdx < 0 && !bb.active_sec);
    const axis = {}; for (let i = 0; i < 9; i++) axis["ax" + i] = pad((hours[0].hour + i * 3) % 24) + "시";
    bind({ ...axis, bubble: curIdx >= 0 ? `지금 ${hhmm()} (${min(bb.active_sec)}분)` : `최대 ${pad(bb.hour)}시 (${min(bb.active_sec)}분)`,
      legend_now: curIdx >= 0 ? `현재 활동 (${hhmm()})` : `최대 활동 (${pad(bb.hour)}시)` });
    const bubble = $("#now-bubble");
    bubble.style.setProperty("--hs-label-width", bubble.firstElementChild.offsetWidth + "px");
    const img = $('[data-img="home-snapshot"]'), note = $('[data-k="home-live-note"]');
    if (img && note && today) {
      let status = st, statusLoading = false, imageLoading = false;
      const paint = () => {
        if (routeController.signal.aborted || !document.contains(img)) return;
        const camera = camState(status);
      $('[data-k="home-live-state"]').textContent = animalStateLine(status, last && last.ended_at);
        if (camera.mode === "offline" || camera.mode === "privacy" || !snapshotIsFresh(status)) {
          img.style.opacity = "0";
          note.textContent = camera.mode === "privacy" ? "프라이버시 모드에서는 화면을 표시하지 않아요."
            : camera.mode === "offline" ? "카메라 연결이 늦어 최신 장면을 기다리고 있어요."
              : "현재 카메라 장면을 기다리고 있어요.";
          imageLoading = false;
          return;
        }
        if (!imageLoading) { imageLoading = true; img.src = "/media/latest.jpg?t=" + Date.now(); }
      };
      img.onload = () => {
        imageLoading = false;
        if (routeController.signal.aborted || !document.contains(img)) return;
        const camera = camState(status);
        if (camera.mode === "offline" || camera.mode === "privacy" || !snapshotIsFresh(status)) { img.style.opacity = "0"; return; }
        img.style.opacity = "1"; note.textContent = status.camera_status === "dark" ? "최신 장면 · 화면 어두움" : "최신 카메라 장면";
      };
      img.onerror = () => { imageLoading = false; if (!routeController.signal.aborted && document.contains(img)) { img.style.opacity = "0"; note.textContent = "최신 장면을 받지 못했어요. 연결 상태를 확인하고 있어요."; } };
      paint();
      S.live.push(setInterval(() => {
        if (statusLoading || routeController.signal.aborted || !document.contains(img)) return;
        statusLoading = true;
        api("/api/status", { signal: routeController.signal }).then((next) => {
          if (routeController.signal.aborted || !document.contains(img)) return;
          status = next; paint();
        }).catch((e) => { if (e.name !== "AbortError" && !routeController.signal.aborted) { status = { ...status, camera_status: "offline", camera_last_seen: null }; paint(); } })
          .finally(() => { statusLoading = false; });
      }, 5000));
      S.live.push(setInterval(paint, 500));
    }
    if (!routeController.signal.aborted) { document.body.classList.remove("hs-data-loading"); if (loader) loader.hidden = true; }
  },

  async timeline(arg) {
    const routeController = S.controller || new AbortController();
    const date = arg || careToday(), today = date === careToday();
    document.body.classList.add("hs-data-loading");
    let ses, evs, st, zs;
    try { [ses, evs, st, zs] = await Promise.all([api(`/api/sessions?date=${date}&care=1`), api(`/api/events?date=${date}&care=1`), api("/api/status"), api("/api/zones")]); }
    catch (error) {
      if (routeController.signal.aborted) return;
      const loader = $(`[data-view-loading="timeline"]`);
      if (loader) { loader.hidden = false; loader.innerHTML = `<span role="status">타임라인을 불러오지 못했어요.</span><button type="button" class="hs-calendar-retry" data-view-retry>다시 시도</button>`; loader.querySelector("[data-view-retry]").onclick = () => route(); }
      return;
    }
    if (routeController.signal.aborted) return;
    const loader = $(`[data-view-loading="timeline"]`);
    const kindOf = Object.fromEntries(zs.map((z) => [z.id, z.kind]));
    const FILTER = { wheel: ["wheel"], water: ["water", "food"], tunnel: ["hide", "custom"], toilet: ["toilet"], repeat: ["repeat"] };
    const p = S.state.pet || {}, clipCount = evs.filter((e) => e.clip_path).length;
    const latestEventEnd = evs.length ? evs[evs.length - 1].ended_at : null;
    const phrase = today ? animalStateLine(st, latestEventEnd) : `${shortLabel(date)}의 활동 기록을 보고 있어요`;
    const reportLink = $('[data-report-link]');
    if (reportLink) reportLink.href = `#report/${date}`;
    show("day-summary", !today);
    bind({ date_label: today ? `오늘 (${shortLabel(date)})` : shortLabel(date), is_today: today, has_report_link: !today, care_cycle: careCycle(), count: ses.length,
      live_line: today ? (p.name ? `현재 ${esc(p.species || "반려동물")} <strong>${esc(p.name)}</strong>는 ${phrase}` : phrase) : `${shortLabel(date)} 기록 요약 · 활동 ${ses.length}회 · 클립 ${clipCount}개`,
      timeline_takeaway: `${dur(ses.reduce((total, item) => total + (+item.active_sec || 0), 0))}의 움직임 기록 · ${evs.length}개 활동 구간 · ${clipCount}개 클립`,
      live_meta: today ? `수집 ${ago(st.camera_last_seen)}` : "과거 날짜 기록" });
    const liveLine = $('[data-html="live_line"]');
    if (today) {
      let statusLoading = false;
      S.live.push(setInterval(() => {
        if (statusLoading || routeController.signal.aborted || !document.contains(liveLine)) return;
        statusLoading = true;
        api("/api/status", { signal: routeController.signal }).then((next) => {
          if (routeController.signal.aborted || !document.contains(liveLine)) return;
          const state = animalStateLine(next, latestEventEnd);
          liveLine.innerHTML = p.name ? `현재 ${esc(p.species || "반려동물")} <strong>${esc(p.name)}</strong>는 ${state}` : state;
          const meta = $('[data-k="live_meta"]'); if (meta) meta.textContent = `수집 ${ago(next.camera_last_seen)}`;
          const dot = $('[data-cls="cam_dot"]'); if (dot) { dot.classList.remove("bg-primary", "bg-tertiary", "bg-error", "bg-surface-variant"); dot.classList.add(...camState(next).dot.split(" ")); }
        }).catch((e) => {
          if (e.name !== "AbortError" && !routeController.signal.aborted && document.contains(liveLine)) liveLine.textContent = animalStateLine({ camera_status: "offline", camera_last_seen: null });
        }).finally(() => { statusLoading = false; });
      }, 5000));
    }
    $('[data-day="1"]').disabled = today;
    const calendar = new TimelineCalendar(date, routeController.signal);
    calendar.bind();
    const list = [...ses].reverse();
    show("empty", !list.length);
    fill("session", list, (n, s) => {
      const t0 = new Date(s.started_at), t1 = new Date(s.ended_at), h = kst(t0).getUTCHours();
      const mine = evs.filter((e) => new Date(e.started_at) >= t0 && new Date(e.started_at) <= t1);
      const clips = mine.filter((e) => e.clip_path);
      n.dataset.kinds = [...new Set(mine.flatMap((e) => (e.zones || []).map((z) => kindOf[z]).concat(e.repeat ? ["repeat"] : [])))].join(" ");
      bind({ icon: h < 6 ? "nightlight" : h < 12 ? "wb_twilight" : h < 18 ? "wb_sunny" : "bedtime",
        title: `${daypart(h)} ${s.span_sec >= 600 ? "활발 타임" : "활동"}`, range: `${hhmm(t0)} ~ ${hhmm(t1)} (${dur(s.span_sec)}간 활동)`,
        nclips: clips.length, dist: num(s.distance_px), frames: num(s.active_frames),
        memo: `${s.event_count}개 구간에서 움직임이 감지됐어요. 움직인 시간 ${dur(s.active_sec)}, 이동 ${num(s.distance_px)}px.` }, n);
      const tpl = $('[data-tpl="clip"]', n), grid = tpl.parentNode;
      for (const e of clips.slice(0, 6)) {
        const a = tpl.cloneNode(true); a.removeAttribute("data-tpl");
        a.href = "#session/" + encodeURIComponent(e.event_id);
        a.onclick = (ev) => { ev.preventDefault(); ev.stopPropagation(); openSession(e.event_id, date); };
        $('[data-img="thumb"]', a).src = "/media/thumb/" + encodeURIComponent(e.event_id);
        $('[data-k="t"]', a).textContent = hhmm(e.started_at);
        grid.appendChild(a);
      }
      tpl.remove();
      if (!clips.length) grid.parentNode.remove();
      const openId = (clips[0] || mine[0] || {}).event_id;
      if (openId) { n.classList.add("cursor-pointer"); n.onclick = () => openSession(openId, date); }
    });
    // zone filters (enabled once zones exist): show sessions that visited a zone of that kind
    const chips = $$(".filter-chip");
    const paint = (f) => {
      chips.forEach((b) => { swap(b, "bg-surface-container text-on-surface-variant", "bg-primary text-on-primary", b.dataset.filter === f); });
      let shown = 0;
      $$(".timeline-card:not([data-tpl])").forEach((el) => { const on = f === "all" || FILTER[f].some((k) => (el.dataset.kinds || "").split(" ").includes(k)); el.classList.toggle("hidden", !on); shown += on; });
      bind({ count: shown }); show("empty", !shown);
    };
    chips.forEach((b) => {
      if (b.dataset.filter !== "all" && b.dataset.filter !== "repeat") { b.disabled = !zs.some((z) => FILTER[b.dataset.filter].includes(z.kind)); b.title = b.disabled ? "케이지 구역을 먼저 설정해 주세요" : ""; }
      b.onclick = () => paint(b.dataset.filter);
    });
    restoreOriginPosition("timeline", date);
    if (!routeController.signal.aborted) { document.body.classList.remove("hs-data-loading"); if (loader) loader.hidden = true; }
  },

  async session(id) {
    const observationSignal = S.controller?.signal;
    let origin;
    try { origin = JSON.parse(sessionStorage.getItem(TIMELINE_RETURN)); } catch (_) { /* stale session state */ }
    if (origin && origin.eventId !== id) sessionStorage.removeItem(TIMELINE_RETURN);
    const e = await api("/api/events/" + encodeURIComponent(id));
    const day = iso(new Date(new Date(e.started_at).getTime() + KST - careHours() * 3600e3));
    if (!origin || origin.eventId !== id) {
      origin = { kind: "timeline", date: day, scrollY: 0, eventId: id };
      sessionStorage.setItem(TIMELINE_RETURN, JSON.stringify(origin));
    }
    const [dayEvents, sessions] = await Promise.all([api(`/api/events?date=${day}&care=1`), api(`/api/sessions?date=${day}&care=1`)]);
    const eventStart = new Date(e.started_at).getTime();
    const session = sessions.find((s) => eventStart >= new Date(s.started_at).getTime() && eventStart <= new Date(s.ended_at).getTime());
    const evs = session ? dayEvents.filter((x) => x.clip_path && new Date(x.started_at) >= new Date(session.started_at) && new Date(x.started_at) <= new Date(session.ended_at)) : [];
    const i = evs.findIndex((x) => x.event_id === e.event_id), prev = i > 0 ? evs[i - 1] : null, next = i >= 0 && i < evs.length - 1 ? evs[i + 1] : null;
    const p = S.state.pet || {}, h = kst(e.started_at).getUTCHours();
    const lighting = eventLighting(e);
    const k = kst(e.started_at);
    const [W, H] = e.frame_size || [160, 90], tr = e.track || [];
    const fps = tr.length > 1 ? tr.length / Math.max(1, e.duration_sec) : 2;
    const total = Math.max(e.active_frames || 0, Math.round(e.duration_sec * Math.max(fps, 1)));
    const ratio = total ? Math.round(((e.active_frames || 0) / total) * 100) : 0;
    const zs = await api("/api/zones");
    const regionOf = (x, y) => {
      const nx = x / W, ny = y / H;
      const col = nx < 1 / 3 ? "좌" : nx > 2 / 3 ? "우" : "";
      const row = ny < 1 / 3 ? "상" : ny > 2 / 3 ? "하" : "";
      if (col && row) return col + row;
      return col || row || "중앙";
    };
    const seenRegions = [...new Set(tr.map((t) => regionOf(t[1], t[2])))];
    const zone = (x, y) => { const z = zs.find((z) => inPoly(x / W, y / H, z.points)); return z ? z.name : regionOf(x, y); };
    bind({ idx: pad(i + 1), clip_position: e.clip_path && i >= 0 ? `${i + 1} / ${evs.length}` : "클립 없음",
      back_label: origin.kind === "report" ? "보고서로" : "타임라인으로",
      session_title: session ? `${daypart(kst(session.started_at).getUTCHours())} ${session.span_sec >= 600 ? "활발 타임" : "활동"} · ${hhmm(session.started_at)} 시작` : "관찰 기록",
      rec_time: `${k.getUTCFullYear()}.${pad(k.getUTCMonth() + 1)}.${pad(k.getUTCDate())} ${hhmmss(e.started_at)}`,
      cam_mode: "촬영 시각 기준", cam_icon: lighting.night ? "nightlight" : "wb_sunny", tag: p.name ? `${p.name} 움직임 감지` : "움직임 감지", daypart: lighting.label,
      title: `${daypart(h)} ${hhmm(e.started_at)} 움직임 기록`, start: hhmmss(e.started_at), duration: dur(e.duration_sec),
      dist: num(e.distance_px), frames: num(e.active_frames), ratio_label: `움직임 ${ratio}% · 정지 ${100 - ratio}%`,
      start_zone: tr.length ? zone(tr[0][1], tr[0][2]) : "-",
      end_zone2: tr.length ? zone(tr[tr.length - 1][1], tr[tr.length - 1][2]) : "-",
      zone_names: (e.zone_names && e.zone_names.length) ? e.zone_names.join(", ") : "지정한 구역 밖",
      regions: seenRegions.length ? seenRegions.join(" ") : "-",
      pace: e.pace ? "이번 클립에서 보였어요" : "이번 클립에서는 안 보였어요",
      circle: e.circle ? "이번 클립에서 보였어요" : "이번 클립에서는 안 보였어요",
      prev: prev ? hhmm(prev.started_at) : "이 세션의 첫 클립", next: next ? hhmm(next.started_at) : "이 세션의 마지막 클립",
      download: `클립 기기에 저장 (MP4${e.clip_bytes ? `, ${(e.clip_bytes / 1e6).toFixed(1)}MB` : ""})` });
    $("#ratio-a").style.width = ratio + "%"; $("#ratio-b").style.width = 100 - ratio + "%";
    // movement trail on the player (400x225) and the mini map (350x160)
    const path = (sw, sh) => tr.map((t, j) => `${j ? "L" : "M"} ${((t[1] / W) * sw).toFixed(1)},${((t[2] / H) * sh).toFixed(1)}`).join(" ");
    const dot = (id, t, sw, sh) => { if (!t) return; $("#" + id).setAttribute("cx", ((t[1] / W) * sw).toFixed(1)); $("#" + id).setAttribute("cy", ((t[2] / H) * sh).toFixed(1)); };
    const mid = tr[Math.floor(tr.length / 2)], end = tr[tr.length - 1];
    $("#trail").setAttribute("d", path(400, 225)); dot("trail-a", tr[0], 400, 225); dot("trail-b", mid, 400, 225); dot("trail-end", end, 400, 225);
    $("#map-trail").setAttribute("d", path(160, 90)); dot("map-a", tr[0], 160, 90); dot("map-b", mid, 160, 90); dot("map-end", end, 160, 90);
    const seen = new Set(tr.map((t) => regionOf(t[1], t[2])));
    const zoneLayer = $("#map-zones");
    zoneLayer.replaceChildren();
    const svgNS = "http://www.w3.org/2000/svg";
    for (const z of zs) {
      if (!Array.isArray(z.points) || z.points.length < 3) continue;
      const points = z.points.map(([x, y]) => `${(+x * 160).toFixed(1)},${(+y * 90).toFixed(1)}`).join(" ");
      const polygon = document.createElementNS(svgNS, "polygon"), color = ZK[z.kind]?.[1] || "#cbc6bd";
      polygon.setAttribute("points", points); polygon.setAttribute("fill", color); polygon.setAttribute("fill-opacity", ".12"); polygon.setAttribute("stroke", color); polygon.setAttribute("stroke-width", ".7"); zoneLayer.append(polygon);
      const center = z.points.reduce((a, p) => [a[0] + +p[0] / z.points.length, a[1] + +p[1] / z.points.length], [0, 0]);
      const label = document.createElementNS(svgNS, "text"); label.setAttribute("x", center[0] * 160); label.setAttribute("y", center[1] * 90); label.setAttribute("text-anchor", "middle"); label.setAttribute("fill", "#e3e2e7"); label.setAttribute("font-size", "3"); label.setAttribute("stroke", "#121317"); label.setAttribute("stroke-width", ".7"); label.setAttribute("paint-order", "stroke"); label.textContent = z.name; zoneLayer.append(label);
    }
    $$("[data-region]").forEach((el) => el.classList.toggle("on", seen.has(el.dataset.region)));
    const tag = $("#tag");
    if (end) { tag.style.left = Math.min(80, Math.max(20, (end[1] / W) * 100)) + "%"; tag.style.top = Math.min(45, Math.max(18, (end[2] / H) * 100 - 30)) + "%"; } else tag.classList.add("hidden");
    // peak marker = largest step in the track
    let pk = 0, best = -1;
    for (let j = 1; j < tr.length; j++) { const d = Math.hypot(tr[j][1] - tr[j - 1][1], tr[j][2] - tr[j - 1][2]); if (d > best) { best = d; pk = tr[j][0]; } }
    $("#peak-pin").style.left = (e.duration_sec ? (pk / e.duration_sec) * 100 : 0) + "%";
    // player
    const v = $("#vid"), clip = "/media/clip/" + encodeURIComponent(e.event_id);
    v.poster = "/media/thumb/" + encodeURIComponent(e.event_id);
    const seek = $("#seek"), status = $("#player-status"), play = $("#playBtn");
    const mediaControls = [play, $("#speedBtn"), $("#fsBtn")];
    mediaControls.forEach((b) => (b.disabled = !e.clip_path));
    seek.disabled = true;
    status.textContent = e.clip_path ? "영상을 불러오는 중이에요." : "저장된 영상이 없어요. 아래 관찰 기록을 확인해 주세요.";
    const t2 = (s) => `${pad(Math.floor(s / 60))}:${pad(Math.floor(s % 60))}`;
    $("#dur").textContent = t2(e.duration_sec);
    v.onloadedmetadata = () => {
      const ready = Number.isFinite(v.duration) && v.duration > 0;
      seek.disabled = !ready; seek.max = ready ? v.duration : 0;
      $("#dur").textContent = t2(ready ? v.duration : e.duration_sec);
      $("#quality").textContent = v.videoHeight ? v.videoHeight + "p" : "SD";
      status.textContent = "";
    };
    v.ontimeupdate = () => {
      $("#cur").textContent = t2(v.currentTime); seek.value = v.currentTime;
      seek.setAttribute("aria-valuetext", `${t2(v.currentTime)} / ${$("#dur").textContent}`);
      $("#progress").style.width = (v.duration ? (v.currentTime / v.duration) * 100 : 0) + "%";
    };
    v.onplay = () => { $("#playIcon").textContent = "pause"; play.setAttribute("aria-label", "일시정지"); status.textContent = ""; };
    v.onpause = () => { $("#playIcon").textContent = "play_arrow"; play.setAttribute("aria-label", "재생"); };
    v.onerror = () => {
      mediaControls.forEach((b) => (b.disabled = true)); seek.disabled = true;
      status.textContent = "영상을 불러오지 못했어요. 기록을 다시 열거나 다른 클립을 확인해 주세요.";
    };
    play.onclick = async () => {
      if (!v.paused) return v.pause();
      try { await v.play(); }
      catch (_) { $("#playIcon").textContent = "play_arrow"; status.textContent = "영상을 재생하지 못했어요. 재생 버튼을 다시 눌러 주세요."; }
    };
    seek.oninput = () => { if (!seek.disabled) v.currentTime = Number(seek.value); };
    if (e.clip_path) v.src = clip;
    const speeds = [1, 1.5, 2, 0.5]; let si = 0;
    $("#speedBtn").onclick = () => { si = (si + 1) % speeds.length; v.playbackRate = speeds[si]; $("#speedText").textContent = speeds[si].toFixed(1) + "x"; };
    $("#fsBtn").onclick = () => (v.requestFullscreen || v.webkitEnterFullscreen || (() => {})).call(v);
    $("#btn-prev").disabled = !prev; $("#btn-next").disabled = !next;
    $("#btn-prev").onclick = () => prev && openSession(prev.event_id, day);
    $("#btn-next").onclick = () => next && openSession(next.event_id, day);
    $$('[data-back]').forEach((b) => {
      b.dataset.returnRoute = origin.kind === "report" ? `#report/${origin.date}` : `#timeline/${origin.date}`;
      b.setAttribute("aria-label", origin.kind === "report" ? "보고서로 돌아가기" : "타임라인으로 돌아가기");
    });
    $("#downloadBtn").disabled = !e.clip_path;
    $("#downloadBtn").onclick = () => { const a = document.createElement("a"); a.href = clip; a.download = e.event_id + ".mp4"; a.click(); };
    const original = $("#originalDownload");
    original.classList.toggle("hidden", !e.original_url);
    if (e.original_url) original.href = e.original_url;
    let fav = !!e.is_protected;
    const favPaint = () => {
      $("#favBtn span").textContent = fav ? "star" : "star_outline";
      $("#favBtn span").style.fontVariationSettings = fav ? "'FILL' 1" : "";
      $("#favActionIcon").textContent = fav ? "star" : "star_outline";
      bind({ fav_label: fav ? "즐겨찾기에서 빼기 (자동 삭제 보호 중)" : "즐겨찾기 보관함에 추가" });
      const favItem = $("[data-more=fav]");
      if (favItem) favItem.textContent = fav ? "즐겨찾기에서 빼기" : "즐겨찾기 보관함에 추가";
    };
    const favToggle = async () => { const r = await post(`/api/events/${encodeURIComponent(e.event_id)}/favorite`, { on: !fav }); fav = r.favorite; favPaint(); };
    $("#favBtn").onclick = favToggle; $("#favoriteActionBtn").onclick = favToggle;
    favPaint();
    const rm = $("#btn-delete");
    if (rm) {
      rm.classList.toggle("hidden", !canDeleteEvents());
      rm.onclick = async () => {
        if (!confirm("이 기록과 영상을 삭제할까요? 되돌릴 수 없어요.")) return;
        rm.disabled = true;
        try {
          await del("/api/events/" + encodeURIComponent(e.event_id));
          const returnPath = origin?.kind === "report" ? `#report/${origin.date}` : `#timeline/${origin?.date || day}`;
          sessionStorage.setItem(TIMELINE_RETURN, JSON.stringify({ kind: origin?.kind || "timeline", date: origin?.date || day, scrollY: origin?.scrollY || 0 }));
          history.replaceState(null, "", returnPath); route();
        }
        catch (_) { rm.disabled = false; alert("삭제하지 못했어요."); }
      };
    }
    const menu = $("#more-menu"), more = $("#btn-more");
    if (more && menu) {
      more.onclick = (ev) => { ev.stopPropagation(); const open = menu.classList.toggle("hidden") === false; more.setAttribute("aria-expanded", open ? "true" : "false"); };
      $("[data-more=save]", menu).onclick = () => { menu.classList.add("hidden"); $("#downloadBtn").click(); };
      $("[data-more=fav]", menu).onclick = () => { menu.classList.add("hidden"); $("#favoriteActionBtn").click(); };
      const delItem = $("[data-more=delete]", menu);
      delItem.classList.toggle("hidden", !canDeleteEvents());
      delItem.onclick = () => { menu.classList.add("hidden"); if (rm) rm.click(); };
    }
    api(`/api/behavior?date=${day}`).then((beh) => {
      if (!beh || !beh.items) return;
      const bits = beh.items.map((it) => `${it.label} ${it.key === "wheel_sec" ? dur(it.today) : it.today + "번"}`);
      const line = behLine(beh, day);
      const label = day === careToday() ? "오늘" : `${dateLabel(day)} 돌봄 하루`;
      bind({ beh_line: `${label} ${bits.join(", ")}. ${line.beh_title}. ${beh.status === "ready" ? "관찰 기록은 진단이 아닌 참고 정보예요." : line.beh_text}` });
    }).catch((e) => { if (e.name !== "AbortError") bind({ beh_line: day === careToday() ? "오늘 행동 참고를 불러오지 못했어요." : `${dateLabel(day)} 돌봄 하루의 행동 참고를 불러오지 못했어요.` }); });
    api(`/api/events/${encodeURIComponent(e.event_id)}/observations`).then((observations) => {
      if (observationSignal?.aborted || !location.hash.startsWith(`#session/${encodeURIComponent(e.event_id)}`)) return;
      const rows = observationRows(observations, 12);
      if (!rows.length) return;
      fill("session-observation", rows, (el, row) => bind({ title: row.label, time: `${row.time} · ${row.source_label}`, meta: row.quality, state: row.state }, el));
      show("session-observations");
    }).catch((error) => { if (error.name !== "AbortError") { /* Older servers may not expose observations. */ } });
    $("#btn-share").onclick = async () => { try { await navigator.clipboard.writeText(location.href); $("#btn-share span").textContent = "check"; } catch (_) { /* no clipboard */ } };
  },

  async zones() {
    const admin = canManage();
    let [zs, stats] = await Promise.all([api("/api/zones"), api(`/api/zones/stats?date=${careToday()}&care=1`)]);
    const by = Object.fromEntries(stats.zones.map((z) => [z.id, z]));
    let kind = "cage", pts = [];
    $("#zone-img").src = "/media/latest.jpg?t=" + Date.now();
    $("#zone-img").onerror = () => { $("#zone-img").removeAttribute("src"); };
    const svg = $("#zone-svg"), list = $("#zone-list"), tpl = $('[data-tpl="zone"]', list);
    const poly = (p) => p.map((q) => q.join(",")).join(" ");
    const draw = () => {
      svg.innerHTML = zs.map((z) => `<polygon points="${poly(z.points)}" fill="${ZK[z.kind][1]}" fill-opacity="0.25" stroke="${ZK[z.kind][1]}" stroke-width="0.006"/>`).join("")
        + (pts.length ? `<polyline points="${poly(pts.length === 2 ? rect(pts) : pts)}" fill="none" stroke="#e3e2e7" stroke-dasharray="0.02 0.01" stroke-width="0.006"/>` : "")
        + pts.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="0.012" fill="#e3e2e7"/>`).join("");
      $$("#zone-list > *:not([data-tpl])").forEach((el) => el.remove());
      for (const z of zs) {
        const n = tpl.cloneNode(true); n.removeAttribute("data-tpl"); n.classList.remove("hidden");
        const st = by[z.id];
        bind({ name: z.name, stat: z.kind === "cage" ? "이 영역 밖의 움직임은 감지하지 않아요" : st ? `오늘 방문 ${st.visits}회 · 머문 시간 ${dur(st.dwell_sec)}` : "저장하면 통계가 계산돼요", dot: ZK[z.kind][2] }, n);
        $("[data-del]", n).disabled = !admin;
        $("[data-del]", n).onclick = () => { zs = zs.filter((x) => x !== z); draw(); };
        tpl.before(n);
      }
      tpl.classList.add("hidden");
      show("zone-empty", !zs.length);
    };
    const rect = ([[x0, y0], [x1, y1]]) => [[Math.min(x0, x1), Math.min(y0, y1)], [Math.max(x0, x1), Math.min(y0, y1)], [Math.max(x0, x1), Math.max(y0, y1)], [Math.min(x0, x1), Math.max(y0, y1)]];
    $$("#zone-kinds [data-kind]").forEach((b) => (b.onclick = () => {
      kind = b.dataset.kind;
      $$("#zone-kinds [data-kind]").forEach((c) => swap(c, "bg-surface-container-high text-on-surface-variant", "bg-primary text-on-primary", c === b));
    }));
    $("#zone-stage").onclick = (ev) => {
      if (!admin) return;
      const r = $("#zone-stage").getBoundingClientRect();
      pts.push([+((ev.clientX - r.left) / r.width).toFixed(4), +((ev.clientY - r.top) / r.height).toFixed(4)]);
      draw();
    };
    $("#btn-zclear").onclick = () => { pts = []; draw(); };
    $("#btn-zadd").onclick = () => {
      if (pts.length < 2) return alert("사진 위를 눌러 꼭짓점을 2개(사각형) 이상 찍어 주세요.");
      if (kind === "cage") zs = zs.filter((z) => z.kind !== "cage");  // one cage mask: redraw replaces it
      let name = ZK[kind][0];
      if (kind === "custom") { name = (prompt("구역 이름 (20자 이내)") || "").trim().slice(0, 20); if (!name) return; }
      const n = zs.filter((z) => z.kind === kind).length;
      zs.push({ id: `${kind}${Date.now().toString(36)}`, name: n && kind !== "custom" && kind !== "cage" ? `${name} ${n + 1}` : name, kind, points: pts.length === 2 ? rect(pts) : pts });
      pts = []; draw();
    };
    $("#btn-zsave").onclick = async () => {
      try { zs = await post("/api/zones", { zones: zs }); stats = await api(`/api/zones/stats?date=${careToday()}&care=1`); Object.assign(by, Object.fromEntries(stats.zones.map((z) => [z.id, z]))); draw(); bind({ sub: "저장했어요. 타임라인 필터와 홈 통계에 반영돼요." }); if (!S.state.onboarding_done && zs.some((z) => z.kind === "cage")) setTimeout(() => go("#camera"), 1200); }
      catch (_) { alert("구역을 저장하지 못했어요."); }
    };
    bind({ sub: admin ? (zs.some((z) => z.kind === "cage") ? "사진 위를 눌러 꼭짓점을 찍어요 (2점 = 사각형)" : "먼저 케이지 영역을 그려 주세요. 지금은 화면 전체를 감지해요") : "관리자만 구역을 편집할 수 있어요" });
    draw();
  },

  async notifications() {
    const error = $("#noti-error");
    try {
      const n = await api("/api/notifications");
      const items = n.items || [], DOT = { alert: "bg-error", warn: "bg-tertiary", info: "bg-secondary" };
      fill("noti", items, (el, it) => { bind({ title: it.title, body: it.body, when: whenLabel(it.created_at) + (it.silent ? " · 무음" : ""), dot: DOT[it.level] || "bg-primary" }, el); if (it.read_at || it.silent) el.classList.add("opacity-70"); });
      show("noti-empty", !items.length); show("noti-error", false);
      bind({ sub: n.unread ? `읽지 않은 알림 ${n.unread}개` : "새 알림이 없어요" });
      $("#btn-read").disabled = !n.unread;
      $("#btn-read").onclick = async () => { if (n.unread) { await post("/api/notifications/read"); route(); } };
    } catch (e) {
      if (e.name === "AbortError") return;
      show("noti-error", true); error.textContent = "알림을 불러오지 못했어요. 잠시 후 다시 확인해 주세요.";
      show("noti-empty", false); $("#btn-read").disabled = true;
    }
  },

  async status() {
    const routeController = S.controller || new AbortController(), date = careToday();
    const [beh, zones] = await Promise.all([api(`/api/behavior?date=${date}`, { signal: routeController.signal }), api("/api/zones").catch(() => [])]);
    if (routeController.signal.aborted) return;
    const profile = S.state.pet || {}, pet = profile.name || "반려동물";
    const reportLink = $(`[data-report-link]`);
    if (reportLink) reportLink.href = "#report";
    bind({ page_title: `${pet} 상태`, page_sub: "반려동물 정보, 케어 시작 시간과 관찰 구역",
      care_start: ampm(careStart()) + (careStart() === "12:00" ? " (정오)" : ""), care_cycle: `${ampm(careStart())}부터 익일 ${ampm(careStart())}`,
      report_heading: "최근 하루 보고서",
      status_pet_name: profile.name || "이름 미등록",
      status_pet_detail: [profile.species, profile.weight_g ? `${profile.weight_g}g` : null].filter(Boolean).join(" · ") });
    fill("status-zone", zones, (el, zone) => bind({ status_zone_name: zone.name || "관찰 구역" }, el));
    show("status-zone-empty", !zones.length);
    const paintBehavior = (data) => {
      const line = behLine(data, date);
      bind({ beh_sub: data.status === "ready" ? `지난 ${data.valid_days}일의 같은 시간대와 비교` : line.beh_text });
      const paintRow = (el, it) => {
        el.dataset.behRow = it.key;
        const dot = $("[data-cls='dot']", el);
        if (dot) dot.classList.remove("bg-outline", "bg-primary", "bg-tertiary", "bg-secondary");
        bind({ title: it.label + (it.ref_only ? " (참고)" : ""), sub: behSub(it, data), when: behVal(it), dot: data.status !== "ready" || it.flag === "unknown" || it.median == null ? "bg-outline" : it.flag === "high" ? (it.ref_only ? "bg-secondary" : "bg-tertiary") : "bg-primary" }, el);
      };
      const rows = $$('[data-beh-row]');
      if (!rows.length && $('[data-tpl="beh"]')) fill("beh", data.items || [], paintRow);
      else for (const it of data.items || []) { const row = rows.find((el) => el.dataset.behRow === it.key); if (row) paintRow(row, it); }
    };
    paintBehavior(beh);
    const paintObservations = (data) => {
      const statusObs = observationRows(data.camera_observations, 6);
      if (!statusObs.length) { show("status-observations", false); return; }
      bind({ status_observation_summary: observationSummary(data.camera_observations, statusObs.length) });
      if ($('[data-tpl="status-observation"]')) fill("status-observation", statusObs, (el, row) => {
        bind({ title: row.label, time: `${row.time} · ${row.source_label}`, meta: row.quality, state: row.state }, el);
        el.href = `#session/${encodeURIComponent(row.event_id)}`;
        el.onclick = (event) => { event.preventDefault(); openSession(row.event_id, data.date || date, "timeline"); };
      });
      show("status-observations", true);
    };
    paintObservations(beh);
    let behaviorLoading = false;
    S.live.push(setInterval(async () => {
      if (document.hidden || behaviorLoading || routeController.signal.aborted) return;
      if (careToday() !== date) { route(); return; }
      behaviorLoading = true;
      try {
        const latest = await api(`/api/behavior?date=${date}`, { signal: routeController.signal });
        if (!routeController.signal.aborted) paintBehavior(latest);
      } catch (error) { if (error.name === "AbortError") return; }
      finally { behaviorLoading = false; }
    }, 60000));
    const admin = canManage();
    $$("[data-admin]").forEach((b) => (b.disabled = !admin));
    $("#btn-care").onclick = () => go("#schedule");
    const petEdit = $("#btn-petedit"), zoneEdit = $("#btn-zones");
    if (petEdit) petEdit.onclick = () => go("#pet");
    if (zoneEdit) zoneEdit.onclick = () => go("#zones");
  },

  async report(arg) {
    const errorText = (e) => e.status === 422 ? "이 날짜는 아직 보고서를 만들 수 없어요." : "보고서를 불러오지 못했어요. 연결을 확인하고 다시 시도해 주세요.";
    const run = async () => {
      err("report-error", ""); show("report-retry", false); show("report-content", false); show("report-loading", true);
      try {
        const [report, zoneShapes] = await Promise.all([api("/api/reports/daily" + (arg ? `?date=${encodeURIComponent(arg)}` : "")), api("/api/zones")]);
        const date = report.date || arg || "";
        const sum = report.summary || {}, baseline = report.baseline || {}, highlights = report.highlights || [], tracks = report.tracks || [];
        const quality = report.quality === "valid";
        const active = dur(sum.active_sec || 0);
        const reportState = "하루 관찰 리포트";
        const p = S.state.pet || {}, petName = p.name || "반려동물";
        const reportObs = observationRows(report.camera_observations, 6);
        if (reportObs.length) {
          bind({ report_observation_summary: observationSummary(report.camera_observations, reportObs.length) });
          fill("report-observation", reportObs, (el, row) => {
            bind({ title: row.label, time: `${row.time} · ${row.source_label}`, meta: row.quality, state: row.state }, el);
            el.href = `#session/${encodeURIComponent(row.event_id)}`;
            el.onclick = (event) => { event.preventDefault(); openSession(row.event_id, date, "report"); };
          });
          show("report-observations");
        }
        const reportInsight = report.quality !== "valid"
          ? `수집 범위 ${Math.round((report.coverage || 0) * 100)}% · 빈 시간대의 케이지 상황도 직접 살펴봐 주세요.`
          : baseline.status === "ready" && Number.isFinite(baseline.metrics?.active_sec?.pct)
            ? (baseline.metrics.active_sec.pct === 0 ? "움직임 기록이 평소 중앙값과 비슷해요. 주변 환경의 변화도 함께 살펴봐 주세요." : `움직임 기록이 평소 중앙값보다 ${Math.abs(Math.round(baseline.metrics.active_sec.pct))}% ${baseline.metrics.active_sec.pct < 0 ? "적게" : "많이"} 남았어요. 주변 환경의 변화도 함께 살펴봐 주세요.`)
            : (report.zones || []).length && (report.zones || []).every((z) => !z.visits)
              ? "구역 방문이 기록되지 않았어요. 카메라 시야와 구역 설정을 살펴봐 주세요."
              : "하루의 영상과 활동 기록을 함께 확인해 보세요.";
        bind({ report_date: date ? dateLabel(date) : "돌봄 하루", report_title: p.name ? `${petName}의 하루 돌아보기` : "오늘의 돌봄 기록", report_pet: petName, report_state: reportState,
          report_takeaway: quality ? `${dur(sum.active_sec || 0)} 움직임 기록 · 활동 구간 ${sum.session_count || 0}회 · 영상 ${sum.clip_count || 0}개` : `관찰 ${dur(sum.observed_sec || 0)} · 수집 범위 ${Math.round((report.coverage || 0) * 100)}%`,
          report_insight: reportInsight, active_stat: active, session_stat: `${sum.session_count || 0}회`, clip_stat: `${sum.clip_count || 0}개`,
          quality_text: quality ? "관찰 수집 기준을 충족한 하루예요" : "수집이 적어 참고 기록으로 살펴봐 주세요",
          coverage_text: `카메라 수집 ${Math.round((report.coverage || 0) * 100)}%`,
          summary_text: `관찰 ${dur(sum.observed_sec || 0)} · 활동 기록 ${sum.session_count || 0}회 · 재생 가능한 클립 ${sum.clip_count || 0}개`,
          activity_text: `${active} 동안 움직임이 기록됐어요`,
          distance_text: `영상 좌표 이동량 ${num(sum.distance_px || 0)}px · 실제 거리 측정값이 아니에요`,
          baseline_text: quality && baseline.status === "ready" ? (() => {
            const m = baseline.metrics?.active_sec || {}, pct = Number.isFinite(m.pct) ? `${m.pct > 0 ? "+" : ""}${Math.round(m.pct)}%` : "비교 수치 없음";
            return `평소보다 ${pct} · 이 돌봄 하루 ${dur(m.today || 0)}, 평소 중앙값 ${dur(m.median || 0)}`;
          })() : "이 날짜는 관찰 수집이 충분하지 않거나 개인 기준선이 준비되지 않아 평소와 비교하지 않아요.",
          track_text: tracks.length ? "각 클립의 위치 표본을 구역 지도에 겹쳐 표시해요. 서로 다른 기록의 경로는 연결하지 않아요." : "이 날에 기록된 위치 표본이 없어요.",
          limitations_text: "수집률은 움직임 감지 정확도를 보장하지 않아요. 먹이·물 구역은 방문 기록이며 섭취량이 아니고, 수면·심박수·개체 식별은 측정하지 않아요.",
          reaggregate_text: "현재 돌봄 설정으로 다시 집계한 기록이에요." });
        const timeline = $("#report-timeline"); if (timeline) { timeline.href = `#timeline/${date}`; timeline.dataset.date = date; }
        const back = $("[data-report-back]"); if (back) back.href = `#timeline/${date}`;
        const hourly = report.hourly || [], maxHour = Math.max(1, ...hourly.map((h) => +h.active_sec || 0));
        const rhythm = Array.from({ length: 8 }, (_, i) => {
          const group = hourly.slice(i * 3, i * 3 + 3), first = group[0]?.hour ?? i * 3, last = group[group.length - 1]?.hour ?? first + 2;
          return { first, last, active_sec: group.reduce((total, h) => total + (+h.active_sec || 0), 0) };
        });
        fill("report-hour-bar", rhythm, (n, h) => {
          const amount = Math.max(0, Math.min(100, Math.round(h.active_sec / (maxHour * 3) * 100)));
          const bar = n.querySelector("[data-hour-bar]"); bar.style.width = `${amount}%`;
          bar.setAttribute("aria-label", `${pad(h.first)}시부터 ${pad((h.last + 1) % 24)}시 전까지 ${dur(h.active_sec)} 움직임 기록`);
          bind({ hour_bar_label: `${pad(h.first)}–${pad((h.last + 1) % 24)}시`, hour_bar_value: dur(h.active_sec) }, n);
        });
        fill("report-hour", hourly, (n, h) => bind({ hour: `${pad(h.hour)}시`, hour_activity: dur(h.active_sec || 0), hour_events: `${h.event_count || 0}개 기록` }, n));
        const zones = report.zones || [], maxDwell = Math.max(1, ...zones.map((z) => +z.dwell_sec || 0));
        fill("report-zone", zones, (n, z) => { n.querySelector("[data-zone-bar]").style.width = `${Math.max(0, (+z.dwell_sec || 0) / maxDwell * 100)}%`; bind({ zone_name: z.name || "구역", zone_detail: `${z.visits || 0}회 · 관찰 체류 ${dur(z.dwell_sec || 0)}` }, n); });
        const frameW = report.frame_size?.width || 160, frameH = report.frame_size?.height || 90;
        const map = $("#report-map");
        renderZoneMap(map, zoneShapes, tracks, frameW, frameH);
        const trackLayer = $("[data-map-density]", map);
        show("report-empty-tracks", !trackLayer.childElementCount);
        fill("highlight", highlights, (n, item) => {
          const playable = !!(item.playable && item.clip_url);
          bind({ highlight_time: item.started_at ? hhmm(item.started_at) : "기록 시각 없음", highlight_state: playable ? "영상 보기" : "영상 파일을 확인할 수 없어요", highlight_duration: dur(item.duration_sec || 0) }, n);
          n.disabled = !playable;
          if (playable) {
            n.href = `#session/${encodeURIComponent(item.id)}`;
            n.onclick = (ev) => { ev.preventDefault(); openSession(item.id, date, "report"); };
          } else { n.removeAttribute("href"); }
          const image = n.querySelector('[data-img="highlight"]');
          if (item.thumbnail_url) image.src = item.thumbnail_url; else image.removeAttribute("src");
        });
        show("report-empty-highlights", !highlights.length);
        show("report-empty-zones", !(report.zones || []).length);
        show("report-loading", false); show("report-content", true);
      } catch (e) {
        if (e.name === "AbortError") return;
        show("report-loading", false); err("report-error", errorText(e)); show("report-retry", true);
      }
    };
    $("#report-retry").onclick = run;
    $("#report-timeline").onclick = (ev) => { ev.preventDefault(); const date = arg || $("#report-timeline").dataset.date; if (date) go(`#timeline/${date}`); else go("#timeline"); };
    await run();
    restoreOriginPosition("report", arg || $("#report-timeline").dataset.date);
  },

  async sensors() {
    const form = $("#sensor-form"), admin = canManage(), error = (message) => err("sensor-error", message || "");
    let editingId = null, scan = null, selectedCandidate = null, sensorItems = [];
    let candidateTemplateHTML = $("[data-tpl='candidate']")?.outerHTML || "";
    const candidateList = $("#sensor-candidates .hs-report-list");
    const savedMessage = sessionStorage.getItem("hs_sensor_saved");
    if (savedMessage) { bind({ sensor_saved: savedMessage }); show("sensor-saved"); sessionStorage.removeItem("hs_sensor_saved"); }
    const value = (name) => form.querySelector(`[name="${name}"]`).value.trim();
    const setPlacement = (candidate) => {
      selectedCandidate = candidate;
      editingId = null;
      $("[data-k='sensor_form_title']").textContent = "선택한 보드 배치";
      $("[data-k='sensor_selected_identity']").textContent = [candidate.product, candidate.port].filter(Boolean).join(" · ");
      form.querySelector('[name="name"]').value = candidate.product || candidate.manufacturer || "USB 보드";
      form.querySelector('[name="role"]').value = "";
      for (const key of ["location", "height", "direction", "notes", "peer_sensor_id"]) form.querySelector(`[name="${key}"]`).value = "";
      const peer = $("#sensor-peer"); if (peer) peer.innerHTML = '<option value="">지정하지 않음</option>' + sensorItems.map((sensor) => `<option value="${esc(sensor.sensor_id)}">${esc(sensor.name || sensor.sensor_id)}</option>`).join("");
      form.querySelector('[type="submit"]').textContent = "보드 등록";
      show("sensor-placement-section", true);
    };
    const draw = (items) => {
      fill("sensor", items, (n, sensor) => {
        const status = sensor.status === "online" ? `CSI 샘플 수신 확인 · ${ago(sensor.last_seen_at)}` : sensor.status === "pending" ? (sensor.role === "transmitter" ? "보드 연결됨" : "수신 대기") : sensor.status === "weak_signal" ? "신호 부족" : sensor.status === "offline" ? "미연결" : "연결 준비";
        bind({ sensor_name: sensor.name || "USB 보드", sensor_model: sensor.physical_device || sensor.device_type || "USB 시리얼 장치",
          sensor_role: sensor.role === "transmitter" ? "송신 보드" : "수신 보드", sensor_status: status,
          sensor_location: sensor.installation?.location || "", sensor_direction: sensor.installation?.direction || "", sensor_height: sensor.installation?.height || "" }, n);
        const edit = n.querySelector("[data-edit]");
        edit.disabled = !admin;
        edit.onclick = () => {
          if (!admin) return;
          editingId = sensor.sensor_id; selectedCandidate = null;
          $("[data-k='sensor_form_title']").textContent = "배치 수정";
          $("[data-k='sensor_selected_identity']").textContent = sensor.physical_device || sensor.device_type || "USB 시리얼 장치";
          for (const key of ["name", "role", "location", "height", "direction", "notes", "peer_sensor_id"])
            form.querySelector(`[name="${key}"]`).value = key === "location" || key === "height" || key === "direction" || key === "notes" || key === "peer_sensor_id" ? sensor.installation?.[key] || "" : sensor[key] || (key === "role" ? "transmitter" : "");
          const peer = $("#sensor-peer");
          if (peer) peer.innerHTML = '<option value="">지정하지 않음</option>' + items.filter((other) => other.sensor_id !== sensor.sensor_id).map((other) => `<option value="${esc(other.sensor_id)}">${esc(other.name || other.sensor_id)}</option>`).join("");
          form.querySelector('[type="submit"]').textContent = "배치 변경 저장";
          show("sensor-placement-section", true);
        };
      });
      show("sensor-empty", !items.length);
      const peer = $("#sensor-peer");
      if (peer && !editingId) peer.innerHTML = '<option value="">지정하지 않음</option>' + items.map((sensor) => `<option value="${esc(sensor.sensor_id)}">${esc(sensor.name || sensor.sensor_id)}</option>`).join("");
    };
    const load = async () => { const result = await api("/api/sensors"); const items = (result.items || result).filter((sensor) => sensor.source_type === "wifi_csi"); sensorItems = items; draw(items); return items; };
    try { await load(); } catch (e) { if (e.name === "AbortError") return; error("보드 목록을 불러오지 못했어요. 다시 시도해 주세요."); }
    const discovery = $("#sensor-discovery");
    if (!admin) { show("sensor-discovery", false); show("sensor-placement-section", false); }
    const discover = $("#sensor-discover");
    if (discover) discover.disabled = !admin;
    if (discover) discover.onclick = async () => {
      if (!admin) return;
      error(""); show("sensor-discovery-empty", false); show("sensor-candidates", false); bind({ sensor_discovery_status: "연결된 USB 장치를 찾고 있어요." }); discover.disabled = true;
      try {
        scan = await post("/api/sensors/discover", {});
        const candidates = scan.candidates || [];
        if (!$('[data-tpl="candidate"]') && candidateList && candidateTemplateHTML) candidateList.innerHTML = candidateTemplateHTML;
        fill("candidate", candidates, (n, candidate) => {
          const identity = candidate.hardware_mac ? `MAC ${candidate.hardware_mac}` : candidate.serial_number ? `기기 ID ${candidate.serial_number}` : "";
          bind({ candidate_product: candidate.product || candidate.manufacturer || "USB 시리얼 장치", candidate_port: candidate.port || "USB 포트 정보 없음",
            candidate_identity: identity, candidate_ids: candidate.vendor_id && candidate.product_id ? `VID ${candidate.vendor_id} · PID ${candidate.product_id}` : "",
            candidate_registered: candidate.registered_sensor_id ? "등록된 보드" : "" }, n);
          const registered = n.querySelector("[data-k='candidate_registered']"); if (!candidate.registered_sensor_id) registered.classList.add("hidden");
          const select = n.querySelector("[data-select]");
          select.textContent = candidate.registered_sensor_id ? "연결 확인" : "선택하고 연결 확인";
          select.disabled = !candidate.candidate_id;
          select.onclick = async () => {
            if (!admin || !scan?.scan_id || !candidate.candidate_id) return;
            error(""); select.disabled = true;
            bind({ sensor_discovery_status: "선택한 USB 장치에서 센서 입력을 확인하고 있어요." });
            try {
              const result = await post("/api/sensors/connect", { scan_id: scan.scan_id, candidate_id: candidate.candidate_id, ...(candidate.registered_sensor_id ? { sensor_id: candidate.registered_sensor_id } : {}) });
              if (result.identity_verified && result.serial_opened) {
                bind({ sensor_discovery_status: result.status === "csi_stream_detected" && result.firmware_format_supported ? "센서 입력을 확인했어요." : result.status === "unsupported_stream" ? "보드는 연결됐어요. 수신 형식을 확인해 주세요." : "보드가 연결됐어요." });
                if (candidate.registered_sensor_id) await load(); else setPlacement(candidate);
              } else bind({ sensor_discovery_status: result.status === "port_unavailable" ? "USB 장치를 다시 연결한 뒤 확인해 주세요." : "이 USB 장치를 보드로 확인할 수 없어요." });
            } catch (e) {
              if (e.name === "AbortError") return;
              error(e.status === 409 ? "검색 결과가 만료됐어요. 다시 찾아주세요." : "센서 입력을 확인하지 못했어요. USB 연결 후 다시 시도해 주세요.");
              bind({ sensor_discovery_status: "" });
            } finally { select.disabled = false; }
          };
        });
        show("sensor-candidates", candidates.length > 0);
        show("sensor-discovery-empty", candidates.length === 0);
        bind({ sensor_discovery_status: candidates.length ? `USB 장치 ${candidates.length}개를 찾았어요.` : "",
          sensor_discovery_empty: candidates.length ? "" : "연결된 보드를 찾지 못했어요. USB 연결 후 다시 찾아주세요." });
      } catch (e) {
        if (e.name === "AbortError") return;
        error(e.status === 403 ? "이 계정에서는 보드 검색을 사용할 수 없어요." : "보드를 검색하지 못했어요. USB 연결 후 다시 시도해 주세요.");
      } finally { discover.disabled = !admin; }
    };
    form.querySelectorAll("input,select,textarea,button[type=submit]").forEach((el) => { el.disabled = !admin; });
    form.onsubmit = async (ev) => {
      ev.preventDefault(); if (!admin) return;
      error("");
      const placement = { name: value("name"), role: value("role"), location: value("location"), height: value("height"), direction: value("direction"), notes: value("notes"), peer_sensor_id: value("peer_sensor_id") || null };
      try {
        if (editingId) await api(`/api/sensors/${encodeURIComponent(editingId)}`, { method: "PATCH", body: JSON.stringify(placement) });
        else {
          if (!scan?.scan_id || !selectedCandidate?.candidate_id) throw new Error("선택한 보드가 없어요.");
          await post("/api/sensors/register", { scan_id: scan.scan_id, candidate_id: selectedCandidate.candidate_id, ...placement });
          sessionStorage.setItem("hs_sensor_saved", "보드를 목록에 추가했어요.");
        }
        show("sensor-placement-section", false); editingId = null; selectedCandidate = null; go("#sensors");
      } catch (e) { if (e.name === "AbortError") return; error(e.status === 409 ? "검색 결과가 만료됐어요. 다시 찾아주세요." : "보드를 저장하지 못했어요. 입력을 확인하고 다시 시도해 주세요."); }
    };
    const retry = $("#sensor-retry"); if (retry) retry.onclick = async () => { try { error(""); await load(); } catch (_) { error("보드 목록을 불러오지 못했어요. 다시 시도해 주세요."); } };
  },

  async settings() {
    const [st, members, evs, sum, bl, sensors, quiet] = await Promise.all([api("/api/status"), api("/api/members"), api(`/api/events?date=${careToday()}&care=1`), api(`/api/summary?date=${careToday()}&care=1`), api("/api/baseline"), api("/api/sensors").catch(() => []), api("/api/settings/quiet")]);
    const c = camState(st), u = S.state.user, admin = canManage();
    const sensorItems = (sensors.items || sensors).filter((s) => s.source_type === "wifi_csi"), sensorOnline = sensorItems.filter((s) => s.status === "online").length;
    const used = st.media_bytes || 0, cap = st.max_storage_bytes || 1, pct = Math.min(100, Math.round((used / cap) * 100));
    bind({ page_sub: "계정, 가족, 기기",
      cam_state: c.state, cam_state_sub: c.sub,
      snap_time: st.camera_last_seen ? hhmmss(st.camera_last_seen) : "-", rec_spec: `스냅샷 ${st.snapshot_fps}fps`,
      last_seen: ago(st.camera_last_seen), fps: "스냅샷으로 수집 중",
      uptime: st.online_24h_min == null ? "–" : `${(st.online_24h_min / 60).toFixed(1)}시간`,
      privacy_tag: c.mode === "privacy" ? "켜짐" : "꺼짐",
      sensor_title: sensorItems.length ? `Wi-Fi 센서 ${sensorItems.length}대` : "Wi-Fi 센서 연결 안 됨",
      sensor_detail: sensorOnline ? `최근 CSI 샘플 확인 ${sensorOnline}대` : sensorItems.length ? "수신 확인을 기다리고 있어요" : "USB 보드 검색 및 배치 설정",
      sensor_status: sensorOnline ? "수신 확인" : sensorItems.length ? "대기" : "미연결",
      pct, used: gb(used), cap: gb(cap), free: gb(st.disk_free_bytes || 0),
      me: `${u.email} · ${ROLE_KO[u.space_role] || (admin ? "대표 관리자" : "가족")}`,
      pin_title: S.state.pin_available ? "간편 PIN 변경" : "간편 PIN 설정",
      pin_sub: S.state.pin_available ? "이 기기 등록됨" : "이 기기 미등록" });
    $("#storage-bar").style.width = pct + "%";
    $("#quiet-enabled").checked = !!quiet.enabled;
    $("#quiet-start").value = quiet.start || "23:00";
    $("#quiet-end").value = quiet.end || "07:00";
    $("#quiet-save").onclick = async () => {
      const result = $("#quiet-result"), button = $("#quiet-save"); button.disabled = true; result.textContent = "저장 중";
      try { await post("/api/settings/quiet", { enabled: $("#quiet-enabled").checked, start: $("#quiet-start").value, end: $("#quiet-end").value }); result.textContent = "내 알림 시간에 저장했어요."; }
      catch (e) { result.textContent = e.status === 422 ? "시작과 종료 시간을 확인해 주세요." : "저장하지 못했어요. 다시 시도해 주세요."; }
      finally { button.disabled = false; }
    };
    const paintPv = (pv) => {
      swap($("#privacy-toggle"), "bg-surface-variant", "bg-primary", pv);
      swap($("#privacy-knob"), "bg-on-surface", "bg-on-primary translate-x-5", pv);
      bind({ privacy_tag: pv ? "켜짐" : "꺼짐" });
    };
    let pv = c.mode === "privacy";
    paintPv(pv);
    api("/api/camera/privacy").then((r) => { if (r.enabled !== null) { pv = r.enabled; paintPv(pv); } }).catch(() => {});
    fill("member", members, (n, m) => bind({ email: m.email, role: m.verified ? (ROLE_KO[m.role] || "가족") : "인증 대기", dot: m.verified ? "bg-primary" : "bg-outline" }, n));
    const last = evs[evs.length - 1];
    fill("log", [
      { dot: c.dot, title: `카메라 ${c.label}`, sub: `마지막 신호 ${ago(st.camera_last_seen)}`, when: st.camera_last_seen ? hhmm(st.camera_last_seen) : "-" },
      last ? { dot: "bg-secondary", title: "활동 클립 저장", sub: `${dur(last.duration_sec)} · ${num(last.distance_px)}px 이동`, when: `오늘 ${hhmm(last.started_at)}` }
        : { dot: "bg-secondary", title: "오늘 저장된 클립 없음", sub: "움직임이 감지되면 자동 저장돼요", when: "-" },
      { dot: "bg-tertiary", title: "케어 데이 집계 중", sub: `활동 ${sum.session_count}회 · ${dur(sum.active_sec)}`, when: `오늘 ${careStart()}` },
      { dot: bl.status === "ready" ? "bg-primary" : "bg-outline", title: `개인 기준선 ${bl.status === "ready" ? "준비됨" : ["learning", "rebuilding"].includes(bl.status) ? "평소 활동 패턴 익히는 중" : bl.status === "low_coverage" ? "오늘 데이터 부족" : bl.status === "early" ? "시간대 비교 대기" : "비교 상태 확인 중"}`, sub: ["learning", "rebuilding"].includes(bl.status) ? baselineText(bl, dur, { date: careToday(), live: true }).text : `유효일 ${bl.valid_days ?? "확인 중"}/${bl.need_days ?? "확인 중"} · 수집률 ${bl.coverage == null ? "확인 중" : Math.round(bl.coverage * 100) + "%"}`, when: "최근 28일" },
    ], (n, it) => bind(it, n));
    $$("[data-admin]").forEach((b) => (b.disabled = !admin));
    $("#privacy-toggle").onclick = async () => {
      const next = !pv;
      if (!confirm(next ? "프라이버시 모드를 켤까요?\n렌즈가 수납되고 감지·저장이 멈춰요." : "프라이버시 모드를 끌까요?\n렌즈가 나오고 30초 안에 감지·저장이 다시 시작돼요.")) return;
      $("#privacy-toggle").disabled = true;
      try { const r = await post("/api/camera/privacy", { enabled: next }); pv = !!r.enabled; paintPv(pv); }
      catch (_) { alert("카메라가 변경을 받지 않았어요. 연결 상태를 확인해주세요."); }
      $("#privacy-toggle").disabled = false;
    };
    $("#btn-invite").onclick = () => go("#family");
    $("#btn-logout").onclick = async () => { await post("/api/auth/logout"); go("#welcome"); };
    $("#btn-password").onclick = () => go("#password");
    $("#btn-pinset").onclick = () => go("#pinset");
    $("#btn-camfind").onclick = () => go("#discover");
    $("#btn-lock").disabled = !S.state.pin_set;
    $("#btn-lock").onclick = async () => { await post("/api/auth/lock"); go("#pin"); };
  },

  async live() {
    const img = $('[data-img="snapshot"]'), note = $('[data-k="live_note"]');
    const st = await api("/api/status");
    let loading = false;
    img.onload = () => { loading = false; img.style.opacity = "1"; note.textContent = `실시간 스냅샷 · ${st.snapshot_fps}fps`; };
    img.onerror = () => { loading = false; img.style.opacity = "0"; note.textContent = "장면을 받지 못했어요. 연결을 다시 확인하고 있어요."; };
    const tick = () => {
      if (loading || !document.contains(img)) return;
      loading = true; img.src = "/media/latest.jpg?t=" + Date.now();
    };
    note.textContent = "첫 장면을 불러오는 중이에요.";
    tick();
    S.live.push(setInterval(tick, 500));
    $("#btn-back").onclick = () => history.back();
  },
};

// ---------- family invite (Stitch "가족 초대") ----------
const remain = (iso) => { const m = Math.max(0, Math.round((Date.parse(iso) - Date.now()) / 6e4)); return m >= 60 ? `${Math.floor(m / 60)}시간 ${m % 60}분` : `${m}분`; };
VIEWS.family = async function family() {
  const admin = canManage(), pet = (S.state.pet && S.state.pet.name) || "반려동물";
  bind({ hero: `초대 링크나 코드를 공유하여 가족과 함께 ${pet}의 조용한 밤과 소중한 일상을 돌보세요.`, code_label: `${pet} 전용 케어 접속 코드`,
    expiry_note: `${pet}의 사생활 보호를 위해 1회 참여 완료 시 발급된 코드는 자동으로 비활성화됩니다.` });
  const toast = (msg) => { $("#toast-message").textContent = msg; swap($("#toast"), "opacity-0", "opacity-100", true); clearTimeout(S.toast); S.toast = setTimeout(() => swap($("#toast"), "opacity-0", "opacity-100", false), 2200); };
  const KEY = "hs_invite";
  let cur = null;
  try { cur = JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (_) { cur = null; }
  const [pending, members] = await Promise.all([admin ? api("/api/invites") : Promise.resolve([]), api("/api/members")]);
  if (cur && !pending.some((p) => p.id === cur.id)) cur = null;  // used, revoked or expired
  const link = () => `${location.origin}/#join/${cur.code}`;
  const paint = () => {
    const k = cur && kst(cur.expires_at);
    bind(cur ? { link_chip: "유효한 초대 링크", url: link(), code: `${cur.code.slice(0, 4)}-${cur.code.slice(4)}`, main_btn: "링크 복사",
      expiry: `24시간 후 만료 (${k.getUTCMonth() + 1}/${k.getUTCDate()} ${pad(k.getUTCHours())}:${pad(k.getUTCMinutes())}까지 유효)` }
      : { link_chip: admin ? "새 초대 링크 만들기" : "관리자만 초대할 수 있어요", url: "아직 만든 초대 링크가 없어요", code: "----", main_btn: "초대 링크 만들기",
        expiry: "만들면 24시간 동안 유효해요" });
    $("#btn-copy-url").disabled = !cur; $("#btn-share-kakao").disabled = !cur; $("#btn-copy-link-main").disabled = !admin;
  };
  const copy = async (msg) => { try { await navigator.clipboard.writeText(link()); toast(msg); } catch (_) { prompt("초대 링크를 복사해 보내주세요", link()); } };
  $("#btn-copy-url").onclick = () => cur && copy("초대 URL이 복사되었습니다");
  $("#btn-copy-link-main").onclick = async () => {
    if (cur) return copy("초대 링크가 복사되었습니다");
    try { cur = await post("/api/invites"); sessionStorage.setItem(KEY, JSON.stringify(cur)); route(); }
    catch (_) { toast("관리자만 초대 링크를 만들 수 있어요"); }
  };
  $("#btn-share-kakao").onclick = async () => {
    if (!cur) return;
    if (navigator.share) { try { await navigator.share({ title: `HomeStudio ${pet} 돌보기 초대`, text: `가족과 함께 ${pet}의 일상을 돌봐요! 초대 코드: ${cur.code}`, url: link() }); } catch (_) { /* cancelled */ } return; }
    copy("공유 링크가 클립보드에 복사되었습니다");
  };
  paint();
  show("pending-sec", admin);
  bind({ pending_count: `${pending.length}건` });
  if (!pending.length) $('[data-tpl="pending"]').outerHTML = '<p class="px-space-xs font-body-sm text-body-sm text-secondary">대기 중인 초대가 없어요.</p>';
  fill("pending", pending, (n, p) => {
    const mine = cur && cur.id === p.id;
    bind({ name: mine ? `가족 초대 ${cur.code.slice(0, 4)}-${cur.code.slice(4)}` : `가족 초대 #${p.id}`, sub: `${p.created_at ? ago(p.created_at) + " 생성 · " : ""}유효시간 ${remain(p.expires_at)} 남음` }, n);
    $("[data-revoke]", n).onclick = async () => {
      if (!confirm("이 초대를 취소할까요? 취소하면 링크와 코드로 더 이상 참여할 수 없어요.")) return;
      await post(`/api/invites/${p.id}/revoke`);
      if (mine) sessionStorage.removeItem(KEY);
      route();
    };
  });
  const me = S.state.user.email, name = (e) => e.split("@")[0];
  bind({ member_count: `${members.filter((m) => m.verified).length}명 활동 중` });
  fill("admin", members.filter((m) => m.role === "owner"), (n, m) => bind({ name: name(m.email), me: m.email === me }, n));
  fill("member", members.filter((m) => m.role !== "owner"), (n, m) => {
    bind({ name: name(m.email), role: m.role === "subadmin" ? "부관리자" : m.verified ? "가족" : "인증 대기", me: m.email === me,
      sub: m.role === "subadmin" ? "구역, 기록 삭제, 초대를 할 수 있어요" : m.verified ? "실시간 화면과 기록을 볼 수 있어요" : "이메일 인증을 기다리고 있어요",
      right: m.role === "subadmin" ? "부관리자" : m.verified ? "보기" : "인증 대기" }, n);
    const box = $("[data-actions]", n);
    const mine = m.email === me;
    const showAct = !mine && (isOwner() || (canManage() && m.role === "member"));
    if (box) box.classList.toggle("hidden", !showAct);
    const hide = (sel, on) => { const b = $(sel, n); if (b) b.classList.toggle("hidden", on); };
    hide("[data-make=subadmin]", !isOwner() || m.role === "subadmin");
    hide("[data-make=member]", !isOwner() || m.role === "member");
    hide("[data-transfer]", !isOwner());
    hide("[data-remove]", mine || m.role === "owner" || !(isOwner() || m.role === "member"));
    const run = async (msg, fn) => { if (!confirm(msg)) return; try { await fn(); route(); } catch (_) { toast("권한을 바꾸지 못했어요"); } };
    const sub = $("[data-make=subadmin]", n), fam = $("[data-make=member]", n), tr = $("[data-transfer]", n), rm = $("[data-remove]", n);
    if (sub) sub.onclick = () => run("부관리자로 바꿀까요? 구역과 기록 삭제를 할 수 있게 돼요.", () => post(`/api/members/${m.user_id}/role`, { role: "subadmin" }));
    if (fam) fam.onclick = () => run("가족 권한으로 바꿀까요? 보기만 할 수 있어요.", () => post(`/api/members/${m.user_id}/role`, { role: "member" }));
    if (tr) tr.onclick = () => run("이 홈스페이스의 대표 관리자를 넘길까요? 넘긴 뒤에는 부관리자로 남아요.", () => post("/api/homespace/transfer", { user_id: m.user_id }));
    if (rm) rm.onclick = () => run("이 가족을 홈스페이스에서 뺄까요? 이 집의 기록은 더 이상 볼 수 없어요.", () => del(`/api/members/${m.user_id}`));
  });
};

// personal-baseline wording (ACTIVITY_HEALTH_GUIDELINES §6: period, direction, data quality, limits, what to check)
function baselineText(b, min, context = {}) {
  const date = context.date || b.date || careToday();
  const live = context.live ?? (date === careToday());
  const cutoff = b.cutoff_h == null || !Number.isFinite(Number(b.cutoff_h)) ? null : Math.max(0, Math.min(24, Number(b.cutoff_h)));
  const now = Number.isFinite(context.now) ? context.now : b.date && cutoff != null ? Date.parse(b.date + "T00:00:00Z") + careHours() * 3600e3 - KST + cutoff * 3600e3 : Date.now();
  const coverage = b.coverage == null || !Number.isFinite(Number(b.coverage)) ? null : Math.round(Number(b.coverage) * 100);
  const valid = b.valid_days == null || !Number.isFinite(Number(b.valid_days)) ? null : Number(b.valid_days);
  const need = b.need_days == null || !Number.isFinite(Number(b.need_days)) ? null : Number(b.need_days);
  if (b.status === "rebuilding" || b.status === "learning") {
    const progress = valid == null || need == null ? "기록 확인 중" : `${valid}/${need}일`;
    const coverageLabel = coverage == null ? "수집률 확인 중" : `${live ? "오늘" : dateLabel(date)} 수집률 ${coverage}%`;
    let nextLabel = "";
    if (live) {
      const since = b.since ? Date.parse(b.since) : NaN;
      if (Number.isFinite(since)) {
        const dayMs = 864e5, startOffset = careHours() * 3600e3;
        const sinceCareMs = since + KST - startOffset, sinceCareDate = iso(new Date(sinceCareMs));
        const phase = ((sinceCareMs % dayMs) + dayMs) % dayMs;
        const exactBoundary = phase === 0;
        let nextDay = addDays(sinceCareDate, exactBoundary ? 1 : 2);
        let nextAt = Date.parse(nextDay + "T00:00:00Z") + startOffset - KST;
        if (nextAt <= now) {
          const currentCareDate = iso(new Date(now + KST - startOffset));
          nextDay = addDays(currentCareDate, 1);
          nextAt = Date.parse(nextDay + "T00:00:00Z") + startOffset - KST;
        }
        nextLabel = ` · 다음 집계 ${dateLabel(nextDay)} ${careStart()}`;
      } else nextLabel = " · 다음 집계 시각 확인 중";
    }
    return { lvl: "비교 준비", title: "평소 활동 패턴을 익히고 있어요", text: `비교 준비 ${progress} · ${coverageLabel}${nextLabel}` };
  }
  const cov = coverage == null ? null : coverage;
  if (b.status === "low_coverage") return { lvl: "데이터 부족", title: "오늘은 데이터가 부족해 비교를 쉬어요", text: cov == null ? "수집 범위를 확인할 수 없어요." : `카메라 수집률 ${cov}% · 끊긴 시간은 기록되지 않은 시간이에요.` };
  if (b.status === "early") return { lvl: "기록 중", title: "아직 비교하기엔 이른 시간이에요", text: `돌봄 하루 ${b.cutoff_h}시간 경과 · 4시간 이후부터 지난 ${valid == null ? "기록" : valid + "일"} 같은 시간대와 비교해요.` };
  if (b.status !== "ready" || !b.metrics?.active_sec || !["low", "high", "usual"].includes(b.metrics.active_sec.flag) || b.metrics.active_sec.median == null) return { lvl: "비교 보류", title: "평소 비교 기준이 부족해 관찰만 기록해요", text: "비교할 수 있는 기록이 모이면 평소와 비교해 드려요." };
  const m = b.metrics.active_sec, sig = b.signals?.[0];
  const pct = m.pct == null ? "" : ` (${m.pct >= 0 ? "+" : ""}${m.pct}%)`;
  const t = { low: ["활동 적음", `평소보다 활동이 적게 관찰됐어요${pct}`], high: ["활동 많음", `평소보다 활발해요${pct}`], usual: ["활동 보통", `평소 범위 안이에요${pct}`] }[m.flag];
  return { lvl: t[0], title: t[1], text: sig ? sig.text : `지난 ${valid}일 같은 시간대 중앙값 ${min(m.median)}분 기준 · 카메라 수집률 ${cov == null ? "확인 중" : cov + "%"}` };
}

// header bell -> notification center, with an unread dot (rules are evaluated server-side on this request)
async function bell() {
  const b = $$("[data-bell]");
  if (!b.length) return;
  b.forEach((x) => (x.onclick = () => go("#notifications")));
  try {
    const n = await api("/api/notifications");
    if (n.unread) b.forEach((x) => { x.classList.add("relative"); x.insertAdjacentHTML("beforeend", '<span class="absolute top-2 right-2 w-2 h-2 rounded-full bg-error"></span>'); });
  } catch (_) { /* logged out */ }
}
const whenLabel = (d) => { const k = kst(d), t = kst(); return (iso(k) === iso(t) ? "오늘 " : `${pad(k.getUTCMonth() + 1)}.${pad(k.getUTCDate())} `) + hhmm(d); };

// PIN keypad (Stitch pin screen): dots grow 4..max, bottom-left key confirms. onDone returns true to clear.
function pinPad(onDone, max = 6) {
  let v = "";
  const draw = () => { $("#pin-dots").innerHTML = Array.from({ length: Math.max(4, v.length) }, (_, i) => `<div class="w-4 h-4 rounded-full transition-all duration-200 ${i < v.length ? "bg-primary scale-110" : "bg-surface-variant"}"></div>`).join(""); };
  $$(".keypad-btn").forEach((b) => { b.disabled = !onDone; b.onclick = () => { if (v.length < max) { v += b.dataset.val; draw(); } }; });
  $("#btn-backspace").disabled = !onDone;
  $("#btn-backspace").onclick = () => { v = v.slice(0, -1); draw(); };
  $("#bio-quick-btn").disabled = !onDone;
  $("#bio-quick-btn").onclick = async () => { if (v.length < 4) return err("pin-error", "PIN 4~6자리를 입력해주세요."); if (await onDone(v)) { v = ""; draw(); } };
  draw();
}

// ---------- shared form helpers ----------
const RULES = { length: (v) => v.length >= 8, upper: (v) => /[A-Z]/.test(v), lower: (v) => /[a-z]/.test(v), digit: (v) => /\d/.test(v), special: (v) => /[!@#$%^&*()\-_=+[\]{};:'",.<>/?\\|`~]/.test(v) };
function pwRules(pw, confirm) {
  const upd = () => {
    let met = 0;
    for (const el of $$("[data-rule]")) {
      const ok = RULES[el.dataset.rule](pw.value); met += ok;
      swap(el, "text-on-surface-variant", "text-primary", ok);
      el.querySelector(".material-symbols-outlined").textContent = ok ? "check_circle" : "radio_button_unchecked";
    }
    const s = $('[data-k="strength"]');
    if (s) s.textContent = pw.value ? `안전 등급: ${["매우 낮음", "매우 낮음", "낮음", "보통", "높음", "매우 높음"][met]}` : "";
    const same = confirm.value && confirm.value === pw.value, hint = $("#match-hint");
    if (hint) {
      show("match-hint", !!confirm.value); show("match-icon", same);
      swap(hint, "text-error", "text-primary", same);
      $("#match-hint-icon").textContent = same ? "check" : "error";
      $('[data-k="match"]').textContent = same ? "두 비밀번호가 완벽히 일치합니다." : "비밀번호가 일치하지 않습니다.";
    }
    return met === 5 && same;
  };
  pw.addEventListener("input", upd); confirm.addEventListener("input", upd);
  return upd;
}
function pwToggle() {
  const b = $("#togglePassword"), i = $("#pwdIcon"), f = $("#password") || $("#user-password");
  if (b) b.onclick = () => { const hid = f.type === "password"; f.type = hid ? "text" : "password"; i.textContent = hid ? "visibility" : "visibility_off"; };
}
async function signupView(inviteRoute, code) {
  const st = S.state, member = st.has_admin || inviteRoute;
  bind({ step: member ? "1/2 단계" : "1/5 단계", cta: member ? "가입하고 이메일 인증 (2/2 단계)" : "다음 (2/5 단계)" });
  $("#step-bar").style.width = member ? "50%" : "20%";
  show("invite-field", member);
  const email = $("#user-email"), pw = $("#user-password"), cf = $("#user-password-confirm"), inv = $("#invite-code");
  const pwOk = pwRules(pw, cf);
  pwToggle();
  if (code) inv.value = decodeURIComponent(code).trim().toUpperCase().slice(0, 8);  // #invite/<code> link autofill
  if (st.user) {  // already signed in on this device: joining needs a fresh session
    err("signup-error", `지금 ${st.user.email}로 로그인돼 있어요. 초대받은 새 계정으로 가입하려면 로그아웃 후 가입해 주세요.`);
    bind({ cta: "로그아웃 후 가입" });
    $("#btn-next").disabled = false;
    $("#btn-next").onclick = async () => { await post("/api/auth/logout"); route(); };
    return;
  }
  const agrees = $$(".agree"), all = $("#agree-all");
  const valid = () => {
    const em = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim());
    show("email-ok", em); show("email-ok-icon", em);
    all.checked = agrees.every((a) => a.checked);
    $("#btn-next").disabled = !(em && pwOk() && all.checked && (!member || inv.value.trim().length === 8));
  };
  all.onchange = () => { agrees.forEach((a) => (a.checked = all.checked)); valid(); };
  agrees.forEach((a) => (a.onchange = valid));
  [email, pw, cf, inv].forEach((el) => el.addEventListener("input", valid));
  valid();
  $("#btn-next").onclick = async () => {
    err("signup-error");
    try {
      await post("/api/auth/signup", { email: email.value, password: pw.value, password_confirm: cf.value,
        agree_terms: $("#agree-terms").checked, agree_privacy: $("#agree-privacy").checked, agree_camera: $("#agree-camera").checked,
        invite_code: member ? inv.value.trim().toUpperCase() : null });
      go("#verify");
    } catch (e) {
      err("signup-error", { 409: "이미 가입된 이메일이에요. 로그인해 주세요.", 403: "유효한 가족 초대 코드가 필요해요. 관리자에게 코드를 받아주세요.", 422: "입력값과 약관 동의를 다시 확인해주세요." }[e.status] || "잠시 후 다시 시도해주세요.");
    }
  };
}

// ---------- global ----------
document.addEventListener("click", (ev) => {
  const menu = $("#more-menu");
  if (menu && !ev.target.closest("#more-menu") && !ev.target.closest("#btn-more")) menu.classList.add("hidden");
  const back = ev.target.closest("[data-back]");
  if (back) {
    ev.preventDefault();
    if (back.dataset.returnRoute) {
      history.replaceState(null, "", back.dataset.returnRoute);
      route();
      return;
    }
    let origin;
    try { origin = JSON.parse(sessionStorage.getItem(TIMELINE_RETURN)); } catch (_) { /* stale session state */ }
    const currentId = decodeURIComponent((location.hash.split("/")[1] || "").split("?")[0]);
    if (back.dataset.timelineDay) {
      const date = origin?.eventId === currentId ? origin.date : back.dataset.timelineDay;
      if (origin?.eventId === currentId) sessionStorage.setItem(TIMELINE_RETURN, JSON.stringify({ date, scrollY: origin.scrollY }));
      history.replaceState(null, "", `#timeline/${date}`); route();
    }
    else if (history.length > 1) history.back();
    else go("#timeline");
    return;
  }
  const d = ev.target.closest("[data-day]");
  if (d && !d.disabled) {
    const [name, arg] = location.hash.slice(1).split("/");
    go(`#${name || "home"}/${addDays(arg || careToday(), +d.dataset.day)}`);
  }
});
addEventListener("hashchange", route);
route();
