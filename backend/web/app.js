const USER_ID = "00000000-0000-4000-8000-000000000001";
const API = "/v1";

const els = {
  apiDot: document.getElementById("apiDot"),
  aiBadge: document.getElementById("aiBadge"),
  aiHint: document.getElementById("aiHint"),
  statePill: document.getElementById("statePill"),
  opener: document.getElementById("opener"),
  planCards: document.getElementById("planCards"),
  taskList: document.getElementById("taskList"),
  chatLog: document.getElementById("chatLog"),
  chatInput: document.getElementById("chatInput"),
  dsaMode: document.getElementById("dsaMode"),
  voiceStatus: document.getElementById("voiceStatus"),
  dash: document.getElementById("dash"),
  toast: document.getElementById("toast"),
};

let conversationId = null;
let recognizing = false;
let recognition = null;

async function api(path, { method = "GET", body } = {}) {
  // Demo builds (GitHub Pages) answer locally with sample data; see demo/demo-api.js.
  if (window.TrainerDemo) return window.TrainerDemo.handle(path, { method, body });
  let res;
  try {
    res = await fetch(`${API}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": USER_ID,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    throw new Error(`Cannot reach API (${err.message}). Is docker compose up?`);
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = typeof data === "string"
      ? data
      : (data?.detail || data?.error || res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return data;
}

function toast(msg) {
  els.toast.textContent = msg;
  els.toast.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { els.toast.hidden = true; }, 2800);
}

function renderPlan(plan) {
  if (!plan) {
    els.opener.textContent = "No plan yet.";
    return;
  }
  const state = plan.day_state || "—";
  els.statePill.textContent = state;
  els.statePill.className = `pill ${state}`;
  els.opener.textContent = plan.opener || "Here’s today’s adapted plan.";

  const n = plan.nutrition || {};
  const w = plan.workout || {};
  const s = plan.study || {};
  els.planCards.innerHTML = `
    <div class="card">
      <h3>Nutrition</h3>
      <p>Protein floor <strong>${Math.round(n.protein_floor_g || 0)}g</strong></p>
      <p>${n.surface_calories === false ? "Calories hidden today" : (n.soft_surplus_kcal != null ? `Soft surplus ~${n.soft_surplus_kcal} kcal` : "")}</p>
      <p>${n.first_intake?.suggestion || ""}</p>
    </div>
    <div class="card">
      <h3>Movement</h3>
      <p><strong>${w.title || "Workout"}</strong></p>
      <p>${w.minutes || 0} min · RPE ≤ ${w.rpe_cap ?? "—"}</p>
    </div>
    <div class="card">
      <h3>Study</h3>
      <p><strong>${s.task_title || "Study"}</strong></p>
      <p>${s.minutes || 0} minutes · bias: ${s.difficulty_bias || "at"}</p>
    </div>
  `;

  const tasks = plan.micro_tasks || [];
  els.taskList.innerHTML = tasks.map((t) => {
    const done = Boolean(t.completed_at);
    return `
      <div class="task ${done ? "done" : ""}" data-id="${t.id}">
        <div class="meta">
          <div class="kind">${t.kind}</div>
          <div>${t.title}</div>
        </div>
        ${done ? "<span>✓</span>" : `<button type="button" class="ghost done-btn" data-id="${t.id}">Done</button>`}
      </div>
    `;
  }).join("") || `<p class="muted">No micro-tasks.</p>`;

  els.taskList.querySelectorAll(".done-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await api("/tasks/complete", { method: "POST", body: { task_id: btn.dataset.id } });
        toast("Counted — you showed up.");
        await refresh();
      } catch (e) {
        toast(e.message);
        btn.disabled = false;
      }
    });
  });
}

function renderDash(dash) {
  if (!dash) return;
  const readiness = (dash.readiness || []).slice(-7);
  const weights = dash.weights || [];
  const streaks = dash.streaks || [];
  const shown = streaks.filter((s) => s.showed_up).length;
  const lastWeight = weights.at(-1);

  els.dash.innerHTML = `
    <div>
      <strong>${shown}</strong> show-up days in recent log
      ${lastWeight ? ` · weight EWMA <strong>${Number(lastWeight.weight_ewma ?? lastWeight.weight_kg).toFixed(1)} kg</strong>` : ""}
    </div>
    <div>
      <div class="muted" style="margin-bottom:0.4rem">Readiness (recent)</div>
      ${readiness.map((r) => {
        const pct = Math.round((r.readiness_score || 0) * 100);
        const color = r.day_state === "GREEN" ? "var(--green)" : r.day_state === "AMBER" ? "var(--amber)" : "var(--red)";
        return `<div class="bar-row">
          <span>${r.day?.slice(5) || ""}</span>
          <div class="bar"><span style="width:${pct}%;background:${color}"></span></div>
          <span>${pct}%</span>
        </div>`;
      }).join("") || `<p class="muted">No readiness rows yet.</p>`}
    </div>
  `;
}

function addChat(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  els.chatLog.appendChild(div);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function setAiStatus(status) {
  const mode = status?.ai_mode || "offline";
  els.aiBadge.textContent = mode === "live" ? `AI: Live (${status.ai_model})` : "AI: Offline rules";
  els.aiBadge.className = `ai-badge ${mode}`;
  if (mode === "offline" && status?.hint) {
    els.aiHint.hidden = false;
    els.aiHint.textContent = status.hint + " Get a free key at https://aistudio.google.com/apikey";
  } else {
    els.aiHint.hidden = true;
  }
}

async function refresh() {
  try {
    const status = await api("/status");
    els.apiDot.className = "dot ok";
    setAiStatus(status);
  } catch {
    els.apiDot.className = "dot bad";
    toast("API not reachable — run docker compose up -d");
    return;
  }
  const [plan, dash] = await Promise.all([
    api("/plans/today"),
    api("/dashboard"),
  ]);
  renderPlan(plan);
  renderDash(dash);
}

document.getElementById("btnRefresh").addEventListener("click", () => {
  refresh().catch((e) => toast(e.message));
});

async function runDemo(path, label) {
  try {
    const plan = await api(path, { method: "POST", body: {} });
    renderPlan(plan);
    toast(`${label}: ${plan.day_state} · study ${plan.study?.minutes || "?"} min`);
    renderDash(await api("/dashboard"));
  } catch (e) {
    toast(e.message);
  }
}

document.getElementById("btnBadDay").addEventListener("click", () => runDemo("/demo/bad-day", "Bad day"));
document.getElementById("btnGoodDay").addEventListener("click", () => runDemo("/demo/good-day", "Good day"));

document.getElementById("moodForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    const plan = await api("/mood", {
      method: "POST",
      body: {
        valence: Number(document.getElementById("valence").value),
        energy: Number(document.getElementById("energy").value),
        stress: Number(document.getElementById("stress").value),
        trigger_text: document.getElementById("trigger").value || null,
        source: "tap",
      },
    });
    renderPlan(plan.plan || plan);
    toast("Mood saved — plan updated");
  } catch (e) {
    toast(e.message);
  }
});

document.getElementById("weightForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    await api("/weight", {
      method: "POST",
      body: { weight_kg: Number(document.getElementById("weight").value) },
    });
    toast("Weight saved");
    renderDash(await api("/dashboard"));
  } catch (e) {
    toast(e.message);
  }
});

document.getElementById("prefForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const content = document.getElementById("pref").value.trim();
  if (!content) return;
  try {
    await api("/preferences", {
      method: "POST",
      body: { content, metadata: { source: "web" } },
    });
    document.getElementById("pref").value = "";
    toast("Memory saved");
  } catch (e) {
    toast(e.message);
  }
});

document.getElementById("chatForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const message = els.chatInput.value.trim();
  if (!message) return;
  els.chatInput.value = "";
  addChat("user", message);
  try {
    const resp = await api("/chat", {
      method: "POST",
      body: {
        message,
        conversation_id: conversationId,
        turn_class: els.dsaMode.checked ? "dsa_hint" : "chat",
      },
    });
    conversationId = resp.conversation_id;
    const tierNote = resp.model_tier === "none" ? " [offline AI]" : "";
    addChat("assistant", resp.reply + tierNote);
    if ("speechSynthesis" in window) {
      const u = new SpeechSynthesisUtterance(resp.reply);
      u.rate = 1.02;
      speechSynthesis.speak(u);
    }
  } catch (e) {
    toast(e.message);
  }
});

function setupVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = document.getElementById("btnMic");
  if (!SR) {
    btn.disabled = true;
    els.voiceStatus.textContent = "Voice needs Chrome or Safari.";
    return;
  }
  recognition = new SR();
  recognition.lang = "en-IN";
  recognition.interimResults = true;
  recognition.continuous = false;

  btn.addEventListener("click", () => {
    if (recognizing) {
      recognition.stop();
      return;
    }
    speechSynthesis.cancel();
    recognizing = true;
    btn.textContent = "Stop";
    els.voiceStatus.textContent = "Listening…";
    recognition.start();
  });

  recognition.onresult = (event) => {
    let finalText = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const chunk = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += chunk;
      else els.voiceStatus.textContent = chunk;
    }
    if (finalText) {
      els.chatInput.value = finalText.trim();
      els.voiceStatus.textContent = "Sending…";
      document.getElementById("chatForm").requestSubmit();
    }
  };
  recognition.onerror = () => {
    recognizing = false;
    btn.textContent = "Mic";
    els.voiceStatus.textContent = "Mic error — try again.";
  };
  recognition.onend = () => {
    recognizing = false;
    btn.textContent = "Mic";
    if (els.voiceStatus.textContent === "Listening…") {
      els.voiceStatus.textContent = "";
    }
  };
}

if (window.TRAINER_DEMO) document.getElementById("demoNote").hidden = false;
setupVoice();
refresh().catch((e) => toast(e.message));
