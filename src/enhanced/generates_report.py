import csv
import os
from datetime import datetime
from typing import List, Dict, Any


from decision_governance_adv import (
    Tool, ToolEnvironment, SimpleToolAgent, DecisionGovernor, 
    generate_scenarios, run_stage
)

def collect_experiment_data() -> List[Dict[str, Any]]:
    """Runs the simulation suite and collects data into structured dictionaries."""
    tools_list = [
        Tool("db.read", False, 0.01, 0.02, 1.0, 1.0),
        Tool("db.delete", True, 0.01, 0.05, 15000.0, 50.0),
        Tool("email.send", True, 0.01, 0.03, 500.0, 5.0),
    ]
    tools = {t.name: t for t in tools_list}
    env = ToolEnvironment(tools)
    
    rollout_levels = [0.01, 0.10, 0.25, 0.50, 1.00]
    p_ood = 0.20
    results_data = []

    print("Running simulations and compiling data...")

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
        
        # Store Baseline Data
        results_data.append({
            "Rollout (%)": f"{rollout * 100:.0f}%",
            "Policy": "Accuracy-only (Baseline)",
            "Success Rate (%)": f"{res_base['success_rate']:.1f}",
            "Catastrophic Failures": res_base['catastrophes'],
            "CVaR (95%)": f"{res_base['cvar_95']:.0f}",
            "Abstention Rate (%)": "0.0",
            "Scale Rate (%)": "0.0"
        })

        # Store Governor Data
        results_data.append({
            "Rollout (%)": f"{rollout * 100:.0f}%",
            "Policy": "Decision Governor",
            "Success Rate (%)": f"{res_gov['success_rate']:.1f}",
            "Catastrophic Failures": res_gov['catastrophes'],
            "CVaR (95%)": f"{res_gov['cvar_95']:.0f}",
            "Abstention Rate (%)": f"{res_gov['abstention_rate']:.1f}",
            "Scale Rate (%)": f"{res_gov['scale_rate']:.1f}"
        })

    return results_data

def export_to_csv(data: List[Dict[str, Any]], filepath: str):
    """Exports the simulation data to a CSV file."""
    if not data:
        return
    
    keys = data[0].keys()
    with open(filepath, 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)
    print(f"✅ CSV report generated: {filepath}")

def export_to_markdown(data: List[Dict[str, Any]], filepath: str):
    """Exports the simulation data to a formatted Markdown file."""
    if not data:
        return

    headers = list(data[0].keys())
    
    with open(filepath, 'w') as md_file:
        md_file.write(f"# Simulation Results\n\n")
        md_file.write(f"*Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        # Write headers
        md_file.write("| " + " | ".join(headers) + " |\n")
        # Write separator
        md_file.write("|" + "|".join(["---"] * len(headers)) + "|\n")
        
        # Write rows
        for row in data:
            # Bold the Governor rows to make the improvements stand out
            if row["Policy"] == "Decision Governor":
                formatted_row = [f"**{str(row[h])}**" for h in headers]
            else:
                formatted_row = [str(row[h]) for h in headers]
            
            md_file.write("| " + " | ".join(formatted_row) + " |\n")
            
    print(f"✅ Markdown report generated: {filepath}")

if __name__ == "__main__":
    # Ensure the analysis directory exists
    os.makedirs(os.path.dirname(os.path.abspath(__file__)), exist_ok=True)
    
    data = collect_experiment_data()
    
    # Generate files in the current directory (assuming script is run from inside /analysis)
    csv_path = os.path.join(os.path.dirname(__file__), "results.csv")
    md_path = os.path.join(os.path.dirname(__file__), "results.md")
    
    export_to_csv(data, csv_path)
    export_to_markdown(data, md_path)
    
    print("\nAll reports successfully generated. You can now link these in your README.")