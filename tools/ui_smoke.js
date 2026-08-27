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
  await page.waitForSelector("#scr-wizard .whero", {timeout: 5000}).catch(() => {});
  ok("онбординг: герой-экран показан", await page.$("#scr-wizard .whero"));
  ok("онбординг: глобус в герое", await page.$(".whero .globe"));
  ok("онбординг: метка закрытой беты", await page.$(".whero .beta-tag"));
  ok("онбординг: кнопка «Начать»", await page.$(".whero #w-next"));
  ok("онбординг: анимация шага (.wz-in)",
    await page.$eval("#wz", el => el.classList.contains("wz-in")).catch(() => false));
  await page.click(".whero #w-next");
  await new Promise(r => setTimeout(r, 400));
  ok("онбординг: шаг 2 — глиф и прогресс-бар",
    (await page.$("#wz .wglyph")) && (await page.$("#wz .mbar")));
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
  /* Фаза 5-E: Терминал 2.0 — три панели */
  ok("терминал 2.0: сетка из трёх панелей", await page.$(".tgrid .tpane-tree") && await page.$(".tgrid .tpane-log"));
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
    await page.click("#tv-chat");
  }
  await tab("wiki", "#wk-q", "поиск по заметкам");
  /* Фаза 5-F: личная вики */
  ok("вики: заголовок «Личная вики» и кнопка обновления",
    (await page.$(".wk-h")) && (await page.$("#wk-regen")));
  await new Promise(r => setTimeout(r, 500));
  ok("вики: секция статей отрисована", await page.$("#wk-arts"));
  ok("вики: анимация открытия (.wk-open)", await page.$("#m-body .wk-open"));
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
  await tab("chat", ".beta", "баннер закрытой беты");
  const title = await page.$eval("#m-title", el => el.textContent).catch(() => "");
  ok("чат: typewriter-заголовок печатается («" + title + "\u2026»)", title.length > 0);
  ok("чат: CSS-каретка typewriter", await page.$("#m-title .caret"));
  const bstyle = await page.$eval(".beta", el => getComputedStyle(el).borderLeftColor).catch(() => "");
  ok("чат: баннер — hatnote.amber Иванопедии (" + bstyle + ")", bstyle === "rgb(208, 160, 74)");
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
  ok("чат: меню моделей открылось, пунктов (факт " + menuItems + ")", menuItems >= 3);
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
