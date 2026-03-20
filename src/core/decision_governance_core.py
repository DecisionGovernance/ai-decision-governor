from dataclasses import dataclass
import random
import math
from typing import Dict, List, Tuple, Optional


# -------------------------
# 1) Core Entities & Constants
# -------------------------


@dataclass
class Tool:
    name: str
    is_irreversible: bool
    base_fail_prob: float
    ood_fail_prob: float
    catastrophic_cost: float
    normal_cost: float


@dataclass
class ToolCall:
    tool_name: str
    args: Dict[str, str]
    is_trap_sensitive: bool = False


@dataclass
class Task:
    task_id: str
    calls: List[ToolCall]


@dataclass
class Scenario:
    """
    Pre-computed scenario for Common Random Numbers (CRN) variance reduction.
    """
    id: str
    task: Task
    is_ood: bool
    is_trap_active: bool
    mechanical_fail_roll: float


# -------------------------
# 2) Environment Simulator
# -------------------------


class ToolEnvironment:
    def __init__(self, tools: Dict[str, Tool]):
        self.tools = tools


    def execute_scenario(self, scenario: Scenario) -> Tuple[bool, float, str]:
        call = scenario.task.calls[0]
        tool = self.tools[call.tool_name]
       
        # 1. Semantic Traps (Safety Failure)
        if scenario.is_trap_active and call.is_trap_sensitive:
            cost = tool.catastrophic_cost if tool.is_irreversible else tool.normal_cost
            return True, cost, "TRAP_WRONG_SEMANTICS"


        # 2. Mechanical Failures (Reliability Failure)
        p_fail = tool.ood_fail_prob if scenario.is_ood else tool.base_fail_prob
       
        if scenario.mechanical_fail_roll < p_fail:
            # Mechanical failure cost is usually low unless catastrophic cascading happens
            loss = tool.normal_cost
            if tool.is_irreversible:
                 loss = min(tool.catastrophic_cost * 0.1, 500.0) # Cap mechanical loss
            return False, loss, "TIMEOUT_OR_ERROR"


        return True, 0.0, "OK"


# -------------------------
# 3) Agent: "Optimistic but Flawed"
# -------------------------


@dataclass
class BetaStats:
    a: float = 2.0
    b: float = 2.0


    def mean(self) -> float:
        return self.a / (self.a + self.b)


    def var(self) -> float:
        a, b = self.a, self.b
        return (a * b) / (((a + b) ** 2) * (a + b + 1))


class SimpleToolAgent:
    def __init__(self, tools: Dict[str, Tool], miscalibrate_tools: Optional[List[str]] = None):
        self.tools = tools
        self.stats: Dict[str, BetaStats] = {t: BetaStats() for t in tools.keys()}
        self.miscalibrate_tools = set(miscalibrate_tools or [])


    def propose(self, call: ToolCall, is_ood: bool) -> Tuple[float, float]:
        stats = self.stats[call.tool_name]
        base_belief = stats.mean()
        # Scale variance to create a usable 0-1 uncertainty signal
        base_unc = min(1.0, math.sqrt(stats.var()) * 4.0)


        # Miscalibration Logic:
        # In OOD, agent is "Confident but Wrong".
        # It reports high belief, and suppresses uncertainty, but not to zero.
        # A good Governor detects that '0.15' uncertainty on a Nuclear Launch is still too high.
        if is_ood and call.tool_name in self.miscalibrate_tools:
            belief = min(0.99, base_belief + 0.2)
            unc = max(0.05, base_unc * 0.5) # Underestimates risk by half
        else:
            belief = base_belief
            unc = base_unc


        return belief, unc


    def update(self, tool_name: str, success: bool):
        st = self.stats[tool_name]
        if success:
            st.a += 1
        else:
            st.b += 1


# -------------------------
# 4) Governor: Dynamic Risk Budgeting
# -------------------------


@dataclass
class GovernorDecision:
    action: str
    reason: str


class DecisionGovernor:
    def __init__(
        self,
        start_budget: float = 5000.0, # High budget for early rollout (Accepts Risk)
        end_budget: float = 500.0,    # Strict budget for full rollout (Safety First)
    ):
        self.start_budget = start_budget
        self.end_budget = end_budget


    def decide(self, tool: Tool, belief: float, uncertainty: float, rollout: float) -> GovernorDecision:
        """
        Implements Dynamic Risk Thresholding.
        """
        # 1. Calculate Expected Impact (Risk)
        # Risk = Probability (Uncertainty Proxy) * Impact (Cost)
        risk_score = uncertainty * tool.catastrophic_cost
       
        # 2. Calculate Current Risk Budget (Linear Decay)
        # We linearly interpolate between Start and End based on rollout %.
        # This provides the "Middle Ground":
        # - Early: Loose threshold (allows 99% of ops)
        # - Late: Tight threshold (blocks dangerous uncertainties)
       
        current_budget = self.start_budget - ((self.start_budget - self.end_budget) * rollout)
       
        # 3. Decision
        # Optimization: Always allow low-impact tools (Risk < End_Budget) to save compute/logging
        if risk_score < self.end_budget:
             return GovernorDecision("ALLOW", "NEGLIGIBLE_RISK")


        if risk_score > current_budget:
            return GovernorDecision("ABSTAIN", f"RISK_{risk_score:.0f}_EXCEEDS_BUDGET_{current_budget:.0f}")
       
        return GovernorDecision("ALLOW", "WITHIN_DYNAMIC_TOLERANCE")


# -------------------------
# 5) Experiment Orchestration
# -------------------------


def cvar(losses: List[float], alpha: float = 0.95) -> float:
    if not losses:
        return 0.0
    losses_sorted = sorted(losses)
    k = int(math.ceil(alpha * len(losses_sorted)))
    tail = losses_sorted[k:]
    return sum(tail) / max(1, len(tail))


def run_stage(
    env: ToolEnvironment,
    agent: SimpleToolAgent,
    governor: Optional[DecisionGovernor],
    scenarios: List[Scenario],
    rollout: float,
) -> Dict[str, float]:


    executed = 0
    success_count = 0
    catastrophes = 0
    losses = []
    abstained = 0
   
    # Specific Selectivity Metrics
    dangerous_ops_total = 0
    dangerous_ops_blocked = 0
    safe_ops_total = 0
    safe_ops_blocked = 0


    for scenario in scenarios:
        call = scenario.task.calls[0]
        tool = env.tools[call.tool_name]
        is_dangerous = (tool.catastrophic_cost > 2000)
       
        if is_dangerous: dangerous_ops_total += 1
        else: safe_ops_total += 1
       
        # Agent Propose
        belief, unc = agent.propose(call, is_ood=scenario.is_ood)


        # Governor Decide
        action = "ALLOW"
        if governor:
            dec = governor.decide(tool, belief, unc, rollout)
            action = dec.action


        if action == "ABSTAIN":
            abstained += 1
            losses.append(2.0) # Small cost for manual review/delay
           
            if is_dangerous: dangerous_ops_blocked += 1
            else: safe_ops_blocked += 1
            continue


        executed += 1
       
        # Environment Execute
        ok, loss, code = env.execute_scenario(scenario)
        agent.update(call.tool_name, success=ok)


        losses.append(loss)
       
        # Track Catastrophes (Trap triggered on irreversible tool)
        if code == "TRAP_WRONG_SEMANTICS" and tool.is_irreversible:
             if loss > 1000: # Ensure it's a major loss
                catastrophes += 1
       
        if ok:
            success_count += 1


    # Calculate Selectivity
    # Ideal: High block rate on Dangerous, Low block rate on Safe
    dang_block_rate = (dangerous_ops_blocked / dangerous_ops_total * 100) if dangerous_ops_total else 0
    safe_block_rate = (safe_ops_blocked / safe_ops_total * 100) if safe_ops_total else 0


    return {
        "success_rate": (success_count / len(scenarios)) * 100.0,
        "catastrophes": catastrophes,
        "mean_loss": sum(losses) / len(scenarios),
        "cvar_95": cvar(losses, 0.95),
        "abstention_rate": (abstained / len(scenarios)) * 100.0,
        "dangerous_block_rate": dang_block_rate,
        "safe_block_rate": safe_block_rate
    }


def generate_scenarios(tools: Dict[str, Tool], count: int, p_ood: float, seed: int) -> List[Scenario]:
    """
    Generates a fixed list of scenarios for fair comparison.
    """
    random.seed(seed)
    scenarios = []
    tool_names = list(tools.keys())
   
    # 25% Dangerous Tools, 75% Safe Tools
    # This reflects a real API where most calls are 'read', few are 'delete'
    weights = [0.25 if "delete" in t else 0.75 / (len(tools)-1) for t in tool_names]
   
    for i in range(count):
        t_name = random.choices(tool_names, weights=weights, k=1)[0]
        tool = tools[t_name]
       
        is_trap_sens = (t_name == "db.delete")
        call = ToolCall(t_name, {"id": str(i)}, is_trap_sensitive=is_trap_sens)
        task = Task(f"T{i}", [call])
       
        # OOD Logic
        is_ood = (random.random() < p_ood)
       
        # Trap Logic: If OOD, 30% chance it's a semantic trap
        becomes_trap = (random.random() < 0.30)
        trap_active = is_ood and becomes_trap
       
        scen = Scenario(
            id=f"S{i}",
            task=task,
            is_ood=is_ood,
            is_trap_active=trap_active,
            mechanical_fail_roll=random.random()
        )
        scenarios.append(scen)
       
    return scenarios


# -------------------------
# 6) Main Execution Suite
# -------------------------


def run_experiment_suite():
    # Define Tools
    # db.delete: The "Nuclear Option". Cost 15000.
    # db.read: The "Safe Option". Cost 1.
    # email.send: The "Middle Option". Cost 500.
    tools_list = [
        Tool("db.read", False, 0.01, 0.02, 1.0, 1.0),
        Tool("db.delete", True, 0.01, 0.05, 15000.0, 50.0),
        Tool("email.send", True, 0.01, 0.03, 500.0, 5.0),
    ]
    tools = {t.name: t for t in tools_list}
    env = ToolEnvironment(tools)
   
    rollout_levels = [0.01, 0.10, 0.25, 0.50, 1.00]
    p_ood = 0.20
   
    print(f"{'Rollout':<8} | {'Model':<5} | {'Succ%':<6} | {'Catast':<6} | {'CVaR':<6} | {'Abst%':<6} | {'Dang.Block%':<12}")
    print("-" * 80)


    for rollout in rollout_levels:
        # Scale task count with rollout, but min 500 for statistical significance
        n_tasks = 2000
       
        # 1. Generate CRN Scenarios (Same for Base and Gov)
        current_scenarios = generate_scenarios(tools, n_tasks, p_ood, seed=100 + int(rollout*100))
       
        # 2. Baseline Run (Fresh Agent)
        base_agent = SimpleToolAgent(tools, miscalibrate_tools=["db.delete"])
        res_base = run_stage(env, base_agent, None, current_scenarios, rollout)
       
        # 3. Governor Run (Fresh Agent)
        gov_agent = SimpleToolAgent(tools, miscalibrate_tools=["db.delete"])
       
        # Start Budget 5000: Allows db.delete (15k) if U < 0.33. (Tolerant)
        # End Budget 500: Allows db.delete (15k) only if U < 0.033. (Strict)
        governor = DecisionGovernor(start_budget=5000.0, end_budget=500.0)
        res_gov = run_stage(env, gov_agent, governor, current_scenarios, rollout)
       
        # 4. Print
        print(f"{rollout:<8.0%} | {'Base':<5} | {res_base['success_rate']:<6.1f} | {res_base['catastrophes']:<6} | {res_base['cvar_95']:<6.0f} | {'-':<6} | {'-':<12}")
        print(f"{'':<8} | {'Gov':<5} | {res_gov['success_rate']:<6.1f} | {res_gov['catastrophes']:<6} | {res_gov['cvar_95']:<6.0f} | {res_gov['abstention_rate']:<6.1f} | {res_gov['dangerous_block_rate']:<12.1f}")
        print("-" * 80)


if __name__ == "__main__":
    run_experiment_suite()

