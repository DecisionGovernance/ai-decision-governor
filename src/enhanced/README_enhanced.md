# decision_governance — Enhanced

An advanced, production-closer simulation of AI decision governance. This module extends the core framework with a **risk-weighted, multi-tiered governor**, a dedicated `MetricsTracker`, full `Action` enum typing, and an automated report generator that exports results to both CSV and Markdown.

---

## Files

| File | Purpose |
|---|---|
| `decision_governance_adv.py` | Main simulation: tools, agent, advanced governor, orchestration |
| `risk_weighted_governor.py` | Standalone `DecisionGovernor` with calibrated, tiered risk logic |
| `generates_report.py` | Runs experiments and exports results to `results.csv` and `results.md` |
| `results.csv` | Machine-readable experiment output |
| `results.md` | Human-readable formatted experiment output |

---

## What's New vs. Core

| Feature | Core | Enhanced |
|---|---|---|
| Governor decisions | ALLOW / ABSTAIN | ALLOW / **SCALE** / ABSTAIN |
| Risk scoring | `uncertainty × cost` (linear) | Weighted: belief + uncertainty + cost ratio |
| Rollout scaling | Linear decay | **Square-root scaling** (configurable) |
| Trap sensitivity | Basic | Multi-tier with per-threshold modifiers |
| Metrics | Inline dict | Dedicated `MetricsTracker` dataclass |
| Type safety | Plain strings | `Action` and `FailCode` enums |
| Reporting | Console only | Auto-export to **CSV + Markdown** |

---

## Architecture

```
Agent (SimpleToolAgent)
     │
     │  propose(belief, uncertainty)            ← Beta-distributed, miscalibrated in OOD
     ▼
DecisionGovernor (risk_weighted_governor.py)
     │
     │  Tiered risk logic:
     │    Tier 1 — Critical trap + high cost   → ABSTAIN
     │    Tier 2 — Risk > abstain threshold    → ABSTAIN
     │    Tier 3 — High uncertainty + cost     → ABSTAIN
     │    Tier 4 — Moderate risk               → SCALE
     │    Otherwise                            → ALLOW
     ▼
ToolEnvironment
     │
     │  execute_scenario → (success, loss, FailCode)
     ▼
MetricsTracker  →  success rate, catastrophes, CVaR, abstention, scale rate
     │
     ▼
generates_report.py  →  results.csv  +  results.md
```

---

## Risk Score Formula

The governor computes a bounded risk score in **[0, 1]**:

$$
\text{base\_risk} = \text{uncertainty} \times 0.6 + p_{\text{fail}} \times (1 - \text{uncertainty} \times 0.4)
$$

$$
\text{risk} = \text{base\_risk} \times \text{trap\_factor} \times \text{cost\_ratio}
$$

$$
\text{abstain\_threshold} = \frac{\text{unc\_abstain}}{\sqrt{1 + \text{rollout} \times \text{rollout\_sensitivity}}}
$$

Where:
- `trap_factor = 1.15` for trap-sensitive calls
- `cost_ratio = catastrophic_cost / (catastrophic_cost + normal_cost)`
- Thresholds tighten as rollout increases

---

## Tools Configured

| Tool | Irreversible | Catastrophic Cost | Description |
|---|---|---|---|
| `db.read` | No | 1 | Safe read, always allowed |
| `db.delete` | Yes | 15,000 | High-risk, trap-sensitive irreversible delete |
| `email.send` | Yes | 500 | External send, moderate risk |

Scenario distribution: **25% dangerous** (`db.delete`), **75% safe** — reflecting realistic API traffic.

---

## Running

```bash
# Run simulation and generate reports
python generates_report.py

# This produces:
#   results.csv   — raw data for analysis
#   results.md    — formatted markdown table
```

Requires Python 3.7+ — standard library only, no external dependencies.

---

## Results

*Generated: 2026-03-19*

| Rollout (%) | Policy | Success Rate (%) | Catastrophic Failures | CVaR (95%) | Abstention Rate (%) | Scale Rate (%) |
|---|---|---|---|---|---|---|
| 1% | Accuracy-only (Baseline) | 98.5 | 26 | 3960 | 0.0 | 0.0 |
| **1%** | **Decision Governor** | **76.2** | **0** | **6** | **18.8** | **4.0** |
| 10% | Accuracy-only (Baseline) | 98.7 | 22 | 3331 | 0.0 | 0.0 |
| **10%** | **Decision Governor** | **73.9** | **0** | **7** | **20.4** | **4.5** |
| 25% | Accuracy-only (Baseline) | 98.8 | 33 | 4979 | 0.0 | 0.0 |
| **25%** | **Decision Governor** | **75.0** | **0** | **5** | **24.0** | **0.0** |
| 50% | Accuracy-only (Baseline) | 98.3 | 24 | 3685 | 0.0 | 0.0 |
| **50%** | **Decision Governor** | **75.1** | **0** | **6** | **23.9** | **0.0** |
| 100% | Accuracy-only (Baseline) | 98.7 | 19 | 2894 | 0.0 | 0.0 |
| **100%** | **Decision Governor** | **74.2** | **0** | **5** | **24.9** | **0.0** |

### Metrics

| Column | Meaning |
|---|---|
| **Success Rate** | % of tasks that completed successfully |
| **Catastrophic Failures** | Count of semantic traps executed on irreversible tools |
| **CVaR (95%)** | Expected loss in worst 5% of cases — tail-risk measure |
| **Abstention Rate** | % of tasks escalated for manual review |
| **Scale Rate** | % of tasks executed with constrained/scaled resources |

### Key Findings

- **Zero catastrophic failures**: Baseline incurs 19–33 catastrophes per stage; the Governor eliminates all of them across every rollout level.
- **CVaR reduced ~660×**: Worst-case expected loss falls from ~2,900–4,979 down to 5–7.
- **SCALE as a middle tier**: At 1% and 10% rollout, ~4–4.5% of tasks are scaled rather than fully blocked, recovering value while controlling risk.
- **Graceful abstention**: ~19–25% abstention rate grows steadily with rollout, reflecting the governor becoming stricter as deployment widens.
- **No missed safe operations**: The governor's tiered design ensures low-risk calls (`db.read`, low-uncertainty `email.send`) are never blocked.

---

## Governor Configuration

Tunable parameters in `DecisionGovernor` (`risk_weighted_governor.py`):

| Parameter | Default | Effect |
|---|---|---|
| `uncertainty_abstain` | 0.70 | Risk score threshold to trigger ABSTAIN |
| `uncertainty_scale` | 0.50 | Risk score threshold to trigger SCALE |
| `catastrophic_cost_threshold` | 8,000 | Min cost for a tool to be gated |
| `rollout_sensitivity` | 0.08 | How quickly thresholds tighten with rollout |
| `trap_factor` | 1.15 | Risk multiplier for trap-sensitive calls |
| `incorporate_belief` | True | Include failure probability in risk score |
| `incorporate_cost` | True | Weight risk by cost ratio |
| `use_sqrt_rollout` | True | Use sqrt scaling (smoother) vs. linear |

---

## License

MIT
