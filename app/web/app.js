"use strict";
const $ = id => document.getElementById(id);
let CFG = null; // models/sources/purposes/languages с сервера

async function api(path, body, method) {
  const r = await fetch(path, {
    method: method || "POST",
    headers: {"Content-Type": "application/json"},
    body: body ? JSON.stringify(body) : "{}"
  });
  return {status: r.status, data: await r.json().catch(() => ({}))};
}

function shell(inner) {
  $("root").innerHTML = '<div class="card">' + inner + "</div>";
}

// ── экран входа ──
function renderLogin() {
  shell(`
    <h1>Моника</h1>
    <div class="sub">спокойное место для твоих мыслей, заметок и проектов</div>
    <label>Юзернейм</label><input id="l-user" type="text" autocomplete="username">
    <label>Пароль</label><input id="l-pass" type="password" autocomplete="current-password">
    <div class="row"><button id="l-hint" class="sub">показать подсказку</button>
    <span></span></div>
    <div class="sub" id="l-hintout"></div>
    <div class="err" id="l-err"></div>
    <div class="row">
      <button id="l-reg">Создать аккаунт</button>
      <button class="primary" id="l-go">Войти</button>
    </div>`);
  $("l-go").onclick = async () => {
    const r = await api("/api/login", {username: $("l-user").value.trim(), password: $("l-pass").value});
    if (r.data.ok) boot(); else $("l-err").textContent = r.data.error || "ошибка";
  };
  $("l-reg").onclick = () => renderWizard();
  $("l-hint").onclick = async () => {
    const r = await api("/api/hint", {username: $("l-user").value.trim()});
    $("l-hintout").textContent = r.data.hint ? "подсказка: " + r.data.hint : (r.data.error || "нет такого пользователя");
  };
}

// ── онбординг: 7 шагов ──
const W = {
  step: 1, source: "", purpose: "", username: "", language: "ru",
  model: "", daily_load: 5, avatar: null,
  modules: {wikipedia: true, telegram: false, analytics: false},
  analytics_unlocked: false, analytics_password: "",
  keys: {glm: "", smart: "", luna: ""}, password: "", hint: ""
};

function wHeader(title) {
  return '<div class="step">Шаг ' + W.step + ' из 7</div>' +
    '<div class="bar"><i style="width:' + (W.step / 7 * 100) + '%"></i></div>' +
    '<h2>' + title + "</h2>";
}

function nav(onNext) {
  const prev = W.step > 1 ? '<button id="w-back">Назад</button>' : "<span></span>";
  return '<div class="err" id="w-err"></div><div class="row">' + prev +
    '<button class="primary" id="w-next">' + (W.step === 7 ? "Перейти в Монику" : "Далее") + "</button></div>";
}

function bindNav(onNext) {
  const b = $("w-next");
  b.onclick = async () => {
    b.disabled = true;
    const err = await onNext();
    b.disabled = false;
    if (err) { $("w-err").textContent = err; return; }
    W.step++;
    renderStep();
  };
  if ($("w-back")) $("w-back").onclick = () => { W.step--; renderStep(); };
}

const STEPS = {
  1: () => { // приветствие
    shell(wHeader("Привет! Это Моника") +
      `<p>Твоё личное ИИ-пространство: заметки, чат с ассистентом, модули и терминал — всё в одном спокойном месте.</p>
       <p>Сейчас за 7 коротких шагов соберём аккаунт под тебя: расскажешь, откуда ты, как планируешь пользоваться, выберешь модули и подключишь ключи моделей.</p>
       <p class="sub">Займёт пару минут. Изменить всё можно потом в настройках.</p>` + nav());
    bindNav(async () => null);
  },

  2: () => { // микроопрос
    shell(wHeader("Пара вопросов о тебе") +
      `<label>Откуда вы узнали о нас?</label><div id="w-src"></div>
       <label>Для чего хочешь использовать Монику? (опционально)</label><div id="w-purpose"></div>` + nav());
    const chips = (arr, cur, set) => {
      const box = set === "source" ? $("w-src") : $("w-purpose");
      box.innerHTML = arr.map(x => '<span class="chip' + (cur === x ? " sel" : "") + '" data-x="' + x + '">' + x + "</span>").join("");
      box.querySelectorAll(".chip").forEach(c => c.onclick = () => {
        if (set === "source") {
          W.source = c.dataset.x;
        } else {
          // цель опциональна: повторный клик по выбранной снимает выбор
          W.purpose = (W.purpose === c.dataset.x) ? "" : c.dataset.x;
        }
        STEPS[2]();
      });
    };
    chips(CFG.sources, W.source, "source");
    chips(CFG.purposes, W.purpose, "purpose");
    bindNav(async () => W.source ? null : "выбери, откуда ты о нас узнал(а)");
  },

  3: () => { // профиль
    shell(wHeader("Профиль") +
      `<label>Юзернейм (латиница, 3-24 символа)</label><input id="w-user" type="text" value="` + W.username + `">
       <label>Язык интерфейса</label><select id="w-lang">` +
       CFG.languages.map(l => '<option' + (W.language === l ? " selected" : "") + ">" + l + "</option>").join("") +
       `</select>
       <label>Аватарка (необязательно, до 300 КБ)</label><input id="w-ava" type="file" accept="image/png,image/jpeg">` + nav());
    $("w-ava").onchange = () => {
      const f = $("w-ava").files[0];
      if (!f) return;
      if (f.size > 300 * 1024) { $("w-err").textContent = "файл больше 300 КБ"; return; }
      const rd = new FileReader();
      rd.onload = () => { W.avatar = rd.result; $("w-err").textContent = ""; };
      rd.readAsDataURL(f);
    };
    bindNav(async () => {
      W.username = $("w-user").value.trim();
      W.language = $("w-lang").value;
      if (W.username !== localStorage.getItem("checked")) {
        const r = await api("/api/check-username", {username: W.username});
        if (!r.data.ok) return r.data.error || "юзернейм не подходит";
        localStorage.setItem("checked", W.username);
      }
      return null;
    });
  },

  4: () => { // модель
    shell(wHeader("Какая модель будет основной?") +
      `<div id="w-models">` + CFG.models.map(m =>
        '<div class="mod"><div><div class="t">' + m.name + '</div><div class="d">' + m.role +
        '</div></div><span class="chip' + (W.model === m.id ? " sel" : "") + '" data-id="' + m.id + '">выбрать</span></div>').join("") +
      `</div>
       <label>Сколько информации планируешь заносить в день</label>
       <input type="range" id="w-load" min="1" max="10" value="` + W.daily_load + `">
       <div class="sub">нагрузка: <b id="w-loadv">` + W.daily_load + `</b>/10</div>` + nav());
    $("w-models").querySelectorAll(".chip").forEach(c => c.onclick = () => {
      W.model = c.dataset.id; STEPS[4]();
    });
    $("w-load").oninput = () => { W.daily_load = +$("w-load").value; $("w-loadv").textContent = W.daily_load; };
    bindNav(async () => W.model ? null : "выбери основную модель");
  },

  5: () => { // модули
    const names = {wikipedia: ["Википедия", "поиск по твоим заметкам, сводки, выжимки"],
      telegram: ["Telegram-бот", "быстрый вход: мысли, голосовые, файлы — прямо в базу"],
      analytics: ["Полная аналитика", "экспериментальный модуль. По умолчанию выключен."]};
    shell(wHeader("Модули") +
      Object.keys(names).map(k =>
        '<div class="mod"><div><div class="t">' + names[k][0] + '</div><div class="d">' + names[k][1] + '</div></div>' +
        '<div class="tg' + (W.modules[k] ? " on" : "") + '" data-m="' + k + '"></div></div>').join("") +
      '<div id="w-modextra"></div>' + nav());
    shell_mods();
    bindNav(async () => null);
  },

  6: () => { // ключи
    const ks = {glm: ["GLM 5.3 Fast", "терминал и быстрые системные операции"],
      smart: ["Умная модель", "ядро интеллектуальной работы со second-brain (аналог ox alpha)"],
      luna: ["ChatGPT 5.6 Luna", "Telegram-бот и чат на сайте"]};
    shell(wHeader("API-ключи") +
      `<p class="sub">Ключи хранятся зашифрованными, каждый сервис — изолированно. Позже можно поменять в настройках. В закрытой бете ключи обязательны.</p>` +
      Object.keys(ks).map(k => '<div class="key"><label>' + ks[k][0] + '</label><div class="d">' + ks[k][1] +
        '</div><input type="password" id="k-' + k + '" placeholder="вставь ключ"></div>').join("") + nav());
    for (const k of Object.keys(ks)) $("k-" + k).value = W.keys[k];
    bindNav(async () => {
      for (const k of Object.keys(ks)) W.keys[k] = $("k-" + k).value.trim();
      const miss = Object.keys(W.keys).filter(k => W.keys[k].length < 8);
      return miss.length ? "заполни ключи: " + miss.join(", ") : null;
    });
  },

  7: () => { // пароль + резюме
    shell(wHeader("Почти готово") +
      `<label>Придумай пароль (мин. 6 символов)</label><input id="w-pass" type="password">
       <label>Подсказка к паролю (если забудешь)</label><input id="w-hint" type="text" value="` + W.hint + `">
       <div class="sum" style="margin-top:16px">
       Юзернейм: <b>` + W.username + `</b><br>
       Откуда: <b>` + (W.source || "-") + `</b> · цель: <b>` + (W.purpose || "-") + `</b><br>
       Язык: <b>` + W.language + `</b> · модель: <b>` + W.model + `</b> · нагрузка: <b>` + W.daily_load + `/10</b><br>
       Модули: <b>` + Object.keys(W.modules).filter(k => W.modules[k]).join(", ") + `</b><br>
       Ключи: <b>` + Object.keys(W.keys).filter(k => W.keys[k]).join(", ") + `</b>
       </div>` + nav());
    $("w-hint").oninput = () => W.hint = $("w-hint").value;
    bindNav(async () => {
      W.password = $("w-pass").value;
      if (W.password.length < 6) return "пароль: минимум 6 символов";
      const payload = {
        username: W.username, password: W.password, hint: W.hint, avatar: W.avatar,
        survey: {source: W.source, purpose: W.purpose},
        prefs: {language: W.language, model: W.model, daily_load: W.daily_load},
        modules: W.modules, analytics_password: W.analytics_password,
        keys: W.keys
      };
      const r = await api("/api/onboarding/complete", payload);
      if (r.data.ok) { location.reload(); return null; }
      return r.data.error || "ошибка сохранения";
    });
  }
};

function shell_mods() {
  document.querySelectorAll(".tg").forEach(t => t.onclick = async () => {
    const m = t.dataset.m;
    if (m === "analytics" && !W.analytics_unlocked && !W.modules.analytics) {
      const pass = prompt("Модуль сырой и может зацеплять данные других людей. Доступ только в рамках закрытого тестирования.\n\nПароль закрытого тестирования:");
      if (pass === null) return;
      const r = await api("/api/analytics/check", {password: pass});
      if (!r.data.ok) { $("w-modextra").innerHTML = '<div class="err">неверный пароль</div>'; return; }
      W.analytics_unlocked = true; W.analytics_password = pass;
      $("w-modextra").innerHTML = '<div class="warn">Аналитика разблокирована. Технология сырая: работаем только с твоими данными, слежка и чужие границы — нет.</div>';
    }
    W.modules[m] = !W.modules[m];
    t.className = "tg" + (W.modules[m] ? " on" : "");
  });
}

function renderStep() {
  if (STEPS[W.step]) STEPS[W.step]();
}

function renderWizard() {
  W.step = 1;
  fetch("/api/models").then(r => r.json()).then(c => { CFG = c; renderStep(); });
}

// ── экран приложения: вкладки Чат / Терминал / Настройки ──
let CHAT_HIST = [];

function renderApp(me) {
  const p = me.profile;
  $("root").innerHTML = `
    <div class="card app" style="min-height:78vh">
      <div style="display:flex;align-items:center;gap:12px;border-bottom:1px solid var(--line);padding-bottom:12px">
        ` + (p.avatar ? '<img class="avatar" src="' + p.avatar + '">' : '<div class="avatar"></div>') + `
        <div><h1 style="font-size:18px">Моника</h1>
        <div class="sub">` + p.username + ` · модель: ` + (p.onboarding.prefs?.model || "-") + `</div></div>
        <span style="flex:1"></span>
        <button id="a-out">Выйти</button>
      </div>
      <div style="display:flex;gap:14px;margin-top:16px;min-height:56vh">
        <div id="tabnav" style="width:150px;flex:none;display:flex;flex-direction:column;gap:8px"></div>
        <div id="tabbody" style="flex:1;min-width:0"></div>
      </div>
    </div>`;
  $("a-out").onclick = async () => { await api("/api/logout", {}); boot(); };
  const defs = [
    ["chat", "💬 Чат", tabChat],
    ["term", "⌨️ Терминал", tabTerm],
  ];
  if (p.modules.wikipedia) defs.push(["wiki", "📚 Википедия", tabWiki]);
  if (p.modules.telegram) defs.push(["tg", "✈️ Бот", tabTg]);
  if (p.modules.analytics) defs.push(["ana", "📊 Аналитика", tabAna]);
  defs.push(["set", "⚙️ Настройки", tabSet]);
  $("tabnav").innerHTML = defs.map((d, i) =>
    '<button class="tabbtn' + (i === 0 ? " sel" : "") + '" data-tab="' + d[0] + '">' + d[1] + "</button>").join("");
  const routes = Object.fromEntries(defs.map(d => [d[0], d[2]]));
  document.querySelectorAll(".tabbtn").forEach(b => b.onclick = () => {
    document.querySelectorAll(".tabbtn").forEach(x => x.classList.remove("sel"));
    b.classList.add("sel");
    routes[b.dataset.tab](p);
  });
  routes.chat(p);
}

function tabChat(p) {
  $("tabbody").innerHTML =
    '<div id="msgs" class="msgs"></div>' +
    '<div style="display:flex;gap:8px;margin-top:10px"><input id="chat-in" style="flex:1" placeholder="напиши Монике…"><button class="primary" id="chat-send">→</button></div>';
  addMsg("bot", "Привет, " + p.username + "! Я Моника. Отвечаю на модели «" + (p.onboarding.prefs?.model || "?") + "». О чём думаем?");
  $("chat-send").onclick = sendChat;
  $("chat-in").onkeydown = e => { if (e.key === "Enter") sendChat(); };
}

function addMsg(role, text) {
  const d = document.createElement("div");
  d.className = "msg " + (role === "user" ? "me" : "bot");
  d.textContent = text;
  const box = $("msgs") || $("tmsgs");
  if (!box) return;
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
}

function esc(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function inline(x) {
  return x.replace(/`([^`]+)`/g, (m, c) => "<code>" + c + "</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*\\n]+)\*/g, "<i>$1</i>")
    .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

function md(src) {
  let s = esc(src);
  s = s.replace(/```([\s\S]*?)```/g, (m, c) => "<pre><code>" + c.replace(/^\n/, "") + "</code></pre>");
  const out = [];
  let inUl = false, inOl = false;
  const closeLists = () => {
    if (inUl) { out.push("</ul>"); inUl = false; }
    if (inOl) { out.push("</ol>"); inOl = false; }
  };
  for (const ln of s.split("\n")) {
    let m;
    if ((m = ln.match(/^###\s+(.*)/))) { closeLists(); out.push("<h3>" + inline(m[1]) + "</h3>"); }
    else if ((m = ln.match(/^##\s+(.*)/))) { closeLists(); out.push("<h2>" + inline(m[1]) + "</h2>"); }
    else if ((m = ln.match(/^#\s+(.*)/))) { closeLists(); out.push("<h2>" + inline(m[1]) + "</h2>"); }
    else if ((m = ln.match(/^&gt;\s?(.*)/))) { closeLists(); out.push("<blockquote>" + inline(m[1]) + "</blockquote>"); }
    else if ((m = ln.match(/^[-*]\s+(.*)/))) {
      if (!inUl) { closeLists(); out.push("<ul>"); inUl = true; }
      out.push("<li>" + inline(m[1]) + "</li>");
    } else if ((m = ln.match(/^\d+[.)]\s+(.*)/))) {
      if (!inOl) { closeLists(); out.push("<ol>"); inOl = true; }
      out.push("<li>" + inline(m[1]) + "</li>");
    } else if (ln.trim() === "") { closeLists(); }
    else { closeLists(); out.push("<p>" + inline(ln) + "</p>"); }
  }
  closeLists();
  return out.join("");
}

function boxScroll() {
  const b = $("msgs") || $("tmsgs");
  if (b) b.scrollTop = b.scrollHeight;
}

function addTyping(boxId) {
  const d = document.createElement("div");
  d.className = "msg bot";
  d.innerHTML = '<span class="typing-dots"><i></i><i></i><i></i></span>';
  const box = $(boxId);
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
  return d;
}

let LAST_CHAT_MSG = null;

async function sendChat() {
  const inp = $("chat-in");
  const text = inp.value.trim();
  if (!text) return;
  inp.value = "";
  await chatTurn(text);
}

async function chatTurn(text) {
  addMsg("user", text);
  CHAT_HIST.push({role: "user", content: text});
  LAST_CHAT_MSG = text;
  const b = addTyping("msgs");
  try {
    const r = await fetch("/api/chat/stream", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text, history: CHAT_HIST.slice(-20)})});
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.error || "HTTP " + r.status);
    }
    b.className = "msg bot";
    b.textContent = "";
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let acc = "";
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      acc += dec.decode(chunk.value, {stream: true});
      b.textContent = acc;
      boxScroll();
    }
    b.innerHTML = '<div class="md">' + md(acc) + "</div>";
    CHAT_HIST.push({role: "assistant", content: acc});
  } catch (e) {
    b.className = "msg bot err-bubble";
    b.innerHTML = "<span>⚠️ " + esc(String(e.message || e)) + "</span>";
    const rb = document.createElement("button");
    rb.textContent = "Повторить";
    rb.onclick = () => { b.remove(); chatTurn(text); };
    b.appendChild(rb);
  }
  boxScroll();
}

function tabTerm(p) {
  $("tabbody").innerHTML =
    '<div class="warn">Терминал работает только с твоим vault. Изменения — после твоего подтверждения. Ядра Моники и чужие данные недоступны.</div>' +
    '<div id="tmsgs" class="msgs"></div>' +
    '<div style="display:flex;gap:8px;margin-top:10px"><input id="term-in" style="flex:1" placeholder="например: создай заметку идеи/тест.md про flот в Stellaris"><button class="primary" id="term-send">→</button></div>';
  addTMsg("bot", "Терминал (GLM 5.3 Fast). Попробуй: «создай заметку проекты/тест.md со списком из трёх идей».");
  $("term-send").onclick = sendTerm;
  $("term-in").onkeydown = e => { if (e.key === "Enter") sendTerm(); };
}

function addTMsg(role, text) {
  const d = document.createElement("div");
  d.className = "msg " + (role === "user" ? "me" : "bot");
  d.textContent = text;
  const box = $("tmsgs");
  if (!box) return;
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
}

async function sendTerm() {
  const inp = $("term-in");
  const text = inp.value.trim();
  if (!text) return;
  addTMsg("user", text);
  inp.value = "";
  const tb = addTyping("tmsgs");
  const r = await api("/api/terminal", {message: text});
  if (tb) tb.remove();
  if (r.data.error) { addTMsg("bot", "⚠️ " + r.data.error); return; }
  addTMsg("bot", r.data.reply || "…");
  const ops = r.data.ops || [];
  if (!ops.length) return;
  const box = document.createElement("div");
  box.className = "ops";
  box.innerHTML = "<b>Предложенные операции:</b><br>" +
    ops.map(o => "• " + o.op + " → " + (o.path || "") + (o.to ? " → " + o.to : "")).join("<br>") +
    '<br><button class="primary" style="margin-top:8px" id="ops-go">Выполнить</button>';
  $("tmsgs").appendChild(box);
  $("tmsgs").scrollTop = $("tmsgs").scrollHeight;
  box.querySelector("#ops-go").onclick = async () => {
    const r2 = await api("/api/terminal/execute", {ops: ops});
    addTMsg("bot", r2.data.results ? r2.data.results.join("\n") : ("⚠️ " + r2.data.error));
    box.remove();
  };
}

function tabSet(p) {
  $("tabbody").innerHTML = `
    <h2>Ключи</h2>
    <div class="sum">` + Object.keys(p.keys_masked).map(k => k + ": <b>" + (p.keys_masked[k] || "не задан") + "</b>").join("<br>") + `</div>
    <div class="row"><input id="s-svc" type="text" placeholder="glm / smart / luna" style="max-width:170px">
    <input id="s-val" type="password" placeholder="новый ключ" style="flex:1">
    <button id="s-key">Сменить</button></div>
    <h2 style="margin-top:20px">Модули</h2>
    <div id="s-mods"></div>
    <div class="err" id="s-err"></div>`;
  const draw = mods => {
    $("s-mods").innerHTML = Object.keys(mods).filter(k => k !== "analytics_unlocked").map(k =>
      '<div class="mod"><div class="t">' + k + '</div><div class="tg' + (mods[k] ? " on" : "") + '" data-m="' + k + '"></div></div>').join("");
    $("s-mods").querySelectorAll(".tg").forEach(tg => tg.onclick = async () => {
      const m = tg.dataset.m;
      let pass = null;
      if (m === "analytics" && !mods.analytics_unlocked && !mods.analytics) {
        pass = prompt("Аналитика сырая, может зацеплять данные других людей. Пароль закрытого тестирования:");
        if (pass === null) return;
      }
      const r = await api("/api/modules", {module: m, enabled: !mods[m], password: pass});
      if (r.data.error) { $("s-err").textContent = r.data.error; return; }
      draw(r.data.modules);
    });
  };
  draw(p.modules);
  $("s-key").onclick = async () => {
    const r = await api("/api/keys", {service: $("s-svc").value.trim(), value: $("s-val").value.trim()});
    $("s-err").textContent = r.data.ok ? "ключ обновлён" : r.data.error;
    if (r.data.ok) boot();
  };
}

// ── модули: Википедия / Telegram-бот / Аналитика ──
function tabWiki(p) {
  $("tabbody").innerHTML =
    '<label>Поиск по твоим заметкам</label><div style="display:flex;gap:8px">' +
    '<input id="wk-q" style="flex:1" placeholder="что ищем?"><button class="primary" id="wk-go">Искать</button></div>' +
    '<div id="wk-res" style="margin-top:14px"></div>';
  const doSearch = async () => {
    const r = await api("/api/wiki/search", {query: $("wk-q").value});
    const res = r.data.results || [];
    $("wk-res").innerHTML = res.length ? res.map(h =>
      '<div class="mod"><div><div class="t">' + h.path + '</div><div class="d">' + h.snippet + '</div></div>' +
      '<button data-p="' + h.path + '" class="x">выжимка</button></div>').join("") :
      '<div class="sub">ничего не найдено</div>';
    $("wk-res").querySelectorAll(".x").forEach(b => b.onclick = () => {
      const title = prompt("Название выжимки:");
      if (!title) return;
      api("/api/wiki/extract", {source_path: b.dataset.p, title: title}).then(r2 => {
        $("wk-res").insertAdjacentHTML("afterbegin",
          r2.data.ok ? '<div class="sum">✅ выжимка: ' + r2.data.path + '</div>' :
          '<div class="err">' + r2.data.error + '</div>');
      });
    });
  };
  $("wk-go").onclick = doSearch;
  $("wk-q").onkeydown = e => { if (e.key === "Enter") doSearch(); };
}

function tabTg(p) {
  $("tabbody").innerHTML = '<div id="tg-body" class="sub">загружаю статус…</div>';
  const draw = async () => {
    const s = (await (await fetch("/api/tg/status")).json());
    $("tg-body").innerHTML =
      '<div class="sum">Модуль: <b>' + (s.module ? "вкл" : "выкл") + '</b> · токен: <b>' +
      (s.configured ? "задан" : "нет") + '</b> · поллер: <b>' + (s.poller ? "работает" : "не запущен") + '</b></div>' +
      '<label>Токен бота (от @BotFather)</label><input id="tg-token" type="password">' +
      '<label>Твой chat_id (узнать у @userinfobot)</label><input id="tg-chat" type="text">' +
      '<div class="row"><span class="sub">после подключения: /note текст — заметка в vault, остальное — чат</span>' +
      '<button class="primary" id="tg-save">Подключить</button></div><div class="err" id="tg-err"></div>';
    $("tg-save").onclick = async () => {
      const r = await api("/api/tg/setup", {token: $("tg-token").value.trim(), chat_id: $("tg-chat").value.trim()});
      $("tg-err").textContent = r.data.ok ? "✅ подключён бот " + r.data.bot : r.data.error;
      if (r.data.ok) setTimeout(draw, 800);
    };
  };
  draw();
}

async function tabAna(p) {
  $("tabbody").innerHTML = '<div class="sub">считаю…</div>';
  const r = await api("/api/analytics/summary", {});
  if (r.data.error) { $("tabbody").innerHTML = '<div class="err">' + r.data.error + '</div>'; return; }
  const s = r.data;
  const max = Math.max(1, ...s.by_day.map(d => d[1]));
  $("tabbody").innerHTML =
    '<div class="sum">Заметок: <b>' + s.notes + '</b> · слов: <b>' + s.words + '</b> · изменено за 7 дней: <b>' + s.changed_last_7d + '</b></div>' +
    '<h2 style="margin-top:16px">Топ тегов</h2><div>' +
    (s.top_tags.map(t => '<span class="chip">' + t[0] + ' · ' + t[1] + '</span>').join("") || '<span class="sub">тегов нет</span>') + '</div>' +
    '<h2 style="margin-top:16px">Активность по дням</h2><div>' +
    s.by_day.map(d => '<div class="row"><span class="sub">' + d[0] + '</span><span style="flex:1;margin:0 10px;height:6px;background:var(--glass);border-radius:3px"><span style="display:block;height:6px;width:' + (d[1] / max * 100) + '%;background:var(--acc);border-radius:3px"></span></span><b>' + d[1] + '</b></div>').join("") +
    '</div><div class="warn" style="margin-top:16px">Аналитика видит только твой vault. Использование для слежки за людьми — запрещено.</div>';
}

async function boot() {
  const me = await (await fetch("/api/me")).json();
  if (me.state === "app") renderApp(me);
  else renderLogin();
}

boot();
