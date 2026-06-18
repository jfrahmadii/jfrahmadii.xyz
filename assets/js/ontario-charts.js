/* ontario-charts.js — renders the dashboard charts from window.ONTARIO_DATA.
   Requires Chart.js and assets/js/ontario-data.js to be loaded first. */
(function () {
  const D = window.ONTARIO_DATA;
  if (!D || typeof Chart === "undefined") return;

  const C = { NUC:"#7c6cf0", HYD:"#2e86c1", WND:"#27ae60", SOL:"#f1c40f", BIO:"#16a085", GAS:"#8a97a6", OTH:"#b0bccb" };
  const NAME = { NUC:"Nuclear", HYD:"Hydro", WND:"Wind", SOL:"Solar", BIO:"Bioenergy", GAS:"Natural Gas", OTH:"Other" };
  const STACK = ["NUC","HYD","WND","SOL","BIO","OTH","GAS"]; // gas on top to read the wedge
  const grid = { color: "#26384c" }, tick = { color: "#93a4b8" };

  Chart.defaults.color = "#93a4b8";
  Chart.defaults.font.family = "'Segoe UI', system-ui, Arial, sans-serif";

  const area = (label, data, color) => ({
    label, data, backgroundColor: color + "cc", borderColor: color,
    fill: true, tension: .3, pointRadius: 0, borderWidth: 1,
  });
  const make = (id, cfg) => { const el = document.getElementById(id); if (el) new Chart(el, cfg); };

  /* ---- 1. Monthly generation mix (the long-run centerpiece) ---- */
  const monthLabels = D.monthly.labels;
  const yearTick = (val, i) => { const l = monthLabels[i]; return l && l.endsWith("-01") ? l.slice(0, 4) : ""; };
  make("mixMonthly", {
    type: "line",
    data: { labels: monthLabels, datasets: STACK.map(f => area(NAME[f], D.monthly.series[f], C[f])) },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
        tooltip: { callbacks: { title: items => items[0]?.label || "", label: c => `${c.dataset.label}: ${c.parsed.y.toLocaleString()} GWh` } },
      },
      scales: {
        y: { stacked: true, grid, ticks: { ...tick, callback: v => (v / 1000) + " TWh" } },
        x: { stacked: true, grid: { display: false }, ticks: { ...tick, autoSkip: false, maxRotation: 0, callback: yearTick } },
      },
    },
  });

  /* ---- annual series sliced to full calendar years (2020–2025) ---- */
  const yrs = D.annual.years;
  const lo = yrs.indexOf(2020), hi = yrs.indexOf(2025);
  const sliceYears = yrs.slice(lo, hi + 1);
  const sliceFuel = f => D.annual.series[f].slice(lo, hi + 1);
  const sliceClean = D.annual.cleanPct.slice(lo, hi + 1);

  /* ---- 2. Annual mix ---- */
  make("mixAnnual", {
    type: "line",
    data: { labels: sliceYears, datasets: STACK.map(f => area(NAME[f], sliceFuel(f), C[f])) },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
        tooltip: { callbacks: { label: c => `${c.dataset.label}: ${(c.parsed.y / 1000).toFixed(1)} TWh` } },
      },
      scales: {
        y: { stacked: true, grid, ticks: { ...tick, callback: v => (v / 1000) + " TWh" } },
        x: { stacked: true, grid: { display: false }, ticks: tick },
      },
    },
  });

  /* ---- 3. Emissions-free share ---- */
  make("clean", {
    type: "line",
    data: { labels: sliceYears, datasets: [{
      label: "Emissions-free %", data: sliceClean,
      borderColor: "#33c2b3", backgroundColor: "#33c2b322", fill: true, tension: .3,
      pointRadius: 4, pointBackgroundColor: "#33c2b3", borderWidth: 2.5,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => c.parsed.y + "% emissions-free" } } },
      scales: { y: { min: 70, max: 100, grid, ticks: { ...tick, callback: v => v + "%" } }, x: { grid: { display: false }, ticks: tick } },
    },
  });

  /* ---- 4. The substitution: gas up, nuclear down ---- */
  const twh = arr => arr.map(v => +(v / 1000).toFixed(1));
  make("sub", {
    type: "line",
    data: { labels: sliceYears, datasets: [
      { label: "Nuclear (TWh)", data: twh(sliceFuel("NUC")), borderColor: C.NUC, backgroundColor: "transparent", tension: .3, pointRadius: 3, borderWidth: 2.5 },
      { label: "Natural Gas (TWh)", data: twh(sliceFuel("GAS")), borderColor: C.GAS, backgroundColor: "transparent", tension: .3, pointRadius: 3, borderWidth: 2.5, borderDash: [5, 4] },
    ] },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } } },
      scales: { y: { grid, ticks: tick }, x: { grid: { display: false }, ticks: tick } },
    },
  });
})();
