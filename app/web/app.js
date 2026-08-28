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
const W = {step: 1, source: "", purpose: "", username: "", language: "ru", model: "",
  daily_load: 5, avatar: null,
  modules: {wikipedia: true, telegram: false, analytics: false},
  analytics_unlocked: false, analytics_password: "",
  keys: {glm: "", smart: "", luna: ""}, password: "", hint: ""};
let CFGM = null;

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

/* Фаза 5-C: SVG-глиф у заголовка каждого шага (stroke-стиль chat.html) */
const WGLYPH = {
  2: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.3c-1.4 0-2.7-.3-3.9-.9L3 20l1.2-4.3a8.1 8.1 0 0 1-1.2-4.2A8.4 8.4 0 0 1 11.5 3.2a8.4 8.4 0 0 1 9.5 8.3z"/><path d="M9.5 9.5a2.5 2.5 0 0 1 4.9.8c0 1.6-2.4 2-2.4 3.2"/><circle cx="12" cy="16.6" r=".4"/></svg>',
  3: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c1.4-3.4 4.4-5 8-5s6.6 1.6 8 5"/></svg>',
  4: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/></svg>',
  5: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/></svg>',
  6: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="15" r="4.5"/><path d="M11.2 11.8 20 3M15.5 7.5l3 3M18 5l2.5 2.5"/></svg>',
  7: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/></svg>'
};

function wHead(title) {
  /* Фаза 5-C: глиф-бейдж над заголовком шага (стиль .wglyph из monica.css) */
  const g = WGLYPH[W.step] ? '<div class="wglyph">' + WGLYPH[W.step] + "</div>" : "";
  return '<div class="mstep">Шаг ' + W.step + " из 7</div>" +
    '<div class="mbar"><i style="width:' + (W.step / 7 * 100) + '%"></i></div>' +
    g + '<div class="mtitle">' + title + "</div>";
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
    W.step++; wDraftSave(); renderW();
  };
  if ($("w-back")) $("w-back").onclick = () => { W.step--; wDraftSave(); renderW(); };
}

function renderW() {
  const wz = $("wz");
  if (W.step === 1) {
    /* Фаза 5-C: полноэкранный герой как у логина (глобус + сериф + закрытая бета) */
    wz.innerHTML =
      '<div class="whero">' +
      '<div class="login-brand"><svg class="globe" viewBox="0 0 64 64" aria-hidden="true">' +
      '<defs><clipPath id="wc"><circle cx="32" cy="32" r="27"/></clipPath></defs>' +
      '<circle cx="32" cy="32" r="27" class="g-fill"/>' +
      '<g clip-path="url(#wc)" class="g-line"><circle cx="32" cy="32" r="27"/>' +
      '<ellipse cx="32" cy="32" rx="10" ry="27"/><ellipse cx="32" cy="32" rx="19" ry="27"/>' +
      '<line x1="5" y1="32" x2="59" y2="32"/><line x1="9" y1="18" x2="55" y2="18"/>' +
      '<line x1="9" y1="46" x2="55" y2="46"/></g>' +
      '<g class="g-type"><text x="32" y="40" text-anchor="middle">М</text></g></svg></div>' +
      "<h2>Привет! Это Моника</h2>" +
      "<p>Твоё личное ИИ-пространство: заметки, чат, модули и терминал — в одном спокойном месте.</p>" +
      '<p class="sub">За 7 коротких шагов соберём аккаунт: расскажешь, откуда ты, как будешь пользоваться, выберешь модули и подключишь ключи моделей.</p>' +
      '<span class="beta-tag">🔒 закрытое тестирование · доступ для друзей и бета-тестеров</span>' +
      '<div class="wz-back-row"><button class="mbtn" id="w-exit">← на главную</button>' +
      '<button class="mbtn acc" id="w-next">Начать →</button></div></div>';
    /* 6.4: возврат на главную (черновик сохраняется — можно продолжить позже) */
    $("w-exit").onclick = () => { wDraftSave(); renderLogin(); };
    $("w-next").onclick = () => { W.step = 2; wDraftSave(); renderW(); };
  } else if (W.step === 2) {
    wz.innerHTML = wHead("Пара вопросов") +
      '<label>Откуда вы узнали о нас?</label><div id="w-src"></div>' +
      '<label>Для чего хочешь использовать Монику? (опционально)</label><div id="w-pur"></div>' + wNav();
    const chips = (arr, box, cur, set) => {
      $(box).innerHTML = arr.filter(Boolean).map(x =>
        '<span class="chip' + (cur === x ? " sel" : "") + '" data-x="' + x + '">' + x + "</span>").join("");
      $(box).querySelectorAll(".chip").forEach(c => c.onclick = () => {
        if (set === "src") W.source = c.dataset.x;
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
      '<label>Язык интерфейса</label><select class="minput" id="w-lang">' +
      CFGM.languages.map(l => '<option' + (W.language === l ? " selected" : "") + ">" + l + "</option>").join("") + "</select>" +
      '<label>Аватарка (необязательно, до 300 КБ)</label><input id="w-ava" type="file" accept="image/png,image/jpeg">' + wNav();
    $("w-ava").onchange = () => {
      const f = $("w-ava").files[0];
      if (!f) return;
      if (f.size > 300 * 1024) { $("w-err").textContent = "файл больше 300 КБ"; return; }
      const rd = new FileReader();
      rd.onload = () => { W.avatar = rd.result; $("w-err").textContent = ""; };
      rd.readAsDataURL(f);
    };
    wBind(async () => {
      W.username = $("w-user").value.trim();
      W.language = $("w-lang").value;
      const r = await api("/api/check-username", {username: W.username});
      return r.data.ok ? null : (r.data.error || "юзернейм не подходит");
    });
  } else if (W.step === 4) {
    wz.innerHTML = wHead("Основная модель") +
      CFGM.models.map(m => '<div class="mod"><div><div class="t">' + m.name + '</div><div class="d">' + m.role +
        (m.desc ? " · " + m.desc : "") +
        '</div></div><span class="chip' + (W.model === m.id ? " sel" : "") + '" data-id="' + m.id + '">выбрать</span></div>').join("") +
      '<label>Сколько информации планируешь заносить в день</label>' +
      '<input type="range" id="w-load" min="1" max="10" value="' + W.daily_load + '">' +
      '<div class="sub">нагрузка: <b id="w-lv">' + W.daily_load + "</b>/10</div>" + wNav();
    wz.querySelectorAll(".chip").forEach(c => c.onclick = () => { W.model = c.dataset.id; renderW(); });
    $("w-load").oninput = () => { W.daily_load = +$("w-load").value; $("w-lv").textContent = W.daily_load; };
    wBind(async () => W.model ? null : "выбери модель");
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
    for (const k of Object.keys(ks)) $("k-" + k).value = W.keys[k];
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
      '</b> · модель: <b>' + W.model + '</b> · нагрузка: <b>' + W.daily_load + '/10</b><br>Модули: <b>' +
      Object.keys(W.modules).filter(k => W.modules[k]).join(", ") + '</b><br>Ключи: <b>' +
      Object.keys(W.keys).filter(k => W.keys[k]).join(", ") + "</b></div>" + wNav();
    $("w-hint").oninput = () => W.hint = $("w-hint").value;
    wBind(async () => {
      W.password = $("w-pass").value;
      if (W.password.length < 6) return "пароль: минимум 6 символов";
      const r = await api("/api/onboarding/complete", {
        username: W.username, password: W.password, hint: W.hint, avatar: W.avatar,
        survey: {source: W.source, purpose: W.purpose},
        prefs: {language: W.language, model: W.model, daily_load: W.daily_load},
        modules: W.modules, analytics_password: W.analytics_password, keys: W.keys});
      if (r.data.ok) { wDraftClear(); boot(); return null; }
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
    SESS.cur = {id: Date.now(), title: "Новая сессия",
      started: new Date().toISOString(),
      ts: new Date().toLocaleString("ru-RU", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"}),
      pinned: false, msgs: []};
    SESS.list.push(SESS.cur);
  }
  return SESS.cur;
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
  /* 8.9: поиск по сессиям; 6.11: закреплённые сверху */
  const q = (($("sess-q") && $("sess-q").value) || "").toLowerCase();
  const sorted = SESS.list.slice().sort((a, b) =>
    (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || b.id - a.id);
  const shown = sorted.filter(s => !q || (s.title || "").toLowerCase().includes(q));
  box.innerHTML = shown.length ? shown.map(s =>
    '<div class="sessrow' + (SESS.cur && s.id === SESS.cur.id ? " on" : "") +
    (s.pinned ? " pinned" : "") + '" data-id="' + s.id + '">' +
    '<span class="spin" data-pin="' + s.id + '" title="закрепить/открепить">' +
    (s.pinned ? "📌" : "📍") + "</span>" +
    '<span class="st" data-ren="' + s.id + '" title="двойной клик — переименовать">' +
    esc(s.title || "Новая сессия") + "</span>" +
    '<span class="sx" data-del="' + s.id + '" title="удалить сессию">×</span></div>').join("") :
    '<div class="sub" style="padding:4px 2px">' + (q ? "не найдено" : "сессий пока нет") + "</div>";
  box.querySelectorAll(".sessrow").forEach(row => {
    const id = +row.dataset.id;
    row.onclick = e => {
      if (e.target.dataset.del || e.target.dataset.pin) return;
      openSess(id);
    };
    const pin = row.querySelector(".spin");
    if (pin) pin.onclick = e => {
      e.stopPropagation();
      const s = SESS.list.find(x => x.id === id);
      if (s) { s.pinned = !s.pinned; sessSave(); drawSess(); }
    };
    const ren = row.querySelector(".st");
    if (ren) ren.ondblclick = e => {
      e.stopPropagation();
      const s = SESS.list.find(x => x.id === id);
      if (!s) return;
      const t = prompt("Новое название сессии:", s.title);
      if (t && t.trim()) { s.title = t.trim().slice(0, 60); sessSave(); drawSess(); }
    };
    const del = row.querySelector(".sx");
    if (del) del.onclick = e => {
      e.stopPropagation();
      SESS.list = SESS.list.filter(x => x.id !== id);
      if (SESS.cur && SESS.cur.id === id) { SESS.cur = null; CHAT_HIST = []; openTab("chat"); }
      sessSave();
      drawSess();
    };
  });
}
function openSess(id) {
  const s = SESS.list.find(x => x.id === id);
  if (!s) return;
  SESS.cur = s;
  CHAT_HIST = s.msgs.slice();
  openTab("chat", {skipAnim: true});
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
  SESS.cur = null;
  CHAT_HIST = [];
  openTab("chat");
  drawSess();
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
    /* 5-H.7 + 6-S: список сессий чата под профильной карточкой */
    '<div class="cs-sess-h">сессии</div>' +
    '<input class="minput sess-q" id="sess-q" placeholder="поиск…" autocomplete="off">' +
    '<div id="cs-sess" class="sesslist"></div>' +
    '<button type="button" class="sess-new" id="sess-new">+ новая сессия</button>';
  sessLoad();
  drawSess();
  $("sess-q").addEventListener("input", drawSess);
  $("sess-new").onclick = newSess;
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
const THINK = ["Думаю…", "Ищу информацию в архиве…", "Сверяю факты и связи…", "Перечитываю заметки…"];
const SUGGESTIONS = ["Что вика знает обо мне?", "Разбери мой последний день",
  "Создай заметку идеи/план на неделю", "Какие у меня открытые вопросы?"];
let SUG_SHOWN = true;

function tabChat(p) {
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

function addTyping() {
  hideEmpty();
  const log = $("chat-log") || $("tlog");
  const d = document.createElement("div");
  d.className = "chat-msg bot typing";
  d.innerHTML = '<span class="tp-phrase">' + THINK[0] + '</span><span class="typing-dots"><i></i><i></i><i></i></span>';
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
  const ph = d.querySelector(".tp-phrase");
  let i = 0;
  const rot = setInterval(() => { i = (i + 1) % THINK.length; if (ph) ph.textContent = THINK[i]; }, 1600);
  return {el: d, stop: () => clearInterval(rot)};
}

let LAST_MSG = null;

async function chatTurn(text) {
  addMsg("user", text);
  CHAT_HIST.push({role: "user", content: text});
  sessTrack("user", text);
  LAST_MSG = text;
  const tp = addTyping();
  try {
    const r = await fetch("/api/chat/stream", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text, history: CHAT_HIST.slice(-20)})});
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
    const rb = document.createElement("button");
    rb.className = "cs-act"; rb.textContent = "Повторить";
    rb.onclick = () => { b.remove(); chatTurn(text); };
    b.appendChild(rb);
  }
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
    '<div class="tpane tpane-tree"><div class="cs-menu-h">vault</div><div id="ttree" class="ttree"></div></div>' +
    '<div class="tpane tpane-mid">' +
    '<div class="tmid-switch">' +
    '<button type="button" class="set-tab' + (TERM.view === "chat" ? " on" : "") + '" id="tv-chat">Чат</button>' +
    '<button type="button" class="set-tab' + (TERM.view === "edit" ? " on" : "") + '" id="tv-edit">Редактор</button></div>' +
    '<div id="tchat"' + (TERM.view === "chat" ? "" : ' class="hidden"') + '>' +
    '<div id="tlog" class="cs-log"></div>' +
    '<div class="cs-bottom"><form id="tform"><div class="cs-inputbar" id="tbar">' +
    '<textarea id="t-input" rows="1"></textarea>' +
    '<button type="submit" class="cs-send" title="Отправить">' + SEND_SVG + "</button>" +
    "</div></form></div></div>" +
    '<div id="teditor"' + (TERM.view === "edit" ? "" : ' class="hidden"') + '>' +
    '<div class="te-head"><span class="te-tab"><span class="te-dot" id="te-dot"></span>' +
    '<span id="te-file">' + esc(TERM.openFile || "файл не выбран — кликни в дереве слева") + "</span></span>" +
    '<button type="button" class="cs-act primary" id="te-save">Сохранить</button></div>' +
    '<div class="te-wrap"><div class="te-gutter" id="te-gutter"></div>' +
    '<textarea id="te-area" class="te-area" spellcheck="false"></textarea></div>' +
    '<div class="te-status" id="te-status"></div></div>' +
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
  /* переключатель Чат ⇄ Редактор — без перерисовки, состояние сохраняется */
  const setView = v => {
    TERM.view = v;
    $("tv-chat").classList.toggle("on", v === "chat");
    $("tv-edit").classList.toggle("on", v === "edit");
    $("tchat").classList.toggle("hidden", v !== "chat");
    $("teditor").classList.toggle("hidden", v !== "edit");
    if (v === "edit" && TERM.openFile) loadEditor();
  };
  $("tv-chat").onclick = () => { setView("chat"); animTab($("tchat")); };
  $("tv-edit").onclick = () => { setView("edit"); animTab($("teditor")); };
  $("te-save").onclick = saveEditor;
  $("te-area").addEventListener("input", () => {
    if (!TERM.dirty) { TERM.dirty = true; $("te-dot").classList.add("on"); }
    updateGutter();
    updateStatus();
  });
  $("te-area").addEventListener("scroll", syncGutter);
  $("te-area").addEventListener("keyup", () => { updateGutter(); updateStatus(); });
  $("te-area").addEventListener("click", () => { updateGutter(); updateStatus(); });
  /* 5-I.3: сохранение по Ctrl+S / Cmd+S */
  $("te-area").addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveEditor(); }
  });
  drawTree();
  drawHist();
}

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

function renderTreeNode(node, out) {
  Object.keys(node.dirs).sort().forEach(name => {
    out.push('<details class="tdir" open><summary>' + FOLDER_SVG + esc(name) + "</summary>");
    renderTreeNode(node.dirs[name], out);
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
  renderTreeNode(buildTree(r.data.tree || []), out);
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
  box.querySelectorAll(".cs-act[data-id]").forEach(b => b.onclick = async () => {
    const r2 = await api("/api/vault/undo", {id: b.dataset.id});
    addTMsg("bot", r2.data.message || ("⚠️ " + (r2.data.error || "ошибка отката")));
    drawTree();
    drawHist();
  });
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
  const tp = addTyping();
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
    '<div class="sgroup"><h3>Статьи</h3><ul id="wk-arts-ul"></ul></div>' +
    '<div class="sgroup"><h3>Инструменты</h3><ul>' +
    '<li><a href="#" id="wk-nav-search">Поиск по заметкам</a></li>' +
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
    $("wk-arts").innerHTML =
      '<div class="sgroup"><h3>Статьи</h3><ul>' +
      (arts.length ? arts.map(a =>
        '<li><a href="#" data-p="' + esc(a.path) + '">' + esc(a.title) + "</a></li>").join("")
        : '<li><span class="sub">Статей пока нет — «Обновить вики» создаст их из очереди.</span></li>') +
      "</ul></div>";
    $("wk-arts").querySelectorAll("a[data-p]").forEach(el =>
      el.onclick = ev => { ev.preventDefault(); openArticle(el.dataset.p); });
  };
  const openArticle = async path => {
    const r = await api("/api/wiki/articles", {path: path});
    if (r.data.error) { $("wk-view").innerHTML = '<p style="color:var(--red)">' + esc(r.data.error) + "</p>"; return; }
    const fm = parseFrontmatter(r.data.content);
    const title = fm.meta.title || (path.split("/").pop() || "").replace(/\.md$/, "");
    /* инфобокс — родная таблица Иванопедии (style.css .infobox, float:right) */
    $("wk-view").innerHTML =
      '<button type="button" class="cs-act" id="wk-back" style="margin-bottom:10px">← к списку статей</button>' +
      '<h1 class="firstHeading">' + esc(title) + "</h1>" +
      '<div class="wk-meta">' + esc(fm.meta.created || "") +
      (fm.meta.source ? " · источник: " + esc(fm.meta.source) : "") + "</div>" +
      '<div class="body">' +
      '<table class="infobox"><caption>' + esc(title) + "</caption>" +
      "<tr><th>создано</th><td>" + esc(fm.meta.created || "—") + "</td></tr>" +
      "<tr><th>источник</th><td>" + esc(fm.meta.source || "—") + "</td></tr>" +
      "<tr><th>теги</th><td>" + esc(fm.meta.tags || "—") + "</td></tr>" +
      '<tr><td colspan="2" class="ib-foot">статья личной вики Моники</td></tr></table>' +
      md(fm.body) + "</div>";
    $("wk-home").classList.add("hidden");
    $("wk-view").classList.remove("hidden");
    animTab($("wk-view"));
    $("wk-back").onclick = () => {
      $("wk-view").classList.add("hidden");
      $("wk-home").classList.remove("hidden");
    };
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
