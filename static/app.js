/* Клиентская логика SPA. Подключается к REST API (см. app/handlers.py). */
"use strict";

const API_BASE = "";
const TOKEN_KEY = "selfhelp_token";

const state = {
  token: localStorage.getItem(TOKEN_KEY) || null,
  page: "dashboard",
  testScale: "gad7",
  testAnswers: {},
  psychologists: [],
};

/* ---------- helpers ---------- */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  if (state.page === "progress") loadProgress();
}

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 3000);
}

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (state.token) opts.headers["Authorization"] = "Bearer " + state.token;
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(API_BASE + path, opts);
  let data = {};
  try { data = await res.json(); } catch (_) { /* noop */ }
  if (!res.ok) {
    if (res.status === 401) { logout(false); }
    throw new Error(data.error || "Ошибка запроса");
  }
  return data;
}

/* ---------- auth ---------- */
function setToken(token) {
  state.token = token;
  localStorage.setItem(TOKEN_KEY, token);
}
function logout(notify = true) {
  state.token = null;
  localStorage.removeItem(TOKEN_KEY);
  // Сбрасываем состояние, чтобы после повторного входа не показывались старые данные
  state.page = "dashboard";
  progressData = null;
  closeDrawer();
  $("#app").classList.add("hidden");
  $("#auth-screen").classList.remove("hidden");
  $("#auth-error").classList.add("hidden");
  $("#login-password").value = "";
  const di = $("#diary-text"); if (di) di.value = "";
  if (notify) toast("Вы вышли из аккаунта");
}

function switchTab(which) {
  $$("#auth-screen .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === which));
  $("#login-form").classList.toggle("hidden", which !== "login");
  $("#register-form").classList.toggle("hidden", which !== "register");
  $("#auth-error").classList.add("hidden");
}

function showAuthError(msg) {
  const el = $("#auth-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

async function doLogin(e) {
  e.preventDefault();
  try {
    const data = await api("POST", "/api/login", {
      email: $("#login-email").value,
      password: $("#login-password").value,
    });
    setToken(data.token);
    enterApp(data.user);
  } catch (err) { showAuthError(err.message); }
}

async function doRegister(e) {
  e.preventDefault();
  if (!$("#reg-consent").checked) {
    showAuthError("Необходимо согласие на обработку персональных данных");
    return;
  }
  try {
    const data = await api("POST", "/api/register", {
      email: $("#reg-email").value,
      password: $("#reg-password").value,
      consent: true,
    });
    setToken(data.token);
    toast("Аккаунт создан. Согласие зафиксировано (хэш сохранён).");
    enterApp(data.user);
  } catch (err) { showAuthError(err.message); }
}

function enterApp(user) {
  $$(".js-user-email").forEach((el) => (el.textContent = user.email));
  $("#auth-screen").classList.add("hidden");
  $("#app").classList.remove("hidden");
  navigate("dashboard");
  loadDashboard();
}

/* ---------- navigation ---------- */
const PAGE_TITLES = {
  dashboard: "Главная",
  diary: "Дневник",
  tests: "Тесты",
  techniques: "Техники КПТ",
  progress: "Динамика",
  psychologists: "Психологи",
  report: "Отчёт",
  crisis: "Экстренная помощь",
};

function navigate(page) {
  state.page = page;
  closeDrawer();
  $$(".page").forEach((p) => p.classList.toggle("active", p.dataset.page === page));
  // Подсвечиваем пункт во ВСЕХ меню (десктопное + мобильное)
  $$(".nav-link").forEach((n) => n.classList.toggle("active", n.dataset.page === page));
  $("#page-title").textContent = PAGE_TITLES[page] || "Самопомощь";
  // Прокрутка к началу страницы: на телефоне иначе остаёшься в середине.
  window.scrollTo(0, 0);
  const loaders = {
    dashboard: loadDashboard,
    diary: loadDiary,
    techniques: loadTechniques,
    progress: loadProgress,
    psychologists: loadPsychologists,
    report: loadReport,
    crisis: loadCrisis,
  };
  if (loaders[page]) loaders[page]();
}

function closeDrawer() {
  const drawer = $("#app-nav-drawer");
  const backdrop = $("#backdrop");
  if (drawer) drawer.classList.remove("open");
  if (backdrop) backdrop.classList.remove("visible");
  document.body.classList.remove("drawer-open");
  const menuBtn = $("#btn-menu");
  if (menuBtn) menuBtn.setAttribute("aria-expanded", "false");
}

function openDrawer() {
  const drawer = $("#app-nav-drawer");
  const backdrop = $("#backdrop");
  if (drawer) drawer.classList.add("open");
  if (backdrop) backdrop.classList.add("visible");
  document.body.classList.add("drawer-open");
  const menuBtn = $("#btn-menu");
  if (menuBtn) menuBtn.setAttribute("aria-expanded", "true");
}

function isMobile() {
  return window.matchMedia("(max-width: 960px)").matches;
}

/* ---------- dashboard ---------- */
async function loadDashboard() {
  try {
    const data = await api("GET", "/api/diary");
    const last = data.entries[0];
    const box = $("#dash-last-entry");
    if (!last) { box.textContent = "Записей пока нет — начните с дневника."; return; }
    box.innerHTML = renderEntry(last);
  } catch (_) { /* noop */ }
}

/* ---------- diary ---------- */
async function loadDiary() {
  try {
    const data = await api("GET", "/api/diary");
    const list = $("#diary-list");
    list.innerHTML = data.entries.length
      ? data.entries.map(renderEntry).join("")
      : '<p class="hint">Записей пока нет.</p>';
  } catch (err) { toast(err.message); }
}

function renderEntry(e) {
  const a = e.analysis;
  let chips = "";
  if (a) {
    const tone = { positive: ["pos", "Позитивный"], negative: ["neg", "Негативный"], neutral: ["", "Нейтральный"] }[a.sentiment];
    chips += `<span class="chip ${tone[0]}">${tone[1]} фон</span>`;
    (a.distortions || []).forEach((d) => (chips += `<span class="chip warn">${escapeHtml(d.name)}</span>`));
    (a.triggers || []).forEach((t) => (chips += `<span class="chip">Триггер: ${escapeHtml(t.name)}</span>`));
  }
  const date = (e.created_at || "").replace("T", " ").slice(0, 16);
  const mood = e.mood ? ` · настроение ${e.mood}/10` : "";
  return `
    <div class="list-item">
      <div class="meta">${date}${mood}${e.source === "voice" ? " · голос" : ""}</div>
      <div>${escapeHtml(e.text)}</div>
      ${a ? `<div style="margin-top:8px">${chips}</div>
             <div class="hint" style="margin-top:6px">${escapeHtml(a.summary)}</div>` : ""}
    </div>`;
}

async function saveEntry() {
  const text = $("#diary-text").value.trim();
  if (!text) { toast("Запись не может быть пустой"); return; }
  try {
    await api("POST", "/api/diary", {
      text,
      mood: parseInt($("#diary-mood").value, 10),
      source: "text",
    });
    $("#diary-text").value = "";
    toast("Запись сохранена и проанализирована");
    loadDiary();
  } catch (err) { toast(err.message); }
}

/* ---------- tests ---------- */
async function loadTest(scale) {
  state.testScale = scale;
  state.testAnswers = {};
  try {
    const spec = await api("GET", "/api/tests/" + scale);
    const body = $("#test-body");
    body.innerHTML = `
      <p class="hint">${escapeHtml(spec.instruction)}</p>
      ${spec.questions.map((q, i) => `
        <div class="test-question">
          <p>${i + 1}. ${escapeHtml(q)}</p>
          <div class="test-options">
            ${spec.options.map((o) => `
              <label>
                <input type="radio" name="q${i}" value="${o.value}" data-q="${i}" />
                ${escapeHtml(o.label)}
              </label>`).join("")}
          </div>
        </div>`).join("")}
      <button class="btn btn-primary" id="btn-submit-test">Рассчитать результат</button>
      <div id="test-result"></div>`;
    body.querySelectorAll("input[type=radio]").forEach((r) =>
      r.addEventListener("change", () => { state.testAnswers[r.dataset.q] = parseInt(r.value, 10); }));
    $("#btn-submit-test").addEventListener("click", submitTest);
  } catch (err) { toast(err.message); }
}

async function submitTest() {
  const spec_len = state.testScale === "gad7" ? 7 : 9;
  const answers = [];
  for (let i = 0; i < spec_len; i++) {
    if (state.testAnswers[i] === undefined) { toast("Ответьте на все вопросы"); return; }
    answers.push(state.testAnswers[i]);
  }
  try {
    const res = await api("POST", "/api/tests/submit", { scale: state.testScale, answers });
    const el = $("#test-result");
    const cls = res.crisis ? "crisis" : (res.score >= 10 ? "warn" : "ok");
    let html = `<div class="result-banner ${cls}">
      <strong>Баллы: ${res.score}</strong> · ${escapeHtml(res.level)}</div>`;
    if (res.crisis) {
      html += `<div class="result-banner crisis">Обнаружены признаки, требующие внимания специалиста.
        Самопомощь приостановлена. Пожалуйста, обратитесь за помощью.</div>
        <button class="btn btn-crisis" data-goto="crisis">Показать экстренные контакты</button>`;
    }
    el.innerHTML = html;
    el.querySelectorAll("[data-goto]").forEach((b) =>
      b.addEventListener("click", () => navigate(b.dataset.goto)));
    if (res.crisis) toast("Выявлены кризисные признаки — показаны контакты помощи");
  } catch (err) { toast(err.message); }
}

/* ---------- techniques ---------- */
async function loadTechniques() {
  try {
    const data = await api("GET", "/api/techniques");
    $("#techniques-list").innerHTML = data.techniques.map((t) => `
      <div class="list-item">
        <div class="meta">${escapeHtml(t.category)} · ~${t.duration_min} мин</div>
        <strong>${escapeHtml(t.title)}</strong>
        <p>${escapeHtml(t.description)}</p>
        <div class="hint">Подходит для: ${t.targets.map(escapeHtml).join(", ")}</div>
        <ol class="tech-steps">${t.steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>
      </div>`).join("");
  } catch (err) { toast(err.message); }
}

/* ---------- progress ---------- */
let progressData = null;

async function loadProgress() {
  try {
    const data = await api("GET", "/api/progress");
    progressData = data;
    // На мобильных страница может ещё не иметь размеров в момент отрисовки,
    // поэтому ждём следующего кадра.
    requestAnimationFrame(() => renderProgress());
  } catch (err) { toast(err.message); }
}

function renderProgress() {
  const data = progressData;
  if (!data) return;
  const mood = data.mood || [];
  const tests = data.tests || [];
  $("#mood-empty").classList.toggle("hidden", mood.length > 0);
  $("#tests-empty").classList.toggle("hidden", tests.length > 0);
  drawLineChart($("#chart-mood"), mood.map((m) => m.value), mood.map((m) => m.t), { min: 1, max: 10, color: cssVar("--primary") });
  const gad7 = tests.filter((t) => t.scale === "gad7").map((t) => t.score);
  const phq9 = tests.filter((t) => t.scale === "phq9").map((t) => t.score);
  const labels = tests.map((t) => t.t);
  drawLineChart($("#chart-tests"), gad7, labels, { min: 0, max: 27, color: cssVar("--primary"), second: phq9, secondColor: cssVar("--danger") });
}

function drawLineChart(canvas, values, labels, opts = {}) {
  if (!canvas) return;
  // При скрытой странице clientWidth равен 0 — fallback на ширину контейнера.
  const rect = canvas.getBoundingClientRect();
  const W = Math.max(240, Math.round(rect.width || canvas.parentElement?.clientWidth || 640));
  const H = Math.max(160, Math.round(rect.height || 240));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const pad = { l: 40, r: 12, t: 12, b: 28 };
  const innerW = W - pad.l - pad.r, innerH = H - pad.t - pad.b;
  const min = opts.min ?? 0, max = opts.max ?? 10;

  // оси
  ctx.strokeStyle = cssVar("--border"); ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, pad.t + innerH);
  ctx.lineTo(pad.l + innerW, pad.t + innerH);
  ctx.stroke();
  ctx.fillStyle = cssVar("--muted"); ctx.font = "11px sans-serif"; ctx.textAlign = "right";
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (innerH * i) / 4;
    const v = max - ((max - min) * i) / 4;
    ctx.fillText(Math.round(v), pad.l - 6, y + 4);
  }

  const plot = (series, color) => {
    if (!series || series.length === 0) return;
    const step = innerW / Math.max(1, series.length - 1);
    ctx.strokeStyle = color; ctx.lineWidth = 2;
    ctx.beginPath();
    series.forEach((v, i) => {
      const x = pad.l + step * i;
      const y = pad.t + innerH * (1 - (v - min) / (max - min));
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = color;
    series.forEach((v, i) => {
      const x = pad.l + step * i;
      const y = pad.t + innerH * (1 - (v - min) / (max - min));
      ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill();
    });
  };
  plot(values, opts.color || cssVar("--primary"));
  if (opts.second) plot(opts.second, opts.secondColor || cssVar("--danger"));

  // подписи по X: на узком экране показываем не каждую, чтобы не наезжали
  if (labels && labels.length) {
    ctx.fillStyle = cssVar("--muted"); ctx.textAlign = "center";
    const step = innerW / Math.max(1, labels.length - 1);
    const maxLabels = W < 420 ? 4 : labels.length;
    const skip = Math.max(1, Math.ceil(labels.length / maxLabels));
    labels.forEach((l, i) => {
      if (i % skip !== 0 && i !== labels.length - 1) return;
      const short = (l || "").slice(5, 10);
      ctx.fillText(short, pad.l + step * i, H - 8);
    });
  }
}

/* ---------- psychologists ---------- */
async function loadPsychologists() {
  try {
    const data = await api("GET", "/api/psychologists");
    state.psychologists = data.psychologists;
    $("#psychologists-list").innerHTML = data.psychologists.map((p) => `
      <div class="list-item">
        <strong>${escapeHtml(p.name)}</strong> · ${escapeHtml(p.specialization)}
        <div class="hint">${escapeHtml(p.format)} · стаж ${p.experience_years} лет · ${p.price_rub} ₽ · ⭐ ${p.rating}</div>
        <button class="btn btn-primary" data-request="${p.id}">Оставить заявку</button>
      </div>`).join("");
    $$("[data-request]").forEach((b) =>
      b.addEventListener("click", () => sendRequest(parseInt(b.dataset.request, 10))));
  } catch (err) { toast(err.message); }
}

async function sendRequest(psychologistId) {
  try {
    await api("POST", "/api/requests", { psychologist_id: psychologistId });
    toast("Заявка оформлена и доставлена специалисту (демо)");
  } catch (err) { toast(err.message); }
}

/* ---------- report ---------- */
async function loadReport() {
  try {
    const data = await api("GET", "/api/report");
    const s = data.sentiment || {};
    const top = (obj) => Object.entries(obj || {}).sort((a, b) => b[1] - a[1]).slice(0, 5)
      .map(([k, v]) => `${escapeHtml(k)}: ${v}`).join("<br>") || "нет данных";
    $("#report-body").innerHTML = `
      <div class="report-grid">
        <div class="report-stat"><div class="num">${data.entries_count}</div><div class="lbl">записей проанализировано</div></div>
        <div class="report-stat"><div class="num">${(data.tests || []).length}</div><div class="lbl">пройденных тестов</div></div>
      </div>
      <h4>Тональность</h4><div class="hint">позитив: ${s.positive || 0} · негатив: ${s.negative || 0} · нейтрально: ${s.neutral || 0}</div>
      <h4>Частые когнитивные искажения</h4><div class="hint">${top(data.distortions)}</div>
      <h4>Частые триггеры</h4><div class="hint">${top(data.triggers)}</div>`;
  } catch (err) { toast(err.message); }
}

/* ---------- crisis ---------- */
async function loadCrisis() {
  try {
    const data = await api("GET", "/api/crisis");
    $("#crisis-disclaimer").textContent = data.disclaimer;
    $("#crisis-contacts").innerHTML = data.contacts.map((c) => `
      <div class="list-item"><strong>${escapeHtml(c.name)}</strong> · ${escapeHtml(c.phone)}</div>`).join("");
  } catch (err) { toast(err.message); }
}

/* ---------- wiring ---------- */
document.addEventListener("DOMContentLoaded", () => {
  $$("#auth-screen .tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  $("#login-form").addEventListener("submit", doLogin);
  $("#register-form").addEventListener("submit", doRegister);

  $("#btn-logout").addEventListener("click", () => { api("POST", "/api/logout", {}).catch(() => {}); logout(); });
  $("#btn-logout-mobile").addEventListener("click", () => { api("POST", "/api/logout", {}).catch(() => {}); logout(); });

  // тема
  $$("[data-theme-toggle]").forEach((b) => b.addEventListener("click", toggleTheme));

  // мобильное меню
  const backdrop = $("#backdrop");
  $("#btn-menu").addEventListener("click", openDrawer);
  $("#btn-close-nav").addEventListener("click", closeDrawer);
  backdrop.addEventListener("click", closeDrawer);

  // Клик по пункту меню: навигация + гарантированное закрытие
  $$(".nav-link").forEach((n) => n.addEventListener("click", (e) => {
    e.preventDefault();
    navigate(n.dataset.page);
  }));

  // Пункты, ведущие на страницу (кнопки «Нужна помощь», карточки на главной)
  $$("[data-goto]").forEach((b) => b.addEventListener("click", (e) => {
    e.preventDefault();
    navigate(b.dataset.goto);
  }));

  // Escape закрывает меню (удобно при подключённой клавиатуре/на планшете)
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDrawer();
  });

  // При переходе на десктопную ширину меню должно «раскрыться» обратно
  window.addEventListener("resize", () => {
    if (!isMobile()) closeDrawer();
  });

  // перерисовка графиков при повороте экрана / изменении ширины окна
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (state.page === "progress") renderProgress();
    }, 150);
  });

  // На мобильных Safari адресная строка меняет высоту — пересчитываем графики
  window.addEventListener("orientationchange", () => {
    setTimeout(() => { if (state.page === "progress") renderProgress(); }, 300);
  });

  $$("#tests .tab").forEach((t) => t.addEventListener("click", () => {
    $$("#tests .tab").forEach((x) => x.classList.toggle("active", x === t));
    loadTest(t.dataset.scale);
  }));

  $("#btn-save-entry").addEventListener("click", saveEntry);
  $("#diary-mood").addEventListener("input", () => { $("#diary-mood-value").textContent = $("#diary-mood").value; });
  $("#btn-voice").addEventListener("click", () => { $("#voice-hint").classList.toggle("hidden"); });
  $("#btn-export-report").addEventListener("click", () => toast("PDF-экспорт — точка подключения (см. README)"));

  // автовход при наличии токена
  if (state.token) {
    api("GET", "/api/me").then((data) => enterApp(data.user)).catch(() => logout(false));
  }
});
