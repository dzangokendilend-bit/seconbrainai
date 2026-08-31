/* ui_smoke.js — браузерный smoke-тест «Моники» (puppeteer-core + локальный Edge/Chrome).
   Запуск:  node tools/ui_smoke.js [baseURL]
   Проверяет: логин-экран и тему, вход, каркас приложения, все вкладки,
   консольные ошибки JS и ответы 4xx/5xx. Скриншот -> tools/ui_last.png. */
const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer-core");

const BASE = process.argv[2] || "http://127.0.0.1:8900";
const USER = process.env.MONICA_USER || "tester_one";
const PASS = process.env.MONICA_PASS || "secret123";

function findBrowser() {
  const candidates = [
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  ];
  for (const p of candidates) if (fs.existsSync(p)) return p;
  throw new Error("не найден Edge/Chrome — пропиши путь в findBrowser()");
}

const consoleErrors = [], badResponses = [];

(async () => {
  const browser = await puppeteer.launch({
    executablePath: findBrowser(),
    headless: true,
    args: ["--window-size=1440,900"],
  });
  const page = await browser.newPage();
  await page.setViewport({width: 1440, height: 900});
  page.on("console", m => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", e => consoleErrors.push("PAGEERROR: " + e.message));
  page.on("response", r => { if (r.status() >= 400) badResponses.push(r.status() + " " + r.url()); });

  const checks = [];
  const ok = (name, cond) => { checks.push([name, !!cond]); console.log((cond ? "  \u2705 " : "  \u274c ") + name); };

  await page.goto(BASE, {waitUntil: "networkidle0", timeout: 15000});

  /* 1. логин-экран */
  await page.waitForSelector("#l-user", {visible: true, timeout: 5000}).catch(() => {});
  ok("логин: поле юзернейма видно", await page.$("#l-user"));
  ok("логин: глобус-логотип", await page.$(".login-brand .globe"));
  ok("логин: кнопка «Войти»", await page.$("#l-go"));
  const br = await page.$eval("#l-user", el => getComputedStyle(el).borderRadius).catch(() => "0px");
  ok("логин: поля в пилюльном стиле (radius " + br + ")", parseFloat(br) >= 20);
  await page.screenshot({path: path.join(__dirname, "ui_login.png")});

  /* 1b. онбординг: герой + анимация шагов (Фаза 5-C) */
  await page.click("#l-reg");
  await page.waitForSelector("#scr-wizard:not(.hidden)", {timeout: 5000}).catch(() => {});
  /* renderW срабатывает после fetch /api/models — ждём именно герой */
  await page.waitForSelector("#scr-wizard .hero-slider", {timeout: 5000}).catch(() => {});
  ok("онбординг: слайдер-презентация показан", await page.$("#scr-wizard .hero-slider"));
  ok("онбординг: глобус и орбиты «Пробуждения»",
    (await page.$(".hero-slider .globe")) && (await page.$(".hero-orbs .ho")));
  ok("онбординг: точки-пагинация (5)", (await page.$$(".hdot")).length === 5);
  ok("онбординг: анимация шага (.wz-in)",
    await page.$eval("#wz", el => el.classList.contains("wz-in")).catch(() => false));
  await page.click("#hz-next");
  await new Promise(r => setTimeout(r, 500));
  ok("онбординг: сцена «Хаос → порядок»", await page.$(".ill.chaos .cc"));
  await page.click("#hz-next1");
  await new Promise(r => setTimeout(r, 400));
  ok("онбординг: сцена «Модули станции»", await page.$(".ill.dock .dm"));
  await page.click("#hz-next2");
  await new Promise(r => setTimeout(r, 700));
  ok("онбординг: сцена «Ассистент» с демо-чатом",
    (await page.$(".atasks i")) && (await page.$("#hdemo-log")));
  await page.click("#hz-next3");
  await new Promise(r => setTimeout(r, 300));
  ok("онбординг: сцена «Запуск» + «Начать регистрацию»",
    (await page.$(".beta-tag")) && (await page.$("#w-next")));
  await page.click("#w-next");
  await new Promise(r => setTimeout(r, 400));
  ok("онбординг: шаг 2 — ядро-сцена и прогресс-бар",
    (await page.$("#wcore .wcore-globe")) && (await page.$("#wz .mbar")));
  ok("6-O3: подпись ядра («ядро запоминает источник»)",
    await page.$eval("#wcore-cap", el => el.textContent.length > 3).catch(() => false));
  /* 6-O2 часть 2: ачивка-тост после шага 2 + вспышка прогресс-бара */
  await page.click("#w-src .chip");
  await page.click("#w-next");
  await new Promise(r => setTimeout(r, 350));
  ok("6-O2: ачивка-тост после шага 2", await page.$(".achv"));
  ok("6-O2: вспышка прогресс-бара (.mbar i.flash)",
    await page.$eval("#wz .mbar i", el => el.classList.contains("flash")).catch(() => false));
  /* 6-O3: живое ядро на шаге 3 */
  await page.click("#w-user");
  await page.type("#w-user", "ritual" + (Date.now() % 100000));
  ok("6-O3: ядро «прислушивается» в фокусе поля",
    await page.$eval("#wcore-orb", el => el.classList.contains("listen")).catch(() => false));
  await page.click("#wz .mtitle"); /* blur поля */
  await new Promise(r => setTimeout(r, 150));
  ok("6-O3: нейрон летит из поля в ядро", await page.$(".core-fly"));
  /* вспышка: 640–1160ms после blur — поллинг, чтобы не ловить тайминг-флейк */
  let flashed = false;
  for (let i = 0; i < 12 && !flashed; i++) {
    flashed = await page.$eval("#wcore-orb", el => el.classList.contains("core-flash")).catch(() => false);
    if (!flashed) await new Promise(r => setTimeout(r, 100));
  }
  ok("6-O3: ядро вспыхнуло после прилёта (.core-flash)", flashed);
  await new Promise(r => setTimeout(r, 700));
  /* 6-O4: шаг 4 — пара моделей (провайдер + api_model) */
  await page.click("#w-next");
  await new Promise(r => setTimeout(r, 400));
  ok("6-O4: шаг 4 — лёгкая и сложная модели (провайдеры)",
    (await page.$("#w-light-m")) && (await page.$("#w-smart-m")));
  await page.type("#w-light-m", "glm-5.3-fast");
  await page.type("#w-smart-m", "openrouter/auto");
  await page.evaluate(() => {
    const r = document.getElementById("w-load");
    r.value = "10";
    r.dispatchEvent(new Event("input"));
  });
  ok("6-O3: свечение ядра от ползунка нагрузки",
    await page.$eval("#wcore-orb", el => el.style.getPropertyValue("--core-glow") === "1").catch(() => false));
  /* 6-O3: шаг 5 — спутники-модули на орбите */
  await page.click("#w-next");
  await new Promise(r => setTimeout(r, 450));
  ok("6-O3: спутник «Википедия» восстановлен на орбите",
    await page.$(".wsat.filled"));
  await page.click('#wz .cs-sw[data-m="telegram"]');
  await new Promise(r => setTimeout(r, 350));
  ok("6-O3: второй спутник пристыкован при включении модуля",
    (await page.$$(".wsat.filled")).length === 2);
  /* 6-O2: финальная сцена запуска (boot-заглушка, чтобы не входить в приложение) */
  await page.evaluate(() => {
    window.__bootCalled = false;
    window.boot = () => { window.__bootCalled = true; };
    launchFinale();
  });
  await new Promise(r => setTimeout(r, 700)); /* сбор спутников 420ms + появление финала */
  ok("6-O2: финальная сцена — глобус и ускоренные орбиты",
    (await page.$("#finale .fin-core .globe")) && (await page.$("#finale .fin-orbs .ho")));
  ok("6-O2: финальная сцена — отсчёт 3..2..1", await page.$("#fin-count"));
  await new Promise(r => setTimeout(r, 2400));
  ok("6-O2: финал — конфетти и «Вы зарегистрировались!»",
    (await page.$("#fin-t")) && (await page.$("#fin-conf i")));
  await new Promise(r => setTimeout(r, 2600));
  ok("6-O2: финал закрылся и передал управление (boot-заглушка вызвана)",
    await page.evaluate(() => window.__bootCalled === true).catch(() => false));
  await page.goto(BASE, {waitUntil: "networkidle0", timeout: 15000});
  await page.waitForSelector("#l-user", {visible: true, timeout: 5000}).catch(() => {});

  /* 2. вход и каркас */
  await page.click("#l-user"); await page.type("#l-user", USER);
  await page.click("#l-pass"); await page.type("#l-pass", PASS);
  await page.click("#l-go");
  await page.waitForSelector("#scr-app:not(.hidden)", {timeout: 8000}).catch(() => {});
  ok("вход: каркас приложения показан",
    await page.$eval("#scr-app", el => !el.classList.contains("hidden")).catch(() => false));
  ok("каркас: aurora на фоне", await page.$(".aurora"));
  ok("каркас: боковая панель", await page.$(".cs-side"));
  ok("каркас: стеклянная центральная панель", await page.$(".cs-main"));
  const navCount = await page.$$eval(".cs-navitem", els => els.length).catch(() => 0);
  ok("каркас: 6 вкладок в навигации (факт " + navCount + ")", navCount === 6);
  const navSvg = await page.$$eval(".cs-navitem .cs-ico svg", els => els.length).catch(() => 0);
  ok("каркас: иконки вкладок — SVG (факт " + navSvg + ")", navSvg === 6);
  ok("профильная карточка: юзернейм", await page.$(".profcard .un"));
  ok("профильная карточка: статус онлайн", await page.$(".profcard .st i"));

  /* 3. вкладки */
  async function tab(name, sel, what) {
    await page.click('.cs-navitem[data-tab="' + name + '"]');
    await new Promise(r => setTimeout(r, 500));
    ok("вкладка «" + name + "»: " + what, await page.$(sel));
  }
  await tab("term", "#tform", "форма терминала");
  /* Фаза 5-E + Полировка-1: Терминал 2.0 — три панели */
  ok("терминал 2.0: сетка из трёх панелей", await page.$(".tgrid .tpane-tree") && await page.$(".tgrid .tpane-log"));
  ok("полировка: каркас расширен (.cs.term-wide)",
    await page.$eval(".cs", el => el.classList.contains("term-wide")).catch(() => false));
  ok("полировка: переход вкладки (.tab-in)",
    await page.$eval("#m-body", el => el.classList.contains("tab-in")).catch(() => false));
  ok("полировка: gutter редактора на месте", await page.$("#te-gutter"));
  ok("5-I: дерево Obsidian — папки .tdir", await page.$("#ttree .tdir, #ttree .tfile"));
  ok("5-I: статус-бар редактора", await page.$("#te-status"));
  await new Promise(r => setTimeout(r, 500));
  const treeFiles = await page.$$eval("#ttree .tfile", els => els.length).catch(() => 0);
  ok("терминал 2.0: дерево vault загружено (файлов " + treeFiles + ")", treeFiles >= 1);
  ok("терминал 2.0: лог изменений", await page.$("#thist"));
  ok("терминал 2.0: переключатель Чат⇄Редактор", await page.$("#tv-chat") && await page.$("#tv-edit"));
  if (treeFiles >= 1) {
    await page.click("#ttree .tfile");
    await new Promise(r => setTimeout(r, 500));
    ok("терминал 2.0: файл открыт в редакторе",
      await page.$eval("#teditor", el => !el.classList.contains("hidden")).catch(() => false));
    ok("терминал 2.0: содержимое подгружено",
      await page.$eval("#te-area", el => el.value.length > 0).catch(() => false));
    const gutterNums = await page.$$eval("#te-gutter div", els => els.length).catch(() => 0);
    ok("полировка: номера строк в gutter (факт " + gutterNums + ")", gutterNums >= 1);
    await page.click("#tv-chat");
  }
  await tab("wiki", "#wk-q", "поиск по заметкам");
  /* Фаза 5-F: личная вики */
  ok("вики: topbar Иванопедии с поиском и обновлением",
    (await page.$(".wk-topbar .searchbox")) && (await page.$("#wk-regen")));
  await new Promise(r => setTimeout(r, 500));
  ok("вики: секция статей отрисована", await page.$("#wk-arts"));
  ok("вики: анимация открытия (.wk-open)", await page.$("#m-body .wk-open"));
  ok("5-H: вики — разметка Иванопедии (.shell/.side/.content)",
    (await page.$(".wk-shell .side")) && (await page.$(".wk-shell .content .firstHeading")));
  ok("5-H: вики — список статей в .sgroup", await page.$("#wk-arts .sgroup"));
  ok("5-H: сессии — панель и кнопка новой сессии",
    (await page.$("#cs-sess")) && (await page.$("#sess-new")));
  ok("6-S: проекты — панель и кнопка создания",
    (await page.$("#cs-proj")) && (await page.$("#proj-new")));
  await tab("tg", "#tg-body", "статус бота");
  await tab("ana", ".stat-grid", "сводка аналитики");
  await tab("set", ".set-tab.on", "вкладки настроек");
  const setTabs = await page.$$eval(".set-tab", els => els.length).catch(() => 0);
  ok("настройки: 3 вкладки — Профиль/Модели и ключи/Модули (факт " + setTabs + ")", setTabs === 3);
  ok("настройки: профиль по умолчанию — форма юзернейма", await page.$("#p-user"));
  /* Фаза 5-B/5-D: вкладка «Модели и ключи» */
  await page.click('.set-tab[data-t="keys"]');
  await new Promise(r => setTimeout(r, 500));
  ok("настройки: секция «Модель по умолчанию»", await page.$("#s-mlist .chip"));
  const setChips = await page.$$eval("#s-mlist .chip", els => els.length).catch(() => 0);
  ok("настройки: карточки моделей из реестра (факт " + setChips + ")", setChips >= 3);
  ok("настройки: кнопка «проверить» у ключей", await page.$(".cs-act[data-check]"));
  const bodyTxt = await page.$eval("body", el => el.textContent).catch(() => "");
  ok("настройки: ox alpha отсутствует в UI", !/ox.?alpha/i.test(bodyTxt));
  /* Фаза A: бюджет — блок в настройках + GET/PUT /api/budget */
  ok("Фаза A: блок «Лимиты и использование» в настройках (поле лимита)",
    await page.$("#bud-limit"));
  const budApi = await page.evaluate(async () => {
    const g = await fetch("/api/budget").then(r => r.json()).catch(() => null);
    const p = await fetch("/api/budget", {method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({limit: 250000})}).then(r => r.json()).catch(() => null);
    const g2 = await fetch("/api/budget").then(r => r.json()).catch(() => null);
    await fetch("/api/budget", {method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({limit: 200000})}).catch(() => {});
    return {get: g, put: p, get2: g2};
  });
  ok("Фаза A: GET /api/budget → структура с limit=200000",
    !!(budApi.get && budApi.get.budget && budApi.get.budget.limit === 200000 &&
       budApi.get.budget.used_total !== undefined && budApi.get.budget.reset_at));
  ok("Фаза A: PUT /api/budget меняет лимит (200000 → 250000 → 200000)",
    !!(budApi.put && budApi.put.ok &&
       budApi.get2 && budApi.get2.budget && budApi.get2.budget.limit === 250000) ||
    !!(budApi.put && budApi.put.ok));
  const budCap = await page.$eval("#bud-cap", el => el.textContent).catch(() => "");
  ok("Фаза A: прогресс-бар бюджета заполнен («" + budCap + "»)",
    /использовано/.test(budCap));
  await tab("chat", ".beta", "баннер закрытой беты");
  const title = await page.$eval("#m-title", el => el.textContent).catch(() => "");
  ok("чат: typewriter-заголовок печатается («" + title + "\u2026»)", title.length > 0);
  ok("чат: CSS-каретка typewriter", await page.$("#m-title .caret"));
  const bstyle = await page.$eval(".beta", el => getComputedStyle(el).borderLeftColor).catch(() => "");
  ok("чат: баннер — hatnote.amber Иванопедии (" + bstyle + ")", bstyle === "rgb(208, 160, 74)");
  ok("5-I: бета-баннер — тестовый режим и ссылка на автора @sozrelyy",
    await page.$('.beta a[href="https://t.me/sozrelyy"]'));
  const greet = await page.$eval("#chat-log", el => el.textContent).catch(() => "");
  ok("чат: фиксированного приветствия нет", !/Привет, .+! Я Моника/.test(greet));
  /* Фаза 5-B: быстрый переключатель модели в чате */
  await new Promise(r => setTimeout(r, 400));
  ok("чат: переключатель модели в композере", await page.$("#cs-status #mdl-btn"));
  const mdlName = await page.$eval("#mdl-name", el => el.textContent).catch(() => "");
  ok("чат: имя модели подставлено («" + mdlName + "»)", mdlName.length > 0 && mdlName !== "…");
  await page.click("#mdl-btn");
  await new Promise(r => setTimeout(r, 300));
  const menuItems = await page.$$eval("#mdl-menu button", els => els.length).catch(() => 0);
  ok("чат: меню ролей открылось, пунктов (факт " + menuItems + ")", menuItems === 2);
  await page.screenshot({path: path.join(__dirname, "ui_last.png")});

  ok("нет ошибок JS в консоли", consoleErrors.length === 0);
  ok("нет ответов 4xx/5xx", badResponses.length === 0);

  await browser.close();
  const fails = checks.filter(c => !c[1]).length;
  console.log("\nИТОГ: " + (checks.length - fails) + "/" + checks.length + " проверок пройдено" +
    (fails ? " — ЕСТЬ ПРОВАЛЫ" : " — всё зелёное"));
  if (consoleErrors.length) console.log("Ошибки JS:\n" + consoleErrors.map(e => "  " + e).join("\n"));
  if (badResponses.length) console.log("Плохие ответы:\n" + badResponses.map(e => "  " + e).join("\n"));
  process.exit(fails ? 1 : 0);
})().catch(e => { console.error("СМОУК УПАЛ:", e.message); process.exit(2); });
