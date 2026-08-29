"use strict";
/* Моника 1.0 — фронт. Каркас и стили перенесены из chat.html / login.html /
   index.html Сибериады почти 1:1; привязки переписаны на API Моники. */
const $ = id => document.getElementById(id);
const esc = s => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function api(path, body) {
  const r = await fetch(path, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})
  });
  return {status: r.status, data: await r.json().catch(() => ({}))};
}

function show(id) {
  for (const s of ["scr-login", "scr-wizard", "scr-app"])
    $(s).classList.toggle("hidden", s !== id);
}

/* ── фон: дрейфующая точечная сетка (как в Сибериаде) ── */
function dotsInit() {
  const c = $("dots");
  if (!c) return;
  const ctx = c.getContext("2d");
  let w, h, t = 0;
  function size() { w = c.width = innerWidth; h = c.height = innerHeight; }
  size(); addEventListener("resize", size);
  (function frame() {
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "rgba(255,255,255,.055)";
    const gap = 42;
    t += 0.12;
    for (let x = (t % gap) - gap; x < w; x += gap)
      for (let y = 0; y < h; y += gap) {
        ctx.beginPath();
        ctx.arc(x + Math.sin((y + t) / 60) * 3, y, 1, 0, 7);
        ctx.fill();
      }
    requestAnimationFrame(frame);
  })();
}

/* ── markdown: заголовки/списки/цитаты/код/ссылки ── */
function md(src) {
  let s = esc(src);
  s = s.replace(/```([\s\S]*?)```/g, (m, c) => "<pre><code>" + c.replace(/^\n/, "") + "</code></pre>");
  const out = [];
  let inUl = false, inOl = false;
  const closeL = () => {
    if (inUl) { out.push("</ul>"); inUl = false; }
    if (inOl) { out.push("</ol>"); inOl = false; }
  };
  for (const ln of s.split("\n")) {
    let m;
    if ((m = ln.match(/^###\s+(.*)/))) { closeL(); out.push("<h3>" + inl(m[1]) + "</h3>"); }
    else if ((m = ln.match(/^##\s+(.*)/))) { closeL(); out.push("<h2>" + inl(m[1]) + "</h2>"); }
    else if ((m = ln.match(/^#\s+(.*)/))) { closeL(); out.push("<h2>" + inl(m[1]) + "</h2>"); }
    else if ((m = ln.match(/^&gt;\s?(.*)/))) { closeL(); out.push("<blockquote>" + inl(m[1]) + "</blockquote>"); }
    else if ((m = ln.match(/^[-*]\s+(.*)/))) {
      if (!inUl) { closeL(); out.push("<ul>"); inUl = true; }
      out.push("<li>" + inl(m[1]) + "</li>");
    } else if ((m = ln.match(/^\d+[.)]\s+(.*)/))) {
      if (!inOl) { closeL(); out.push("<ol>"); inOl = true; }
      out.push("<li>" + inl(m[1]) + "</li>");
    } else if (ln.trim() === "") { closeL(); }
    else { closeL(); out.push("<p>" + inl(ln) + "</p>"); }
  }
  closeL();
  return out.join("");
}

function inl(x) {
  return x.replace(/`([^`]+)`/g, (m, c) => "<code>" + c + "</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*\n]+)\*/g, "<i>$1</i>")
    .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

/* ── вход ── */
function renderLogin() {
  show("scr-login");
  /* 6-P: подсказка пароля — только после 3 неудачных попыток подряд с одним юзернеймом */
  let fails = 0, failUser = "";
  $("l-hint").classList.add("hidden");
  $("l-hintbox").innerHTML = "";
  $("l-go").onclick = async () => {
    const u = $("l-user").value.trim();
    const r = await api("/api/login", {username: u, password: $("l-pass").value});
    if (r.data.ok) { boot(); return; }
    $("l-err").textContent = r.data.error || "ошибка";
    if (u === failUser) fails++; else { failUser = u; fails = 1; }
    if (fails >= 3) $("l-hint").classList.remove("hidden");
  };
  $("l-hint").onclick = async () => {
    const r = await api("/api/hint", {username: $("l-user").value.trim()});
    $("l-hintbox").innerHTML = r.data.hint ? "подсказка: " + esc(r.data.hint) : "нет такого пользователя";
  };
  $("l-reg").onclick = () => renderWizard();
}

/* ── онбординг: 7 шагов (порядок Ивана) ── */
const W = {step: 1, source: "", purpose: "", username: "", language: "ru",
  model: "gpt-5.6-luna",
  light: {provider: "glm", api_model: ""},
  smart: {provider: "smart", api_model: ""},
  daily_load: 5, avatar: null,
  modules: {wikipedia: true, telegram: false, analytics: false},
  analytics_unlocked: false, analytics_password: "",
  keys: {glm: "", smart: "", luna: ""}, password: "", hint: ""};
let CFGM = null;
/* 6-O4: провайдеры для кастомных моделей + мета языков (флаги) */
const PROVIDERS = {glm: "GLM", smart: "OpenRouter", luna: "Luna"};
const LANG_META = {ru: ["🇷🇺", "Русский"], ua: ["🇺🇦", "Українська"], en: ["🇬🇧", "English"]};

/* ── Фаза 5-B: реестр моделей во фронте ── */
async function ensureCFGM() {
  if (!CFGM) CFGM = await (await fetch("/api/models")).json();
  return CFGM;
}
function modelName(id) {
  const m = ((CFGM && CFGM.models) || []).find(x => x.id === id);
  return m ? m.name : (id || "?");
}

function renderWizard() {
  show("scr-wizard");
  coreReset(); /* 6-O3: чистое ядро при (пере)входе в визард */
  coreInit();
  /* 8.4: черновик онбординга — вернулся и продолжил с того же шага */
  try {
    const d = JSON.parse(localStorage.getItem("monica_wizard_draft") || "null");
    if (d && d.step >= 1) Object.assign(W, d);
  } catch (e) {}
  W.step = Math.min(Math.max(W.step || 1, 1), 7);
  fetch("/api/models").then(r => r.json()).then(c => { CFGM = c; renderW(); });
}
function wDraftSave() {
  try { localStorage.setItem("monica_wizard_draft", JSON.stringify(W)); } catch (e) {}
}
function wDraftClear() {
  try { localStorage.removeItem("monica_wizard_draft"); } catch (e) {}
}

function wHead(title) {
  /* 6-O3: глиф заменён живым ядром-сценой (#wcore); вспышка бара после ачивки */
  const flash = W.barFlash ? ' class="flash"' : "";
  W.barFlash = false;
  return '<div class="mstep">Шаг ' + W.step + " из 7</div>" +
    '<div class="mbar"><i' + flash + ' style="width:' + (W.step / 7 * 100) + '%"></i></div>' +
    '<div class="mtitle">' + title + "</div>";
}
function wNav() {
  return '<div class="err" id="w-err"></div><div class="row">' +
    (W.step > 1 ? '<button class="mbtn" id="w-back">Назад</button>' : "<span></span>") +
    '<button class="mbtn acc" id="w-next">' + (W.step === 7 ? "Перейти в Монику" : "Далее") + "</button></div>";
}
function wBind(next) {
  $("w-next").onclick = async () => {
    $("w-next").disabled = true;
    const err = await next();
    $("w-next").disabled = false;
    if (err) { $("w-err").textContent = err; return; }
    /* 6-O2: ачивка-тост после ключевых шагов (2/4/5/6) */
    if (ACHV[W.step]) achvToast(ACHV[W.step]);
    W.step++; wDraftSave(); renderW();
  };
  if ($("w-back")) $("w-back").onclick = () => { W.step--; wDraftSave(); renderW(); };
}

/* ── 6-O2: «Ритуал запуска» — сюжетный слайдер онбординга ── */
const HZ = {slide: 0, timer: null, demoDone: false};

function heroGlobeSvg(cls) {
  return '<svg class="globe ' + (cls || "") + '" viewBox="0 0 64 64" aria-hidden="true">' +
    '<defs><clipPath id="wch"><circle cx="32" cy="32" r="27"/></clipPath></defs>' +
    '<circle cx="32" cy="32" r="27" class="g-fill"/>' +
    '<g clip-path="url(#wch)" class="g-line"><circle cx="32" cy="32" r="27"/>' +
    '<ellipse cx="32" cy="32" rx="10" ry="27"/><ellipse cx="32" cy="32" rx="19" ry="27"/>' +
    '<line x1="5" y1="32" x2="59" y2="32"/><line x1="9" y1="18" x2="55" y2="18"/>' +
    '<line x1="9" y1="46" x2="55" y2="46"/></g>' +
    '<g class="g-type"><text x="32" y="40" text-anchor="middle">М</text></g></svg>';
}
function hcard(icon, title, text) {
  return '<div class="hcard"><span class="hico">' + ICO[icon] + "</span>" +
    "<b>" + esc(title) + '</b><span class="sub">' + esc(text) + "</span></div>";
}
function renderHeroSlider(wz) {
  wz.innerHTML =
    '<div class="hero-slider" id="hero-slider">' +
    /* пробуждение: орбиты-«нейроны», parallax от мыши */
    '<div class="hero-orbs" aria-hidden="true"><i class="ho o1"></i><i class="ho o2"></i>' +
    '<i class="ho o3"></i><i class="ho o4"></i></div>' +
    /* сцена 0 — пробуждение */
    '<div class="hslide' + (HZ.slide === 0 ? " on" : "") + '" data-s="0">' +
    '<div class="login-brand hg-wake">' + heroGlobeSvg("hg") + "</div>" +
    "<h2>Пробуждение</h2>" +
    '<p class="sub">Твой цифровой мозг просыпается. Моника соберёт заметки, задачи и идеи в одно спокойное пространство.</p>' +
    '<div class="wz-back-row"><button class="mbtn" id="w-exit">← на главную</button>' +
    '<button class="mbtn acc" id="hz-next">Дальше →</button></div></div>' +
    /* сцена 1 — хаос → порядок */
    '<div class="hslide' + (HZ.slide === 1 ? " on" : "") + '" data-s="1">' +
    '<div class="ill chaos" aria-hidden="true"><i class="cc">заметки</i><i class="cc">задачи</i>' +
    '<i class="cc">идеи</i><i class="cc">встречи</i><i class="cc">проекты</i><i class="cc">теги</i></div>' +
    "<h2>Хаос → порядок</h2>" +
    '<p class="sub">Я превращаю твой хаос из заметок, задач и идей в понятную карту.</p>' +
    '<div class="wz-back-row"><button class="mbtn" id="hz-prev">← Назад</button>' +
    '<button class="mbtn acc" id="hz-next1">Дальше →</button></div></div>' +
    /* сцена 2 — модули станции */
    '<div class="hslide' + (HZ.slide === 2 ? " on" : "") + '" data-s="2">' +
    '<div class="ill dock" aria-hidden="true"><span class="dglobe">' + heroGlobeSvg("hg sm") + "</span>" +
    '<i class="dm d1">Чат</i><i class="dm d2">Вики</i><i class="dm d3">Терминал</i></div>' +
    "<h2>Модули как блоки станции</h2>" +
    '<p class="sub">Ты сам решаешь, из каких модулей собирать свой мозг: чат, вики, терминал, бот.</p>' +
    '<div class="wz-back-row"><button class="mbtn" id="hz-prev2">← Назад</button>' +
    '<button class="mbtn acc" id="hz-next2">Дальше →</button></div></div>' +
    /* сцена 3 — ассистент + живое демо чата */
    '<div class="hslide' + (HZ.slide === 3 ? " on" : "") + '" data-s="3">' +
    '<div class="ill assist" aria-hidden="true"><span class="dglobe nod">' + heroGlobeSvg("hg sm") + "</span>" +
    '<div class="atasks"><i>сводка недели</i><i>напоминание: встреча</i><i>идея → заметка</i></div></div>' +
    "<h2>Персональный ассистент</h2>" +
    '<p class="sub">Я слежу за твоими проектами и напоминаю о важном — бережно и вовремя.</p>' +
    '<div class="hdemo"><div class="hdemo-h">живой пример</div><div class="hdemo-log" id="hdemo-log"></div></div>' +
    '<div class="wz-back-row"><button class="mbtn" id="hz-prev3">← Назад</button>' +
    '<button class="mbtn acc" id="hz-next3">Дальше →</button></div></div>' +
    /* сцена 4 — запуск */
    '<div class="hslide' + (HZ.slide === 4 ? " on" : "") + '" data-s="4">' +
    '<span class="beta-tag">🔒 закрытое тестирование · тестовый режим</span>' +
    "<h2>Запуск</h2>" +
    '<p class="sub">Чтобы всё это работало для тебя — нужно всего пара полей.</p>' +
    '<p class="sub">Нашёл баг или есть идея — пиши автору в Telegram: <a href="https://t.me/sozrelyy" target="_blank" rel="noopener">@sozrelyy</a>.</p>' +
    '<div class="wz-back-row"><button class="mbtn" id="hz-prev4">← Назад</button>' +
    '<button class="mbtn acc" id="w-next">Начать регистрацию →</button></div></div>' +
    "</div>" +
    '<div class="hero-dots">' + [0, 1, 2, 3, 4].map(i =>
      '<span class="hdot' + (HZ.slide === i ? " on" : "") + '" data-d="' + i + '"></span>').join("") + "</div>";
  /* 6.4: возврат на главную (черновик сохраняется) */
  $("w-exit").onclick = () => { wDraftSave(); renderLogin(); };
  const go = n => {
    HZ.slide = Math.max(0, Math.min(4, n));
    wz.querySelectorAll(".hslide").forEach(s => s.classList.toggle("on", +s.dataset.s === HZ.slide));
    wz.querySelectorAll(".hdot").forEach(d => d.classList.toggle("on", +d.dataset.d === HZ.slide));
    if (HZ.slide === 3) setTimeout(heroDemoRun, 350);
  };
  /* $() ждёт голый id — срезаем ведущий "#" (без этого кнопки слайдера мертвы) */
  const bind = (id, fn) => { const el = $(id.replace(/^#/, "")); if (el) el.onclick = fn; };
  /* баг-1: «Назад» на сцене пробуждения — явная привязка (дублирует w-exit) */
  bind("#w-exit", () => { wDraftSave(); renderLogin(); });
  bind("#hz-next", () => go(HZ.slide + 1));
  bind("#hz-next1", () => go(HZ.slide + 1));
  bind("#hz-next2", () => go(HZ.slide + 1));
  bind("#hz-next3", () => go(HZ.slide + 1));
  bind("#hz-prev", () => go(HZ.slide - 1));
  bind("#hz-prev2", () => go(HZ.slide - 1));
  bind("#hz-prev3", () => go(HZ.slide - 1));
  /* слайд «Запуск» → шаг 2 визарда */
  bind("#w-next", () => { W.step = 2; wDraftSave(); renderW(); });
  wz.querySelectorAll(".hdot").forEach(d =>
    d.onclick = () => go(+d.dataset.d));
  /* 6-O2: parallax орбит от мыши (off при reduced-motion) */
  const sl = $("hero-slider");
  if (sl && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    sl.addEventListener("mousemove", e => {
      const r = sl.getBoundingClientRect();
      sl.style.setProperty("--mx", ((e.clientX - r.left) / r.width - .5).toFixed(3));
      sl.style.setProperty("--my", ((e.clientY - r.top) / r.height - .5).toFixed(3));
    });
  }
  /* автопрокрутка со сцены пробуждения */
  if (HZ.timer) { clearTimeout(HZ.timer); HZ.timer = null; }
  if (HZ.slide === 0 &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    HZ.timer = setTimeout(() => {
      if (W.step === 1 && HZ.slide === 0) go(1);
    }, 5000);
  }
  if (HZ.slide === 3) setTimeout(heroDemoRun, 350);
}
function heroDemoRun() {
  const log = $("hdemo-log");
  if (!log || HZ.demoDone) return;
  HZ.demoDone = true;
  const script = [
    ["user", "Моника, что у меня в заметках на этой неделе?"],
    ["bot", "План на неделю, 3 встречи и заметка про флот 📋 Хочешь — соберу краткую сводку."]
  ];
  let i = 0;
  const next = () => {
    if (i >= script.length || !$("hdemo-log")) return;
    const role = script[i][0], text = script[i][1];
    const d = document.createElement("div");
    d.className = "hdemo-msg " + role;
    $("hdemo-log").appendChild(d);
    let k = 0;
    const t = setInterval(() => {
      const log = $("hdemo-log");
      if (!log || !d.isConnected) { clearInterval(t); return; } /* ушли со слайда */
      d.textContent = text.slice(0, ++k);
      log.scrollTop = log.scrollHeight;
      if (k >= text.length) { clearInterval(t); i++; setTimeout(next, 450); }
    }, 22);
  };
  next();
}

/* ── 6-O2 часть 2: ачивки-тосты, «поле → ядро», финальный запуск ── */
const ACHV = {2: "Мозг запомнил, откуда ты", 4: "Мозг выбрал основную модель",
  5: "Модули пристыкованы к станции", 6: "Каналы связи активированы"};
let achvT = null;
function achvToast(text) {
  const old = document.querySelector(".achv");
  if (old) old.remove();
  if (achvT) clearTimeout(achvT);
  const d = document.createElement("div");
  d.className = "achv";
  d.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
    'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/>' +
    '<path d="M8 12.5l2.7 2.7L16 9.5"/></svg>' + esc(text);
  document.body.appendChild(d);
  W.barFlash = true; /* вспышка прогресс-бара на следующем шаге */
  achvT = setTimeout(() => {
    d.classList.add("hide");
    achvT = setTimeout(() => d.remove(), 340);
  }, 2000);
}
/* ── 6-O3: «Живое ядро» — сквозная сцена визарда (plans/6-O3-living-core-concept.md) ── */
const WCORE_PAL = ["#8fb4ff", "#b9a3ff", "#d0a04a", "#6be08a", "#e06c75", "#8b96a3"];
const MOD_NAMES = {wikipedia: "Википедия", telegram: "Telegram-бот", analytics: "Аналитика"};
const CORE_CAP = {2: "ядро запоминает источник", 3: "ядро узнаёт тебя",
  4: "настройка мощности", 5: "стыковка модулей", 6: "каналы связи", 7: "защита ядра"};
const CORE = {sats: {}};
function coreInit() {
  const c = $("wcore");
  if (!c || c.dataset.ready) return;
  c.dataset.ready = "1";
  c.innerHTML = '<div class="wcore-scene"><div class="wcore-orb" id="wcore-orb">' +
    '<i class="ho o1"></i><i class="ho o2"></i><span class="wcore-glow"></span>' +
    '<span class="wcore-globe">' + heroGlobeSvg("") + "</span>" +
    '<img class="wcore-ava" id="wcore-ava" alt="" hidden>' +
    '<span class="wcore-ring" id="wcore-ring"></span>' +
    '<span class="wcore-shield" id="wcore-shield"></span>' +
    '<span class="wsat" data-slot="0"></span><span class="wsat" data-slot="1"></span>' +
    '<span class="wsat" data-slot="2"></span></div>' +
    '<div class="wcore-cap" id="wcore-cap"></div></div>';
}
function coreReset() {
  CORE.sats = {};
  document.querySelectorAll("#wcore .wsat").forEach(s => { s.className = "wsat"; s.textContent = ""; });
  setRing(null); setShield(false); setCoreGlow(0); coreListen(false);
  const a = $("wcore-ava");
  if (a) { a.hidden = true; a.removeAttribute("src"); }
}
function coreShowStep() {
  const c = $("wcore");
  if (!c) return;
  c.classList.toggle("off", W.step <= 1);
  if (W.step <= 1) return;
  coreCaption(CORE_CAP[W.step] || "");
  /* восстановление состояния ядра из черновика (мгновенно, без полётов) */
  if (W.step === 4 && W.model) {
    const i = ((CFGM && CFGM.models) || []).findIndex(m => m.id === W.model);
    setRing(WCORE_PAL[(i < 0 ? 0 : i) % WCORE_PAL.length]);
    setCoreGlow((W.daily_load - 1) / 9);
  }
  if (W.step === 5) {
    Object.keys(MOD_NAMES).forEach(k => {
      if (W.modules[k]) addSatellite(MOD_NAMES[k], true); else removeSatellite(MOD_NAMES[k]);
    });
  }
}
function coreCaption(t) { const el = $("wcore-cap"); if (el) el.textContent = t || ""; }
function coreFlash() {
  const o = $("wcore-orb");
  if (!o || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  o.classList.remove("core-flash"); void o.offsetWidth; o.classList.add("core-flash");
  setTimeout(() => o.classList.remove("core-flash"), 520);
}
function setCoreGlow(v) {
  const o = $("wcore-orb");
  if (o) o.style.setProperty("--core-glow", String(Math.max(0, Math.min(1, v))));
}
function coreListen(on) { const o = $("wcore-orb"); if (o) o.classList.toggle("listen", !!on); }
function setRing(color) {
  const r = $("wcore-ring");
  if (!r) return;
  if (color) { r.style.borderColor = color; r.classList.add("on"); }
  else { r.classList.remove("on"); r.style.borderColor = ""; }
}
function setShield(on) { const s = $("wcore-shield"); if (s) s.classList.toggle("on", !!on); }
function coreAvatar(dataUrl) {
  /* баг-5: аватар замощает глобус и остаётся до конца регистрации */
  const a = $("wcore-ava"), o = $("wcore-orb");
  if (!a || !o || !dataUrl) return;
  a.src = dataUrl; a.hidden = false; o.classList.add("show-ava");
}
/* полёт точки «действие → ядро» (шаги 2/3/4/6) */
function coreFly(fromEl, cls) {
  const o = $("wcore-orb");
  if (!fromEl || !o || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const a = fromEl.getBoundingClientRect(), b = o.getBoundingClientRect();
  const dot = document.createElement("i");
  dot.className = "core-fly " + (cls || "");
  dot.style.left = (a.left + a.width / 2) + "px";
  dot.style.top = (a.top + a.height / 2) + "px";
  document.body.appendChild(dot);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    dot.style.transform = "translate(" + (b.left + b.width / 2 - a.left - a.width / 2) + "px," +
      (b.top + b.height / 2 - a.top - a.height / 2) + "px) scale(.25)";
    dot.style.opacity = ".1";
  }));
  setTimeout(() => { dot.remove(); coreFlash(); }, 640);
}
/* спутники-модули на орбите ядра (шаг 5) */
function addSatellite(name, instant, fromEl) {
  if (CORE.sats[name] !== undefined) return;
  const used = Object.values(CORE.sats);
  const slot = [0, 1, 2].find(i => !used.includes(i));
  if (slot === undefined) return;
  CORE.sats[name] = slot;
  const s = document.querySelector('.wsat[data-slot="' + slot + '"]');
  if (!s) return;
  s.textContent = name;
  if (!instant && fromEl) coreFly(fromEl);
  s.classList.add("filled");
}
function removeSatellite(name) {
  const slot = CORE.sats[name];
  if (slot === undefined) return;
  delete CORE.sats[name];
  const s = document.querySelector('.wsat[data-slot="' + slot + '"]');
  if (!s) return;
  s.classList.add("bye");
  setTimeout(() => { s.classList.remove("filled", "bye"); s.textContent = ""; }, 380);
}
/* финальный запуск: отсчёт 3..2..1 → конфетти → «Вы зарегистрировались!» → чат */
function launchFinale() {
  const orb = $("wcore-orb");
  if (orb) orb.classList.add("gather");
  const f = document.createElement("div");
  f.id = "finale";
  f.innerHTML = '<div class="fin-orbs" aria-hidden="true"><i class="ho o1"></i>' +
    '<i class="ho o2"></i><i class="ho o3"></i></div>' +
    '<div class="fin-core">' + heroGlobeSvg("fin") + "</div>" +
    '<div class="fin-count" id="fin-count">3</div>' +
    '<div class="fin-t hidden" id="fin-t"></div>' +
    '<div class="fin-confetti" id="fin-conf"></div>';
  document.body.appendChild(f);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let n = 3;
  const tick = () => {
    const c = $("fin-count");
    if (!c) return;
    if (n > 0) { c.textContent = n--; setTimeout(tick, 700); return; }
    /* барабанная дробь → конфетти + приветствие */
    c.classList.add("hidden");
    const t = $("fin-t");
    t.classList.remove("hidden");
    t.innerHTML = "🎉 Вы зарегистрировались!<br><b>Ура, " + esc(W.username) + "</b> — спасибо!";
    if (!reduced) confettiBurst();
    setTimeout(() => f.classList.add("out"), reduced ? 1200 : 2600);
    setTimeout(() => { f.remove(); boot(); }, reduced ? 2600 : 2900);
  };
  setTimeout(tick, orb ? 420 : 0);
}
function confettiBurst() {
  const box = $("fin-conf");
  if (!box) return;
  const colors = ["#8fb4ff", "#b9a3ff", "#d0a04a", "#6be08a", "#e06c75"];
  for (let i = 0; i < 46; i++) {
    const p = document.createElement("i");
    p.style.left = (50 + (Math.random() * 30 - 15)) + "%";
    p.style.background = colors[i % colors.length];
    p.style.animationDelay = (Math.random() * .5) + "s";
    p.style.animationDuration = (1.6 + Math.random() * 1.4) + "s";
    p.style.setProperty("--cx", (Math.random() * 2 - 1).toFixed(2));
    p.style.setProperty("--rot", (Math.random() * 720 - 360) + "deg");
    box.appendChild(p);
  }
}

function renderW() {
  const wz = $("wz");
  /* баг-2: каскад и .wz-in — только при смене шага, не при перерисовке выбора */
  const stepChanged = wz.dataset.step !== String(W.step);
  wz.dataset.step = String(W.step);
  wz.classList.toggle("wz-anim", stepChanged);
  coreShowStep(); /* 6-O3: ядро живёт на шагах 2–7 */
  if (W.step === 1) {
    /* 6-O: онбординг 2.0 — слайдер-презентация продукта */
    renderHeroSlider(wz);
  } else if (W.step === 2) {
    wz.innerHTML = wHead("Пара вопросов") +
      '<label>Откуда вы узнали о нас?</label><div id="w-src"></div>' +
      '<label>Для чего хочешь использовать Монику? (опционально)</label><div id="w-pur"></div>' + wNav();
    const chips = (arr, box, cur, set) => {
      $(box).innerHTML = arr.filter(Boolean).map(x =>
        '<span class="chip' + (cur === x ? " sel" : "") + '" data-x="' + x + '">' + x + "</span>").join("");
      $(box).querySelectorAll(".chip").forEach(c => c.onclick = () => {
        if (set === "src") { W.source = c.dataset.x; coreFly(c); } /* 6-O3: нейрон в ядро */
        else W.purpose = (W.purpose === c.dataset.x) ? "" : c.dataset.x;
        renderW();
      });
    };
    chips(CFGM.sources, "w-src", W.source, "src");
    chips(CFGM.purposes, "w-pur", W.purpose, "pur");
    wBind(async () => W.source ? null : "выбери, откуда ты о нас узнал(а)");
  } else if (W.step === 3) {
    wz.innerHTML = wHead("Профиль") +
      '<label>Юзернейм (латиница, 3-24)</label><input class="minput" id="w-user" type="text" value="' + W.username + '">' +
      /* баг-3/4: стилизованный выбор языка с флагами вместо нативного select */
      '<label>Язык интерфейса</label><div id="w-lang" class="langrow">' +
      CFGM.languages.map(l => {
        const f = LANG_META[l] || ["🏳️", l];
        return '<span class="chip' + (W.language === l ? " sel" : "") + '" data-l="' + l + '">' +
          f[0] + " " + f[1] + "</span>";
      }).join("") + "</div>" +
      '<label>Аватарка (необязательно, до 300 КБ)</label><input id="w-ava" type="file" accept="image/png,image/jpeg">' + wNav();
    $("w-lang").querySelectorAll(".chip").forEach(c =>
      c.onclick = () => { W.language = c.dataset.l; renderW(); });
    $("w-ava").onchange = () => {
      const f = $("w-ava").files[0];
      if (!f) return;
      if (f.size > 300 * 1024) { $("w-err").textContent = "файл больше 300 КБ"; return; }
      const rd = new FileReader();
      rd.onload = () => { W.avatar = rd.result; $("w-err").textContent = ""; coreAvatar(W.avatar); };
      rd.readAsDataURL(f);
    };
    /* 6-O3: ядро «прислушивается» в фокусе; blur заполненного — нейрон в ядро */
    $("w-user").addEventListener("focus", () => coreListen(true));
    $("w-user").addEventListener("blur", () => {
      coreListen(false);
      if ($("w-user").value.trim()) coreFly($("w-user"));
    });
    wBind(async () => {
      W.username = $("w-user").value.trim();
      const r = await api("/api/check-username", {username: W.username});
      return r.data.ok ? null : (r.data.error || "юзернейм не подходит");
    });
  } else if (W.step === 4) {
    /* 6-O4: пара «лёгкая + сложная» модель — провайдер + ручной api_model */
    wz.innerHTML = wHead("Модели") +
      '<div class="mod2"><div class="modcol"><div class="t">⚡ Лёгкая модель</div>' +
      '<div class="d">повседневное общение в чате</div>' +
      '<div class="provrow" data-k="light">' + Object.keys(PROVIDERS).map(p =>
        '<span class="chip' + (W.light.provider === p ? " sel" : "") + '" data-p="' + p + '">' + PROVIDERS[p] + "</span>").join("") + "</div>" +
      '<input class="minput" id="w-light-m" placeholder="id модели у провайдера, напр. glm-5.3-fast" value="' + esc(W.light.api_model) + '"></div>' +
      '<div class="modcol"><div class="t">🧠 Сложная модель</div>' +
      '<div class="d">хранилище, терминал и режим pro</div>' +
      '<div class="provrow" data-k="smart">' + Object.keys(PROVIDERS).map(p =>
        '<span class="chip' + (W.smart.provider === p ? " sel" : "") + '" data-p="' + p + '">' + PROVIDERS[p] + "</span>").join("") + "</div>" +
      '<input class="minput" id="w-smart-m" placeholder="id модели у провайдера (напр. openrouter/auto)" value="' + esc(W.smart.api_model) + '"></div></div>' +
      '<label>Сколько информации планируешь заносить в день</label>' +
      '<input type="range" id="w-load" min="1" max="10" value="' + W.daily_load + '">' +
      '<div class="sub">нагрузка: <b id="w-lv">' + W.daily_load + "</b>/10</div>" + wNav();
    ["light", "smart"].forEach(k => {
      wz.querySelector('[data-k="' + k + '"]').querySelectorAll(".chip").forEach(c =>
        c.onclick = () => { W[k].provider = c.dataset.p; renderW(); });
    });
    $("w-light-m").oninput = () => W.light.api_model = $("w-light-m").value.trim();
    $("w-smart-m").oninput = () => W.smart.api_model = $("w-smart-m").value.trim();
    $("w-load").oninput = () => {
      W.daily_load = +$("w-load").value; $("w-lv").textContent = W.daily_load;
      setCoreGlow((W.daily_load - 1) / 9); /* 6-O3: свечение = нагрузка */
    };
    wBind(async () => {
      W.light.api_model = $("w-light-m").value.trim();
      W.smart.api_model = $("w-smart-m").value.trim();
      if (!W.light.api_model) return "впиши id лёгкой модели (например glm-5.3-fast)";
      if (!W.smart.api_model) return "впиши id сложной модели (напр. openrouter/auto)";
      return null;
    });
  } else if (W.step === 5) {
    const names = {wikipedia: ["Википедия", "поиск по твоим заметкам, сводки, выжимки"],
      telegram: ["Telegram-бот", "мысли, голосовые, файлы — прямо в базу"],
      analytics: ["Полная аналитика", "экспериментальный модуль. По умолчанию выключен."]};
    wz.innerHTML = wHead("Модули") +
      Object.keys(names).map(k => '<div class="mod"><div><div class="t">' + names[k][0] +
        '</div><div class="d">' + names[k][1] + '</div></div>' +
        '<button class="cs-sw' + (W.modules[k] ? " on" : "") + '" data-m="' + k + '"></button></div>').join("") +
      '<div id="w-modx"></div>' + wNav();
    wz.querySelectorAll(".cs-sw").forEach(t => t.onclick = async () => {
      const m = t.dataset.m;
      if (m === "analytics" && !W.modules.analytics) {
        const pass = prompt("Модуль сырой и может зацеплять данные других людей. Доступ только в рамках закрытого тестирования.\n\nПароль:");
        if (pass === null) return;
        const r = await api("/api/analytics/check", {password: pass});
        if (!r.data.ok) { $("w-modx").innerHTML = '<div class="err">неверный пароль</div>'; return; }
        W.analytics_unlocked = true; W.analytics_password = pass;
        $("w-modx").innerHTML = '<div class="warn">Разблокировано. Работаем только с твоими данными.</div>';
      }
      W.modules[m] = !W.modules[m];
      t.className = "cs-sw" + (W.modules[m] ? " on" : "");
      /* 6-O3: модуль пристыковывается/отстыковывается на орбите ядра */
      if (W.modules[m]) addSatellite(MOD_NAMES[m], false, t);
      else removeSatellite(MOD_NAMES[m]);
    });
    wBind(async () => null);
  } else if (W.step === 6) {
    /* Фаза 5-B: подписи ключей из реестра моделей (без хардкода ox alpha) */
    const ks = CFGM.key_labels ||
      {glm: ["GLM 5.3 Fast", "терминал и быстрые операции"],
       smart: ["OpenRouter", "глубокие модели для second-brain"],
       luna: ["ChatGPT 5.6 Luna", "Telegram-бот и чат на сайте"]};
    wz.innerHTML = wHead("API-ключи") +
      '<p class="sub">Ключи шифруются, каждый сервис изолирован. В закрытой бете обязательны.</p>' +
      Object.keys(ks).map(k => '<label>' + ks[k][0] + ' — ' + ks[k][1] + '</label>' +
        '<input class="minput" type="password" id="k-' + k + '">').join("") + wNav();
    for (const k of Object.keys(ks)) {
      const inp = $("k-" + k);
      inp.value = W.keys[k];
      /* 6-O3: канал связи — ключ ≥8 символов испускает золотой нейрон */
      inp.addEventListener("input", () => {
        const full = inp.value.trim().length >= 8;
        if (full && !inp.dataset.chan) { inp.dataset.chan = "1"; coreFly(inp, "chan"); }
        if (!full && inp.dataset.chan) inp.dataset.chan = "";
      });
    }
    wBind(async () => {
      for (const k of Object.keys(ks)) W.keys[k] = $("k-" + k).value.trim();
      const miss = Object.keys(W.keys).filter(k => W.keys[k].length < 8);
      return miss.length ? "заполни ключи: " + miss.join(", ") : null;
    });
  } else {
    wz.innerHTML = wHead("Почти готово") +
      '<label>Пароль (мин. 6 символов)</label><input class="minput" type="password" id="w-pass">' +
      '<label>Подсказка к паролю</label><input class="minput" id="w-hint" value="' + W.hint + '">' +
      '<div class="sum">Юзернейм: <b>' + W.username + '</b><br>Откуда: <b>' + (W.source || "-") +
      '</b> · модели: <b>' + W.light.provider + "/" + W.light.api_model + " + " +
      W.smart.provider + "/" + W.smart.api_model + '</b> · нагрузка: <b>' + W.daily_load + '/10</b><br>Модули: <b>' +
      Object.keys(W.modules).filter(k => W.modules[k]).join(", ") + '</b><br>Ключи: <b>' +
      Object.keys(W.keys).filter(k => W.keys[k]).join(", ") + "</b></div>" + wNav();
    $("w-hint").oninput = () => W.hint = $("w-hint").value;
    /* 6-O3: щит ядра при работе с паролем */
    $("w-pass").addEventListener("focus", () => setShield(true));
    $("w-pass").addEventListener("blur", () => setShield(false));
    wBind(async () => {
      W.password = $("w-pass").value;
      if (W.password.length < 6) return "пароль: минимум 6 символов";
      const r = await api("/api/onboarding/complete", {
        username: W.username, password: W.password, hint: W.hint, avatar: W.avatar,
        survey: {source: W.source, purpose: W.purpose},
        prefs: {language: W.language, model: W.model, daily_load: W.daily_load,
          light: W.light, smart: W.smart},
        modules: W.modules, analytics_password: W.analytics_password, keys: W.keys});
      if (r.data.ok) { wDraftClear(); launchFinale(); return null; }
      return r.data.error || "ошибка сохранения";
    });
  }
  /* Фаза 5-C: плавный переход между шагами (slide+fade) */
  wz.classList.remove("wz-in");
  void wz.offsetWidth;
  wz.classList.add("wz-in");
}

/* ── каркас приложения (скелет chat.html) ── */
/* SVG-иконки — в стиле stroke-иконок chat.html Сибериады */
const ICO = {
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.3c-1.4 0-2.7-.3-3.9-.9L3 20l1.2-4.3a8.1 8.1 0 0 1-1.2-4.2A8.4 8.4 0 0 1 11.5 3.2a8.4 8.4 0 0 1 9.5 8.3z"/><path d="M8.5 10.5h7M8.5 13.5h4.5"/></svg>',
  term: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 9l3 3-3 3M13 15h4"/></svg>',
  wiki: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/><path d="M9 7h7M9 10.5h5"/></svg>',
  tg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13M22 2 15 22l-4-9-9-4 20-7z"/></svg>',
  ana: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M3 21h18"/><path d="M6 17V9M11 17V5M16 17v-6M21 17v-3" transform="translate(-1.5 0)"/></svg>',
  set: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M21 12h-2.5M5.5 12H3M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8M18.4 18.4l-1.8-1.8M7.4 7.4L5.6 5.6"/></svg>',
};
const SEND_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M12 5.5 18.5 12 12 18.5"/></svg>';
const NAV = [
  ["chat", "Чат"],
  ["term", "Терминал"],
  ["wiki", "Википедия"],
  ["tg", "Бот"],
  ["ana", "Аналитика"],
  ["set", "Настройки"],
];
const TITLES = {chat: "Чат с Моникой", term: "Терминал", wiki: "Википедия",
  tg: "Telegram-бот", ana: "Полная аналитика", set: "Настройки"};
let ME = null, TAB = "chat", CHAT_HIST = [];

/* ── 5-H.7: сессии чата — localStorage, только фронт (бэкенд не тронут) ── */
let SESS = {list: [], cur: null};
function sessKey() { return "monica_sess_" + ((ME && ME.username) || "anon"); }
function sessLoad() {
  try { SESS.list = JSON.parse(localStorage.getItem(sessKey()) || "[]") || []; }
  catch (e) { SESS.list = []; }
  SESS.cur = null;
}
function sessSave() {
  try { localStorage.setItem(sessKey(), JSON.stringify(SESS.list.slice(-30))); } catch (e) {}
}
function sessEnsure() {
  if (!SESS.cur) {
    /* баг-13: сессия, созданная внутри проекта, наследует его; баг-18: сразу в списке */
    SESS.cur = {id: Date.now(), title: "Новая сессия",
      started: new Date().toISOString(),
      ts: new Date().toLocaleString("ru-RU", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"}),
      pinned: false, projId: PROJ.filter, msgs: []};
    SESS.list.push(SESS.cur);
    sessSave();
    drawSess();
  }
  return SESS.cur;
}

/* ── 6-S: проекты сессий (localStorage; общая инструкция уходит на бэкенд) ── */
const PROJ_COLORS = ["#8fb4ff", "#b9a3ff", "#d0a04a", "#6be08a", "#e06c75", "#8b96a3"];
let PROJ = {list: [], filter: null};
function projKey() { return "monica_proj_" + ((ME && ME.username) || "anon"); }
function projLoad() {
  try { PROJ.list = JSON.parse(localStorage.getItem(projKey()) || "[]") || []; }
  catch (e) { PROJ.list = []; }
  PROJ.filter = null;
}
function projSave() {
  try { localStorage.setItem(projKey(), JSON.stringify(PROJ.list)); } catch (e) {}
}
function projById(id) { return PROJ.list.find(p => p.id === id); }
function curInstr() {
  const s = SESS.cur;
  const p = s && s.projId ? projById(s.projId) : null;
  return p ? (p.instruction || "") : "";
}
function drawProj() {
  const box = $("cs-proj");
  if (!box) return;
  box.innerHTML = PROJ.list.map(p =>
    '<div class="projrow' + (PROJ.filter === p.id ? " on" : "") + '" data-id="' + p.id + '" ' +
    'title="' + esc(p.instruction || "инструкция не задана") + '">' +
    '<span class="pdot" style="background:' + p.color + '"></span>' +
    '<span class="pem">' + esc(p.emoji || "📁") + "</span>" +
    '<span class="pn">' + esc(p.name) + "</span>" +
    '<span class="px" data-del="' + p.id + '" title="удалить проект (сессии сохранятся)">×</span></div>').join("") ||
    '<div class="sub" style="padding:2px">проектов нет</div>';
  box.querySelectorAll(".projrow").forEach(row => {
    const id = +row.dataset.id;
    row.onclick = e => {
      if (e.target.dataset.del) return;
      openProjPage(id); /* 6-S2: клик по проекту открывает его страницу */
    };
    const del = row.querySelector(".px");
    if (del) del.onclick = e => {
      e.stopPropagation();
      if (!confirm("Удалить проект? Сессии останутся, но без проекта.")) return;
      PROJ.list = PROJ.list.filter(p => p.id !== id);
      SESS.list.forEach(s => { if (s.projId === id) s.projId = null; });
      if (PROJ.filter === id) PROJ.filter = null;
      projSave();
      sessSave();
      drawProj();
      drawSess();
    };
  });
}

/* 6-S2: модальное окно создания/настройки проекта (вместо browser-prompt) */
function projModal(p, onSaved) {
  closeSessMenu();
  const isNew = !p;
  const ov = document.createElement("div");
  ov.className = "modal-ov";
  ov.innerHTML =
    '<div class="modal"><h3>' + (isNew ? "Новый проект" : "Настройки проекта") + "</h3>" +
    '<label>Название</label><input class="minput" id="pm-name" value="' + esc(p ? p.name : "") + '">' +
    '<label>Эмодзи / символ</label><input class="minput" id="pm-emoji" style="width:90px;text-align:center" value="' + esc(p ? p.emoji : "📁") + '">' +
    "<label>Цвет</label><div class=\"swatches\">" +
    PROJ_COLORS.map(c => '<span class="swatch' + ((p ? p.color : PROJ_COLORS[0]) === c ? " on" : "") +
      '" data-c="' + c + '" style="background:' + c + '"></span>').join("") + "</div>" +
    '<label>Общая инструкция для Моники</label>' +
    '<textarea class="minput" id="pm-instr" rows="3" style="height:auto;line-height:1.45;resize:none" ' +
    'placeholder="например: мы учим английский — отвечай частью на английском">' + esc(p ? p.instruction : "") + "</textarea>" +
    '<div class="row" style="justify-content:flex-end">' +
    '<button class="mbtn" id="pm-cancel">Отмена</button>' +
    '<button class="mbtn acc" id="pm-save">' + (isNew ? "Создать" : "Сохранить") + "</button></div></div>";
  document.body.appendChild(ov);
  let color = p ? p.color : PROJ_COLORS[0];
  ov.querySelectorAll(".swatch").forEach(s => s.onclick = () => {
    color = s.dataset.c;
    ov.querySelectorAll(".swatch").forEach(x => x.classList.toggle("on", x === s));
  });
  ov.querySelector("#pm-cancel").onclick = () => ov.remove();
  ov.onclick = e => { if (e.target === ov) ov.remove(); };
  ov.querySelector("#pm-save").onclick = () => {
    const nameEl = ov.querySelector("#pm-name");
    const name = nameEl.value.trim();
    if (!name) { nameEl.style.borderColor = "var(--red)"; return; }
    const rec = {name: name.slice(0, 40),
      emoji: ov.querySelector("#pm-emoji").value.trim().slice(0, 4) || "📁",
      color: color,
      instruction: ov.querySelector("#pm-instr").value.trim().slice(0, 500)};
    if (isNew) PROJ.list.push(Object.assign({id: Date.now()}, rec));
    else Object.assign(p, rec);
    projSave();
    ov.remove();
    drawProj();
    if (onSaved) onSaved();
  };
}

/* 6-S2: страница проекта — карточки сессий (как в ChatGPT) */
function openProjPage(id) {
  const p = projById(id);
  if (!p) return;
  TAB = "proj";
  document.querySelectorAll(".cs-navitem").forEach(x => x.classList.remove("on"));
  const shell = document.querySelector(".cs");
  if (shell) shell.classList.remove("term-wide");
  const sessions = SESS.list.filter(s => s.projId === id)
    .sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || b.id - a.id);
  $("m-title").textContent = p.name;
  $("m-sub").textContent = "проект · сессий: " + sessions.length;
  $("m-body").innerHTML =
    '<div class="tab-in">' +
    '<div class="pc-head">' +
    '<span class="pc-emoji" style="border-color:' + p.color + ';color:' + p.color + '">' + esc(p.emoji || "📁") + "</span>" +
    '<div class="pc-name"><h2 class="wk-h" style="margin:0">' + esc(p.name) + "</h2>" +
    (p.instruction ? '<div class="sub">' + esc(p.instruction) + "</div>" : "") + "</div>" +
    '<button type="button" class="cs-act" id="pp-settings">Настройки проекта</button>' +
    '<button type="button" class="cs-act" id="pp-back">← к чату</button></div>' +
    '<div class="pcard-grid">' +
    '<button type="button" class="pcard new" id="pp-new"><span class="plus">＋</span>Новая сессия</button>' +
    sessions.map(s =>
      '<button type="button" class="pcard" data-id="' + s.id + '">' +
      (s.pinned ? '<span class="pc-pin" title="закреплена">📌</span>' : "") +
      '<span class="t">' + esc(s.title || "Новая сессия") + "</span>" +
      '<span class="d">' + (s.started ? new Date(s.started).toLocaleDateString("ru-RU", {day: "numeric", month: "long"}) : "") +
      " · реплик: " + s.msgs.length + "</span></button>").join("") +
    "</div></div>";
  $("pp-back").onclick = () => openTab("chat");
  $("pp-settings").onclick = () => projModal(p, () => openProjPage(id));
  $("pp-new").onclick = () => {
    /* баг-17: сессия создаётся сразу в проекте и остаётся в списке */
    const s = {id: Date.now(), title: "Новая сессия",
      started: new Date().toISOString(),
      ts: new Date().toLocaleString("ru-RU", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"}),
      pinned: false, projId: id, msgs: []};
    SESS.list.push(s);
    sessSave();
    openSess(s.id);
  };
  $("m-body").querySelectorAll(".pcard[data-id]").forEach(c =>
    c.onclick = () => openSess(+c.dataset.id));
}
function closeSessMenu() {
  const m = document.querySelector(".sessmenu");
  if (m) m.remove();
}
function sessMenu(id, anchor) {
  closeSessMenu();
  const s = SESS.list.find(x => x.id === id);
  if (!s) return;
  const p = s.projId ? projById(s.projId) : null;
  const m = document.createElement("div");
  m.className = "sessmenu";
  let html = '<button data-a="rename">Переименовать</button>' +
    '<button data-a="pin">' + (s.pinned ? "Открепить" : "Закрепить") + "</button>" +
    '<div class="sm-h">Проект: ' + esc(p ? p.name : "нет") + "</div>" +
    PROJ.list.map(pp =>
      '<button data-a="proj" data-id="' + pp.id + '">' +
      (s.projId === pp.id ? "● " : "○ ") + esc(pp.name) + "</button>").join("");
  if (s.projId) html += '<button data-a="proj" data-id="0">○ Без проекта</button>';
  html += '<button data-a="del" class="danger">Удалить сессию</button>';
  m.innerHTML = html;
  document.body.appendChild(m);
  const r = anchor.getBoundingClientRect();
  m.style.top = Math.min(r.bottom + 4, window.innerHeight - m.offsetHeight - 8) + "px";
  m.style.left = Math.max(8, r.left - 130) + "px";
  m.onclick = e => {
    const a = e.target.dataset.a;
    if (!a) return;
    closeSessMenu();
    if (a === "rename") {
      const t = prompt("Название сессии:", s.title);
      if (t && t.trim()) { s.title = t.trim().slice(0, 60); sessSave(); drawSess(); }
    } else if (a === "pin") {
      s.pinned = !s.pinned; sessSave(); drawSess();
    } else if (a === "proj") {
      s.projId = +e.target.dataset.id || null;
      sessSave(); drawSess();
      if (SESS.cur && SESS.cur.id === id) openSess(id);
    } else if (a === "del") {
      /* фича 19: перед удалением сессия сохраняется в vault/inbox */
      archiveSess(s);
      SESS.list = SESS.list.filter(x => x.id !== id);
      if (SESS.cur && SESS.cur.id === id) { SESS.cur = null; CHAT_HIST = []; openTab("chat"); }
      sessSave(); drawSess();
    }
  };
  setTimeout(() => document.addEventListener("click", closeSessMenu, {once: true}), 0);
}
function sessTrack(role, content) {
  const s = sessEnsure();
  s.msgs.push({role: role, content: content});
  if (role === "user" && s.msgs.filter(m => m.role === "user").length === 1)
    s.title = content.slice(0, 42) || "Новая сессия";
  s.ts = new Date().toLocaleString("ru-RU", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"});
  sessSave();
  drawSess();
  const cnt = $("pf-cnt");
  if (cnt) cnt.textContent = s.msgs.length;
}
function drawSess() {
  const box = $("cs-sess");
  if (!box) return;
  /* 8.9: поиск; 6.11: закреплённые сверху; 6-S: фильтр по проекту */
  const q = (($("sess-q") && $("sess-q").value) || "").toLowerCase();
  const sorted = SESS.list.slice().sort((a, b) =>
    (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || b.id - a.id);
  let shown = sorted.filter(s => !q || (s.title || "").toLowerCase().includes(q));
  if (PROJ.filter !== null) shown = shown.filter(s => s.projId === PROJ.filter);
  box.innerHTML = shown.length ? shown.map(s => {
    const p = s.projId ? projById(s.projId) : null;
    return '<div class="sessrow' + (SESS.cur && s.id === SESS.cur.id ? " on" : "") +
      (s.pinned ? " pinned" : "") + '" data-id="' + s.id + '">' +
      (p ? '<span class="pdot" style="background:' + p.color + '" title="проект: ' +
        esc(p.name) + '"></span>' : "") +
      (s.pinned ? '<span class="spin2" title="закреплена">' + PIN_SVG + "</span>" : "") +
      '<span class="st">' + esc(s.title || "Новая сессия") + "</span>" +
      '<span class="smore" data-menu="' + s.id + '" title="действия">⋯</span></div>';
  }).join("") :
    '<div class="sub" style="padding:4px 2px">' +
    (q || PROJ.filter !== null ? "не найдено" : "сессий пока нет") + "</div>";
  box.querySelectorAll(".sessrow").forEach(row => {
    const id = +row.dataset.id;
    row.onclick = e => {
      if (e.target.dataset.menu) return;
      openSess(id);
    };
    const more = row.querySelector(".smore");
    if (more) more.onclick = e => {
      e.stopPropagation();
      sessMenu(id, more);
    };
  });
}
function openSess(id) {
  const s = SESS.list.find(x => x.id === id);
  if (!s) return;
  SESS.cur = s;
  CHAT_HIST = s.msgs.slice();
  openTab("chat", {skipAnim: true});
  /* баг-12: заголовок сессии — typewriter, остаётся до смены сессии */
  sessTitleType(s.title || "Новая сессия");
  /* 6.10: дата начала сессии в подзаголовке */
  if (s.started) {
    const d = new Date(s.started);
    $("m-sub").textContent += " · сессия начата " +
      d.toLocaleDateString("ru-RU", {day: "numeric", month: "long"}) + ", " +
      d.toLocaleTimeString("ru-RU", {hour: "2-digit", minute: "2-digit"});
  }
  const log = $("chat-log");
  if (log) {
    log.innerHTML = "";
    s.msgs.forEach(m => {
      const d = document.createElement("div");
      d.className = "chat-msg " + (m.role === "user" ? "user" : "bot");
      if (m.role === "bot") d.innerHTML = md(m.content);
      else d.textContent = m.content;
      log.appendChild(d);
    });
    log.scrollTop = log.scrollHeight;
  }
  hideEmpty();
  drawSess();
  const cnt = $("pf-cnt");
  if (cnt) cnt.textContent = s.msgs.length;
}
function newSess() {
  /* баг-16/17/18: новая сессия сразу видима в списке и привязана к проекту */
  SESS.cur = null;
  CHAT_HIST = [];
  openTab("chat");
  drawSess();
}
/* баг-12: заголовок сессии печатается и остаётся (вместо цикла «С чего начнём») */
let SESS_TW = null;
function sessTitleType(title) {
  if (TW_TIMER) { clearInterval(TW_TIMER); clearTimeout(TW_TIMER); TW_TIMER = null; }
  if (SESS_TW) { clearTimeout(SESS_TW); SESS_TW = null; }
  const el = $("m-title");
  if (!el) return;
  el.classList.remove("tw"); void el.offsetWidth; el.classList.add("tw");
  let k = 0;
  const step = () => {
    if (!document.getElementById("m-title")) return;
    el.innerHTML = esc(title.slice(0, k)) + (k < title.length ? '<span class="caret"></span>' : "");
    if (k >= title.length) return;
    k++;
    SESS_TW = setTimeout(step, 55 + Math.random() * 30);
  };
  step();
}

function renderShell() {
  show("scr-app");
  $("cs-nav").innerHTML = NAV.map((n, i) =>
    '<button class="cs-navitem' + (i === 0 ? " on" : "") + '" data-tab="' + n[0] + '">' +
    '<span class="cs-ico">' + ICO[n[0]] + "</span><span>" + n[1] + "</span></button>").join("");
  $("cs-nav").querySelectorAll(".cs-navitem").forEach(b => b.onclick = () => {
    document.querySelectorAll(".cs-navitem").forEach(x => x.classList.remove("on"));
    b.classList.add("on");
    openTab(b.dataset.tab);
  });
  const p = ME;
  $("cs-prof").innerHTML =
    '<div class="profcard">' +
    (p.avatar ? '<img class="pa" src="' + p.avatar + '">' : '<div class="pa">' + esc(((p.username || "?")[0]) || "?").toUpperCase() + "</div>") +
    '<div class="un">' + esc(p.username) + "</div>" +
    '<div class="mdl">' + esc((p.onboarding.prefs || {}).model || "") + "</div>" +
    '<div class="st"><i></i>онлайн</div>' +
    '<div class="cnt">реплик в сессии: <b id="pf-cnt">0</b></div>' +
    "</div>" +
    /* 5-H.7 + 6-S: сессии и проекты под профильной карточкой */
    '<div class="cs-sess-h">сессии</div>' +
    '<input class="minput sess-q" id="sess-q" placeholder="поиск…" autocomplete="off">' +
    '<div id="cs-sess" class="sesslist"></div>' +
    '<button type="button" class="sess-new" id="sess-new">+ новая сессия</button>' +
    '<div class="cs-sess-h">проекты</div>' +
    '<div id="cs-proj" class="projlist"></div>' +
    '<button type="button" class="sess-new" id="proj-new">+ новый проект</button>';
  sessLoad();
  projLoad();
  drawSess();
  drawProj();
  $("sess-q").addEventListener("input", drawSess);
  $("sess-new").onclick = newSess;
  $("proj-new").onclick = () => projModal(null);
  $("cs-logout").onclick = async () => { await api("/api/logout", {}); location.reload(); };
  /* 5-I: солнце открывает настройки и подсвечивает вкладку в правом меню */
  $("cs-gear").onclick = () => openTab("set");
  openTab("chat");
}

/* typewriter 2.0: «дыхание» интерфейса — джиттер набора, быстрое стирание,
   длинная пауза на прочтение, CSS-каретка, фейд новой фразы. Только чат. */
const PHRASES = ["Чат с Моникой", "С чего начнём?", "О чём поговорим?", "Что разберём сегодня?"];
let TW_TIMER = null;
function setTitleTab(tab) {
  if (TW_TIMER) { clearInterval(TW_TIMER); clearTimeout(TW_TIMER); TW_TIMER = null; }
  const el = $("m-title");
  /* баг-12: в чате с выбранной сессией заголовок = название сессии (не цикл фраз) */
  if (tab === "chat" && SESS.cur) { sessTitleType(SESS.cur.title || "Новая сессия"); return; }
  if (SESS_TW) { clearTimeout(SESS_TW); SESS_TW = null; }
  if (tab !== "chat") { el.textContent = TITLES[tab] || tab; return; }
  let pi = 0;
  const cycle = () => {
    if (TAB !== "chat") return;
    const t = PHRASES[pi % PHRASES.length]; pi++;
    el.classList.remove("tw"); void el.offsetWidth; el.classList.add("tw");
    let k = 0, del = false;
    const step = () => {
      if (TAB !== "chat") { clearInterval(TW_TIMER); TW_TIMER = null; return; }
      el.innerHTML = esc(t.slice(0, k)) + '<span class="caret"></span>';
      if (!del) {
        k++;
        if (k > t.length) { del = true; TW_TIMER = setTimeout(cycle, 2800); return; }
        TW_TIMER = setTimeout(step, 62 + Math.random() * 36);
      } else {
        k -= 2;
        if (k <= 0) { TW_TIMER = setTimeout(cycle, 420); return; }
        TW_TIMER = setTimeout(step, 26);
      }
    };
    step();
  };
  cycle();
}

function openTab(tab, opts) {
  TAB = tab;
  setTitleTab(tab);
  $("m-sub").textContent = new Date().toLocaleDateString("ru-RU", {day: "numeric", month: "long", weekday: "long"});
  /* Полировка-1: терминал расширяет каркас, остальные вкладки — обычная ширина */
  const shell = document.querySelector(".cs");
  if (shell) shell.classList.toggle("term-wide", tab === "term");
  /* 5-I: активная вкладка в правом меню синхронизируется всегда (солнце/сессии) */
  document.querySelectorAll(".cs-navitem").forEach(x => x.classList.toggle("on", x.dataset.tab === tab));
  ({chat: tabChat, term: tabTerm, wiki: tabWiki, tg: tabTg, ana: tabAna, set: tabSet})[tab](ME);
  /* Полировка-1: slide+fade переход между модулями (в духе .wz-in).
     6.13: при переключении сессий анимации нет — иначе мигает чужая сессия */
  if (!(opts && opts.skipAnim)) {
    const body = $("m-body");
    body.classList.remove("tab-in");
    void body.offsetWidth;
    body.classList.add("tab-in");
  }
}

/* ── чат: лента, пустой экран с подсказками, стриминг, thinking-фразы ── */
/* баг-11: контекстные фразы «думаю» — системный стиль, анимация точек */
const THINK = {
  chat: ["Думаю…", "Ищу информацию в архиве…", "Сверяю факты и связи…", "Перечитываю заметки…"],
  term: ["Планирую операции…", "Проверяю структуру vault…", "Сверяюсь с белым списком…"],
  err: ["Перезапускаю запрос…", "Разбираюсь в ошибке…"]
};
const SUGGESTIONS = ["Что вика знает обо мне?", "Разбери мой последний день",
  "Создай заметку идеи/план на неделю", "Какие у меня открытые вопросы?"];
let SUG_SHOWN = true;

function tabChat(p) {
  /* баг-16: реплики показываются только когда выбрана сессия */
  if (!SESS.cur) CHAT_HIST = [];
  $("m-body").innerHTML =
    '<div id="chat-log" class="cs-log"></div>' +
    '<div id="cs-empty" class="cs-empty"><div class="cs-empty-t">С чего начнём?</div>' +
    '<div class="beta" id="beta-box"><button type="button" class="beta-min" id="beta-min" title="свернуть">–</button>' +
    '<h3><i>🔒</i>Закрытое тестирование</h3>' +
    "<p>Моника работает в тестовом режиме: это закрытая бета для друзей и бета-тестеров, часть функций ещё в разработке, возможны странности.</p>" +
    '<p>Нашёл баг или есть идея — пиши автору в Telegram: <a href="https://t.me/sozrelyy" target="_blank" rel="noopener">@sozrelyy</a>. Баг-репорты и предложения очень помогают.</p>' +
    "<p>Твои заметки и данные принадлежат только тебе.</p></div></div>" +
    '<div class="cs-bottom"><form id="chat-form"><div class="cs-inputbar">' +
    '<span class="cs-att" title="скоро: изображения"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="M21 15.5 16.5 11 7 19"/></svg></span>' +
    '<span class="cs-att" title="скоро: файлы"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21.4 11.05 12.25 20.2a5.5 5.5 0 0 1-7.78-7.78l8.49-8.48a3.67 3.67 0 0 1 5.18 5.18l-8.48 8.49a1.83 1.83 0 0 1-2.6-2.6l7.79-7.78"/></svg></span>' +
    '<textarea id="chat-input" rows="1" placeholder="напиши Монике…"></textarea>' +
    '<button type="submit" class="cs-send" title="Отправить">' + SEND_SVG + "</button>" +
    "</div></form>" +
    '<div class="cs-actions"><span id="cs-status" class="cs-status"></span></div></div>';
  const form = $("chat-form"), input = $("chat-input"), log = $("chat-log");
  /* Фаза 5-B: быстрый переключатель модели вместо статичного чипа */
  const cur = ((p.onboarding.prefs || {}).model) || "";
  $("cs-status").innerHTML =
    '<span class="cs-modelwrap"><button type="button" class="cs-modelbtn" id="mdl-btn">' +
    '<span class="dot"></span><span id="mdl-name">…</span> <span class="chev">▾</span></button>' +
    '<div class="cs-modelmenu" id="mdl-menu"></div></span>';
  ensureCFGM().then(c => {
    const sel = c.models.some(m => m.id === cur) ? cur : c.default_model;
    $("mdl-name").textContent = modelName(sel);
    $("mdl-menu").innerHTML = c.models.map(m =>
      '<button type="button" data-id="' + m.id + '"' + (m.id === sel ? ' class="sel"' : "") + ">" +
      esc(m.name) + '<span class="d">' + esc((m.desc ? m.desc + " · " : "") + m.role) + "</span></button>").join("");
    $("mdl-menu").querySelectorAll("button").forEach(b => b.onclick = async () => {
      const r = await api("/api/prefs/model", {model: b.dataset.id});
      if (!r.data.ok) return;
      $("mdl-menu").classList.remove("open");
      $("mdl-btn").classList.remove("open");
      $("mdl-name").textContent = modelName(r.data.model);
      $("mdl-menu").querySelectorAll("button").forEach(x =>
        x.classList.toggle("sel", x.dataset.id === r.data.model));
      if (ME.onboarding && ME.onboarding.prefs) ME.onboarding.prefs.model = r.data.model;
    });
  });
  $("mdl-btn").onclick = e => {
    e.stopPropagation();
    const menu = $("mdl-menu");
    menu.classList.remove("up");
    menu.classList.toggle("open");
    $("mdl-btn").classList.toggle("open");
    /* 5-H.5: если список не влезает снизу — открываем вверх */
    const r = menu.getBoundingClientRect();
    if (menu.classList.contains("open") && r.bottom > window.innerHeight - 8)
      menu.classList.add("up");
  };
  if (!window.__mdlDocClose) {
    window.__mdlDocClose = true;
    document.addEventListener("click", () => {
      const m = $("mdl-menu"), b = $("mdl-btn");
      if (m) m.classList.remove("open");
      if (b) b.classList.remove("open");
    });
  }
  /* 8.8: баннер сворачивается в маленький бейдж */
  const bb = $("beta-box"), bmin = $("beta-min");
  const setMin = v => {
    bb.classList.toggle("min", v);
    bmin.textContent = v ? "🔒 бета" : "–";
  };
  try { setMin(localStorage.getItem("monica_beta_min") === "1"); } catch (e) {}
  bmin.onclick = () => {
    const v = !bb.classList.contains("min");
    setMin(v);
    try { localStorage.setItem("monica_beta_min", v ? "1" : "0"); } catch (e) {}
  };
  const resize = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; };
  input.addEventListener("input", resize);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  form.onsubmit = e => { e.preventDefault(); const t = input.value.trim(); if (!t) return; input.value = ""; resize(); chatTurn(t); };
}

function hideEmpty() {
  const e = $("cs-empty");
  if (e) e.classList.add("off");
}

function addBotMsg(text, opts) { return addMsg("bot", text, opts); }

function addMsg(role, text, opts) {
  if (!opts || !opts.keepEmpty) hideEmpty();
  const d = document.createElement("div");
  d.className = "chat-msg " + role;
  d.textContent = text;
  const log = $("chat-log") || $("tlog");
  if (!log) return null;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
  return d;
}

function addTyping(kind) {
  /* баг-11: «Думаю…» — системный текст: приглушён, с анимацией, фразы по контексту */
  hideEmpty();
  const log = $("chat-log") || $("tlog");
  const d = document.createElement("div");
  d.className = "chat-msg bot typing sysnote";
  const pool = THINK[kind] || THINK.chat;
  d.innerHTML = '<span class="tp-phrase">' + pool[0] + '</span><span class="typing-dots"><i></i><i></i><i></i></span>';
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
  const ph = d.querySelector(".tp-phrase");
  let i = 0;
  const rot = setInterval(() => { i = (i + 1) % pool.length; if (ph) ph.textContent = pool[i]; }, 1600);
  return {el: d, stop: () => clearInterval(rot)};
}

let LAST_MSG = null;

async function chatTurn(text) {
  addMsg("user", text);
  CHAT_HIST.push({role: "user", content: text});
  sessTrack("user", text);
  LAST_MSG = text;
  const tp = addTyping("chat");
  try {
    const r = await fetch("/api/chat/stream", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text, history: CHAT_HIST.slice(-20),
        project_instruction: curInstr()})});
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.error || "HTTP " + r.status);
    }
    tp.stop();
    const b = addMsg("bot", "");
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let acc = "";
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      acc += dec.decode(chunk.value, {stream: true});
      b.textContent = acc;
      log && (log.scrollTop = log.scrollHeight);
    }
    b.innerHTML = md(acc);
    CHAT_HIST.push({role: "assistant", content: acc});
    sessTrack("assistant", acc);
  } catch (e) {
    tp.stop();
    const b = addMsg("bot", "⚠️ " + (e.message || e));
    b.classList.add("sysnote");
    const rb = document.createElement("button");
    rb.className = "cs-act"; rb.textContent = "Повторить";
    rb.onclick = () => { b.remove(); chatTurn(text); };
    b.appendChild(rb);
  }
}
/* фича 19: сессия сохраняется в vault/inbox как .md */
async function archiveSess(s) {
  if (!s || !s.msgs || !s.msgs.length) return;
  try {
    await api("/api/session/archive", {title: s.title || "сессия",
      started: s.started, msgs: s.msgs});
  } catch (e) { /* архивация не блокирует работу чата */ }
}

/* ── терминал 2.0: дерево / чат⇄редактор / лог изменений (Фаза 5-E + Полировка-1) ── */
let TERM = {view: "chat", openFile: null, dirty: false};

function animTab(el) {
  if (!el) return;
  el.classList.remove("tab-in");
  void el.offsetWidth;
  el.classList.add("tab-in");
}

function tabTerm(p) {
  $("m-body").innerHTML =
    '<div class="tgrid">' +
    '<div class="tpane tpane-tree" id="ttree-pane"><div class="cs-menu-h">vault' +
    '<button type="button" class="tt-new" id="tt-new" title="создать">＋</button></div>' +
    '<div id="ttree" class="ttree"></div>' +
    '<div class="tt-hint">перетащи файлы сюда — они попадут в vault</div></div>' +
    '<div class="tpane tpane-mid">' +
    '<div class="tmid-switch">' +
    '<button type="button" class="set-tab' + (TERM.view === "chat" ? " on" : "") + '" id="tv-chat">Чат</button>' +
    '<button type="button" class="set-tab' + (TERM.view === "edit" ? " on" : "") + '" id="tv-edit">Редактор</button>' +
    '<button type="button" class="set-tab' + (TERM.view === "prev" ? " on" : "") + '" id="tv-prev">Превью</button></div>' +
    '<div id="tchat"' + (TERM.view === "chat" ? "" : ' class="hidden"') + '>' +
    '<div id="tlog" class="cs-log"></div>' +
    '<div class="tchips" id="tchips"></div>' +
    '<div class="cs-bottom"><form id="tform"><div class="cs-inputbar" id="tbar">' +
    '<textarea id="t-input" rows="1"></textarea>' +
    '<button type="submit" class="cs-send" title="Отправить">' + SEND_SVG + "</button>" +
    "</div></form></div></div>" +
    '<div id="teditor"' + (TERM.view === "edit" ? "" : ' class="hidden"') + '>' +
    '<div class="te-find hidden" id="te-findbar">' +
    '<input id="te-find" placeholder="найти… (Enter — далее)">' +
    '<span id="te-fn" class="sub"></span>' +
    '<button type="button" class="cs-act" id="te-find-close">×</button></div>' +
    '<div class="te-head"><span class="te-tab"><span class="te-dot" id="te-dot"></span>' +
    '<span id="te-file">' + esc(TERM.openFile || "файл не выбран — кликни в дереве слева") + "</span></span>" +
    '<button type="button" class="cs-act primary" id="te-save">Сохранить</button></div>' +
    '<div class="te-wrap"><div class="te-gutter" id="te-gutter"></div>' +
    '<textarea id="te-area" class="te-area" spellcheck="false"></textarea></div>' +
    '<div class="te-status" id="te-status"></div></div>' +
    '<div id="te-prev" class="body te-prev' + (TERM.view === "prev" ? "" : " hidden") + '">' +
    (TERM.view === "prev" ? "<p>Открой файл в редакторе — здесь появится превью.</p>" : "") + "</div>" +
    "</div>" +
    '<div class="tpane tpane-log"><div class="cs-menu-h">изменения</div><div id="thist" class="thist"></div></div>' +
    "</div>";
  if (!$("tlog").children.length)
    addTMsg("bot", "Терминал работает только с твоим vault. Изменения — после подтверждения. Ядро Моники и чужие данные недоступны.");
  const form = $("tform"), input = $("t-input");
  /* 5-H.3: высота управляется CSS (#t-input / #tbar.tfocus), без JS-конфликта */
  input.addEventListener("focus", () => $("tbar").classList.add("tfocus"));
  input.addEventListener("blur", () => { if (!input.value.trim()) $("tbar").classList.remove("tfocus"); });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  form.onsubmit = e => {
    e.preventDefault(); const t = input.value.trim(); if (!t) return;
    input.value = ""; $("tbar").classList.remove("tfocus"); termTurn(t);
  };
  /* 6-T: рецепты — быстрые запросы к ИИ терминала */
  const RECIPES = ["создай заметку идеи/план на неделю",
    "покажи структуру моих заметок",
    "наведи порядок в заметках — предложи структуру",
    "сгруппируй заметки по темам"];
  $("tchips").innerHTML = RECIPES.map(r =>
    '<button type="button" class="tchip">' + esc(r) + "</button>").join("");
  $("tchips").querySelectorAll(".tchip").forEach(b =>
    b.onclick = () => { input.value = b.textContent; input.focus(); input.dispatchEvent(new Event("input")); });
  /* переключатель Чат ⇄ Редактор ⇄ Превью — без перерисовки */
  const setView = v => {
    TERM.view = v;
    ["chat", "edit", "prev"].forEach(x =>
      $("tv-" + x).classList.toggle("on", v === x));
    $("tchat").classList.toggle("hidden", v !== "chat");
    $("teditor").classList.toggle("hidden", v !== "edit");
    $("te-prev").classList.toggle("hidden", v !== "prev");
    if (v === "edit" && TERM.openFile) loadEditor();
    if (v === "prev" && TERM.openFile) renderPreview();
  };
  $("tv-chat").onclick = () => { setView("chat"); animTab($("tchat")); };
  $("tv-edit").onclick = () => { setView("edit"); animTab($("teditor")); };
  $("tv-prev").onclick = () => { setView("prev"); animTab($("te-prev")); };
  $("te-save").onclick = saveEditor;
  $("te-area").addEventListener("input", () => {
    if (!TERM.dirty) { TERM.dirty = true; $("te-dot").classList.add("on"); }
    updateGutter();
    updateStatus();
  });
  $("te-area").addEventListener("scroll", () => { syncGutter(); syncFind(); });
  $("te-area").addEventListener("keyup", () => { updateGutter(); updateStatus(); });
  $("te-area").addEventListener("click", () => { updateGutter(); updateStatus(); });
  /* 5-I.3 + 6-T: Ctrl+S — сохранить, Ctrl+F — найти */
  $("te-area").addEventListener("keydown", e => {
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === "s") { e.preventDefault(); saveEditor(); }
    if ((e.ctrlKey || e.metaKey) && k === "f") {
      e.preventDefault();
      $("te-findbar").classList.remove("hidden");
      $("te-find").focus();
      $("te-find").select();
    }
    if (e.key === "Escape" && !$("te-findbar").classList.contains("hidden")) {
      $("te-findbar").classList.add("hidden");
      $("te-find").value = ""; $("te-fn").textContent = "";
    }
  });
  /* 6-T: find-бар — последовательный поиск с выделением */
  let findIdx = -1;
  const findNext = back => {
    const q = $("te-find").value;
    if (!q) { $("te-fn").textContent = ""; return; }
    const v = $("te-area").value;
    const low = v.toLowerCase(), ql = q.toLowerCase();
    let i;
    if (back) {
      i = low.lastIndexOf(ql, Math.max(0, findIdx - 1));
      if (i < 0) i = low.lastIndexOf(ql);
    } else {
      i = low.indexOf(ql, findIdx + 1);
      if (i < 0) i = low.indexOf(ql);
    }
    if (i < 0) { $("te-fn").textContent = "не найдено"; return; }
    findIdx = i;
    $("te-area").focus();
    $("te-area").setSelectionRange(i, i + q.length);
    const line = v.slice(0, i).split("\n").length;
    $("te-area").scrollTop = Math.max(0, (line - 4) * 20);
    syncGutter();
    const total = low.split(ql).length - 1;
    const num = low.slice(0, i).split(ql).length;
    $("te-fn").textContent = num + " / " + total;
  };
  $("te-find").addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); findNext(e.shiftKey); }
    if (e.key === "Escape") { $("te-findbar").classList.add("hidden"); $("te-area").focus(); }
  });
  $("te-find").addEventListener("input", () => { findIdx = -1; findNext(false); });
  $("te-find-close").onclick = () => { $("te-findbar").classList.add("hidden"); $("te-area").focus(); };
  /* 6-I: меню создания файла/папки */
  $("tt-new").onclick = e => {
    e.stopPropagation();
    closeTreeMenu();
    const m = document.createElement("div");
    m.className = "sessmenu treemenu";
    m.innerHTML = '<button data-a="file">Новый файл</button>' +
      '<button data-a="dir">Новая папка</button>';
    document.body.appendChild(m);
    const r = e.currentTarget.getBoundingClientRect();
    m.style.top = Math.min(r.bottom + 4, window.innerHeight - m.offsetHeight - 8) + "px";
    m.style.left = r.left + "px";
    m.onclick = ev => {
      const a = ev.target.dataset.a;
      closeTreeMenu();
      if (a) newItemModal(a);
    };
    setTimeout(() => document.addEventListener("click", closeTreeMenu, {once: true}), 0);
  };
  /* 6-I: drag&drop файлов в дерево */
  const pane = $("ttree-pane");
  pane.addEventListener("dragover", e => { e.preventDefault(); pane.classList.add("dragover"); });
  pane.addEventListener("dragleave", () => pane.classList.remove("dragover"));
  pane.addEventListener("drop", e => {
    e.preventDefault();
    pane.classList.remove("dragover");
    handleDrop(e.dataTransfer.files, e.target);
  });
  drawTree();
  drawHist();
  /* 6-W: правка статьи из вики — редактор открывается сразу с файлом */
  if (TERM.view === "edit" && TERM.openFile) loadEditor();
}

function closeTreeMenu() {
  const m = document.querySelector(".treemenu");
  if (m) m.remove();
}

const TEXT_EXT = /\.(md|txt|markdown|json|csv|log|html|css|js|py|yml|yaml|ts|ini|cfg)$/i;

/* 6-I: импорт перетащенных файлов (текстовые) в vault */
async function handleDrop(files, target) {
  const dirEl = target && target.closest ? target.closest(".tdir") : null;
  const folder = dirEl ? (dirEl.dataset.dir || "") : "";
  const list = Array.from(files || []).slice(0, 10);
  if (!list.length) return;
  for (const f of list) {
    if (!TEXT_EXT.test(f.name) && !(f.type || "").startsWith("text/")) {
      addTMsg("bot", "⚠️ «" + f.name + "» пропущен: пока поддерживаются только текстовые файлы.");
      continue;
    }
    const text = await f.text();
    const path = (folder ? folder + "/" : "") + f.name;
    const r = await api("/api/vault/write", {path: path, content: text.slice(0, 100_000)});
    if (r.data.error) addTMsg("bot", "⚠️ " + f.name + ": " + r.data.error);
    else addTMsg("bot", "✅ импортировано: " + r.data.path);
  }
  drawTree();
  drawHist();
}

/* 6-I: мини-модалка создания файла/папки */
function newItemModal(type) {
  const isFile = type === "file";
  const ov = document.createElement("div");
  ov.className = "modal-ov";
  ov.innerHTML = '<div class="modal"><h3>' + (isFile ? "Новый файл" : "Новая папка") + "</h3>" +
    "<label>" + (isFile ? "Путь (можно с папкой: заметки/имя.md)" : "Имя папки") + "</label>" +
    '<input class="minput" id="nm-name" placeholder="' +
    (isFile ? "заметки/имя.md" : "новая папка") + '">' +
    '<div class="row"><button class="mbtn" id="nm-cancel">Отмена</button>' +
    '<button class="mbtn acc" id="nm-go">Создать</button></div></div>';
  document.body.appendChild(ov);
  const inp = ov.querySelector("#nm-name");
  inp.focus();
  ov.querySelector("#nm-cancel").onclick = () => ov.remove();
  ov.onclick = e => { if (e.target === ov) ov.remove(); };
  const create = async () => {
    const raw = inp.value.trim();
    if (!raw) { inp.style.borderColor = "var(--red)"; return; }
    const path = isFile ? (raw.endsWith(".md") ? raw : raw + ".md") : raw + "/Черновик.md";
    const title = (path.split("/").pop() || "").replace(/\.md$/, "");
    const r = await api("/api/vault/write", {path: path,
      content: "---\ntitle: " + title + "\ncreated: " +
        new Date().toISOString().slice(0, 10) + "\n---\n\n# " + title + "\n\n"});
    if (r.data.error) { inp.style.borderColor = "var(--red)"; return; }
    ov.remove();
    TERM.openFile = isFile ? r.data.path : null;
    drawTree();
    drawHist();
    if (isFile) { setViewEdit(); loadEditor(); }
  };
  ov.querySelector("#nm-go").onclick = create;
  inp.addEventListener("keydown", e => { if (e.key === "Enter") create(); });
}
function setViewEdit() {
  if ($("tv-edit")) {
    $("tv-chat").classList.remove("on");
    $("tv-edit").classList.add("on");
    $("tchat").classList.add("hidden");
    $("teditor").classList.remove("hidden");
    TERM.view = "edit";
  }
}

/* 6-T: markdown-превью открытого файла */
async function renderPreview() {
  const box = $("te-prev");
  if (!box || !TERM.openFile) return;
  const r = await api("/api/vault/read", {path: TERM.openFile});
  if (r.data.error) { box.innerHTML = '<p style="color:var(--red)">' + esc(r.data.error) + "</p>"; return; }
  const fm = parseFrontmatter(r.data.content);
  box.innerHTML = '<h1 class="firstHeading">' +
    esc(fm.meta.title || (TERM.openFile.split("/").pop() || "").replace(/\.md$/, "")) + "</h1>" +
    '<div class="wk-meta">' + esc(fm.meta.created || "") +
    (fm.meta.tags ? " · теги: " + esc(fm.meta.tags) : "") + "</div>" + md(fm.body);
}
function syncFind() { /* заготовка: gutter уже синхронен через syncGutter */ }

/* Полировка-1: gutter с номерами строк, синхронный скролл, текущая строка */
function updateGutter() {
  const ta = $("te-area"), g = $("te-gutter");
  if (!ta || !g) return;
  const lines = Math.max(ta.value.split("\n").length, 1);
  const curLine = ta.value.slice(0, ta.selectionStart).split("\n").length;
  let html = "";
  for (let i = 1; i <= lines; i++)
    html += "<div" + (i === curLine ? ' class="cur"' : "") + ">" + i + "</div>";
  g.innerHTML = html;
  syncGutter();
}
function syncGutter() {
  const ta = $("te-area"), g = $("te-gutter");
  if (ta && g) g.scrollTop = ta.scrollTop;
}

/* 5-I.3: дерево в стиле Obsidian — иерархия папок со сворачиванием */
function buildTree(paths) {
  const root = {dirs: {}, files: []};
  (paths || []).forEach(p => {
    const parts = p.split("/");
    let node = root;
    for (let i = 0; i < parts.length - 1; i++)
      node = node.dirs[parts[i]] || (node.dirs[parts[i]] = {dirs: {}, files: []});
    node.files.push({name: parts[parts.length - 1], path: p});
  });
  return root;
}
const FOLDER_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
const FILE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/></svg>';
const PIN_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5M9 3h6l1 7 3 3H5l3-3z"/></svg>';

function renderTreeNode(node, out, prefix) {
  Object.keys(node.dirs).sort().forEach(name => {
    const dirPath = prefix ? prefix + "/" + name : name;
    out.push('<details class="tdir" open data-dir="' + esc(dirPath) + '"><summary>' +
      FOLDER_SVG + esc(name) + "</summary>");
    renderTreeNode(node.dirs[name], out, dirPath);
    out.push("</details>");
  });
  node.files.sort((a, b) => a.name.localeCompare(b.name)).forEach(f => {
    out.push('<button type="button" class="tfile' + (f.path === TERM.openFile ? " sel" : "") +
      '" data-p="' + esc(f.path) + '">' + FILE_SVG + esc(f.name) + "</button>");
  });
}

async function drawTree() {
  const box = $("ttree");
  if (!box) return;
  const r = await api("/api/vault/tree", {});
  const out = [];
  renderTreeNode(buildTree(r.data.tree || []), out, "");
  box.innerHTML = out.length ? out.join("") : '<div class="sub">vault пуст</div>';
  box.querySelectorAll(".tfile").forEach(b => b.onclick = () => {
    TERM.openFile = b.dataset.p;
    box.querySelectorAll(".tfile").forEach(x => x.classList.toggle("sel", x === b));
    $("tv-chat").classList.remove("on");
    $("tv-edit").classList.add("on");
    $("tchat").classList.add("hidden");
    $("teditor").classList.remove("hidden");
    TERM.view = "edit";
    loadEditor();
  });
}

async function loadEditor() {
  if (!TERM.openFile || !$("te-area")) return;
  $("te-file").textContent = TERM.openFile;
  const r = await api("/api/vault/read", {path: TERM.openFile});
  if (r.data.error) { $("te-area").value = ""; $("te-file").textContent = "⚠️ " + r.data.error; updateGutter(); updateStatus(); return; }
  $("te-area").value = r.data.content;
  TERM.dirty = false;
  $("te-dot").classList.remove("on");
  updateGutter();
  updateStatus();
}

/* 5-I.3: статус-строка редактора — путь, Ln/Col, кодировка */
function updateStatus() {
  const ta = $("te-area"), st = $("te-status");
  if (!ta || !st) return;
  const upto = ta.value.slice(0, ta.selectionStart).split("\n");
  st.textContent = (TERM.openFile || "—") + " · Ln " + upto.length +
    ", Col " + (upto[upto.length - 1].length + 1) + " · UTF-8";
}

async function saveEditor() {
  if (!TERM.openFile || !$("te-area")) return;
  const r = await api("/api/vault/write", {path: TERM.openFile, content: $("te-area").value});
  if (r.data.error) { $("te-file").textContent = "⚠️ " + r.data.error; return; }
  $("te-file").textContent = "сохранено: " + r.data.path;
  TERM.dirty = false;
  $("te-dot").classList.remove("on");
  drawTree();
  drawHist();
}

async function drawHist() {
  const box = $("thist");
  if (!box) return;
  const r = await api("/api/vault/history", {});
  const items = r.data.history || [];
  const mut = {create_note: 1, edit_note: 1, rename: 1, move: 1};
  box.innerHTML = items.length ? items.map(h =>
    '<div class="thist-row"><span class="thist-t">' + esc(h.ts || "") + '</span>' +
    '<span class="thist-op">' + esc(h.op) + "</span> " + esc(h.path || "") +
    (h.to ? " → " + esc(h.to) : "") +
    (mut[h.op] ? '<button type="button" class="cs-act" data-id="' + h.id + '">откатить</button>' : "") +
    "</div>").join("") : '<div class="sub">изменений пока нет</div>';
  box.querySelectorAll(".cs-act[data-id]").forEach(b => b.onclick = () => {
    const rec = items.find(x => x.id === b.dataset.id);
    if (rec) undoModal(rec);
  });
}

/* 6-T: модалка отката с превью «сейчас → после» */
function undoModal(rec) {
  const ov = document.createElement("div");
  ov.className = "modal-ov";
  ov.innerHTML = '<div class="modal"><h3>Откатить операцию?</h3>' +
    '<div class="sub">' + esc(rec.op) + " · " + esc(rec.path || "") +
    (rec.to ? " → " + esc(rec.to) : "") + "</div>" +
    '<div id="ud-body" class="sub" style="margin-top:10px">загрузка…</div>' +
    '<div class="row"><button class="mbtn" id="ud-cancel">Отмена</button>' +
    '<button class="mbtn acc" id="ud-go">Подтвердить откат</button></div></div>';
  document.body.appendChild(ov);
  const body = ov.querySelector("#ud-body");
  (async () => {
    if (rec.op === "edit_note") {
      const cur = await api("/api/vault/read", {path: rec.path});
      const curText = cur.data.error ? "(файл отсутствует)" : (cur.data.content || "").slice(0, 1200);
      const prevText = rec.prev === null ? "— файл будет удалён —" : (rec.prev || "").slice(0, 1200);
      body.classList.remove("sub");
      body.innerHTML = '<div class="undo-diff">' +
        '<div class="ud-col"><div class="ud-h">сейчас</div><pre>' + esc(curText) + "</pre></div>" +
        '<div class="ud-col"><div class="ud-h">после отката</div><pre>' + esc(prevText) + "</pre></div></div>";
    } else if (rec.op === "create_note") {
      body.innerHTML = '<div class="warn">⚠️ Файл <b>' + esc(rec.path) +
        "</b> будет удалён. Восстановить его после этого будет нельзя.</div>";
    } else {
      body.innerHTML = "<p>Вернуть: <b>" + esc(rec.to || "") + "</b> → <b>" + esc(rec.path || "") + "</b></p>";
    }
  })();
  ov.querySelector("#ud-cancel").onclick = () => ov.remove();
  ov.onclick = e => { if (e.target === ov) ov.remove(); };
  ov.querySelector("#ud-go").onclick = async () => {
    const r2 = await api("/api/vault/undo", {id: rec.id});
    ov.remove();
    addTMsg("bot", r2.data.message || ("⚠️ " + (r2.data.error || "ошибка отката")));
    drawTree();
    drawHist();
  };
}

function addTMsg(role, text) {
  hideEmpty();
  const log = $("tlog");
  if (!log) return;
  const d = document.createElement("div");
  d.className = "chat-msg " + role;
  d.textContent = text;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
}

async function termTurn(text) {
  const tp = addTyping("term");
  try {
    const r = await api("/api/terminal", {message: text});
    tp.stop();
    if (r.data.error) { addTMsg("bot", "⚠️ " + r.data.error); return; }
    addTMsg("bot", r.data.reply || "…");
    const ops = r.data.ops || [];
    if (!ops.length) return;
    const box = document.createElement("div");
    box.className = "cs-menu";
    box.innerHTML = '<div class="cs-menu-h">Предложенные операции — подтверди выполнение</div>' +
      ops.map(o => '<div class="cs-menu-row">' + o.op + " → " + esc(o.path || "") + (o.to ? " → " + esc(o.to) : "") + "</div>").join("") +
      '<div style="padding:6px 10px 10px"><button class="cs-act primary" id="ops-go">Выполнить</button></div>';
    $("tlog").appendChild(box);
    $("tlog").scrollTop = $("tlog").scrollHeight;
    box.querySelector("#ops-go").onclick = async () => {
      const r2 = await api("/api/terminal/execute", {ops: ops});
      addTMsg("bot", r2.data.results ? r2.data.results.join("\n") : ("⚠️ " + r2.data.error));
      box.remove();
      drawTree();
      drawHist();
    };
  } catch (e) {
    tp.stop();
    addTMsg("bot", "⚠️ " + e);
  }
}

/* ── Википедия: личная вики в стиле Иванопедии (Фаза 5-F + Полировка-1) ── */
function parseFrontmatter(text) {
  const meta = {};
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (m) m[1].split(/\r?\n/).forEach(line => {
    const kv = line.match(/^(\w+):\s*(.*)$/);
    if (kv) meta[kv[1]] = kv[2].replace(/^\[/, "").replace(/\]$/, "").trim();
  });
  return {meta: meta, body: text.slice(m ? m[0].length : 0)};
}

function tabWiki(p) {
  /* 5-H.6: разметка 1:1 из Иванопедии (wiki/index.html):
     .shell > nav.side (.sgroup) + main.content (.firstHeading + .body) + инфобокс.
     Классы уже стилизованы в style.css — «обёртка Моники» вокруг них. */
  $("m-body").innerHTML =
    '<div class="wk-open">' +
    /* 5-I.4: topbar как в wiki/index.html Иванопедии */
    '<header class="topbar wk-topbar">' +
    '<a class="brand"><svg class="globe" viewBox="0 0 64 64" aria-hidden="true">' +
    '<defs><clipPath id="wkc"><circle cx="32" cy="32" r="27"/></clipPath></defs>' +
    '<circle cx="32" cy="32" r="27" class="g-fill"/>' +
    '<g clip-path="url(#wkc)" class="g-line"><circle cx="32" cy="32" r="27"/>' +
    '<ellipse cx="32" cy="32" rx="10" ry="27"/><ellipse cx="32" cy="32" rx="19" ry="27"/>' +
    '<line x1="5" y1="32" x2="59" y2="32"/><line x1="9" y1="18" x2="55" y2="18"/>' +
    '<line x1="9" y1="46" x2="55" y2="46"/></g>' +
    '<g class="g-type"><text x="32" y="40" text-anchor="middle">М</text></g></svg>' +
    '<span class="brand-t"><b>Личная вики</b><small>твоя энциклопедия</small></span></a>' +
    '<div class="searchbox"><input id="wk-q" type="search" placeholder="Поиск по заметкам" autocomplete="off"></div>' +
    '<div class="topcta"><button type="button" class="btn-black" id="wk-regen" title="Сгенерировать статьи из очереди">⟳ Обновить</button></div>' +
    "</header>" +
    '<div class="wk-shell">' +
    '<nav class="side wk-side" id="wk-arts">' +
    '<div class="sgroup"><h3>Навигация</h3><ul>' +
    '<li><a href="#" id="wk-nav-home">Заглавная страница</a></li>' +
    '<li><a href="#" id="wk-nav-random">Случайная статья</a></li>' +
    '<li><a href="#" id="wk-nav-all">Все статьи</a></li></ul></div>' +
    '<div class="sgroup"><h3>Статьи</h3><ul id="wk-arts-ul"></ul></div>' +
    '<div class="sgroup"><h3>Инструменты</h3><ul>' +
    '<li><a href="#" id="wk-nav-search">Поиск по заметкам</a></li>' +
    '<li><a href="#" id="wk-nav-links">Ссылки сюда</a></li>' +
    '<li><a href="#" id="wk-nav-edit">Править статью</a></li>' +
    '<li><a href="#" id="wk-nav-regen">Обновить вики</a></li></ul></div>' +
    "</nav>" +
    '<main class="content wk-content">' +
    '<div id="wk-home">' +
    '<h1 class="firstHeading">Личная вики</h1>' +
    '<div class="body"><p>Это твоя личная энциклопедия — статьи генерируются из твоих заметок.</p>' +
    '<p class="sub">Новые заметки попадают в очередь автоматически; кнопка «Обновить вики» создаёт статьи через умную модель.</p></div>' +
    "</div>" +
    '<div id="wk-view" class="hidden"></div>' +
    "</main>" +
    "</div>" +
    '<div id="wk-res" class="body" style="margin-top:12px"></div></div>';
  const drawArts = async () => {
    const r = await api("/api/wiki/articles", {});
    const arts = r.data.articles || [];
    $("wk-regen").textContent = "Обновить вики" +
      (r.data.queued ? " (" + r.data.queued + " в очереди)" : "");
    /* 5-I фикс: обновляем только список статей, не затирая Навигацию/Инструменты */
    const ul = $("wk-arts-ul");
    if (!ul) return;
    ul.innerHTML = arts.length ? arts.map(a =>
      '<li><a href="#" data-p="' + esc(a.path) + '">' + esc(a.title) + "</a></li>").join("")
      : '<li><span class="sub">Статей пока нет — «Обновить вики» создаст их из очереди.</span></li>';
    ul.querySelectorAll("a[data-p]").forEach(el =>
      el.onclick = ev => { ev.preventDefault(); openArticle(el.dataset.p); });
  };
  let WK_CUR = null;
  const openArticle = async path => {
    const r = await api("/api/wiki/articles", {path: path});
    if (r.data.error) { $("wk-view").innerHTML = '<p style="color:var(--red)">' + esc(r.data.error) + "</p>"; return; }
    const fm = parseFrontmatter(r.data.content);
    const title = fm.meta.title || (path.split("/").pop() || "").replace(/\.md$/, "");
    WK_CUR = {path: path, title: title};
    const bl = await api("/api/wiki/backlinks", {title: title});
    const links = bl.data.backlinks || [];
    /* 6-W: полный шаблон статьи Иванопедии — hatnote, инфобокс с портретом,
       «Ссылки сюда», категории */
    $("wk-view").innerHTML =
      (fm.meta.source ? '<div class="hatnote amber" style="margin:0 0 14px">Источник заметки: <b>' +
        esc(fm.meta.source) + "</b></div>" : "") +
      '<h1 class="firstHeading">' + esc(title) + "</h1>" +
      '<table class="infobox wk-ib"><caption>' + esc(title) + "</caption>" +
      '<tr><td colspan="2" class="ib-portrait">📄</td></tr>' +
      "<tr><th>создано</th><td>" + esc(fm.meta.created || "—") + "</td></tr>" +
      "<tr><th>источник</th><td>" + esc(fm.meta.source || "—") + "</td></tr>" +
      "<tr><th>теги</th><td>" + esc(fm.meta.tags || "—") + "</td></tr>" +
      '<tr><td colspan="2" class="ib-foot">статья личной вики Моники</td></tr></table>' +
      '<div class="body">' + md(fm.body) +
      (links.length ? '<h2 style="font-family:var(--serif);font-size:20px;margin:1.2em 0 .4em">Ссылки сюда</h2>' +
        '<ul class="wk-links">' + links.map(l =>
          '<li><a href="#" data-p="wiki/' + esc(l) + '.md">' + esc(l) + "</a></li>").join("") + "</ul>" : "") +
      (fm.meta.tags ? '<div class="wk-cats">Категории: ' + fm.meta.tags.split(/[,;]\s*/)
        .filter(Boolean).map(t => '<span class="tagc">' + esc(t) + "</span>").join(" ") + "</div>" : "") +
      "</div>";
    $("wk-home").classList.add("hidden");
    $("wk-view").classList.remove("hidden");
    animTab($("wk-view"));
    $("wk-back").onclick = () => {
      $("wk-view").classList.add("hidden");
      $("wk-home").classList.remove("hidden");
    };
    $("wk-view").querySelectorAll(".wk-links a").forEach(a =>
      a.onclick = ev => { ev.preventDefault(); openArticle(a.dataset.p); });
  };
  const showBacklinks = async () => {
    if (!WK_CUR) { $("wk-res").innerHTML = '<p class="sub">Открой статью — тогда покажу, кто на неё ссылается.</p>'; return; }
    const bl = await api("/api/wiki/backlinks", {title: WK_CUR.title});
    const links = bl.data.backlinks || [];
    $("wk-home").classList.add("hidden");
    $("wk-view").classList.remove("hidden");
    $("wk-view").innerHTML =
      '<button type="button" class="cs-act" id="wk-back" style="margin-bottom:10px">← к статье «' +
      esc(WK_CUR.title) + "»</button>" +
      '<h1 class="firstHeading">Ссылки сюда</h1>' +
      '<div class="wk-meta">статьи, упоминающие «' + esc(WK_CUR.title) + "»</div>" +
      '<div class="body">' + (links.length ?
        '<ul class="wk-links">' + links.map(l =>
          '<li><a href="#" data-p="wiki/' + esc(l) + '.md">' + esc(l) + "</a></li>").join("") + "</ul>" :
        "<p>Пока ни одна статья не ссылается на эту.</p>") + "</div>";
    $("wk-back").onclick = () => {
      $("wk-view").classList.add("hidden");
      $("wk-home").classList.remove("hidden");
    };
  };
  const editArticle = () => {
    if (!WK_CUR) { $("wk-res").innerHTML = '<p class="sub">Сначала открой статью.</p>'; return; }
    TERM.openFile = WK_CUR.path;
    TERM.view = "edit";
    openTab("term");
  };
  const randomArticle = () => {
    api("/api/wiki/articles", {}).then(r => {
      const arts = r.data.articles || [];
      if (!arts.length) { $("wk-res").innerHTML = '<p class="sub">Статей пока нет.</p>'; return; }
      openArticle(arts[Math.floor(Math.random() * arts.length)].path);
    });
  };
  $("wk-regen").onclick = async () => {
    $("wk-regen").disabled = true;
    $("wk-regen").textContent = "генерирую…";
    const r = await api("/api/wiki/regen", {});
    $("wk-regen").disabled = false;
    if (r.data.error) { $("wk-regen").textContent = "Обновить вики"; return; }
    drawArts();
  };
  const doSearch = async () => {
    const r = await api("/api/wiki/search", {query: $("wk-q").value});
    const res = r.data.results || [];
    if (!res.length) { $("wk-res").innerHTML = "<p>По этому запросу заметок нет.</p>"; return; }
    $("wk-res").innerHTML = res.map(h =>
      '<div class="wl"><div class="wl-t">' + esc(h.path) + "</div>" +
      '<div class="wl-s">' + esc(h.snippet) + "</div>" +
      '<button class="cs-act" data-p="' + esc(h.path) + '">сделать выжимку</button></div>').join("");
    $("wk-res").querySelectorAll(".cs-act").forEach(b => b.onclick = () => {
      const title = prompt("Название выжимки:");
      if (!title) return;
      api("/api/wiki/extract", {source_path: b.dataset.p, title: title}).then(r2 => {
        $("wk-res").insertAdjacentHTML("afterbegin",
          r2.data.ok ? "<p>✅ Выжимка сохранена: <b>" + esc(r2.data.path) + "</b></p>" :
          '<p style="color:var(--red)">' + esc(r2.data.error) + "</p>");
      });
    });
  };
  $("wk-q").onkeydown = e => { if (e.key === "Enter") doSearch(); };
  /* 6-W: навигация и инструменты Иванопедии */
  $("wk-nav-home").onclick = ev => {
    ev.preventDefault();
    $("wk-view").classList.add("hidden");
    $("wk-home").classList.remove("hidden");
  };
  $("wk-nav-random").onclick = ev => { ev.preventDefault(); randomArticle(); };
  $("wk-nav-all").onclick = ev => {
    ev.preventDefault();
    $("wk-view").classList.add("hidden");
    $("wk-home").classList.remove("hidden");
    $("wk-res").innerHTML = '<p class="sub">Все статьи — в списке слева.</p>';
  };
  $("wk-nav-links").onclick = ev => { ev.preventDefault(); showBacklinks(); };
  $("wk-nav-edit").onclick = ev => { ev.preventDefault(); editArticle(); };
  drawArts();
}

/* ── Telegram-бот: подключение токена и статус поллера ── */
function tabTg(p) {
  $("m-body").innerHTML = '<div id="tg-body" class="body"><p>загружаю статус…</p></div>';
  const draw = async () => {
    const s = await (await api("/api/tg/status", {})).data;
    $("tg-body").innerHTML =
      '<p class="sum">Модуль: <b>' + (s.module ? "вкл" : "выкл") + '</b> · токен: <b>' +
      (s.configured ? "задан" : "нет") + '</b> · поллер: <b>' + (s.poller ? "работает" : "не запущен") + '</b></p>' +
      '<label>Токен бота (от @BotFather)</label><input class="minput" id="tg-token" type="password">' +
      '<label>Твой chat_id (узнать у @userinfobot)</label><input class="minput" id="tg-chat" type="text">' +
      '<div class="row"><span class="sub">/note текст — заметка в vault, остальное — просто чат со мной</span>' +
      '<button class="cs-act primary" id="tg-save">Подключить</button></div>' +
      '<div class="err" id="tg-err"></div>';
    $("tg-save").onclick = async () => {
      const r = await api("/api/tg/setup", {token: $("tg-token").value.trim(), chat_id: $("tg-chat").value.trim()});
      $("tg-err").textContent = r.data.ok ? "✅ подключён бот " + r.data.bot : r.data.error;
      if (r.data.ok) setTimeout(draw, 800);
    };
  };
  draw();
}

/* ── Полная аналитика: сводка + бары активности ── */
async function tabAna(p) {
  $("m-body").innerHTML = '<p class="sum">считаю…</p>';
  const r = await api("/api/analytics/summary", {});
  if (r.data.error) { $("m-body").innerHTML = '<p style="color:var(--red)">' + esc(r.data.error) + '</p>'; return; }
  const s = r.data;
  const days = s.by_day.length || 1;
  const avg = (s.by_day.reduce((a, d) => a + d[1], 0) / days).toFixed(1);
  const max = Math.max(1, ...s.by_day.map(d => d[1]));
  $("m-body").innerHTML =
    '<div class="stat-grid">' +
    '<div class="stat-box"><b>' + s.notes + '</b><span>заметок</span></div>' +
    '<div class="stat-box"><b>' + s.words + '</b><span>слов всего</span></div>' +
    '<div class="stat-box"><b>' + s.changed_last_7d + '</b><span>изменено за 7 дней</span></div>' +
    '<div class="stat-box"><b>' + avg + '</b><span>заметок в день (среднее)</span></div></div>' +
    '<h2>Топ тегов</h2><div>' + (s.top_tags.map(t =>
      '<span class="tagc">' + esc(t[0]) + ' · ' + t[1] + '</span>').join("") || '<span class="sub">тегов нет</span>') + '</div>' +
    '<h2 style="margin-top:20px">Активность по дням</h2>' +
    s.by_day.map(d => '<div class="bar-row"><span class="d">' + d[0] + '</span>' +
      '<span class="bar-track"><span class="bar-fill" style="width:' + (d[1] / max * 100) + '%"></span></span><b>' + d[1] + '</b></div>').join("") +
    '<div class="warn" style="margin-top:18px">Аналитика видит только твой vault. Использование для слежки за людьми запрещено — я откажусь и объясню.</div>';
}

/* ── настройки ×3: Профиль / Модели и ключи / Модули (Фаза 5-D) ── */
let SET_TAB = "profile";
const SVC_NAMES = {glm: "GLM 5.3 Fast", smart: "OpenRouter", luna: "ChatGPT 5.6 Luna"};

function tabSet(p) {
  const tabs = [["profile", "Профиль"], ["keys", "Модели и ключи"], ["modules", "Модули"]];
  $("m-body").innerHTML =
    '<div class="set-tabs">' + tabs.map(t =>
      '<button class="set-tab' + (SET_TAB === t[0] ? " on" : "") + '" data-t="' + t[0] + '">' + t[1] + "</button>").join("") +
    '</div><div id="s-body"></div><div class="err" id="s-err"></div>';
  $("m-body").querySelectorAll(".set-tab").forEach(b =>
    b.onclick = () => { SET_TAB = b.dataset.t; tabSet(p); });
  if (SET_TAB === "profile") setTabProfile(p);
  else if (SET_TAB === "keys") setTabKeys(p);
  else setTabModules(p);
}

function setOk(msg) { const e = $("s-err"); if (e) { e.style.color = "#6be08a"; e.textContent = msg; } }
function setFail(msg) { const e = $("s-err"); if (e) { e.style.color = ""; e.textContent = msg; } }

function setTabProfile(p) {
  $("s-body").innerHTML =
    '<div class="cs-menu"><div class="cs-menu-h">Юзернейм</div>' +
    '<div class="mrow" style="padding:4px 12px 12px"><input class="minput" id="p-user" style="margin:0" value="' + esc(p.username) + '">' +
    '<button class="cs-act primary" id="p-user-go">Сохранить</button></div></div>' +
    '<div class="cs-menu"><div class="cs-menu-h">Аватарка (png/jpeg, до 300 КБ)</div>' +
    '<div class="mrow" style="padding:4px 12px 12px"><input id="p-ava" type="file" accept="image/png,image/jpeg">' +
    '<button class="cs-act primary" id="p-ava-go">Загрузить</button></div></div>' +
    '<div class="cs-menu"><div class="cs-menu-h">Смена пароля</div>' +
    '<div style="padding:6px 12px 14px">' +
    '<input class="minput" type="password" id="p-old" placeholder="текущий пароль" autocomplete="current-password">' +
    '<input class="minput" type="password" id="p-new" placeholder="новый пароль (мин. 6)" autocomplete="new-password">' +
    '<input class="minput" type="password" id="p-new2" placeholder="повтори новый пароль" autocomplete="new-password">' +
    '<button class="cs-act primary" id="p-pass-go">Сменить пароль</button>' +
    '<div class="sub" style="margin-top:8px">После смены пароля все устройства выйдут из аккаунта.</div></div></div>';
  $("p-user-go").onclick = async () => {
    const r = await api("/api/profile/username", {username: $("p-user").value.trim()});
    if (r.data.error) return setFail(r.data.error);
    ME.username = r.data.username;
    const un = document.querySelector(".profcard .un");
    if (un) un.textContent = r.data.username;
    setOk("юзернейм обновлён");
  };
  $("p-ava-go").onclick = () => {
    const f = $("p-ava").files[0];
    if (!f) return setFail("выбери файл");
    if (f.size > 300 * 1024) return setFail("файл больше 300 КБ");
    const rd = new FileReader();
    rd.onload = async () => {
      const r = await api("/api/profile/avatar", {avatar: rd.result});
      if (r.data.error) return setFail(r.data.error);
      setOk("аватарка обновлена — обнови раздел (кнопка слева)");
    };
    rd.readAsDataURL(f);
  };
  $("p-pass-go").onclick = async () => {
    if ($("p-new").value !== $("p-new2").value) return setFail("новые пароли не совпадают");
    const r = await api("/api/profile/password",
      {old_password: $("p-old").value, new_password: $("p-new").value});
    if (r.data.error) return setFail(r.data.error);
    await api("/api/logout", {});
    location.reload();
  };
}

function setTabKeys(p) {
  const kmask = p.keys_masked || {};
  $("s-body").innerHTML =
    '<div class="cs-menu"><div class="cs-menu-h">Модель по умолчанию</div>' +
    '<div id="s-mlist" style="padding:8px 12px 12px"></div></div>' +
    '<div class="cs-menu"><div class="cs-menu-h">Ключи API (маскированы)</div>' +
    Object.keys(SVC_NAMES).map(s =>
      '<div class="cs-menu-row">' + SVC_NAMES[s] + ': <b>' + (kmask[s] || "не задан") + '</b>' +
      '<span><button class="cs-act" data-check="' + s + '">проверить</button> ' +
      '<button class="cs-act" data-s="' + s + '">сменить</button></span></div>').join("") +
    '<div class="mrow" style="padding:4px 12px 12px"><select class="minput" id="k-svc" style="margin:0;width:auto">' +
    Object.keys(SVC_NAMES).map(s => "<option>" + s + "</option>").join("") + "</select>" +
    '<input class="minput" id="s-val" style="margin:0" placeholder="новое значение ключа">' +
    '<button class="cs-act primary" id="s-apply">Применить</button></div></div>';
  /* Фаза 5-B: секция «Модель по умолчанию» из реестра */
  ensureCFGM().then(c => {
    const box = $("s-mlist");
    if (!box) return;
    const draw = curMdl => {
      box.innerHTML = c.models.map(m =>
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:7px 0">' +
        '<div><b style="font-size:13px">' + esc(m.name) + "</b>" +
        '<div class="sub" style="margin:0">' + esc((m.desc ? m.desc + " · " : "") + m.role) + "</div></div>" +
        '<span class="chip' + (m.id === curMdl ? " sel" : "") + '" data-id="' + m.id + '">' +
        (m.id === curMdl ? "текущая" : "выбрать") + "</span></div>").join("");
      box.querySelectorAll(".chip").forEach(ch => ch.onclick = async () => {
        const r = await api("/api/prefs/model", {model: ch.dataset.id});
        if (r.data.ok) {
          if (ME.onboarding && ME.onboarding.prefs) ME.onboarding.prefs.model = r.data.model;
          draw(r.data.model);
        }
      });
    };
    draw(((ME.onboarding.prefs || {}).model) || c.default_model);
  });
  const saveKey = async (svc, val, check) => {
    const r = await api("/api/keys", {service: svc, value: val, check: check});
    if (r.data.error) return setFail(r.data.error);
    ME.keys_masked = r.data.keys_masked;
    if (r.data.check) {
      if (r.data.check.ok) setOk("ключ сохранён · " + r.data.check.message);
      else setFail("ключ сохранён, но проверка не прошла: " + r.data.check.message);
    } else setOk("ключ сохранён");
    tabSet(ME);
  };
  $("m-body").querySelectorAll(".cs-act[data-s]").forEach(b =>
    b.onclick = () => {
      const val = prompt("Новый ключ для " + (SVC_NAMES[b.dataset.s] || b.dataset.s) + ":");
      if (val) saveKey(b.dataset.s, val.trim(), false);
    });
  $("m-body").querySelectorAll(".cs-act[data-check]").forEach(b =>
    b.onclick = async () => {
      const r = await api("/api/profile/key-check", {service: b.dataset.check});
      if (r.data.error) return setFail(r.data.error);
      if (r.data.ok) setOk((SVC_NAMES[b.dataset.check] || b.dataset.check) + ": " + r.data.message);
      else setFail((SVC_NAMES[b.dataset.check] || b.dataset.check) + ": " + r.data.message);
    });
  $("s-apply").onclick = () => {
    const val = $("s-val").value.trim();
    if (val) saveKey($("k-svc").value, val, true);
  };
}

function setTabModules(p) {
  const mods = p.modules;
  const modName = {wikipedia: "Википедия", telegram: "Telegram-бот", analytics: "Полная аналитика"};
  $("s-body").innerHTML =
    '<div class="cs-menu"><div class="cs-menu-h">Модули</div>' +
    Object.keys(modName).map(k =>
      '<button class="cs-menu-row" data-m="' + k + '">' + modName[k] +
      '<span class="cs-sw' + (mods[k] ? " on" : "") + '"></span></button>').join("") +
    '<div class="cs-menu-note">Аналитика сырая: включается паролем закрытого тестирования, работает только с твоим vault.</div></div>';
  $("s-body").querySelectorAll(".cs-menu-row[data-m]").forEach(row => row.onclick = async () => {
    const m = row.dataset.m;
    let pass = null;
    if (m === "analytics" && !mods.analytics_unlocked && !mods[m]) {
      pass = prompt("Аналитика сырая и может зацеплять данные других людей. Пароль закрытого тестирования:");
      if (pass === null) return;
    }
    const r = await api("/api/modules", {module: m, enabled: !mods[m], password: pass});
    if (r.data.error) return setFail(r.data.error);
    p.modules = r.data.modules;
    tabSet(p);
  });
}

/* ── загрузка ── */
async function boot() {
  dotsInit();
  const me = await (await fetch("/api/me")).json();
  if (me.state === "app") {
    // ВАЖНО: храним именно профиль (username/keys_masked внутри него),
    // а не весь ответ — иначе renderShell читает undefined (баг 27.08).
    ME = me.profile || me;
    renderShell();
  } else renderLogin();
}

boot();
