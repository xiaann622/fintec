const MONTH_NAMES = ["January","February","March","April","May","June","July","August","September","October","November","December"];

function setupMonthYearPickers() {
  const now = new Date();
  const monthSel = document.getElementById("t-month");
  const yearSel = document.getElementById("t-year");

  MONTH_NAMES.forEach((m, i) => {
    const opt = document.createElement("option");
    opt.value = i + 1; opt.textContent = m;
    if (i + 1 === now.getMonth() + 1) opt.selected = true;
    monthSel.appendChild(opt);
  });

  for (let y = now.getFullYear(); y >= now.getFullYear() - 5; y--) {
    const opt = document.createElement("option");
    opt.value = y; opt.textContent = y;
    if (y === now.getFullYear()) opt.selected = true;
    yearSel.appendChild(opt);
  }

  monthSel.addEventListener("change", loadWeekProgression);
  yearSel.addEventListener("change", loadWeekProgression);
}

async function loadTimeOfDay() {
  try {
    const rows = await API.get("/api/trends/time-of-day");
    new Chart(document.getElementById("chart-tod"), {
      type: "bar",
      data: {
        labels: rows.map(r => `${String(r.hour).padStart(2, "0")}:00`),
        datasets: [{ label: "Transactions", data: rows.map(r => r.count), backgroundColor: rows.map((_, i) =>
          (i >= 6 && i <= 9) || (i >= 17 && i <= 21) ? "#e8b84b" : "#4c8be0"), borderRadius: 5 }],
      },
      options: { ...baseGridOptions(), plugins: { legend: { display: false },
        tooltip: { callbacks: { footer: () => "Gold bars = typical morning/evening rush hours" } } } },
    });
  } catch (err) { console.error(err); }
}

async function loadWeekdayWeekend() {
  try {
    const rows = await API.get("/api/trends/weekday-vs-weekend");
    new Chart(document.getElementById("chart-wkwd"), {
      type: "doughnut",
      data: {
        labels: rows.map(r => `${r.bucket} (${r.count})`),
        datasets: [{ data: rows.map(r => r.count), backgroundColor: ["#1fd18f", "#e8b84b"], borderWidth: 0 }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } },
    });
  } catch (err) { console.error(err); }
}

async function loadDayOfWeek() {
  try {
    const rows = await API.get("/api/trends/weekly-pattern");
    new Chart(document.getElementById("chart-dow"), {
      type: "bar",
      data: {
        labels: rows.map(r => r.day.slice(0, 3)),
        datasets: [{ data: rows.map(r => r.count), backgroundColor: rows.map((_, i) => colorFor(i)), borderRadius: 6 }],
      },
      options: baseGridOptions(),
    });
  } catch (err) { console.error(err); }
}

let weekChart = null;
async function loadWeekProgression() {
  const month = parseInt(document.getElementById("t-month").value);
  const year = parseInt(document.getElementById("t-year").value);
  document.getElementById("month-progress-tag").textContent =
    `${MONTH_NAMES[month - 1]} ${year} · Week 1 → Week 5`;

  try {
    const data = await API.get("/api/trends/monthly-week-progression", { month, year });
    const labels = data.weeks.map(w => `Week ${w.week}`);
    if (weekChart) weekChart.destroy();
    weekChart = new Chart(document.getElementById("chart-week-progress"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Transaction count", data: data.weeks.map(w => w.count), borderColor: "#1fd18f",
            backgroundColor: "rgba(31,209,143,0.15)", fill: true, tension: 0.35, yAxisID: "y" },
          { label: "Total value (KES)", data: data.weeks.map(w => w.total_value), borderColor: "#e8b84b",
            backgroundColor: "rgba(232,184,75,0.1)", fill: true, tension: 0.35, yAxisID: "y1" },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          x: { grid: { display: false } },
          y: { position: "left", grid: { color: "rgba(255,255,255,0.06)" }, title: { display: true, text: "Count" } },
          y1: { position: "right", grid: { display: false }, title: { display: true, text: "KES" } },
        },
        plugins: { legend: { display: true, position: "top" } },
      },
    });
  } catch (err) { console.error(err); }
}

async function loadFullHistory() {
  try {
    const rows = await API.get("/api/trends/monthly-overview");
    new Chart(document.getElementById("chart-full-history"), {
      type: "line",
      data: {
        labels: rows.map(r => `${MONTH_NAMES[r.month - 1].slice(0,3)} ${r.year}`),
        datasets: [{ label: "Transaction count", data: rows.map(r => r.count), borderColor: "#4c8be0",
          backgroundColor: "rgba(76,139,224,0.12)", fill: true, tension: 0.3, pointRadius: 3 }],
      },
      options: { ...baseGridOptions(), plugins: { legend: { display: true, position: "top" } } },
    });
  } catch (err) { console.error(err); }
}

document.addEventListener("DOMContentLoaded", () => {
  setupMonthYearPickers();
  loadTimeOfDay();
  loadWeekdayWeekend();
  loadDayOfWeek();
  loadWeekProgression();
  loadFullHistory();
});
