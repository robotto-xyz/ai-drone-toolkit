# AGENTS.md — AI Drone Toolkit

> Grounding file for AI coding agents (Cursor, Claude Code, etc.) working in this
> repository. Read this before writing code. It encodes the architecture, the
> hard rules, the domain landmines, and the roadmap so suggestions land in the
> right place and don't reintroduce bugs we've already fixed.

---

## 1. What this project is

**Robotto** (https://robotto.xyz) is building "the intelligence layer for the
physical world," starting with drones. This repository — **AI Drone Toolkit** —
is the open-source flagship: a suite of **Model Context Protocol (MCP) servers
and libraries** that let AI assistants (Cursor, Claude, etc.) understand, debug,
and eventually command drone systems.

The toolkit has **two product tracks**:

1. **Read / diagnose** — backward-looking analysis of flight data. Offline,
   zero-risk. Shipping today: `px4-ulog-mcp` (PX4 `.ulg` flight-log inspection).
2. **Command** — natural-language → *simulated* drone control. The mirror image:
   intent → bounded action tools → PX4 SITL → telemetry back. Planned next:
   `px4-sitl-mcp` (see Roadmap).

The guiding product belief: **two genuinely-finished, polished servers beat six
toy repos.** Finish things. Depth over breadth.

---

## 2. Repository layout

This is a [`uv`](https://docs.astral.sh/uv/) **workspace monorepo**. Shared,
MCP-agnostic logic lives in a core package; each tool is a thin, independently
installable layer on top.

```
ai-drone-toolkit/
├── packages/
│   └── robotto-drone-core/   # Shared, MCP-AGNOSTIC parsers & utilities.
│                             # PX4 ULog parsing today; coordinate-frame,
│                             # telemetry, and SAFETY helpers as the toolkit grows.
├── tools/
│   ├── px4-ulog-mcp/         # MCP server: inspect PX4 .ulg logs.
│   └── px4-sitl-mcp/         # MCP server: command PX4 SITL only.
│                             # (future tools live here, one dir each)
├── examples/                 # Runnable scripts that drive core directly
│                             # (no MCP client needed).
├── docs/                     # Architecture & project-wide guides.
├── pyproject.toml            # Workspace root.
└── uv.lock
```

**The core/tool split is an architectural rule, not just tidiness.** See §4.

### Setup & common commands

```bash
uv sync --all-packages        # one venv for the whole workspace
uv run px4-ulog-mcp           # run the ULog MCP server (stdio)
uv run px4-sitl-mcp           # run the PX4 SITL command MCP server (stdio)
uv run pytest                 # run all tests
uv run python examples/analyze_ulog.py /abs/path/to/flight.ulg
```

Requires **Python 3.12+** and `uv`. (Note: when adding MAVSDK-based tools,
confirm MAVSDK ships wheels for the pinned Python version before committing.)

---

## 3. Non-negotiable principles

These are hard rules. Do not violate them, and flag any request that would.

### 3.1 Simulation-only, always
Any drone-**command** code targets **PX4 SITL on localhost only** — never real
hardware. This is enforced by a hard `SIMULATION_ONLY` gate in code, not a stray
env var, and not an afterthought. The connection address must be a local SITL
endpoint (e.g. `udpin://0.0.0.0:14540`). Commanding real aircraft is the
**founders' safety-owned domain**, out of scope for this repo.

### 3.2 Safety/verification is the thesis, not a feature
The defensible idea behind the command track is: *"make sure a bad LLM command
never reaches an aircraft."* Every command path goes through a safety layer:
altitude clamps, geofence, speed caps, an arming interlock, and **structured
refusals the LLM can relay to the user** (e.g.
`{"ok": false, "refused": true, "reason": "Requested 5000 m exceeds MAX_ALT_M=50"}`).
Safety logic that is reusable across tools belongs in **`robotto-drone-core`**,
not buried inside one tool.

### 3.3 Core/server separation
Parsing and domain logic stay **MCP-agnostic** and unit-testable with **no
server and no simulator running**. The `@mcp.tool` wrappers stay thin: validate
inputs, call core, shape the result. A tool function should rarely be more than
a few lines around a core call.

### 3.4 Verify library APIs before writing code
`pyulog`, `fastmcp`, and `mavsdk` all shift between versions. **Check current
docs / the installed version rather than relying on memory**, and validate
against real fixtures (sample logs, a running SITL) when possible. Several real
bugs in this codebase were caught only by running against actual data — see §5.

---

## 4. Architecture patterns

### The two-layer shape (every tool follows this)

```
LLM client (Cursor/Claude)
      │  MCP / stdio
      ▼
tools/<name>/…/server.py     ← thin @mcp.tool wrappers (no domain logic)
      │  plain Python calls
      ▼
packages/robotto-drone-core  ← all parsing / domain / safety logic
                               (knows nothing about MCP; pure, testable)
```

- **`server.py`** imports from `robotto_drone_core`, wraps functions as
  `@mcp.tool`, returns JSON-serializable dicts. No parsing, no MAVSDK calls
  inline, no business logic.
- **core** takes plain arguments (paths, numbers) and returns plain
  dicts/lists of primitives. No `@mcp.tool`, no FastMCP imports, no I/O beyond
  what the domain requires.

**Why:** it makes the domain logic unit-testable without a server or simulator,
lets the same core power a CLI / web app / multiple MCP servers, and keeps each
tool independently installable. When you add a new capability, ask first: *does
this belong in core (reusable) or in a single tool (specific)?* Default to core
for anything another tool might reuse — **especially safety logic.**

### FastMCP conventions
- One `FastMCP(name=..., instructions=...)` instance per tool; tools registered
  with the `@mcp.tool` decorator.
- Tool **docstrings are the LLM's API documentation** — write them for the model:
  say what the tool does, when to call it, and what each argument means. State
  units and frames explicitly (meters, seconds, AMSL, NED).
- Transport is **stdio** for local/editor use. Only add HTTP/auth if a hosted,
  multi-tenant deployment is actually needed (not for the dev-facing tools).
- Keep the tool surface small and composable (≈5–10 clear verbs per server, not
  a 30-tool mega-server). Editors degrade past ~40 active tools.

### Editor integration
Each tool ships a `.cursor/mcp.json` snippet in its README. The same stdio
server works unmodified in Cursor, Claude Code, Claude Desktop, and Windsurf.

### Current tool notes
- `px4-ulog-mcp` is fully fixture-tested through `robotto_drone_core.ulog_tools`.
- `px4-sitl-mcp` has simulator-free tests for safety and frame logic. Its
  MAVSDK paths are code-complete but must be flight-verified by running PX4 SITL
  locally; do not claim live command verification until that happens.

---

## 5. Domain landmines (read before touching flight data or commands)

These are the bugs that have bitten us or will. Internalize them.

| Landmine | What goes wrong | Rule |
|---|---|---|
| **pyulog `log_level` is an ASCII byte** | It's `51` (`ord('3')`), not int `3`. Naive mapping silently drops every ERROR — the whole value of the tool, gone, with no exception. | Decode ASCII digits; handle both forms. (Already fixed in core.) |
| **Unsigned-int timestamp underflow** | Subtracting `start_timestamp` from a change logged at t=0 underflows numpy `uint` to a huge number. | Do relative-time math in Python ints, not numpy. (Already fixed.) |
| **AMSL vs relative altitude** | `goto_location` / `set_position_global` take **AMSL** (above mean sea level), not height-above-home. Mixing them flies the drone into the ground. | Fetch home AMSL once from `telemetry.home()`, add the relative target. |
| **NED vs ENU frames** | PX4 is **North-East-Down**; most robotics tooling and human intuition are ENU. Sign/axis errors come from here. Down is **positive**. | Convert explicitly at the boundary; unit-test the conversion. Prefer exposing intuitive meters-from-home to the LLM and converting internally. |
| **MAVSDK-Python raises exceptions** | Unlike the C++ API (which returns Result enums), Python raises `ActionError` / `OffboardError`. | Wrap calls in try/except; convert to structured `{"ok": false, "reason": ...}`. Never let a raw exception escape a tool. |
| **PX4 auto-disarms quickly** | Arm-then-wait leaves the vehicle to auto-disarm within a few seconds. | `takeoff` should arm → take off promptly in one tool call, not two slow round-trips. |
| **Arming preconditions** | PX4 refuses to arm without a healthy global + home position. | Wait for `health.is_global_position_ok and health.is_home_position_ok` before arming; surface a clear message if not ready. |
| **Tool success ≠ action complete** | A command returning success means PX4 *accepted* it, not that the drone arrived. | For good UX, poll telemetry until the target is reached, or expose a `get_state` the LLM can call to confirm. Don't claim "done" prematurely. |
| **Offboard needs a setpoint before start** | `offboard.start()` fails if no setpoint was set first; setpoints must stream ≥2 Hz (MAVSDK sends 20 Hz). | Set an initial setpoint, then `start()`; expect `OffboardError`. |

---

## 6. Coding conventions

- **Python 3.12+**, type hints on public functions, `from __future__ import
  annotations` where useful.
- Core functions return **JSON-serializable** primitives (dicts/lists/str/num/
  bool) — no numpy scalars, no custom objects, across the MCP boundary.
- Errors in core raise a domain exception (e.g. `ULogError`); tools catch and
  convert to structured results. Tools never leak raw library tracebacks.
- Tests live in each member's `tests/`; **safety and parsing logic must be
  unit-tested with no simulator and no MCP client** (this is the backbone of the
  test suite and the proof of the safety story).
- Keep dependencies isolated per tool: a consumer installing one tool should not
  drag in another tool's heavy deps (e.g. MAVSDK, future ROS bindings). Declare
  deps in each tool's own `pyproject.toml`.
- MIT licensed; keep upstream license notices intact for vendored/derived code.
- Conventional, readable commits. Update the relevant README when behavior or
  the tool surface changes.

---

## 7. Roadmap

Status legend: ✅ done · 🟡 in progress · ⬜ planned

### Track 1 — Read / diagnose (`px4-ulog-mcp`)
- ✅ `list_log_topics` — uORB topic inventory (name, multi-id, samples, fields)
- ✅ `get_log_summary` — duration, hardware/firmware, flight-mode timeline,
  dropouts, logged warnings/errors
- ⬜ `query_topic(path, topic, start_s, end_s)` — pull one signal over a time
  window (battery, altitude, EKF innovations). The natural next tool.
- ⬜ `get_failsafe_events(path)` — extract failsafe triggers & arming-state
  changes with timestamps
- ⬜ `diagnose_flight(path)` — opinionated "what went wrong" bundle (EKF
  divergence, low battery, high vibration, mode thrash)
- ⬜ Round out docs + a short demo recording; this track is the credibility
  builder and should reach "finished" first.

### Track 2 — Command (`px4-sitl-mcp`)
The natural-language-to-drone track the CEO is most excited about. **Simulation-
only.** The server mirrors the log analyzer's structure: `drone.py` (MAVSDK
connection + raw actions), shared core safety/frame helpers, thin `server.py`
wrappers. Current status: code complete with simulator-free tests; live flight
behavior still needs verification against a running PX4 SITL instance.

- ✅ **Safety layer first** — `SIMULATION_ONLY` gate, `clamp_altitude`,
  `check_geofence`, speed cap, arming interlock. Unit-tested with no simulator.
- 🟡 `connect_sim()` / `get_drone_state()` — connect to SITL, read-only state
- 🟡 `takeoff(altitude_m)` — arm + take off, altitude-clamped
- 🟡 `goto(north_m, east_m, altitude_m)` — meters-from-home (intuitive for an
  LLM); convert to lat/lon/AMSL internally; geofence-checked
- 🟡 `land()` / `return_home()` — `land()` exists; `return_home()` is still planned
- 🟡 Telemetry-confirmed completion (poll until target reached)
- 🟡 `fly_survey_pattern(...)` — lawnmower generator; code-complete as a
  composition of `goto`s with upfront waypoint validation, pending live-SITL
  verification.
- 🟡 Multi-drone foundation — code-complete for multiple local SITL connections,
  per-drone safety gates, `list_drones`, `connect_drone(s)`, and per-drone
  command dispatch. Live multi-instance behavior still needs local verification.
- ⬜ Record a "sentence → simulated flight, with a visible safety refusal" demo.

### Core (`robotto-drone-core`) evolution
- ✅ PX4 ULog parsing helpers
- ✅ Coordinate-frame conversions (NED⇄ENU, AMSL⇄relative) — needed by track 2,
  unit-tested independently
- ✅ **Shared safety/verification primitives** — the crown jewel; reusable across
  every tool that ever commands a drone
- ⬜ Telemetry parsing/normalization shared between read and command tracks

### Longer-term (vision; resolve with founders before building deep)
- ⬜ Live-docs MCP server (version-pinned ROS 2 / PX4 / MAVLink) to stop AI
  assistants hallucinating deprecated APIs
- ⬜ Swarm-level command verbs in SITL (formations, collision avoidance,
  leader/follower, area search). The multi-drone plumbing exists, but these
  abstractions require a founder conversation before implementation.
- ⬜ Command authentication, **audit logging of every LLM-issued command**, and
  anomaly detection on the command stream — the security layer that makes this a
  defensible role as the collaboration deepens
- ⬜ Eventually target the founders' **real autonomy stack (likely ROS 2-based)**,
  not just vanilla PX4. **This is a conversation with them, not a guess** — where
  a natural-language command layer plugs in determines what the tools wrap (ROS 2
  actions vs. raw MAVSDK).

---

## 8. Context an agent should keep in view

- **Not selling yet.** This is built for learning and experience first;
  monetization comes later. Optimize for correctness, clarity, and a strong
  portfolio/demo story over premature generality.
- **Frontier models via MCP should beat the ~40% mission-success ceiling** seen
  in academic ROS 2 + Ollama work (arXiv:2506.07509) — that paper is useful as a
  model-selection cheat sheet and a map of potholes, not a competitor.
- When a decision touches the **founders' real stack or real hardware**, stop and
  flag it as a conversation to have with them rather than guessing.
- Be a **candid reviewer**: when reviewing code or structure, say what's right
  *and* what's broken or risky. Don't just validate.
