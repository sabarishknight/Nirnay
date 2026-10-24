// Shared header, footer and formatting helpers.
const NAV = [
  ["/", "Overview"], ["/demo", "Officer desk"], ["/head", "Lending head"], ["/applicant", "Applicant"],
  ["/story", "Approach"], ["/architecture", "Architecture"], ["/research", "Research"], ["/faq", "FAQ"], ["/about", "About"], ["/contact", "Contact"],
];

function chrome() {
  const here = location.pathname.replace(/\/$/, "") || "/";
  const top = document.createElement("div");
  top.innerHTML = `
  <div class="demo-strip">Demonstration with synthetic data and an illustrative credit policy. Not a real bank, customer or lending decision.</div>
  <header class="top"><div class="top-in">
    <a class="brand" href="/"><span class="brand-mark" aria-hidden="true">N</span><span class="brand-name">Nirnay</span><span class="brand-sub">Home loan decisions</span></a>
    <button class="nav-toggle" aria-expanded="false" aria-controls="nav">Menu</button>
    <nav class="nav" id="nav" aria-label="Main">${NAV.map(([h, t]) => `<a href="${h}" ${here === h ? 'aria-current="page"' : ""}>${t}</a>`).join("")}</nav>
  </div></header>`;
  document.body.prepend(...top.children);
  const t = document.querySelector(".nav-toggle");
  t.addEventListener("click", () => { const n = document.getElementById("nav"); n.classList.toggle("open"); t.setAttribute("aria-expanded", n.classList.contains("open")); });
  const f = document.createElement("footer");
  f.className = "foot";
  f.innerHTML = `<div class="wrap"><span>Nirnay is a point-of-view demo for a mid-sized Indian bank's retail lending team. All data is synthetic.</span>
    <span><a href="/policy">Policy library</a> &nbsp; <a href="/ai-log">How this was built</a> &nbsp; <span id="engine-note"></span></span></div>`;
  document.body.append(f);
  api("/api/meta").then(m => {
    const el = document.getElementById("engine-note");
    if (el) el.textContent = `Data: ${m.data_engine}${m.bq_location ? " (" + m.bq_location + ")" : ""}. AI: ${m.ai_model ? m.ai_model : m.ai}`;
    window.META = m;
  }).catch(() => {});
}

async function api(url, opts = {}) {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Indian digit grouping: 12,34,567
function inr(n, withSymbol = true) {
  if (n === null || n === undefined || isNaN(n)) return "–";
  const neg = n < 0; n = Math.round(Math.abs(n));
  let s = String(n);
  if (s.length > 3) { const last = s.slice(-3); let rest = s.slice(0, -3); rest = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ","); s = rest + "," + last; }
  return (neg ? "-" : "") + (withSymbol ? "₹" : "") + s;
}
function lakh(n) { if (n == null) return "–"; return n >= 1e7 ? "₹" + (n / 1e7).toFixed(2) + " cr" : "₹" + (n / 1e5).toFixed(2) + " L"; }
function dmy(s) { if (!s) return "–"; const d = new Date(String(s).slice(0, 10) + "T00:00:00"); return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }); }
function statusPill(s) {
  const map = { "Within policy": "pass", "Deviation": "flag", "Hold": "fail", "Not eligible": "fail", pass: "pass", flag: "flag", fail: "fail", info: "" };
  const label = { pass: "Pass", flag: "Flag", fail: "Fail", info: "Info" }[s] || s;
  return `<span class="pill ${map[s] ?? ""}">${esc(label)}</span>`;
}
document.addEventListener("DOMContentLoaded", chrome);
