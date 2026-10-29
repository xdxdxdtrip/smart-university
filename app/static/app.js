// Smart University — простой веб-интерфейс на чистом JavaScript поверх REST API.
"use strict";

const ROLE_RU = { student: "Студент", teacher: "Преподаватель", admin: "Администратор" };
const STATUS_RU = {
  available: "Доступно", maintenance: "На обслуживании", decommissioned: "Списано",
  pending: "Ожидает", approved: "Одобрена", rejected: "Отклонена", cancelled: "Отменена",
};

const state = { token: null, user: null, labs: [], equipment: [], selected: null };

// ---------- утилиты ----------
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const statusChip = (s) => `<span class="status s-${s}">${STATUS_RU[s] || s}</span>`;
const fmtDT = (iso) => new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const fmtT = (iso) => iso.slice(11, 16);
const todayISO = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };

function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast" + (isError ? " error" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.add("hidden"), 3500);
}

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let payload;
  if (form) { payload = new URLSearchParams(form); }
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(path, { method, headers, body: payload });
  if (res.status === 401 && state.token) { logout(); throw new Error("Сессия истекла, войдите снова"); }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail;
    if (Array.isArray(msg)) msg = msg.map((e) => e.msg.replace("Value error, ", "")).join("; ");
    throw new Error(msg || `Ошибка ${res.status}`);
  }
  return data;
}

const run = (fn) => async (...args) => { try { await fn(...args); } catch (e) { toast(e.message, true); } };

// ---------- авторизация ----------
document.querySelectorAll("[data-auth]").forEach((btn) => btn.addEventListener("click", () => {
  document.querySelectorAll("[data-auth]").forEach((b) => b.classList.toggle("active", b === btn));
  $("#loginForm").classList.toggle("hidden", btn.dataset.auth !== "login");
  $("#registerForm").classList.toggle("hidden", btn.dataset.auth !== "register");
}));

async function login(username, password) {
  const data = await api("/api/auth/login", { method: "POST", form: { username, password } });
  state.token = data.access_token;
  state.user = data.user;
  try { localStorage.setItem("su_token", state.token); } catch { /* ignore */ }
  await enterApp();
}

$("#loginForm").addEventListener("submit", run(async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  await login(f.get("username"), f.get("password"));
}));

$("#registerForm").addEventListener("submit", run(async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target));
  await api("/api/auth/register", { method: "POST", body });
  toast("Регистрация прошла успешно");
  await login(body.email, body.password);
}));

document.querySelectorAll("[data-demo]").forEach((btn) => btn.addEventListener("click", run(async () => {
  const [u, p] = btn.dataset.demo.split("|");
  await login(u, p);
})));

function logout() {
  state.token = null; state.user = null;
  try { localStorage.removeItem("su_token"); } catch { /* ignore */ }
  $("#toast").classList.add("hidden");
  $("#appView").classList.add("hidden");
  $("#userbox").classList.add("hidden");
  $("#authView").classList.remove("hidden");
}
$("#logoutBtn").addEventListener("click", logout);

async function enterApp() {
  if (!state.user) state.user = await api("/api/auth/me");
  $("#authView").classList.add("hidden");
  $("#appView").classList.remove("hidden");
  $("#userbox").classList.remove("hidden");
  $("#userName").textContent = state.user.full_name;
  $("#userRole").textContent = ROLE_RU[state.user.role];
  document.querySelectorAll("#mainTabs .tab").forEach((t) => {
    const roles = t.dataset.roles;
    t.classList.toggle("hidden", Boolean(roles) && !roles.split(",").includes(state.user.role));
  });
  await loadLabs();
  showView("equipment");
  refreshBell();
}

// ---------- навигация ----------
document.querySelectorAll("#mainTabs .tab").forEach((t) => t.addEventListener("click", () => showView(t.dataset.view)));
$("#bellBtn").addEventListener("click", () => showView("notifications"));

const loaders = {
  equipment: () => loadEquipment(),
  my: () => loadMy(),
  requests: () => loadRequests(),
  notifications: () => loadNotifications(),
  admin: () => loadAdmin(),
};

function showView(name) {
  document.querySelectorAll("#mainTabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("hidden", v.id !== `view-${name}`));
  run(loaders[name])();
}

// ---------- оборудование ----------
async function loadLabs() {
  state.labs = await api("/api/laboratories");
  const opts = state.labs.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join("");
  $("#labFilter").innerHTML = `<option value="">Все лаборатории</option>${opts}`;
  $("#eqLabSelect").innerHTML = opts;
}

async function loadEquipment() {
  const params = new URLSearchParams();
  if ($("#labFilter").value) params.set("laboratory_id", $("#labFilter").value);
  if ($("#statusFilter").value) params.set("status", $("#statusFilter").value);
  if ($("#searchInput").value.trim()) params.set("q", $("#searchInput").value.trim());
  state.equipment = await api(`/api/equipment?${params}`);
  $("#equipmentList").innerHTML = state.equipment.length
    ? state.equipment.map((e) => `
      <div class="item ${state.selected === e.id ? "selected" : ""}" data-id="${e.id}">
        <div><strong>${esc(e.name)}</strong>
          <div class="meta">${esc(e.inventory_number)} · ${esc(e.category)} · ${esc(e.laboratory_name)}</div></div>
        ${statusChip(e.status)}
      </div>`).join("")
    : `<p class="muted">Ничего не найдено</p>`;
  document.querySelectorAll("#equipmentList .item").forEach((el) =>
    el.addEventListener("click", run(() => selectEquipment(Number(el.dataset.id)))));
}
["#labFilter", "#statusFilter"].forEach((s) => $(s).addEventListener("change", run(loadEquipment)));
$("#searchInput").addEventListener("input", () => { clearTimeout(loadEquipment.t); loadEquipment.t = setTimeout(run(loadEquipment), 300); });

function timeOptions(fromH, toH, selected) {
  const out = [];
  for (let m = fromH * 60; m <= toH * 60; m += 30) {
    const v = `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
    out.push(`<option ${v === selected ? "selected" : ""}>${v}</option>`);
  }
  return out.join("");
}

async function selectEquipment(id, day) {
  state.selected = id;
  document.querySelectorAll("#equipmentList .item").forEach((el) => el.classList.toggle("selected", Number(el.dataset.id) === id));
  const e = state.equipment.find((x) => x.id === id) || (await api(`/api/equipment/${id}`));
  day = day || $("#bookDay")?.value || todayISO();
  const av = await api(`/api/equipment/${id}/availability?day=${day}`);
  const startH = Number(fmtT(av.work_start).slice(0, 2));
  const endH = Number(fmtT(av.work_end).slice(0, 2));
  const total = (endH - startH) * 60;
  const pos = (iso) => ((Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16)) - startH * 60) / total) * 100;
  const busy = av.busy.map((b) => `<div class="busy ${b.status}" style="left:${pos(b.start)}%;width:${pos(b.end) - pos(b.start)}%" title="${fmtT(b.start)}–${fmtT(b.end)} ${STATUS_RU[b.status]}">${fmtT(b.start)}</div>`).join("");
  const scale = []; for (let h = startH; h <= endH; h += 2) scale.push(`<span>${h}:00</span>`);
  const canBook = ["student", "teacher"].includes(state.user.role) && e.status === "available";

  $("#equipmentDetail").innerHTML = `
    <h2>${esc(e.name)}</h2>
    <p class="muted">${esc(e.laboratory_name)} · инв. № ${esc(e.inventory_number)} · ${statusChip(e.status)}</p>
    ${e.description ? `<p>${esc(e.description)}</p>` : ""}
    <label class="muted">Дата <input type="date" id="bookDay" value="${day}" min="${todayISO()}"></label>
    <div class="timeline">${busy}</div>
    <div class="scale">${scale.join("")}</div>
    <div class="legend"><span><i style="background:var(--ok-bg)"></i>Свободно</span><span><i style="background:var(--warn)"></i>Ожидает</span><span><i style="background:var(--bad)"></i>Одобрено</span></div>
    <div class="muted" style="font-size:13px;margin-bottom:6px">Свободные интервалы:</div>
    <div class="slots">${av.free.length ? av.free.map((f) => `<button class="chip slot" data-s="${fmtT(f.start)}">${fmtT(f.start)}–${fmtT(f.end)}</button>`).join("") : `<span class="muted">нет</span>`}</div>
    ${canBook ? `
    <form class="form" id="bookForm">
      <div class="row">
        <label>Начало<select name="start">${timeOptions(startH, endH - 1, "10:00")}</select></label>
        <label>Окончание<select name="end">${timeOptions(startH + 1, endH, "12:00")}</select></label>
      </div>
      <label>Цель<input name="purpose" required minlength="3" placeholder="Например: лабораторная работа №3"></label>
      <button class="btn primary">Отправить заявку</button>
    </form>` : `<p class="muted">${e.status !== "available" ? "Оборудование сейчас недоступно для брони." : "Администратор не создаёт брони — он рассматривает заявки."}</p>`}`;

  $("#bookDay").addEventListener("change", run((ev) => selectEquipment(id, ev.target.value)));
  document.querySelectorAll(".slot").forEach((b) => b.addEventListener("click", () => {
    const form = $("#bookForm"); if (!form) return;
    form.start.value = b.dataset.s;
  }));
  const form = $("#bookForm");
  if (form) form.addEventListener("submit", run(async (ev) => {
    ev.preventDefault();
    const f = new FormData(form);
    await api("/api/bookings", { method: "POST", body: {
      equipment_id: id,
      start_time: `${day}T${f.get("start")}:00`,
      end_time: `${day}T${f.get("end")}:00`,
      purpose: f.get("purpose"),
    } });
    toast("Заявка отправлена и ожидает подтверждения");
    await selectEquipment(id, day);
    refreshBell();
  }));
}

// ---------- мои брони ----------
async function historyHtml(id) {
  const h = await api(`/api/bookings/${id}/history`);
  return h.map((x) => `${fmtDT(x.changed_at)} — ${x.old_status ? STATUS_RU[x.old_status] + " → " : ""}${STATUS_RU[x.new_status]} (${esc(x.changed_by_name || "система")})${x.comment ? ": " + esc(x.comment) : ""}`).join("<br>");
}

async function loadMy() {
  const s = $("#myStatusFilter").value;
  const rows = await api(`/api/bookings/my${s ? "?status=" + s : ""}`);
  $("#myTable").innerHTML = `<tr><th>#</th><th>Оборудование</th><th>Время</th><th>Цель</th><th>Статус</th><th></th></tr>` +
    (rows.length ? rows.map((b) => `
      <tr><td>${b.id}</td><td>${esc(b.equipment_name)}</td>
      <td>${fmtDT(b.start_time)}–${fmtT(b.end_time)}</td>
      <td>${esc(b.purpose)}${b.review_comment ? `<div class="history">Комментарий: ${esc(b.review_comment)}</div>` : ""}<div class="history" id="h${b.id}"></div></td>
      <td>${statusChip(b.status)}</td>
      <td class="actions">
        <button class="btn sm" data-hist="${b.id}">История</button>
        ${["pending", "approved"].includes(b.status) ? `<button class="btn sm bad" data-cancel="${b.id}">Отменить</button>` : ""}
      </td></tr>`).join("") : `<tr><td colspan="6" class="muted">Броней пока нет</td></tr>`);
  bindRowButtons("#myTable", loadMy);
}
$("#myStatusFilter").addEventListener("change", run(loadMy));

function bindRowButtons(table, reload) {
  document.querySelectorAll(`${table} [data-hist]`).forEach((b) => b.addEventListener("click", run(async () => {
    const el = $(`#h${b.dataset.hist}`);
    el.innerHTML = el.innerHTML ? "" : await historyHtml(b.dataset.hist);
  })));
  document.querySelectorAll(`${table} [data-cancel]`).forEach((b) => b.addEventListener("click", run(async () => {
    if (!confirm("Отменить бронь?")) return;
    await api(`/api/bookings/${b.dataset.cancel}/cancel`, { method: "POST" });
    toast("Бронь отменена"); await reload();
  })));
  document.querySelectorAll(`${table} [data-approve]`).forEach((b) => b.addEventListener("click", run(async () => {
    await api(`/api/bookings/${b.dataset.approve}/approve`, { method: "POST", body: { comment: null } });
    toast("Заявка одобрена"); await reload();
  })));
  document.querySelectorAll(`${table} [data-reject]`).forEach((b) => b.addEventListener("click", run(async () => {
    const comment = prompt("Причина отклонения:");
    if (comment === null) return;
    await api(`/api/bookings/${b.dataset.reject}/reject`, { method: "POST", body: { comment: comment || null } });
    toast("Заявка отклонена"); await reload();
  })));
}

// ---------- заявки (преподаватель / админ) ----------
async function loadRequests() {
  const params = new URLSearchParams();
  if ($("#reqStatusFilter").value) params.set("status", $("#reqStatusFilter").value);
  if ($("#reqDay").value) params.set("day", $("#reqDay").value);
  const rows = await api(`/api/bookings?${params}`);
  $("#reqTable").innerHTML = `<tr><th>#</th><th>Заявитель</th><th>Оборудование</th><th>Время</th><th>Цель</th><th>Статус</th><th></th></tr>` +
    (rows.length ? rows.map((b) => `
      <tr><td>${b.id}</td><td>${esc(b.user_full_name)}</td><td>${esc(b.equipment_name)}</td>
      <td>${fmtDT(b.start_time)}–${fmtT(b.end_time)}</td>
      <td>${esc(b.purpose)}<div class="history" id="h${b.id}"></div></td>
      <td>${statusChip(b.status)}</td>
      <td class="actions">
        ${b.status === "pending" ? `<button class="btn sm ok" data-approve="${b.id}">Одобрить</button><button class="btn sm bad" data-reject="${b.id}">Отклонить</button>` : ""}
        ${b.status === "approved" && state.user.role === "admin" ? `<button class="btn sm bad" data-cancel="${b.id}">Отменить</button>` : ""}
        <button class="btn sm" data-hist="${b.id}">История</button>
      </td></tr>`).join("") : `<tr><td colspan="7" class="muted">Заявок нет</td></tr>`);
  bindRowButtons("#reqTable", loadRequests);
}
["#reqStatusFilter", "#reqDay"].forEach((s) => $(s).addEventListener("change", run(loadRequests)));

// ---------- уведомления ----------
async function refreshBell() {
  try {
    const unread = await api("/api/notifications?unread_only=true");
    $("#bellCount").textContent = unread.length;
    $("#bellCount").classList.toggle("hidden", unread.length === 0);
  } catch { /* ignore */ }
}

async function loadNotifications() {
  const items = await api("/api/notifications");
  $("#notificationList").innerHTML = items.length ? items.map((n) => `
    <div class="note ${n.is_read ? "" : "unread"}" data-id="${n.id}">
      ${esc(n.message)}<br><small>${fmtDT(n.created_at)}</small>
    </div>`).join("") : `<p class="muted">Уведомлений нет</p>`;
  document.querySelectorAll(".note.unread").forEach((el) => el.addEventListener("click", run(async () => {
    await api(`/api/notifications/${el.dataset.id}/read`, { method: "POST" });
    el.classList.remove("unread"); refreshBell();
  })));
}
$("#readAllBtn").addEventListener("click", run(async () => {
  await api("/api/notifications/read-all", { method: "POST" });
  await loadNotifications(); refreshBell();
}));

// ---------- управление (админ) ----------
async function loadAdmin() {
  const [stats, users, equipment] = await Promise.all([api("/api/stats"), api("/api/users"), api("/api/equipment")]);
  $("#statsBox").innerHTML = [
    ["Пользователи", stats.users_total], ["Лаборатории", stats.laboratories_total],
    ["Оборудование", stats.equipment_total], ["Всего броней", stats.bookings_total],
    ["Ожидают", stats.bookings_by_status.pending], ["Одобрено", stats.bookings_by_status.approved],
  ].map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("") +
    (stats.top_equipment.length ? `<div class="stat" style="grid-column:1/-1"><span>Самое востребованное:</span> ${stats.top_equipment.map((t) => `${esc(t.name)} (${t.bookings})`).join(", ")}</div>` : "");

  $("#adminEqTable").innerHTML = `<tr><th>Название</th><th>Инв. №</th><th>Лаборатория</th><th>Статус</th></tr>` +
    equipment.map((e) => `<tr><td>${esc(e.name)}</td><td>${esc(e.inventory_number)}</td><td>${esc(e.laboratory_name)}</td>
      <td><select data-eqstatus="${e.id}">${["available", "maintenance", "decommissioned"].map((s) => `<option value="${s}" ${s === e.status ? "selected" : ""}>${STATUS_RU[s]}</option>`).join("")}</select></td></tr>`).join("");
  document.querySelectorAll("[data-eqstatus]").forEach((sel) => sel.addEventListener("change", run(async () => {
    await api(`/api/equipment/${sel.dataset.eqstatus}`, { method: "PATCH", body: { status: sel.value } });
    toast("Статус оборудования обновлён");
  })));

  $("#usersTable").innerHTML = `<tr><th>ФИО</th><th>Email</th><th>Роль</th><th>Активен</th></tr>` +
    users.map((u) => `<tr><td>${esc(u.full_name)}</td><td>${esc(u.email)}</td>
      <td>${u.id === state.user.id ? ROLE_RU[u.role] : `<select data-role="${u.id}">${Object.keys(ROLE_RU).map((r) => `<option value="${r}" ${r === u.role ? "selected" : ""}>${ROLE_RU[r]}</option>`).join("")}</select>`}</td>
      <td>${u.id === state.user.id ? "—" : `<input type="checkbox" data-active="${u.id}" ${u.is_active ? "checked" : ""}>`}</td></tr>`).join("");
  document.querySelectorAll("[data-role]").forEach((sel) => sel.addEventListener("change", run(async () => {
    await api(`/api/users/${sel.dataset.role}`, { method: "PATCH", body: { role: sel.value } });
    toast("Роль изменена");
  })));
  document.querySelectorAll("[data-active]").forEach((cb) => cb.addEventListener("change", run(async () => {
    await api(`/api/users/${cb.dataset.active}`, { method: "PATCH", body: { is_active: cb.checked } });
    toast(cb.checked ? "Пользователь активирован" : "Пользователь отключён");
  })));
}

function formJSON(form) {
  const data = Object.fromEntries(new FormData(form));
  Object.keys(data).forEach((k) => { if (data[k] === "") data[k] = null; });
  return data;
}
$("#labForm").addEventListener("submit", run(async (e) => {
  e.preventDefault();
  await api("/api/laboratories", { method: "POST", body: formJSON(e.target) });
  e.target.reset(); toast("Лаборатория добавлена");
  await loadLabs(); await loadAdmin();
}));
$("#eqForm").addEventListener("submit", run(async (e) => {
  e.preventDefault();
  const body = formJSON(e.target); body.laboratory_id = Number(body.laboratory_id);
  await api("/api/equipment", { method: "POST", body });
  e.target.reset(); toast("Оборудование добавлено");
  await loadAdmin();
}));

// ---------- старт ----------
(async () => {
  try { state.token = localStorage.getItem("su_token"); } catch { state.token = null; }
  if (state.token) {
    try { await enterApp(); } catch { logout(); }
  }
  setInterval(() => state.token && refreshBell(), 30000);
})();
