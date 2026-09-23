const LEVEL_OF = {
  "Fuite d'air (O2)": "critique",
  "Incendie": "haute",
  "Panne electrique": "haute",
  "Intrusion": "moyenne",
};
const LEVEL_COLOR = {
  critique: "#E8543F",
  haute: "#F0A93A",
  moyenne: "#4FA8E0",
  inconnue: "#8896B3",
};

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

function fmtDurationMs(ms) {
  if (ms == null) return "—";
  const s = Math.round(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

function renderSummary(totals) {
  document.getElementById("cardTotal").textContent = totals.detections;
  document.getElementById("cardAvgDuration").textContent = fmtDurationMs(totals.avg_duration_ms);
  const rate = totals.resolutions > 0 ? Math.round((totals.escalades / totals.resolutions) * 100) : 0;
  document.getElementById("cardEscalade").textContent = totals.resolutions > 0 ? `${rate}%` : "—";
  document.getElementById("cardResolutions").textContent = totals.resolutions;
}

function renderByTypeTable(byType) {
  const body = document.getElementById("byTypeBody");
  if (!byType || byType.length === 0) {
    body.innerHTML = '<tr><td colspan="5" class="log-table__empty">Aucune donnée pour l\'instant</td></tr>';
    return;
  }
  body.innerHTML = byType
    .map((r) => {
      const escRate = r.resolutions > 0 ? Math.round((r.escalade_count / r.resolutions) * 100) : null;
      return (
        `<tr>` +
        `<td>${escapeHtml(r.incident)}</td>` +
        `<td>${r.detections}</td>` +
        `<td>${r.resolutions}</td>` +
        `<td>${fmtDurationMs(r.avg_duration_ms)}</td>` +
        `<td>${escRate == null ? "—" : escRate + "% (" + r.escalade_count + ")"}</td>` +
        `</tr>`
      );
    })
    .join("");
}

function renderBarChart(byType) {
  const el = document.getElementById("barChart");
  if (!byType || byType.length === 0) {
    el.innerHTML = '<p class="hist-empty">Pas encore assez de données pour un graphique.</p>';
    return;
  }

  const width = 700;
  const height = 260;
  const paddingLeft = 40;
  const paddingBottom = 50;
  const chartW = width - paddingLeft - 20;
  const chartH = height - paddingBottom - 20;

  const maxCount = Math.max(...byType.map((r) => r.detections), 1);
  const n = byType.length;
  const gap = 24;
  const barW = Math.max(20, (chartW - gap * (n - 1)) / n);

  let bars = "";
  let labels = "";
  byType.forEach((r, i) => {
    const x = paddingLeft + i * (barW + gap);
    const h = (r.detections / maxCount) * chartH;
    const y = 20 + (chartH - h);
    const color = LEVEL_COLOR[LEVEL_OF[r.incident]] || LEVEL_COLOR.inconnue;
    bars += `<rect x="${x}" y="${y}" width="${barW}" height="${h}" rx="4" fill="${color}" opacity="0.85"/>`;
    bars += `<text x="${x + barW / 2}" y="${y - 8}" text-anchor="middle" class="chart-value">${r.detections}</text>`;
    labels += `<text x="${x + barW / 2}" y="${height - paddingBottom + 18}" text-anchor="middle" class="chart-label">${escapeHtml(shortLabel(r.incident))}</text>`;
  });

  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" class="chart-svg" role="img">
    <line x1="${paddingLeft}" y1="${20 + chartH}" x2="${width - 20}" y2="${20 + chartH}" class="chart-axis"/>
    ${bars}
    ${labels}
  </svg>`;
}

function shortLabel(name) {
  if (name.startsWith("Fuite")) return "Fuite d'air";
  if (name.startsWith("Panne")) return "Panne élec.";
  return name;
}

function renderTimeline(timeline) {
  const el = document.getElementById("timelineChart");
  if (!timeline || timeline.length === 0) {
    el.innerHTML = '<p class="hist-empty">Pas encore assez de données pour une chronologie.</p>';
    return;
  }

  const width = Math.max(700, timeline.length * 46);
  const height = 220;
  const paddingLeft = 40;
  const paddingBottom = 44;
  const chartW = width - paddingLeft - 20;
  const chartH = height - paddingBottom - 20;

  const maxCount = Math.max(...timeline.map((r) => r.count), 1);
  const n = timeline.length;
  const gap = 10;
  const barW = Math.max(14, (chartW - gap * (n - 1)) / n);

  let bars = "";
  let labels = "";
  timeline.forEach((r, i) => {
    const x = paddingLeft + i * (barW + gap);
    const h = (r.count / maxCount) * chartH;
    const y = 20 + (chartH - h);
    bars += `<rect x="${x}" y="${y}" width="${barW}" height="${h}" rx="3" fill="#6FE7DD" opacity="0.85"/>`;
    bars += `<text x="${x + barW / 2}" y="${y - 6}" text-anchor="middle" class="chart-value">${r.count}</text>`;
    const label = r.bucket.slice(5, 13).replace(" ", " · "); // MM-DD · HH:00
    labels += `<text x="${x + barW / 2}" y="${height - paddingBottom + 16}" text-anchor="middle" class="chart-label chart-label--rotate" transform="rotate(45 ${x + barW / 2} ${height - paddingBottom + 16})">${label}</text>`;
  });

  el.innerHTML = `<div class="chart-scroll"><svg viewBox="0 0 ${width} ${height}" width="${width}" class="chart-svg" role="img">
    <line x1="${paddingLeft}" y1="${20 + chartH}" x2="${width - 20}" y2="${20 + chartH}" class="chart-axis"/>
    ${bars}
    ${labels}
  </svg></div>`;
}

async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    const stats = await res.json();
    renderSummary(stats.totals);
    renderByTypeTable(stats.by_type);
    renderBarChart(stats.by_type);
    renderTimeline(stats.timeline);
  } catch (e) {
    document.getElementById("byTypeBody").innerHTML =
      '<tr><td colspan="5" class="log-table__empty">Serveur injoignable</td></tr>';
  }
}

loadStats();
setInterval(loadStats, 5000);