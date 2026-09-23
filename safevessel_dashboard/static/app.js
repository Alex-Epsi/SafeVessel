const LEVEL_LABEL = {
  critique: "Critique",
  haute: "Haute",
  moyenne: "Moyenne",
  inconnue: "Inconnue",
};

function fmtDuration(sinceEpochSeconds, nowEpochSeconds) {
  const s = Math.max(0, Math.floor(nowEpochSeconds - sinceEpochSeconds));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}

function renderState(data) {
  const dot = document.getElementById("connIndicator");
  const label = document.getElementById("connLabel");
  dot.className = "conn-dot " + (data.connected ? "conn-dot--on" : "conn-dot--off");
  label.textContent = data.connected ? "connecté" : "déconnecté";

  const card = document.getElementById("currentState");
  if (!data.current) {
    card.className = "state-card state-card--normal";
    card.innerHTML =
      '<p class="state-card__label">Système normal</p>' +
      '<p class="state-card__sub">Aucun incident actif</p>';
  } else {
    const c = data.current;
    card.className = "state-card state-card--" + c.level;
    const dur = fmtDuration(c.since, data.server_time);
    const label = LEVEL_LABEL[c.level] || c.level;
    card.innerHTML =
      `<p class="state-card__label">${escapeHtml(c.name)}</p>` +
      `<p class="state-card__sub">Niveau ${label} — en cours depuis ${dur}` +
      `${c.escalated ? " · escaladé" : ""}</p>`;
  }

  const queueList = document.getElementById("queueList");
  if (!data.queue || data.queue.length === 0) {
    queueList.innerHTML = '<li class="queue-list__empty">Aucun incident en attente</li>';
  } else {
    queueList.innerHTML = data.queue
      .map((q) => {
        const label = LEVEL_LABEL[q.level] || q.level;
        return (
          `<li class="queue-list__item queue-list__item--${q.level}">` +
          `<span>${escapeHtml(q.name)}</span>` +
          `<span class="queue-list__level">${label}</span></li>`
        );
      })
      .join("");
  }
}

function renderLogs(rows) {
  const body = document.getElementById("logBody");
  if (!rows || rows.length === 0) {
    body.innerHTML = '<tr><td colspan="5" class="log-table__empty">Aucun événement enregistré</td></tr>';
    return;
  }
  body.innerHTML = rows
    .map((r) => {
      const levelClass = (r.level || "").toLowerCase();
      return (
        `<tr class="log-row log-row--${levelClass}">` +
        `<td>${escapeHtml(r.ts)}</td>` +
        `<td>${escapeHtml(r.event_type)}</td>` +
        `<td>${escapeHtml(r.incident || "-")}</td>` +
        `<td>${escapeHtml(r.level || "-")}</td>` +
        `<td>${escapeHtml(r.details || "")}</td></tr>`
      );
    })
    .join("");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    renderState(data);
  } catch (e) {
    document.getElementById("connLabel").textContent = "serveur injoignable";
  }
}

async function pollLogs() {
  try {
    const res = await fetch("/api/logs?limit=200");
    const rows = await res.json();
    renderLogs(rows);
  } catch (e) {
    /* silencieux : on retentera au prochain cycle */
  }
}

function tickClock() {
  document.getElementById("clock").textContent = new Date().toLocaleTimeString("fr-FR");
}

async function requireAuthThen(fetchPromise, onOk) {
  try {
    const res = await fetchPromise;
    if (res.status === 401) {
      window.location.href = "/login?next=/";
      return;
    }
    const data = await res.json().catch(() => ({}));
    onOk(res, data);
  } catch (e) {
    alert("Impossible de contacter le serveur.");
  }
}

document.getElementById("btnClearCache").addEventListener("click", () => {
  requireAuthThen(fetch("/api/clear_cache", { method: "POST" }), () => {
    pollStatus();
    pollLogs();
  });
});

document.getElementById("btnReset").addEventListener("click", () => {
  if (!window.confirm("Réinitialiser toutes les alertes en cours sur l'Arduino ?")) {
    return;
  }
  requireAuthThen(fetch("/api/reset", { method: "POST" }), (res, data) => {
    if (!data.ok) {
      alert("Échec : " + (data.error || "Arduino non joignable"));
    }
    pollStatus();
    pollLogs();
  });
});

document.getElementById("btnExport").addEventListener("click", () => {
  window.location.href = "/api/logs/export";
});

document.getElementById("btnClear").addEventListener("click", () => {
  if (!window.confirm("Vider tout le journal des événements ? Cette action est irréversible.")) {
    return;
  }
  requireAuthThen(fetch("/api/logs/clear", { method: "POST" }), () => {
    pollLogs();
  });
});

pollStatus();
pollLogs();
tickClock();
setInterval(pollStatus, 1500);
setInterval(pollLogs, 3000);
setInterval(tickClock, 1000);