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
  $("l-go").onclick = async () => {
    const r = await api("/api/login", {username: $("l-user").value.trim(), password: $("l-pass").value});
    if (r.data.ok) boot(); else $("l-err").textContent = r.data.error || "ошибка";
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

function renderWizard() {
  show("scr-wizard");
  W.step = 1;
  fetch("/api/models").then(r => r.json()).then(c => { CFGM = c; renderW(); });
}

function wHead(title) {
  return '<div class="mstep">Шаг ' + W.step + " из 7</div>" +
    '<div class="mbar"><i style="width:' + (W.step / 7 * 100) + '%"></i></div>' +
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
    W.step++; renderW();
  };
  if ($("w-back")) $("w-back").onclick = () => { W.step--; renderW(); };
}

function renderW() {
  const wz = $("wz");
  if (W.step === 1) {
    wz.innerHTML = wHead("Привет! Это Моника") +
      '<p>Твоё личное ИИ-пространство: заметки, чат, модули и терминал — в одном спокойном месте.</p>' +
      '<p>За 7 коротких шагов соберём аккаунт: расскажешь, откуда ты, как будешь пользоваться, выберешь модули и подключишь ключи моделей.</p>' +
      '<p class="sub">Пара минут. Всё можно поменять потом в настройках.</p>' + wNav();
    wBind(async () => null);
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
    const ks = {glm: ["GLM 5.3 Fast", "терминал и быстрые операции"],
      smart: ["Умная модель", "ядро анализа (аналог ox alpha)"],
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
      if (r.data.ok) { boot(); return null; }
      return r.data.error || "ошибка сохранения";
    });
  }
}

/* ── каркас приложения (скелет chat.html) ── */
const NAV = [
  ["chat", "💬", "Чат"],
  ["term", "⌨️", "Терминал"],
  ["wiki", "📚", "Википедия"],
  ["tg", "✈️", "Бот"],
  ["ana", "📊", "Аналитика"],
  ["set", "⚙️", "Настройки"],
];
const TITLES = {chat: "Чат с Моникой", term: "Терминал", wiki: "Википедия",
  tg: "Telegram-бот", ana: "Полная аналитика", set: "Настройки"};
let ME = null, TAB = "chat", CHAT_HIST = [];

function renderShell() {
  show("scr-app");
  $("cs-nav").innerHTML = NAV.map((n, i) =>
    '<button class="cs-navitem' + (i === 0 ? " on" : "") + '" data-tab="' + n[0] + '">' +
    '<span class="cs-ico">' + n[1] + "</span><span>" + n[2] + "</span></button>").join("");
  $("cs-nav").querySelectorAll(".cs-navitem").forEach(b => b.onclick = () => {
    document.querySelectorAll(".cs-navitem").forEach(x => x.classList.remove("on"));
    b.classList.add("on");
    openTab(b.dataset.tab);
  });
  const p = ME;
  $("cs-prof").innerHTML =
    '<div class="prof">' + (p.avatar ? '<img src="' + p.avatar + '">' : '<div class="pa">' + esc(p.username[0].toUpperCase()) + '</div>') +
    '<div><div class="un">' + esc(p.username) + '</div><div class="mdl">' + esc((p.onboarding.prefs || {}).model || "") + '</div></div></div>' +
    '<div class="sum" style="padding:0 6px 8px">реплик в сессии: <b id="pf-cnt">0</b></div>';
  $("cs-logout").onclick = async () => { await api("/api/logout", {}); location.reload(); };
  $("cs-gear").onclick = () => openTab("set");
  $("cs-refresh").onclick = () => location.reload();
  openTab("chat");
}

function openTab(tab) {
  TAB = tab;
  $("m-title").textContent = TITLES[tab] || tab;
  $("m-sub").textContent = new Date().toLocaleDateString("ru-RU", {day: "numeric", month: "long", weekday: "long"});
  ({chat: tabChat, term: tabTerm, wiki: tabWiki, tg: tabTg, ana: tabAna, set: tabSet})[tab](ME);
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
    '<div class="cs-empty-grid">' + SUGGESTIONS.map(s =>
      '<button type="button" class="cs-sug">' + s + "</button>").join("") + "</div></div>" +
    '<div class="cs-bottom"><form id="chat-form"><div class="cs-inputbar">' +
    '<textarea id="chat-input" rows="1" placeholder="напиши Монике…"></textarea>' +
    '<button type="submit" class="cs-send" title="Отправить">➤</button>' +
    "</div></form>" +
    '<div class="cs-actions"><span id="cs-status" class="cs-status"></span></div></div>';
  const form = $("chat-form"), input = $("chat-input"), log = $("chat-log");
  const resize = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; };
  input.addEventListener("input", resize);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  form.onsubmit = e => { e.preventDefault(); const t = input.value.trim(); if (!t) return; input.value = ""; resize(); chatTurn(t); };
  document.querySelectorAll(".cs-sug").forEach(b => b.onclick = () => chatTurn(b.textContent));
  addBotMsg("Привет, " + p.username + "! Я Моника. Отвечаю на модели «" +
    ((p.onboarding.prefs || {}).model || "?") + "». О чём думаем?");
}

function hideEmpty() {
  const e = $("cs-empty");
  if (e) e.classList.add("off");
}

function addMsg(role, text) {
  hideEmpty();
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
  } catch (e) {
    tp.stop();
    const b = addMsg("bot", "⚠️ " + (e.message || e));
    const rb = document.createElement("button");
    rb.className = "cs-act"; rb.textContent = "Повторить";
    rb.onclick = () => { b.remove(); chatTurn(text); };
    b.appendChild(rb);
  }
}

/* ── терминал: тот же панельный стиль, GLM, подтверждение операций ── */
function tabTerm(p) {
  $("m-body").innerHTML =
    '<div id="tlog" class="cs-log"></div>' +
    '<div class="cs-bottom"><form id="tform"><div class="cs-inputbar">' +
    '<textarea id="t-input" rows="1" placeholder="например: создай заметку идеи/план.md"></textarea>' +
    '<button type="submit" class="cs-send" title="Отправить">➤</button>' +
    "</div></form></div>";
  addTMsg("bot", "Терминал работает только с твоим vault. Изменения — после подтверждения. Ядро Моники и чужие данные недоступны.");
  const form = $("tform"), input = $("t-input");
  const resize = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; };
  input.addEventListener("input", resize);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  form.onsubmit = e => { e.preventDefault(); const t = input.value.trim(); if (!t) return; input.value = ""; resize(); termTurn(t); };
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
    };
  } catch (e) {
    tp.stop();
    addTMsg("bot", "⚠️ " + e);
  }
}

/* ── Википедия: поиск и выжимки в стиле статей Иванопедии ── */
function tabWiki(p) {
  $("m-body").innerHTML =
    '<div class="wk-search"><input class="minput" id="wk-q" style="margin:0" placeholder="что ищем в своих заметках?">' +
    '<button class="cs-act primary" id="wk-go">Искать</button></div>' +
    '<div id="wk-res" class="body"></div>';
  const doSearch = async () => {
    const r = await api("/api/wiki/search", {query: $("wk-q").value});
    const res = r.data.results || [];
    if (!res.length) { $("wk-res").innerHTML = '<p>По этому запросу заметок нет.</p>'; return; }
    $("wk-res").innerHTML = res.map(h =>
      '<div class="wl"><div class="wl-t">' + esc(h.path) + '</div>' +
      '<div class="wl-s">' + esc(h.snippet) + '</div>' +
      '<button class="cs-act" data-p="' + esc(h.path) + '">сделать выжимку</button></div>').join("");
    $("wk-res").querySelectorAll(".cs-act").forEach(b => b.onclick = () => {
      const title = prompt("Название выжимки:");
      if (!title) return;
      api("/api/wiki/extract", {source_path: b.dataset.p, title: title}).then(r2 => {
        $("wk-res").insertAdjacentHTML("afterbegin",
          r2.data.ok ? '<p>✅ Выжимка сохранена: <b>' + esc(r2.data.path) + '</b></p>' :
          '<p style="color:var(--red)">' + esc(r2.data.error) + '</p>');
      });
    });
  };
  $("wk-go").onclick = doSearch;
  $("wk-q").onkeydown = e => { if (e.key === "Enter") doSearch(); };
}

/* ── Telegram-бот: подключение токена и статус поллера ── */
function tabTg(p) {
  $("m-body").innerHTML = '<div id="tg-body" class="body"><p>загружаю статус…</p></div>';
  const draw = async () => {
    const s = await (await fetch("/api/tg/status")).json();
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

/* ── настройки: ключи + модули в стиле cs-menu ── */
function tabSet(p) {
  const mods = p.modules;
  const kmask = p.keys_masked || {};
  const modName = {wikipedia: "Википедия", telegram: "Telegram-бот", analytics: "Полная аналитика"};
  $("m-body").innerHTML =
    '<div class="cs-menu"><div class="cs-menu-h">Ключи API (маскированы, можно сменить)</div>' +
    ["glm", "smart", "luna"].map(s =>
      '<div class="cs-menu-row">' + s + ': <b>' + (kmask[s] || "не задан") + '</b>' +
      '<button class="cs-act" data-s="' + s + '">сменить</button></div>').join("") +
    '<div class="mrow" style="padding:4px 12px 12px"><input class="minput" id="s-val" style="margin:0" placeholder="новое значение ключа">' +
    '<button class="cs-act primary" id="s-apply">Применить</button></div></div>' +
    '<div class="cs-menu"><div class="cs-menu-h">Модули</div>' +
    Object.keys(modName).map(k =>
      '<button class="cs-menu-row" data-m="' + k + '">' + modName[k] +
      '<span class="cs-sw' + (mods[k] ? " on" : "") + '"></span></button>').join("") +
    '<div class="cs-menu-note">Аналитика сырая: включается паролем закрытого тестирования, работает только с твоим vault.</div></div>' +
    '<div class="err" id="s-err"></div>';
  $("m-body").querySelectorAll(".cs-menu-row[data-m]").forEach(row => row.onclick = async () => {
    const m = row.dataset.m;
    let pass = null;
    if (m === "analytics" && !mods.analytics_unlocked && !mods[m]) {
      pass = prompt("Аналитика сырая и может зацеплять данные других людей. Пароль закрытого тестирования:");
      if (pass === null) return;
    }
    const r = await api("/api/modules", {module: m, enabled: !mods[m], password: pass});
    if (r.data.error) { $("s-err").textContent = r.data.error; return; }
    p.modules = r.data.modules;
    tabSet(p);
  });
  $("m-body").querySelectorAll(".cs-act[data-s]").forEach(b => b.onclick = async () => {
    const val = prompt("Новый ключ для " + b.dataset.s + ":");
    if (!val) return;
    const r = await api("/api/keys", {service: b.dataset.s, value: val});
    if (r.data.ok) { ME.keys_masked = r.data.keys_masked; tabSet(ME); }
    else $("s-err").textContent = r.data.error;
  });
  $("s-apply").onclick = async () => {
    const svc = prompt("Для какого сервиса? (glm / smart / luna)");
    if (!svc) return;
    const r = await api("/api/keys", {service: svc, value: $("s-val").value.trim()});
    if (r.data.ok) { ME.keys_masked = r.data.keys_masked; tabSet(ME); }
    else $("s-err").textContent = r.data.error;
  };
}

/* ── загрузка ── */
async function boot() {
  dotsInit();
  const me = await (await fetch("/api/me")).json();
  if (me.state === "app") { ME = me; renderShell(); }
  else renderLogin();
}

boot();
