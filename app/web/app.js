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

// ── экран приложения (каркас, чат появится в фазе 2) ──
function renderApp(me) {
  const p = me.profile;
  shell(`
    <div style="display:flex;align-items:center;gap:14px">
      ` + (p.avatar ? '<img class="avatar" src="' + p.avatar + '">' : '<div class="avatar"></div>') + `
      <div><h1>Привет, ` + p.username + `</h1>
      <div class="sub">Моника 1.0 · фаза 1: аккаунт и онбординг готовы</div></div>
    </div>
    <div class="apps">
      <a href="#" id="a-keys">Ключи</a><a href="#" id="a-mods">Модули</a>
      <a href="#" id="a-out">Выйти</a>
    </div>
    <div id="a-out2" style="margin-top:14px"></div>
    <h2 style="margin-top:22px">Модули</h2>
    <div id="a-modlist"></div>
    <h2 style="margin-top:22px">Ключи (маскированы)</h2>
    <div class="sum">` + Object.keys(p.keys_masked).map(k => k + ": <b>" + (p.keys_masked[k] || "не задан") + "</b>").join("<br>") + `</div>`);
  $("a-out").onclick = async () => { await api("/api/logout", {}); boot(); };
  $("a-keys").onclick = () => {
    const svc = prompt("Какой ключ меняем? (glm / smart / luna)");
    if (!svc) return;
    const val = prompt("Новый ключ:");
    if (!val) return;
    api("/api/keys", {service: svc, value: val}).then(r => {
      $("a-out2").textContent = r.data.ok ? "ключ обновлён: " + JSON.stringify(r.data.keys_masked) : r.data.error;
    });
  };
  $("a-mods").onclick = () => {
    const mod = prompt("Модуль (wikipedia / telegram / analytics):");
    if (!mod) return;
    const on = confirm("Включить? (Отмена = выключить)");
    api("/api/modules", {module: mod, enabled: on}).then(r => {
      $("a-out2").textContent = r.data.ok ? "модули: " + JSON.stringify(r.data.modules) : r.data.error;
      boot();
    });
  };
  $("a-modlist").innerHTML = Object.keys(p.modules)
    .filter(k => k !== "analytics_unlocked")
    .map(k => '<div class="mod"><div class="t">' + k + '</div><div>' + (p.modules[k] ? "🟢 вкл" : "🔴 выкл") + "</div></div>").join("");
}

async function boot() {
  const me = await (await fetch("/api/me")).json();
  if (me.state === "app") renderApp(me);
  else renderLogin();
}

boot();
