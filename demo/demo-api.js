/* Trainer demo mode (GitHub Pages build only).
 *
 * Answers the web UI's /v1 calls in the browser with sample data so the app can be
 * tried without Postgres or the API. It is included only by scripts/build_demo.py (GitHub Pages);
 * the FastAPI server never serves it.
 *
 *  - Readiness scoring is a direct port of backend/app/engine/readiness.py.
 *  - Plans per day state are snapshots of real API responses from a local run.
 *  - Chat uses a port of the offline fallback in backend/app/llm/router.py.
 */
(function () {
  "use strict";

  const PLANS = {
  "GREEN": {
    "day_state": "GREEN",
    "tone": "coaching",
    "nutrition": {
      "meal_count": 3,
      "first_intake": {
        "effort": "low",
        "suggestion": "Whatever is easy — eggs, curd+banana, or leftover dal-rice"
      },
      "protein_floor_g": 112.0,
      "surface_calories": true,
      "soft_surplus_kcal": 200
    },
    "workout": {
      "kind": "full_body",
      "title": "Full-body strength (prescribed)",
      "minutes": 45,
      "rpe_cap": 8
    },
    "study": {
      "minutes": 60,
      "task_title": "Study: next unfinished topic at current mastery",
      "allow_hints": true,
      "difficulty_bias": "at",
      "counts_toward_streak": true
    },
    "opener": "Green day. Full-body work, protein around 112.0g, and 60 minutes of study. One thing at a time.",
    "micro_tasks": [
      {
        "kind": "intake",
        "title": "First intake: Whatever is easy — eggs, curd+banana, or leftover dal-rice",
        "minutes": 5,
        "counts_toward_streak": true,
        "sort_order": 0
      },
      {
        "kind": "movement",
        "title": "Full-body strength (prescribed)",
        "minutes": 45,
        "counts_toward_streak": true,
        "sort_order": 1
      },
      {
        "kind": "study",
        "title": "Study: next unfinished topic at current mastery (60 min)",
        "minutes": 60,
        "counts_toward_streak": true,
        "sort_order": 2
      }
    ]
  },
  "AMBER": {
    "day_state": "AMBER",
    "tone": "neutral",
    "nutrition": {
      "meal_count": 3,
      "first_intake": {
        "effort": "low",
        "suggestion": "Whatever is easy — eggs, curd+banana, or leftover dal-rice"
      },
      "protein_floor_g": 112.0,
      "surface_calories": false,
      "soft_surplus_kcal": null
    },
    "workout": {
      "kind": "scaled_full_body",
      "title": "Scaled strength (70% volume)",
      "minutes": 30,
      "rpe_cap": 7
    },
    "study": {
      "minutes": 30,
      "task_title": "Study: one topic at current mastery",
      "allow_hints": true,
      "difficulty_bias": "at",
      "counts_toward_streak": true
    },
    "opener": "Amber day. Scaled session (~30 min), protein floor 112.0g, 30 minutes of study. Pick the order that fits.",
    "micro_tasks": [
      {
        "kind": "intake",
        "title": "First intake: Whatever is easy — eggs, curd+banana, or leftover dal-rice",
        "minutes": 5,
        "counts_toward_streak": true,
        "sort_order": 0
      },
      {
        "kind": "movement",
        "title": "Scaled strength (70% volume)",
        "minutes": 30,
        "counts_toward_streak": true,
        "sort_order": 1
      },
      {
        "kind": "study",
        "title": "Study: one topic at current mastery (30 min)",
        "minutes": 30,
        "counts_toward_streak": true,
        "sort_order": 2
      }
    ]
  },
  "RED": {
    "day_state": "RED",
    "tone": "empathetic_no_guilt",
    "nutrition": {
      "meal_count": 2,
      "first_intake": {
        "effort": "none",
        "texture": "drinkable",
        "appetite": "low",
        "suggestion": "Flavored milk or protein coffee + banana (sip, no cooking)"
      },
      "protein_floor_g": 98.0,
      "surface_calories": false,
      "soft_surplus_kcal": null
    },
    "workout": {
      "kind": "movement_snack",
      "title": "Movement snack: easy walk + band pulls",
      "minutes": 12,
      "rpe_cap": 5
    },
    "study": {
      "minutes": 15,
      "task_title": "Easy study review below mastery — one small problem",
      "allow_hints": true,
      "difficulty_bias": "below",
      "counts_toward_streak": true
    },
    "opener": "Rough recovery day — we are not doing a full program. One easy sip-something when you are ready, a short walk later, and fifteen minutes on an easy problem if the head clears. Nothing else is owed.",
    "micro_tasks": [
      {
        "kind": "intake",
        "title": "First intake: Flavored milk or protein coffee + banana (sip, no cooking)",
        "minutes": 5,
        "counts_toward_streak": true,
        "sort_order": 0
      },
      {
        "kind": "movement",
        "title": "Movement snack: easy walk + band pulls",
        "minutes": 12,
        "counts_toward_streak": true,
        "sort_order": 1
      },
      {
        "kind": "study",
        "title": "Easy study review below mastery — one small problem (15 min)",
        "minutes": 15,
        "counts_toward_streak": true,
        "sort_order": 2
      },
      {
        "kind": "recovery",
        "title": "Optional: 10-minute walk or nap — either counts",
        "minutes": 10,
        "counts_toward_streak": true,
        "sort_order": 3
      }
    ]
  }
};

  // ---- readiness.py port -------------------------------------------------
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
  function zToUnit(value, baseline, sigma) {
    if (baseline == null || value == null) return 0.5;
    sigma = sigma || Math.max(baseline * 0.15, 1.0);
    return clamp(0.5 + ((value - baseline) / sigma) * 0.25, 0, 1);
  }
  function invZToUnit(value, baseline, sigma) {
    if (baseline == null || value == null) return 0.5;
    sigma = sigma || Math.max(baseline * 0.08, 1.0);
    return clamp(0.5 + ((baseline - value) / sigma) * 0.25, 0, 1);
  }
  function classifyDay(health, mood, consecutiveRed) {
    let s = 0;
    const sleepH = health.sleep_hours ?? 6.5;
    const sleepEff = health.sleep_efficiency ?? 0.85;
    s += clamp(sleepH / 7.5, 0, 1) * 0.30;
    s += clamp(sleepEff / 0.90, 0, 1) * 0.15;
    s += zToUnit(health.hrv_sdnn_ms, health.hrv_baseline) * 0.25;
    s += invZToUnit(health.rhr_bpm, health.rhr_baseline) * 0.15;
    if (mood) {
      s += (mood.energy / 5) * 0.15;
      if (mood.stress >= 4 || mood.valence <= 2) s = Math.min(s, 0.45);
    } else {
      s += 0.5 * 0.15;
    }
    if (consecutiveRed >= 3) return [s, "DELOAD"];
    if (s >= 0.70) return [s, "GREEN"];
    if (s >= 0.45) return [s, "AMBER"];
    return [s, "RED"];
  }

  // ---- sample data -------------------------------------------------------
  const DAY = 86400000;
  const iso = (d) => d.toISOString().slice(0, 10);
  const today = new Date();
  const uid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2));

  const SAMPLE_HEALTH = { sleep_hours: 7.1, sleep_efficiency: 0.88, hrv_sdnn_ms: 47, rhr_bpm: 58, hrv_baseline: 46, rhr_baseline: 58 };
  const BAD_DAY = { sleep_hours: 4.8, sleep_efficiency: 0.72, hrv_sdnn_ms: 28, rhr_bpm: 72, hrv_baseline: 45, rhr_baseline: 58 };
  const GOOD_DAY = { sleep_hours: 7.8, sleep_efficiency: 0.92, hrv_sdnn_ms: 52, rhr_bpm: 56, hrv_baseline: 48, rhr_baseline: 58 };

  const state = {
    health: { ...SAMPLE_HEALTH },
    mood: null,
    plan: null,
    preferences: ["Dislikes mass-gainer shakes (sample memory)"],
    weights: [],
    readiness: [],
    streaks: [],
  };

  // Two weeks of made-up history so the Progress panel has something to show.
  (function seedHistory() {
    let ewma = 69.4;
    const scores = [0.74, 0.68, 0.52, 0.81, 0.77, 0.43, 0.71, 0.79, 0.66, 0.58, 0.83, 0.72, 0.47];
    for (let i = 13; i >= 1; i -= 1) {
      const day = new Date(today.getTime() - i * DAY);
      const kg = 69.2 + (13 - i) * 0.06 + Math.sin(i) * 0.25;
      ewma = 0.2 * kg + 0.8 * ewma;
      if (i % 2 === 1) state.weights.push({ measured_at: day.toISOString(), weight_kg: +kg.toFixed(1), weight_ewma: +ewma.toFixed(2) });
      const score = scores[13 - i];
      state.readiness.push({ day: iso(day), readiness_score: score, day_state: score >= 0.7 ? "GREEN" : score >= 0.45 ? "AMBER" : "RED" });
      state.streaks.push({ day: iso(day), showed_up: i !== 6 && i !== 10 });
    }
  })();

  const currentWeight = () => {
    const last = state.weights[state.weights.length - 1];
    return last ? Number(last.weight_ewma ?? last.weight_kg) : 70;
  };

  function consecutiveRed() {
    let n = 0;
    for (let i = state.readiness.length - 1; i >= 0; i -= 1) {
      if (state.readiness[i].day === iso(today)) continue;
      if (state.readiness[i].day_state === "RED") n += 1; else break;
    }
    return n;
  }

  function buildPlan() {
    const [score, dayState] = classifyDay(state.health, state.mood, consecutiveRed());
    const base = JSON.parse(JSON.stringify(PLANS[dayState === "DELOAD" ? "RED" : dayState]));
    const perKg = dayState === "GREEN" || dayState === "AMBER" ? 1.6 : 1.4;
    const protein = Math.round(currentWeight() * perKg);
    base.nutrition.protein_floor_g = protein;
    base.opener = base.opener.replace(/protein (floor|around) [0-9.]+g/, (_, word) => `protein ${word} ${protein}g`);
    base.day_state = dayState;
    base.readiness_score = Number(score.toFixed(3));
    base.day = iso(today);
    base.id = uid();
    base.micro_tasks = base.micro_tasks.map((t) => ({ ...t, id: uid(), completed_at: null }));
    state.plan = base;
    const row = { day: iso(today), readiness_score: base.readiness_score, day_state: dayState };
    const at = state.readiness.findIndex((r) => r.day === row.day);
    if (at >= 0) state.readiness[at] = row; else state.readiness.push(row);
    return base;
  }

  // ---- router.py offline fallback port -----------------------------------
  function offlineReply(message, turnClass) {
    const lower = message.toLowerCase().trim();
    const plan = state.plan || buildPlan();
    const st = plan.day_state;
    const protein = Math.round(plan.nutrition.protein_floor_g || 85);
    const studyMin = plan.study.minutes || 15;
    const has = (words) => words.some((w) => lower.includes(w));
    const low = st === "RED" || st === "DELOAD";

    if (has(["solution", "give me the code", "full answer", "write the code"])) {
      return "I will not paste a full working solution. Tell me your current approach and where it fails (base case / edge case), and I will give the next small hint only.";
    }
    if (has(["hello", "hi", "hey", "yo"]) && lower.length < 12) {
      if (low) return `Hey — today is a ${st} recovery day. Tiny plan only: easy sip-something (~${protein}g protein floor), a short walk, and ${studyMin} minutes on an easy practice problem. Nothing else is owed. What do you want to tackle first?`;
      if (st === "AMBER") return `Hey — amber day. Scaled training, protein floor ~${protein}g (no calorie target), ${studyMin} min study. Want food, movement, or study first?`;
      return `Hey — green day if recovery holds. Protein ~${protein}g, full-ish session, ~${studyMin} min study. Food, lift, or study?`;
    }
    if (has(["tired", "exhausted", "awful", "rough", "slept", "sleep", "stressed", "late", "bad day", "burnt", "burned"])) {
      return `Got it — we treat this as a low-energy day (current plan state: ${st}). Skip the hero session. Do one of: flavored milk/curd+banana, a 10–12 min walk, or ${studyMin} easy minutes of study below mastery. Mark any one Done in Today and it counts as showing up.`;
    }
    if (has(["food", "eat", "meal", "hungry", "appetite", "breakfast", "lunch", "dinner", "protein"])) {
      if (low || st === "AMBER") return `Low-effort only. Aim for ~${protein}g protein today — calories stay hidden. Ideas: flavored milk + banana, curd + honey + chana, peanut butter on toast, leftover dal-rice. No mass-gainer shakes. What sounds least awful?`;
      return `Keep convenience-friendly meals around ~${protein}g protein. Dal-rice, eggs, curd, paneer wrap, peanut butter toast all count. Want a 2-meal sketch?`;
    }
    if (has(["workout", "gym", "lift", "train", "exercise", "walk"])) {
      if (low) return "Not a heavy day. Movement snack: easy walk + band pull-aparts, ~12 min, RPE ≤ 5. Stop while it still feels easy.";
      if (st === "AMBER") return "Scaled full-body ~30 min at RPE ≤ 7. Cut a set from each lift vs a normal day.";
      return "Full-body strength ~45 min is fine if joints feel good. Leave 1–2 reps in the tank.";
    }
    if (has(["study", "dsa", "leetcode", "code", "problem", "array", "tree", "graph", "dp"])) {
      if (turnClass === "dsa_hint" || lower.includes("hint")) {
        return "Before coding: restate the invariant in one sentence, then pick the simplest data structure that protects it. What’s the smallest input where your idea breaks?";
      }
      return `Timebox ${studyMin} minutes. ` + (low ? "Pick something below your current mastery — easy win today." : "One topic at your current level is enough.") + " Showing up for the block counts.";
    }
    if (has(["plan", "today", "what should", "schedule", "do today"])) {
      if (low) return `Today’s adapted plan is ${st}: protein floor ~${protein}g (no calorie number), 12-min movement snack, ${studyMin}-min easy study block. Pick one micro-task and mark it Done.`;
      return `Today’s plan is ${st}: protein ~${protein}g, training as prescribed, ${studyMin} min study. Say food / workout / study and I’ll zoom in.`;
    }
    if (low) return `I’m here. Today is dialed back (${st}). Ask me about food, a short walk, or an easy study block — one thing.`;
    return `I’m here (plan state ${st}). Ask about food, training, or study and I’ll keep it concrete.`;
  }

  // ---- route table -------------------------------------------------------
  const conversationId = uid();
  const routes = {
    "GET /status": () => ({ ok: true, ai_mode: "offline", ai_model: "offline-fallback", demo: true }),
    "GET /healthz": () => ({ ok: true }),
    "GET /plans/today": () => state.plan || buildPlan(),
    "GET /dashboard": () => ({ weights: state.weights, readiness: state.readiness, streaks: state.streaks, curriculum: {} }),
    "POST /demo/bad-day": () => {
      state.health = { ...BAD_DAY };
      state.mood = { valence: 2, energy: 2, stress: 4 };
      return buildPlan();
    },
    "POST /demo/good-day": () => {
      state.health = { ...GOOD_DAY };
      state.mood = { valence: 4, energy: 4, stress: 2 };
      return buildPlan();
    },
    "POST /mood": (body) => {
      state.mood = { valence: Number(body.valence), energy: Number(body.energy), stress: Number(body.stress) };
      if (body.trigger_text) state.preferences.push(`Mood trigger: ${body.trigger_text}`);
      return { mood_id: uid(), plan: buildPlan() };
    },
    "POST /weight": (body) => {
      const kg = Number(body.weight_kg);
      if (!Number.isFinite(kg) || kg <= 0) throw Object.assign(new Error("weight_kg must be a positive number"), { status: 422 });
      const ewma = 0.2 * kg + 0.8 * currentWeight();
      state.weights.push({ measured_at: new Date().toISOString(), weight_kg: kg, weight_ewma: +ewma.toFixed(2) });
      return { ok: true };
    },
    "POST /preferences": (body) => { state.preferences.push(String(body.content || "")); return { ok: true }; },
    "POST /tasks/complete": (body) => {
      const task = state.plan && state.plan.micro_tasks.find((t) => t.id === body.task_id);
      if (!task) throw Object.assign(new Error("task not found"), { status: 404 });
      task.completed_at = new Date().toISOString();
      const streak = state.streaks.find((s) => s.day === iso(today));
      if (streak) streak.showed_up = true; else state.streaks.push({ day: iso(today), showed_up: true });
      return { task, showed_up: true };
    },
    "POST /chat": (body) => {
      const message = String(body.message || "");
      const words = message.toLowerCase().split(/\W+/).filter((w) => w.length > 3);
      const memories = state.preferences.filter((p) => words.some((w) => p.toLowerCase().includes(w))).slice(0, 3);
      return {
        conversation_id: body.conversation_id || conversationId,
        reply: offlineReply(message, body.turn_class),
        model_tier: "none",
        memories_used: memories,
        day_state: (state.plan || buildPlan()).day_state,
      };
    },
  };

  window.TRAINER_DEMO = true;
  window.TrainerDemo = {
    async handle(path, { method = "GET", body } = {}) {
      await new Promise((r) => setTimeout(r, 120 + Math.random() * 180));
      const handler = routes[`${method} ${path.split("?")[0]}`];
      if (!handler) throw new Error(`API 404: ${path} is not part of the demo`);
      try {
        return JSON.parse(JSON.stringify(handler(body || {})));
      } catch (err) {
        throw new Error(`API ${err.status || 500}: ${err.message}`);
      }
    },
  };
})();
