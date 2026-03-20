"""
Risk‑weighted, calibrated decision governor for safe automated decision making.

This module defines a `DecisionGovernor` class that combines an agent’s
uncertainty, its predicted failure probability, the cost of an operation, and
the rollout exposure to decide whether to allow, scale or abstain from a
proposed irreversible tool call.  The governor uses a weighted risk score
bounded in [0,1], applies optional multipliers for trap‐sensitive calls and
high‐cost operations, and scales its thresholds with the rollout fraction.
It implements a multi‑tiered policy that abstains on the riskiest
combinations, scales moderate risk, and allows low‑risk actions.  This
governor can be used in safe reinforcement learning experiments to
demonstrate trade‑offs between task success and catastrophic risk.
"""

from dataclasses import dataclass
import math
from typing import Optional

@dataclass
class Tool:
    """
    Minimal definition of a tool used by the decision governor.

    Parameters
    ----------
    name : str
        Name of the tool.
    is_irreversible : bool
        Whether the tool performs an irreversible action.  Only irreversible
        tools are subject to gating.
    catastrophic_cost : float
        The cost incurred if the tool fails catastrophically.
    normal_cost : float
        The cost incurred if the tool fails in a non‑catastrophic way.
    """

    name: str
    is_irreversible: bool
    catastrophic_cost: float
    normal_cost: float


@dataclass
class GovernorDecision:
    """Encapsulates a decision made by the governor."""

    action: str  # one of "ALLOW", "SCALE", "ABSTAIN"
    reason: str  # short code describing why this action was taken


class DecisionGovernor:
    """
    Risk‑weighted and calibrated decision governor.

    This governor assesses the risk of executing a tool call based on the
    agent's uncertainty about success, its estimated probability of failure,
    and the relative cost of the operation.  It applies optional modifiers
    for trap‑sensitive calls and high‑cost tools, and adjusts its abstain
    and scale thresholds according to the rollout fraction using either
    linear or square‑root scaling.  A multi‑tiered logic then determines
    whether the call should be allowed, scaled or abstained.

    Parameters
    ----------
    uncertainty_abstain : float, default=0.70
        Base threshold on the risk score above which the governor abstains.
        Higher values make the governor less likely to abstain.  Must be
        greater than `uncertainty_scale`.
    uncertainty_scale : float, default=0.50
        Base threshold on the risk score above which the governor scales
        (but does not abstain).
    catastrophic_cost_threshold : float, default=8000.0
        Minimum catastrophic cost for a tool to be subject to gating.  Tools
        below this threshold are always allowed.
    rollout_sensitivity : float, default=0.08
        Controls how quickly the abstain and scale thresholds shrink as
        rollout increases.  Smaller values make the governor less sensitive
        to rollout.
    trap_factor : float, default=1.15
        Multiplier applied to the risk score when the call is marked
        trap‑sensitive.  Values above 1.0 increase the perceived risk of
        trap‑sensitive operations.
    incorporate_belief : bool, default=True
        Whether to incorporate the agent’s predicted failure probability into
        the risk score.  If False, the risk score is based solely on the
        uncertainty.
    incorporate_cost : bool, default=True
        Whether to weight the risk score by the ratio of catastrophic cost
        to the total cost (catastrophic + normal).  This makes higher‑cost
        irreversible tools subject to stricter governance.
    use_sqrt_rollout : bool, default=True
        If True, the thresholds are scaled by the square root of
        `(1 + rollout*rollout_sensitivity)`; otherwise linear scaling is used.
    """

    def __init__(
        self,
        uncertainty_abstain: float = 0.70,
        uncertainty_scale: float = 0.50,
        catastrophic_cost_threshold: float = 8000.0,
        rollout_sensitivity: float = 0.08,
        trap_factor: float = 1.15,
        incorporate_belief: bool = True,
        incorporate_cost: bool = True,
        use_sqrt_rollout: bool = True,
    ) -> None:
        self.unc_abstain = uncertainty_abstain
        self.unc_scale = uncertainty_scale
        self.cat_cost_thresh = catastrophic_cost_threshold
        self.rollout_sens = rollout_sensitivity
        self.trap_factor = trap_factor
        self.incorporate_belief = incorporate_belief
        self.incorporate_cost = incorporate_cost
        self.use_sqrt_rollout = use_sqrt_rollout

    def decide(
        self,
        tool: Tool,
        belief: float,
        uncertainty: float,
        rollout: float,
        is_trap_sensitive: bool,
    ) -> GovernorDecision:
        """
        Decide whether to allow, scale, or abstain from executing a tool call.

        The governor considers only irreversible tools whose catastrophic
        cost exceeds the configured threshold.  It computes a bounded risk
        score by combining the agent’s uncertainty and predicted failure
        probability, multiplies it by optional trap and cost modifiers, and
        scales the abstain and scale thresholds according to the rollout
        fraction.  A tiered set of rules then returns a `GovernorDecision`:

        * **Tier 1:** For trap‑sensitive operations with uncertainty ≥ 0.25 and
          catastrophic cost ≥ 10 000, abstain if the risk score is at least
          70 % of the adjusted abstain threshold.
        * **Tier 2:** If the risk score exceeds the adjusted abstain threshold,
          abstain in two sub‑cases: (a) trap‑sensitive calls with uncertainty
          ≥ 0.3, or (b) calls with risk ≥ 1.15× the adjusted abstain threshold.
        * **Tier 3:** If the uncertainty alone exceeds the base abstain
          threshold and the catastrophic cost ≥ 15 000, abstain.
        * **Tier 4:** For risk above the adjusted scale threshold with
          uncertainty ≥ 0.25, return a scaling decision.
        * **Otherwise:** Allow the call.
        """
        # Only gate irreversible tools with sufficiently high cost
        if not tool.is_irreversible:
            return GovernorDecision("ALLOW", "REVERSIBLE_TOOL")
        if tool.catastrophic_cost < self.cat_cost_thresh:
            return GovernorDecision("ALLOW", "LOW_CATASTROPHIC_COST")

        # Base risk from uncertainty and (optionally) failure belief
        if self.incorporate_belief:
            p_fail_est = max(0.0, min(1.0, 1.0 - belief))
            base_risk = uncertainty * 0.6 + p_fail_est * (1.0 - uncertainty * 0.4)
        else:
            base_risk = uncertainty

        # Apply trap multiplier for sensitive calls
        risk = base_risk * (self.trap_factor if is_trap_sensitive else 1.0)

        # Apply cost weighting if enabled
        if self.incorporate_cost:
            cost_ratio = tool.catastrophic_cost / (tool.catastrophic_cost + tool.normal_cost)
            risk *= cost_ratio

        # Compute rollout scaling factor for thresholds
        if self.use_sqrt_rollout:
            roll_factor = math.sqrt(1.0 + rollout * self.rollout_sens)
        else:
            roll_factor = 1.0 + rollout * self.rollout_sens

        # Adjust thresholds by rollout factor
        abstain_th = self.unc_abstain / roll_factor
        scale_th = self.unc_scale / roll_factor

        ccost = tool.catastrophic_cost

        # Tier 1: High‑risk trap sensitive operations
        if is_trap_sensitive and uncertainty >= 0.25 and ccost >= 10000.0:
            if risk >= abstain_th * 0.7:
                return GovernorDecision("ABSTAIN", "CRITICAL_TRAP_RISK")

        # Tier 2: Standard critical risk
        if risk >= abstain_th:
            if is_trap_sensitive and uncertainty >= 0.3:
                return GovernorDecision("ABSTAIN", "TRAP_HIGH_UNCERTAINTY")
            if risk >= abstain_th * 1.15:
                return GovernorDecision("ABSTAIN", "EXTREME_RISK")

        # Tier 3: Very high uncertainty & cost
        if uncertainty >= self.unc_abstain and ccost >= 15000.0:
            return GovernorDecision("ABSTAIN", "HIGH_UNCERTAINTY_HIGH_COST")

        # Tier 4: Moderate risk triggers scaling
        if risk >= scale_th and uncertainty >= 0.25:
            return GovernorDecision("SCALE", "MODERATE_RISK")

        # Otherwise allow
        return GovernorDecision("ALLOW", "LOW_RISK")