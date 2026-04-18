# Traffic-lyt — 5-Minute Demo Walkthrough

A guided script for showing the platform end-to-end. Assumes the stack is already running (`docker compose up`) and data is loaded (`init_nyc_zones` + `generate_synthetic_data`).

**Total estimated time:** ~5 minutes  
**Audience:** anyone evaluating the platform for the first time

---

## Setup checklist (before you begin)

- [ ] Stack is up: `docker compose -f infra/docker-compose.yml up -d`
- [ ] Browser open at `http://localhost:3000`
- [ ] API is healthy: `http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] Data is loaded (65 k violations, 8 zones visible on the map)

---

## Introduction *(~15 s)*

> "Traffic-lyt is an NYC traffic violation analytics platform. It ingests
> violation records, runs spatial and temporal analysis, and surfaces
> actionable enforcement recommendations — all in a single web interface.
> Let me walk you through it from the landing page to the decision dashboard."

---

## Step 1 — Landing Page *(~20 s)*

**URL:** `http://localhost:3000`

**What to do:**
1. Let the page fully load. Watch the three stat cards fill in.

**What to point out:**
- The three live stat cards fetch directly from the API — *Violations in database*, *Active zones*, *Active warnings*.
- "These numbers are real — pulled from PostgreSQL each time the page loads."
- The six feature cards below give a quick map to every part of the system.

**What to say:**
> "This is the entry point. The stats are live API calls — if you loaded the
> synthetic dataset you'll see ~65,000 violations. Click any card to jump
> straight to that section."

---

## Step 2 — Live Map *(~60 s)*

**URL:** `http://localhost:3000/map`

**What to do:**
1. The map opens centred on NYC at zoom 11. Scroll in to zoom toward **Midtown Manhattan** (around Times Square / 42nd St).
2. In the header toolbar, click **Heatmap** to switch view modes.
3. Zoom back out to city level; observe the hotspot clusters.
4. Switch back to **Markers** and click any red pin to see the popup.
5. Glance at the **Top 5 Hotspots** list below the map — click **Go to** on the top entry.

**What to point out:**
- Marker density is heaviest in Midtown, Lower Manhattan, and Brooklyn — matching the synthetic hotspot distribution.
- The heatmap shows spatial density at a glance; the grid size dropdown changes cell resolution.
- The sidebar **Risk Panel** shows a 24h forecast and switches to 30-day with the toggle.
- The **Zone Compare** panel lets you pin zones and zoom to them.

**What to say:**
> "The map is the real-time view. Zoom level controls how many violation
> points are loaded — under zoom 11 we fetch 200 points to keep it fast;
> above zoom 13 we load the full 500. The heatmap and risk forecast update
> automatically as you pan."

---

## Step 3 — Zone Analytics *(~45 s)*

**URL:** `http://localhost:3000/zones`

**What to do:**
1. The page opens with **Risk** sort active. Point out the top zone.
2. Click **Trend** — the order re-sorts by week-over-week velocity.
3. Click **Volume** — re-sorts by raw violation count.
4. Click the top-ranked zone to open its analytics panel on the right.
5. In the **Compare** section, tick a second zone to see the WoW / MoM delta table.

**What to point out:**
- Risk score, trend direction badge (↑ / ↓), and violation count all visible per row.
- The analytics panel shows a time-series chart, top violation types, and trend summary.
- The WoW comparison quantifies "this week vs last week" and "this month vs last month".

**What to say:**
> "Zone analytics is the neighbourhood-level view. Sort by risk to find the
> hottest areas, sort by trend to find what's accelerating. The compare panel
> is useful for before/after policy analysis."

---

## Step 4 — Early Warnings *(~30 s)*

**URL:** `http://localhost:3000/warnings`

**What to do:**
1. Let the warning cards load — they auto-refresh every 60 seconds.
2. Point to the severity colour bar (red = high, amber = medium, green = low).
3. Hover over the signal type badge on any card.

**What to point out:**
- Four signal types: **Trend up** (sustained daily rise), **WoW spike** (week-over-week jump), **MoM spike** (month-over-month jump), **Anomaly cluster** (spatially correlated z-score outliers).
- Cards are ranked by severity and signal strength.
- The cache pill (top right) shows whether data was served from the API response cache.

**What to say:**
> "Warnings are generated automatically. The system computes z-scores and
> delta percentages for every zone every time the endpoint is called. If a
> zone crosses a threshold, a card appears here. No manual configuration."

---

## Step 5 — Patrol Allocation *(~45 s)*

**URL:** `http://localhost:3000/patrol`

**What to do:**
1. Set **Units** to `8`.
2. Under **Strategy**, select **Balanced**.
3. In the **Zones to consider** selector, choose *Midtown Manhattan* and *Lower Manhattan*.
4. Click **Allocate patrols**.
5. Once the plan loads, scroll down to see the map overlay with unit markers.

**What to point out:**
- Each zone row shows assigned units, a priority score (0–1), and reason chips explaining the assignment (high volume, WoW spike, anomaly cluster, etc.).
- The recommendation hint under each zone gives a plain-English action.
- The Explain section at the bottom shows the full scoring narrative.
- The map renders a circle marker per zone; size proportional to assigned units.

**What to say:**
> "Patrol allocation runs a deterministic scoring algorithm — it combines
> volume, trend, WoW delta, and anomaly signals into a priority score, then
> distributes your units across zones. Everything is explainable: the reason
> chips tell you exactly why each zone ranked where it did."

---

## Step 6 — Policy Simulator *(~45 s)*

**URL:** `http://localhost:3000/policy`

**What to do:**
1. Select *Midtown Manhattan* and *Brooklyn Downtown* as target zones.
2. Click **+ Add intervention**, choose **Enforcement intensity**, set to **150 %**.
3. Click **+ Add intervention** again, choose **Patrol units**, set *From* `2` → *To* `5`.
4. Set horizon to **30 days**.
5. Click **Run simulation**.
6. Point to the delta bars in the Result panel.

**What to point out:**
- The **Baseline** column shows forecast violations without intervention.
- The **Simulated** column shows the projected outcome.
- The **Delta** column shows absolute and percentage reduction.
- The confidence badge (High / Medium / Low) tells you how reliable the forecast model is for these zones.

**What to say:**
> "The policy simulator lets you ask 'what if?' before committing to a policy.
> Stack multiple interventions, set your horizon, and the engine runs the
> forecast model with those parameters applied. You can export the result to
> CSV for reporting."

---

## Step 7 — Decision Dashboard *(~60 s)*

**URL:** `http://localhost:3000/decision`

**What to do:**
1. In the **Configure** panel, select *Midtown Manhattan*, *Lower Manhattan*, and *Brooklyn Downtown*.
2. Set horizon to **24 hours**.
3. Click **Get Recommendation**.
4. Walk through each section of the result:
   - **Verdict card** — the priority action and urgency badge.
   - **Confidence** — score and label with supporting detail.
   - **Warnings** section — which zones triggered signals.
   - **Patrol Plan** — the pre-computed unit assignments.
   - **Forecast** — expected violation count for the horizon.
5. Click **Explain** to expand the reasoning log.
6. Click **Print Report** to preview the printable version.

**What to point out:**
- The verdict is synthesised from all signals: warnings, patrol scoring, forecast, and confidence.
- The urgency badge (Critical / High / Medium / Low) drives the colour of the verdict card.
- The Explain log is the full audit trail — every signal and weight used to produce the recommendation.
- Print Report opens the browser print dialog with a clean layout (nav/buttons hidden, colours overridden for print).

**What to say:**
> "The decision dashboard is the synthesised output of everything else. Instead
> of switching between six pages, you get a single answer: 'here is what you
> should do right now, and here is exactly why.' It's the interface a shift
> supervisor would open at the start of a watch."

---

## Wrap-up *(~15 s)*

> "That's the full platform — from raw violation data to a structured,
> explainable recommendation in under five minutes. The stack is
> Next.js + FastAPI + PostgreSQL/PostGIS, fully Dockerised. The synthetic
> dataset has 65,000 records; swap in the real NYC open-data CSV with
> `make ingest` to run on actual data."

---

## Quick-reference URLs

| Page | URL |
|------|-----|
| Landing | http://localhost:3000 |
| Map | http://localhost:3000/map |
| Zones | http://localhost:3000/zones |
| Warnings | http://localhost:3000/warnings |
| Patrol | http://localhost:3000/patrol |
| Policy | http://localhost:3000/policy |
| Decision | http://localhost:3000/decision |
| API docs | http://localhost:8000/docs |
