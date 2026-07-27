/* Shared Chart.js defaults so every chart in the app looks consistent. */

const PALETTE = [
  "#1fd18f", "#4c8be0", "#e8b84b", "#e2574c", "#a884e8",
  "#3ec6d6", "#f08a5d", "#6fcf97", "#8fb4ee", "#ff9b92",
];

if (window.Chart) {
  Chart.defaults.color = "#93a7bb";
  Chart.defaults.font.family = "'Inter', 'Segoe UI', sans-serif";
  Chart.defaults.borderColor = "rgba(255,255,255,0.06)";
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.legend.labels.padding = 14;
}

function baseGridOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { grid: { display: false }, ticks: { color: "#93a7bb" } },
      y: { grid: { color: "rgba(255,255,255,0.06)" }, ticks: { color: "#93a7bb" }, beginAtZero: true },
    },
    plugins: { legend: { display: false } },
  };
}

function colorFor(i) {
  return PALETTE[i % PALETTE.length];
}

function badgeClassFor(i) {
  const classes = ["badge-green", "badge-blue", "badge-gold", "badge-red", "badge-grey"];
  return classes[i % classes.length];
}
