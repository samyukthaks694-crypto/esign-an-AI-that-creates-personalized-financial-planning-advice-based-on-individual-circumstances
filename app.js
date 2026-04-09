const API = "http://localhost:5000/api";
let currentUser = null;
let currentAdviceType = null;

function showPage(pageId) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  const page = document.getElementById(pageId);
  if (page) { page.classList.add("active"); window.scrollTo(0, 0); }
}

function toast(message, type = "info", duration = 3500) {
  const icons = { success: "✓", error: "✕", info: "ℹ" };
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type]}</span><span>${message}</span>`;
  container.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

function setLoading(active, message = "Analyzing your financial data…") {
  const overlay = document.getElementById("loading-overlay");
  const msg = document.getElementById("loading-msg");
  overlay.classList.toggle("active", active);
  if (msg) msg.textContent = message;
}

async function api(path, method = "GET", body = null) {
  const opts = { method, credentials: "include", headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

async function checkAuth() {
  try { const user = await api("/me"); currentUser = user; updateNavUser(user); return true; }
  catch { return false; }
}

function updateNavUser(user) {
  document.querySelectorAll(".nav-user-name").forEach(el => el.textContent = user.name.split(" ")[0]);
  document.querySelectorAll(".nav-avatar").forEach(el => el.textContent = user.name[0].toUpperCase());
}

async function handleLogin(e) {
  e.preventDefault();
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;
  const btn = document.getElementById("login-btn");
  btn.disabled = true; btn.textContent = "Signing in…";
  try {
    const data = await api("/login", "POST", { email, password });
    currentUser = { name: data.name }; updateNavUser(currentUser);
    toast("Welcome back, " + data.name.split(" ")[0] + "!", "success");
    await loadHome();
  } catch (err) { toast(err.message, "error"); }
  finally { btn.disabled = false; btn.textContent = "Sign In"; }
}

async function handleSignup(e) {
  e.preventDefault();
  const name = document.getElementById("signup-name").value;
  const email = document.getElementById("signup-email").value;
  const password = document.getElementById("signup-password").value;
  const confirm = document.getElementById("signup-confirm").value;
  if (password !== confirm) return toast("Passwords do not match", "error");
  const btn = document.getElementById("signup-btn");
  btn.disabled = true; btn.textContent = "Creating account…";
  try {
    await api("/signup", "POST", { name, email, password });
    toast("Account created! Please sign in.", "success");
    showPage("page-login");
  } catch (err) { toast(err.message, "error"); }
  finally { btn.disabled = false; btn.textContent = "Create Account"; }
}

async function handleLogout() {
  await api("/logout", "POST"); currentUser = null;
  toast("Signed out successfully", "info"); showPage("page-login");
}

async function loadHome() {
  try {
    const { profile } = await api("/profile");
    const banner = document.getElementById("profile-banner");
    const bannerText = document.getElementById("profile-status-text");
    const bannerSub = document.getElementById("profile-status-sub");
    if (profile) {
      banner.style.borderColor = "rgba(52,211,153,0.3)";
      bannerText.textContent = "Financial Profile Complete";
      bannerSub.textContent = `Last updated • Income: ${formatCurrency(profile.monthly_income)}/mo • Risk: ${profile.risk_tolerance}`;
      document.getElementById("profile-banner-btn").textContent = "Update Profile";
    } else {
      bannerText.textContent = "Complete Your Financial Profile";
      bannerSub.textContent = "Upload your financial situation to unlock personalized AI advice";
    }
  } catch {}
  showPage("page-home");
}

async function showProfilePage() {
  try { const { profile } = await api("/profile"); if (profile) prefillProfile(profile); } catch {}
  showPage("page-profile");
}

function prefillProfile(p) {
  ["monthly_income","monthly_expenses","monthly_savings","current_savings","total_debt",
   "age","dependents","employment_type","country","primary_goal","retirement_age","goals_notes","life_notes"]
  .forEach(f => { const el = document.getElementById("p-" + f); if (el && p[f] !== undefined) el.value = p[f]; });
  if (p.risk_tolerance) {
    const radio = document.querySelector(`input[name="risk_tolerance"][value="${p.risk_tolerance}"]`);
    if (radio) radio.checked = true;
  }
}

async function handleProfileSave(e) {
  e.preventDefault();
  const risk = document.querySelector('input[name="risk_tolerance"]:checked');
  if (!risk) return toast("Please select your risk tolerance", "error");
  const profile = {
    monthly_income:   +document.getElementById("p-monthly_income").value,
    monthly_expenses: +document.getElementById("p-monthly_expenses").value,
    monthly_savings:  +document.getElementById("p-monthly_savings").value,
    current_savings:  +document.getElementById("p-current_savings").value,
    total_debt:       +document.getElementById("p-total_debt").value,
    age:              +document.getElementById("p-age").value,
    dependents:       +document.getElementById("p-dependents").value,
    employment_type:   document.getElementById("p-employment_type").value,
    country:           document.getElementById("p-country").value,
    primary_goal:      document.getElementById("p-primary_goal").value,
    retirement_age:   +document.getElementById("p-retirement_age").value,
    risk_tolerance:    risk.value,
    goals_notes:       document.getElementById("p-goals_notes").value,
    life_notes:        document.getElementById("p-life_notes").value,
  };
  const btn = document.getElementById("save-profile-btn");
  btn.disabled = true; btn.textContent = "Saving…";
  try { await api("/profile", "POST", profile); toast("Profile saved successfully!", "success"); await loadHome(); }
  catch (err) { toast(err.message, "error"); }
  finally { btn.disabled = false; btn.textContent = "Save & Analyze Profile"; }
}

const ADVICE_META = {
  financial:  { icon: "💼", label: "Financial Advice" },
  retirement: { icon: "🏖️", label: "Retirement Plan" },
  tax:        { icon: "📊", label: "Tax Optimization" },
  insurance:  { icon: "🛡️", label: "Insurance Needs" },
  investment: { icon: "📈", label: "Investment Strategy" },
};

async function requestAdvice(type) {
  currentAdviceType = type;
  const meta = ADVICE_META[type];
  setLoading(true, `Generating your personalized ${meta.label}…`);
  try {
    const data = await api(`/advice/${type}`, "POST");
    renderAdviceResult(type, data.advice);
    if (type === "investment" || type === "retirement") await loadScenario("base");
  } catch (err) {
    if (err.message.includes("profile")) { toast("Please complete your financial profile first", "error"); showProfilePage(); }
    else toast(err.message, "error");
  } finally { setLoading(false); }
}

function renderAdviceResult(type, advice) {
  const meta = ADVICE_META[type];
  document.getElementById("result-icon").textContent = meta.icon;
  document.getElementById("result-title").textContent = meta.label;
  document.getElementById("result-subtitle").textContent = "Personalized AI-generated analysis based on your financial profile";
  document.getElementById("advice-output").innerHTML = formatAdviceText(advice);
  document.getElementById("scenario-panel").style.display =
    (type === "investment" || type === "retirement") ? "block" : "none";
  showPage("page-result");
}

function formatAdviceText(text) {
  return text
    .replace(/^#{1,3} (.+)$/gm, (_, t) => `<h2>${t}</h2>`)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
    .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
    .replace(/\n\n/g, "</p><p>");
}

async function loadScenario(scenario) {
  document.querySelectorAll(".scenario-btn").forEach(b => b.classList.toggle("active", b.dataset.scenario === scenario));
  try {
    const data = await api("/scenario", "POST", { scenario, years: 10 });
    renderScenarioBars(data.projections, data.final_balance);
    document.getElementById("scenario-final").textContent = formatCurrency(data.final_balance);
    document.getElementById("scenario-rate").textContent = ((data.rate || 0) * 100).toFixed(1) + "% annual return";
  } catch (err) { console.error(err); }
}

function renderScenarioBars(projections, max) {
  const container = document.getElementById("scenario-bars");
  container.innerHTML = "";
  const milestone = Math.max(1, Math.floor(projections.length / 5));
  projections.filter((_, i) => i % milestone === 0 || i === projections.length - 1)
    .forEach(({ year, balance }) => {
      const pct = Math.min(100, (balance / max) * 100);
      const row = document.createElement("div");
      row.className = "scenario-bar-row";
      row.innerHTML = `<span>Y${year}</span>
        <div class="scenario-bar-track"><div class="scenario-bar-fill" style="width:${pct}%"></div></div>
        <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-2)">${formatCurrency(balance)}</span>`;
      container.appendChild(row);
    });
}

function formatCurrency(num) {
  if (!num && num !== 0) return "—";
  if (num >= 1_000_000) return "$" + (num / 1_000_000).toFixed(1) + "M";
  if (num >= 1_000) return "$" + (num / 1_000).toFixed(1) + "K";
  return "$" + num.toFixed(0);
}

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("login-form")?.addEventListener("submit", handleLogin);
  document.getElementById("signup-form")?.addEventListener("submit", handleSignup);
  document.getElementById("profile-form")?.addEventListener("submit", handleProfileSave);
  document.querySelectorAll(".logout-btn").forEach(btn => btn.addEventListener("click", handleLogout));
  document.querySelectorAll(".advice-card").forEach(card => card.addEventListener("click", () => requestAdvice(card.dataset.type)));
  document.querySelectorAll(".scenario-btn").forEach(btn => btn.addEventListener("click", () => loadScenario(btn.dataset.scenario)));
  document.getElementById("back-btn")?.addEventListener("click", () => showPage("page-home"));
  const authenticated = await checkAuth();
  if (authenticated) await loadHome(); else showPage("page-login");
});