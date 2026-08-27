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
  await tab("wiki", "#wk-q", "поиск по заметкам");
  await tab("tg", "#tg-body", "статус бота");
  await tab("ana", ".stat-grid", "сводка аналитики");
  await tab("set", "#s-apply", "настройки ключей");
  await tab("chat", ".beta", "баннер закрытой беты");
  const title = await page.$eval("#m-title", el => el.textContent).catch(() => "");
  ok("чат: typewriter-заголовок печатается («" + title + "\u2026»)", title.length > 0);
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
