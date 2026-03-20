# AI Decision Governor

> **A safety framework that sits between an AI agent and the real world — blocking dangerous, irreversible actions before they cause harm.**

[![Python 3.7+](https://img.shields.io/badge/python-3.7%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![No Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)]()

---

## The Problem This Solves

Modern AI agents — language models connected to tools — can read files, send emails, delete database records, and execute code. Most of the time, this is exactly what we want. But sometimes an agent acts on bad instructions, misreads context (out-of-distribution input), or is manipulated into doing something destructive.

**The consequences can be irreversible.**

A database record deleted in error. An email sent to 10,000 customers by mistake. A financial transaction committed with the wrong amount.

Existing AI safety approaches either block too aggressively (making agents useless) or too permissively (allowing catastrophes). This project implements and quantifies a **middle path**: a *Decision Governor* that dynamically adjusts its risk tolerance based on how widely the AI is deployed, blocking dangerous operations while preserving the vast majority of legitimate work.

---

## What This Project Demonstrates

This repository contains a complete simulation framework — built from first principles — that:

1. **Models the failure modes** of AI agents acting on irreversible tools under uncertainty
2. **Implements a Governor** that intercepts tool calls, scores their risk, and decides: Allow, Scale, or Abstain
3. **Proves quantitatively** that catastrophic failures drop to zero while throughput is preserved (~75%)
4. **Provides two implementations**: a clean core version and an advanced calibrated version with full reporting

The framework uses **Common Random Numbers (CRN)**, a variance-reduction technique from quantitative research, to ensure fair, reproducible comparisons between governed and ungoverned agents.

---

## Key Results at a Glance

| | Ungoverned Agent | **Governed Agent** | Improvement |
|---|---|---|---|
| Catastrophic failures | 19 – 35 per run | **0** | **100% elimination** |
| Worst-case loss (CVaR 95%) | 2,894 – 5,285 | **5 – 11** | **~500× reduction** |
| Dangerous ops blocked | 0% | **100%** | Full interception |
| Task throughput | 98% | **~74%** | 25% escalated for review |

> The Governor eliminates every catastrophic failure across all deployment stages — from 1% rollout to full production — with no false negatives on dangerous operations.

---

## How It Works

### The Core Idea: Dynamic Risk Budgeting

The Governor's threshold is not fixed. It tightens as the AI is deployed more widely:

```
Risk Budget
    │
5000┤━━━━━━━━━┓                  ← Permissive at 1% rollout
    │          ┃                    Allows fast iteration early
    │          ┗━━━━━┓
    │                ┗━━━━━┓
    │                      ┗━━━━━┓
 500┤                            ┗━━━  ← Strict at 100% rollout
    └──────────────────────────────────
    1%        25%        50%       100%
                   Rollout %
```

**At 1% rollout** (testing): High budget → allows moderate-risk operations → faster iteration  
**At 100% rollout** (production): Low budget → only near-certain safe operations proceed → maximum protection

### Decision Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                        AI AGENT                                  │
│  Tracks per-tool success via Beta distributions                  │
│  Becomes miscalibrated in unfamiliar (OOD) situations            │
│  Reports: belief (0-1) + uncertainty (0-1) per tool call         │
└────────────────────────────┬─────────────────────────────────────┘
                             │  propose(belief, uncertainty)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                     DECISION GOVERNOR                            │
│                                                                  │
│  risk_score = f(uncertainty, failure_probability, cost_ratio)    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  TIER 1  Critical trap + high cost (≥$10,000) → ABSTAIN  │   │
│  │  TIER 2  Risk > tightened abstain threshold   → ABSTAIN  │   │
│  │  TIER 3  High uncertainty + cost (≥$15,000)   → ABSTAIN  │   │
│  │  TIER 4  Moderate risk                        → SCALE    │   │
│  │  DEFAULT Low risk                             → ALLOW    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Thresholds tighten as rollout % increases                       │
└──────────┬───────────────────┬──────────────────────────────────┘
           │ ALLOW / SCALE     │ ABSTAIN
           ▼                   ▼
┌──────────────────┐  ┌────────────────────────────────────────────┐
│  TOOL            │  │  HUMAN REVIEW QUEUE                        │
│  ENVIRONMENT     │  │  Operation held for manual approval        │
│                  │  │  Small delay cost (2 units) logged         │
│  Executes with   │  └────────────────────────────────────────────┘
│  real costs +    │
│  failure modes   │
└──────────────────┘
```

### The Two Failure Modes Modeled

```
SEMANTIC TRAP (Safety Failure)
──────────────────────────────
Agent receives ambiguous/adversarial input in OOD context
  → Calls db.delete with wrong target
  → Irreversible, catastrophic cost: $15,000
  → Governor blocks 100% of these in all experiments

MECHANICAL FAILURE (Reliability Failure)
─────────────────────────────────────────
Random execution failure based on tool's fail probability
  → Timeout, network error, partial write
  → Bounded cost, non-catastrophic
  → Governor allows through (expected, manageable)
```

---

## Repository Structure

```
ai-decision-governor/
│
├── README.md                          ← You are here
├── LICENSE
│
└── src/
    ├── core/
    │   ├── decision_governance_core.py    ← Clean baseline implementation
    │   └── README_core.md                 ← Core module documentation
    │
    └── enhanced/
        ├── decision_governance_adv.py     ← Advanced simulation engine
        ├── risk_weighted_governor.py      ← Calibrated multi-tier governor
        ├── generates_report.py            ← Report generator (CSV + Markdown)
        ├── results.csv                    ← Raw experiment output
        ├── results.md                     ← Formatted experiment output
        └── README_enhanced.md             ← Enhanced module documentation
```

---

## Module Overview

### `src/core/` — The Foundation

A clean, readable implementation that establishes the core concepts:

| Component | Description |
|---|---|
| `Tool` | Defines a tool: reversibility, failure rates, costs |
| `ToolCall` / `Task` / `Scenario` | CRN-enabled scenario generation for fair testing |
| `SimpleToolAgent` | Bayesian agent with Beta-distributed beliefs; miscalibrates in OOD |
| `DecisionGovernor` | Linear dynamic risk budgeting: `risk = uncertainty × cost` |
| `ToolEnvironment` | Simulates both semantic traps and mechanical failures |

**Run:**
```bash
python src/core/decision_governance_core.py
```

**Sample output:**
```
Rollout  | Model | Succ%  | Catast | CVaR   | Abst%  | Dang.Block%
--------------------------------------------------------------------------------
1%       | Base  | 98.4   | 30     | 4532   | -      | -
         | Gov   | 73.6   | 0      | 9      | 25.0   | 100.0
--------------------------------------------------------------------------------
100%     | Base  | 98.3   | 33     | 5009   | -      | -
         | Gov   | 74.4   | 0      | 11     | 24.4   | 100.0
--------------------------------------------------------------------------------
```

---

### `src/enhanced/` — The Advanced Framework

Extends the core with production-grade features:

| Component | What's New |
|---|---|
| `Action` / `FailCode` enums | Type-safe decisions replacing plain strings |
| `MetricsTracker` dataclass | Encapsulates all per-run statistics cleanly |
| `DecisionGovernor` (adv) | Adds **SCALE** tier: constrained execution between Allow and Abstain |
| `risk_weighted_governor.py` | Standalone calibrated governor with 4-tier logic, trap multipliers, cost weighting, and sqrt rollout scaling |
| `generates_report.py` | Automated export to `results.csv` and `results.md` |

**Run:**
```bash
cd src/enhanced
python generates_report.py
```

---

## Full Experimental Results

*2,000 tasks per rollout stage · 20% out-of-distribution rate · Common Random Numbers for variance control*

| Rollout | Policy | Success Rate | Catastrophes | CVaR (95%) | Abstention | Scale Rate |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1% | Baseline | 98.5% | **26** | 3,960 | — | — |
| 1% | **Governor** | 76.2% | **0** | **6** | 18.8% | 4.0% |
| 10% | Baseline | 98.7% | **22** | 3,331 | — | — |
| 10% | **Governor** | 73.9% | **0** | **7** | 20.4% | 4.5% |
| 25% | Baseline | 98.8% | **33** | 4,979 | — | — |
| 25% | **Governor** | 75.0% | **0** | **5** | 24.0% | 0.0% |
| 50% | Baseline | 98.3% | **24** | 3,685 | — | — |
| 50% | **Governor** | 75.1% | **0** | **6** | 23.9% | 0.0% |
| 100% | Baseline | 98.7% | **19** | 2,894 | — | — |
| 100% | **Governor** | 74.2% | **0** | **5** | 24.9% | 0.0% |

### What the Numbers Mean

```
CATASTROPHES
  Baseline  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  19–35
  Governor  ░  0  ← Complete elimination across all stages

CVaR (worst-case expected loss, 95th percentile)
  Baseline  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  2,894 – 5,285
  Governor  ░  5–11  ← ~500× reduction

THROUGHPUT (tasks completed without escalation)
  Baseline  ████████████████████████████████  ~98%
  Governor  ██████████████████████████░░░░░░  ~74–76%
                                      ↑
                        ~24% escalated for human review
                        (the right tradeoff for safety)
```

---

## Technical Highlights

### Common Random Numbers (CRN)
Each rollout stage generates a fixed set of scenarios before running both the baseline and governor. This ensures any difference in outcomes is due solely to the governor's decisions — not random luck — producing statistically valid comparisons.

### Beta Distribution Belief Tracking
The agent maintains per-tool Beta(α, β) distributions updated with each execution outcome. Uncertainty is derived from the distribution's variance, giving a principled, data-driven confidence signal rather than a hardcoded heuristic.

### Miscalibration Modeling
The "Confident but Wrong" failure mode — where an agent becomes more confident as it encounters unfamiliar inputs — is explicitly modeled. In OOD scenarios, the agent inflates its belief by +0.2 and halves its reported uncertainty. This is the precise condition a safety governor must catch.

### Risk Score Formula (Enhanced)

$$
\text{base\_risk} = \text{uncertainty} \times 0.6 \;+\; p_{\text{fail}} \times (1 - \text{uncertainty} \times 0.4)
$$

$$
\text{risk} = \text{base\_risk} \;\times\; \text{trap\_factor} \;\times\; \frac{C_{\text{catastrophic}}}{C_{\text{catastrophic}} + C_{\text{normal}}}
$$

$$
\text{threshold}_{\text{abstain}} = \frac{0.70}{\sqrt{1 + \text{rollout} \times 0.08}}
$$

The square-root rollout scaling provides a gentler tightening curve than linear decay, reducing over-blocking during mid-stage rollouts.

---

## Real-World Applicability

This framework directly models a problem at the frontier of AI deployment:

| Simulated Concept | Real-World Analogue |
|---|---|
| `db.delete` (cost $15,000) | Deleting production customer records |
| `email.send` (cost $500) | Sending a mass communication incorrectly |
| Semantic trap | Prompt injection / adversarial input attack |
| OOD scenario | Agent used outside its training distribution |
| SCALE decision | Human-in-the-loop confirmation step |
| ABSTAIN decision | Hard block requiring supervisor approval |
| Rollout % | Phased deployment: internal → beta → production |

The Governor pattern implemented here is directly applicable to any system where an AI makes consequential decisions: financial automation, healthcare workflows, infrastructure management, and enterprise software agents.

---

## Getting Started

```bash
# Clone the repository
git clone https://github.com/your-username/ai-decision-governor.git
cd ai-decision-governor

# Run the core simulation (no dependencies required)
python src/core/decision_governance_core.py

# Run the advanced simulation with report generation
cd src/enhanced
python generates_report.py
# Output: results.csv and results.md
```

**Requirements:** Python 3.7+ · Standard library only · No pip installs needed

---

## License

MIT — see [LICENSE](LICENSE)

