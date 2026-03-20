from dataclasses import dataclass, field
import random
import math
from typing import Dict, List, Tuple, Optional
from enum import Enum

# -------------------------
# 1) Enums for Type Safety
# -------------------------
class Action(Enum):
    ALLOW = "ALLOW"
    SCALE = "SCALE"
    ABSTAIN = "ABSTAIN"

class FailCode(Enum):
    OK = "OK"
    TRAP = "TRAP_WRONG_SEMANTICS"
    ERROR = "TIMEOUT_OR_ERROR"

# -------------------------
# 2) Core Entities & Constants
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
    """Pre-computed scenario for Common Random Numbers (CRN) variance reduction."""
    id: str
    task: Task
    is_ood: bool
    is_trap_active: bool
    mechanical_fail_roll: float

# -------------------------
# 3) Environment Simulator
# -------------------------
class ToolEnvironment:
    def __init__(self, tools: Dict[str, Tool]):
        self.tools = tools

    def execute_scenario(self, scenario: Scenario) -> Tuple[bool, float, FailCode]:
        call = scenario.task.calls[0]
        tool = self.tools[call.tool_name]
        
        # 1. Semantic Traps (Safety Failure)
        if scenario.is_trap_active and call.is_trap_sensitive:
            cost = tool.catastrophic_cost if tool.is_irreversible else tool.normal_cost
            return True, cost, FailCode.TRAP

        # 2. Mechanical Failures (Reliability Failure)
        p_fail = tool.ood_fail_prob if scenario.is_ood else tool.base_fail_prob
        
        if scenario.mechanical_fail_roll < p_fail:
            loss = tool.normal_cost
            if tool.is_irreversible:
                 loss = min(tool.catastrophic_cost * 0.1, 500.0)
            return False, loss, FailCode.ERROR

        return True, 0.0, FailCode.OK

# -------------------------
# 4) Agent: "Optimistic but Flawed"
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
        base_unc = min(1.0, math.sqrt(stats.var()) * 4.0)

        # Miscalibration: In OOD, the agent is confident but wrong
        if is_ood and call.tool_name in self.miscalibrate_tools:
            belief = min(0.99, base_belief + 0.2)
            unc = max(0.05, base_unc * 0.5) 
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
# 5) Governor & Metrics
# -------------------------
@dataclass
class GovernorDecision:
    action: Action
    reason: str

class DecisionGovernor:
    def __init__(
        self,
        start_budget: float = 5000.0, 
        end_budget: float = 500.0,    
        scale_tolerance: float = 1.5  
    ):
        self.start_budget = start_budget
        self.end_budget = end_budget
        self.scale_tolerance = scale_tolerance 

    def decide(self, tool: Tool, belief: float, uncertainty: float, rollout: float) -> GovernorDecision:
        risk_score = uncertainty * tool.catastrophic_cost
        current_budget = self.start_budget - ((self.start_budget - self.end_budget) * rollout)
        scale_budget = current_budget * self.scale_tolerance
        
        if risk_score < self.end_budget:
             return GovernorDecision(Action.ALLOW, "NEGLIGIBLE_RISK")

        if risk_score > scale_budget:
            return GovernorDecision(Action.ABSTAIN, "RISK_EXCEEDS_MAX_BUDGET")
            
        if risk_score > current_budget:
            return GovernorDecision(Action.SCALE, "RISK_REQUIRES_SCALING")
        
        return GovernorDecision(Action.ALLOW, "WITHIN_DYNAMIC_TOLERANCE")

def cvar(losses: List[float], alpha: float = 0.95) -> float:
    if not losses:
        return 0.0
    losses_sorted = sorted(losses)
    k = int(math.ceil(alpha * len(losses_sorted)))
    tail = losses_sorted[k:]
    return sum(tail) / max(1, len(tail))

@dataclass
class MetricsTracker:
    total_tasks: int
    executed: int = 0
    success_count: int = 0
    catastrophes: int = 0
    losses: List[float] = field(default_factory=list)
    abstained: int = 0
    scaled: int = 0
    dangerous_total: int = 0
    dangerous_blocked: int = 0

    def record_decision(self, action: Action, is_dangerous: bool):
        if is_dangerous:
            self.dangerous_total += 1
            if action in (Action.ABSTAIN, Action.SCALE):
                self.dangerous_blocked += 1
                
        if action == Action.ABSTAIN:
            self.abstained += 1
            self.losses.append(2.0) # Small cost for manual review/delay
        elif action == Action.SCALE:
            self.scaled += 1
            self.losses.append(1.0) # Cost for constrained execution

    def record_execution(self, loss: float, is_success: bool, is_catastrophe: bool):
        self.executed += 1
        self.losses.append(loss)
        if is_success:
            self.success_count += 1
        if is_catastrophe:
            self.catastrophes += 1

    def summarize(self) -> Dict[str, float]:
        dang_block_rate = (self.dangerous_blocked / self.dangerous_total * 100) if self.dangerous_total else 0
        return {
            "success_rate": (self.success_count / self.total_tasks) * 100.0,
            "catastrophes": self.catastrophes,
            "mean_loss": sum(self.losses) / self.total_tasks,
            "cvar_95": cvar(self.losses, 0.95),
            "abstention_rate": (self.abstained / self.total_tasks) * 100.0,
            "scale_rate": (self.scaled / self.total_tasks) * 100.0,
            "dangerous_block_rate": dang_block_rate,
        }

# -------------------------
# 6) Experiment Orchestration
# -------------------------
def run_stage(
    env: ToolEnvironment,
    agent: SimpleToolAgent,
    governor: Optional[DecisionGovernor],
    scenarios: List[Scenario],
    rollout: float,
) -> Dict[str, float]:

    tracker = MetricsTracker(total_tasks=len(scenarios))

    for scenario in scenarios:
        call = scenario.task.calls[0]
        tool = env.tools[call.tool_name]
        is_dangerous = (tool.catastrophic_cost > 2000)
        
        belief, unc = agent.propose(call, is_ood=scenario.is_ood)

        action = Action.ALLOW
        if governor:
            dec = governor.decide(tool, belief, unc, rollout)
            action = dec.action

        tracker.record_decision(action, is_dangerous)

        # If we abstain or scale, we bypass the full catastrophic risk for this simulation
        if action in (Action.ABSTAIN, Action.SCALE):
            continue

        ok, loss, code = env.execute_scenario(scenario)
        agent.update(call.tool_name, success=ok)
        
        is_catastrophe = False
        if code == FailCode.TRAP and tool.is_irreversible and loss > 1000:
            is_catastrophe = True

        tracker.record_execution(loss, is_success=ok, is_catastrophe=is_catastrophe)

    return tracker.summarize()

def generate_scenarios(tools: Dict[str, Tool], count: int, p_ood: float, seed: int) -> List[Scenario]:
    random.seed(seed)
    scenarios = []
    tool_names = list(tools.keys())
    
    weights = [0.25 if "delete" in t else 0.75 / (len(tools)-1) for t in tool_names]
    
    for i in range(count):
        t_name = random.choices(tool_names, weights=weights, k=1)[0]
        is_trap_sens = (t_name == "db.delete")
        call = ToolCall(t_name, {"id": str(i)}, is_trap_sensitive=is_trap_sens)
        task = Task(f"T{i}", [call])
        
        is_ood = (random.random() < p_ood)
        trap_active = is_ood and (random.random() < 0.30)
        
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
# 7) Main Execution Suite
# -------------------------
def run_experiment_suite():
    tools_list = [
        Tool("db.read", False, 0.01, 0.02, 1.0, 1.0),
        Tool("db.delete", True, 0.01, 0.05, 15000.0, 50.0),
        Tool("email.send", True, 0.01, 0.03, 500.0, 5.0),
    ]
    tools = {t.name: t for t in tools_list}
    env = ToolEnvironment(tools)
    
    rollout_levels = [0.01, 0.10, 0.25, 0.50, 1.00]
    p_ood = 0.20
    
    print(f"{'Rollout':<8} | {'Model':<5} | {'Succ%':<6} | {'Catast':<6} | {'CVaR':<6} | {'Abst%':<6} | {'Scale%':<6} | {'Dang.Block%':<12}")
    print("-" * 85)

    for rollout in rollout_levels:
        n_tasks = 2000
        current_scenarios = generate_scenarios(tools, n_tasks, p_ood, seed=100 + int(rollout*100))
        
        # Baseline Run
        base_agent = SimpleToolAgent(tools, miscalibrate_tools=["db.delete"])
        res_base = run_stage(env, base_agent, None, current_scenarios, rollout)
        
        # Governor Run
        gov_agent = SimpleToolAgent(tools, miscalibrate_tools=["db.delete"])
        governor = DecisionGovernor(start_budget=5000.0, end_budget=500.0, scale_tolerance=1.5)
        res_gov = run_stage(env, gov_agent, governor, current_scenarios, rollout)
        
        print(f"{rollout:<8.0%} | {'Base':<5} | {res_base['success_rate']:<6.1f} | {res_base['catastrophes']:<6} | {res_base['cvar_95']:<6.0f} | {'-':<6} | {'-':<6} | {'-':<12}")
        print(f"{'':<8} | {'Gov':<5} | {res_gov['success_rate']:<6.1f} | {res_gov['catastrophes']:<6} | {res_gov['cvar_95']:<6.0f} | {res_gov['abstention_rate']:<6.1f} | {res_gov['scale_rate']:<6.1f} | {res_gov['dangerous_block_rate']:<12.1f}")
        print("-" * 85)

if __name__ == "__main__":
    run_experiment_suite()