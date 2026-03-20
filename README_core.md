# decision_governance_core

A simulation framework for **AI Decision Governance** — a safety layer that wraps an AI agent's tool calls and dynamically decides whether to allow or block them based on risk scoring and rollout stage.

---

## Overview

As AI agents are deployed at scale, they increasingly call powerful, irreversible tools (e.g., database deletes, external emails). `decision_governance_core` models a **Governor** that sits between an agent and its tool environment and enforces **dynamic risk budgeting**: stricter thresholds are applied as rollout percentage increases.

The simulation uses **Common Random Numbers (CRN)** variance reduction so that the Baseline agent and the Governed agent are evaluated on identical scenarios for a fair comparison.

---

## Architecture

```
Agent (SimpleToolAgent)
     │
     │  propose(belief, uncertainty)
     ▼
Governor (DecisionGovernor)         ← Risk budget tightens as rollout → 100%
     │
     │  ALLOW / ABSTAIN
     ▼
Tool Environment (ToolEnvironment)
     │
     │  execute_scenario → (success, loss, code)
     ▼
Metrics (success rate, catastrophes, CVaR, abstention rate)
```

---

## Key Components

### `Tool`
Defines a tool's risk profile:
- `is_irreversible` — whether the action cannot be undone
- `base_fail_prob` / `ood_fail_prob` — mechanical failure rates in-distribution vs. out-of-distribution
- `catastrophic_cost` / `normal_cost` — loss values on failure

### `SimpleToolAgent`
A Bayesian agent that tracks per-tool success with Beta distributions. In out-of-distribution (OOD) scenarios it becomes **miscalibrated**: it reports inflated confidence while suppressing uncertainty — the "Confident but Wrong" failure mode.

### `DecisionGovernor`
Implements **Dynamic Risk Thresholding**:

```
risk_score     = uncertainty × catastrophic_cost
current_budget = start_budget − (start_budget − end_budget) × rollout
```

- Early rollout (1%): loose budget → allows most operations
- Full rollout (100%): strict budget → blocks high-uncertainty irreversible calls
- Always allows negligible-risk operations (risk < `end_budget`) without overhead

### Failure Modes Simulated
| Type | Trigger | Effect |
|---|---|---|
| **Semantic Trap** | OOD + trap-sensitive call | Tool executes with wrong semantics → catastrophic loss |
| **Mechanical Failure** | Based on `fail_prob` roll | Tool times out or errors → normal/capped loss |

---

## Tools Configured

| Tool | Irreversible | Catastrophic Cost | Description |
|---|---|---|---|
| `db.read` | No | 1 | Safe read, low impact |
| `db.delete` | Yes | 15,000 | High-risk, irreversible delete |
| `email.send` | Yes | 500 | External communication |

Scenario distribution: **25% dangerous** (`db.delete`), **75% safe** operations — reflecting realistic API traffic.

---

## Running

```bash
python decision_governance_core.py
```

Requires Python 3.7+ (standard library only, no external dependencies).

---

## Results

Simulation output across rollout stages (2,000 tasks per stage, 20% OOD rate):

```
Rollout  | Model | Succ%  | Catast | CVaR   | Abst%  | Dang.Block%
--------------------------------------------------------------------------------
1%       | Base  | 98.4   | 30     | 4532   | -      | -
         | Gov   | 73.6   | 0      | 9      | 25.0   | 100.0
--------------------------------------------------------------------------------
10%      | Base  | 98.2   | 27     | 4086   | -      | -
         | Gov   | 74.0   | 0      | 8      | 24.5   | 100.0
--------------------------------------------------------------------------------
25%      | Base  | 98.2   | 32     | 4842   | -      | -
         | Gov   | 75.5   | 0      | 8      | 23.1   | 100.0
--------------------------------------------------------------------------------
50%      | Base  | 98.9   | 35     | 5285   | -      | -
         | Gov   | 73.5   | 0      | 7      | 25.7   | 100.0
--------------------------------------------------------------------------------
100%     | Base  | 98.3   | 33     | 5009   | -      | -
         | Gov   | 74.4   | 0      | 11     | 24.4   | 100.0
--------------------------------------------------------------------------------
```

### Metrics

| Column | Meaning |
|---|---|
| **Succ%** | Percentage of tasks that completed successfully |
| **Catast** | Count of catastrophic losses (semantic trap on irreversible tool) |
| **CVaR** | Conditional Value at Risk at 95th percentile — expected loss in the worst 5% of cases |
| **Abst%** | Percentage of tasks the Governor abstained from (sent for manual review) |
| **Dang.Block%** | Percentage of dangerous operations (`db.delete`) that were blocked |

### Key Findings

- **Zero catastrophes**: The Governor completely eliminates catastrophic events across all rollout stages (30–35 catastrophes in baseline → 0 with governance).
- **CVaR reduced ~500×**: Worst-case expected loss drops from ~5,000 to ~8–11, demonstrating effective tail-risk control.
- **100% dangerous op blocking**: Every `db.delete` attempt under uncertainty is intercepted across all rollout levels.
- **~25% abstention**: The Governor escalates roughly 1 in 4 tasks for human review — a tractable overhead given the safety guarantee.
- **Graceful degradation**: Success rate on governed tasks (~74%) reflects abstentions being excluded, not execution failures.

---

## Configuration

Key parameters in `run_experiment_suite()`:

| Parameter | Default | Effect |
|---|---|---|
| `start_budget` | 5,000 | Risk tolerance at 0% rollout (permissive) |
| `end_budget` | 500 | Risk tolerance at 100% rollout (strict) |
| `p_ood` | 0.20 | Fraction of OOD scenarios |
| `n_tasks` | 2,000 | Tasks per rollout stage |

---

## License

MIT
