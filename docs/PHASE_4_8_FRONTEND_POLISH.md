# Phase 4.8: Frontend Usability Upgrades

## Layout fix (regression)

**Problem**: Page was not scrollable; map was pushed to bottom and partially hidden on common laptop screens.

**Root cause**:
- `main` had `height: 100vh` and `display: flex` with `flexDirection: column`
- Header (title, totals, controls, AnchorInfo, Insights, Top 5 Hotspots, RiskPanel) was all stacked above the map
- With fixed viewport height, the map got `flex: 1` and only the leftover space
- No `overflow-y: auto` → page could not scroll
- `globals.css` `main { max-width: 640px }` kept the layout narrow

**Fix**:
- Replaced `height: 100vh` with `min-height: 100vh` and `overflow-y: auto` on `.map-page`
- Increased max-width to 1400px
- Two-column responsive grid: left = map + Top 5 Hotspots, right = RiskPanel (sidebar)
- Map container: `height: 60vh`, `min-height: 360px`
- On narrow screens (< 900px): single column, stacked
- Sidebar scrolls independently when long; page scroll works normally

**Screenshots guidance**:
- Before: Map appeared below a tall header, often off-screen; no scroll
- After: Map visible immediately under compact header; page scrolls; right sidebar shows risk content on wide screens

---

## What changed

- **Types**: `MetaTimeContract`, `MetaCache`, `MetaEval`, `MetaExplain` in `app/lib/types.ts`
- **AnchorInfo**: Displays "Data anchored to…" with anchor timestamp, window, anchored/absolute badge, UTC
- **Risk panel**: Model evaluation (MAE/MAPE, points, horizon) + Top drivers (meta.explain.features, top 5 with Show more to 10)
- **AbortController**: Viewport fetches cancel previous requests; no stale updates
- **Loading**: Spinner shown only if loading > 150ms (non-flickering)
- **Risk legend**: Bottom-right overlay (Low/Medium/High thresholds, "Directional effects, not causation")
- **Cache pill**: "Cached" badge in dev mode when `meta.response_cache.hit` is true

## Manual QA steps

1. **Pan/zoom**
   - Pan the map; verify insights (stats, hotspots, risk) update
   - Zoom in/out; verify no stale data after rapid zoom
   - Confirm loading spinner does not flicker for fast responses

2. **Anchor info**
   - After map loads, verify "Data anchored to…" appears with timestamp and "anchored" badge
   - Pan to a new area; verify anchor info updates (or stays consistent if same data)

3. **Risk panel**
   - Ensure "Risk forecast" section shows expected violations
   - Verify "Model evaluation" (MAE/MAPE) when meta.eval present
   - Verify "Top drivers" with effect indicators (green ↑, red ↓) and weights
   - Click "Show more" to see up to 10 features

4. **Risk legend**
   - Bottom-right of map: Low (0–33), Medium (34–66), High (67–100)
   - Note: "Directional effects, not causation"

5. **Cache pill (dev only)**
   - In development: after first load, pan back to same area; "Cached" pill should appear next to "Total violations"
   - Production: pill is hidden

6. **Rapid interactions**
   - Rapidly pan/zoom; verify no console errors, no race-condition flashes
   - AbortController should cancel in-flight requests
