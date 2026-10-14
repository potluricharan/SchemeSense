import sys
from core.db import get_store, schemes_for_state
from core.profile_schema import sample_profile
from core.optimizer import optimize_schemes
import json

def test_opt():
    store = get_store()
    schemes = store.list_schemes()
    if not schemes:
        print("No verified schemes found.")
        return
    
    prof = sample_profile()
    # Filter for the state
    valid_schemes = schemes_for_state(prof["state"], schemes)
    print(f"Testing optimizer for {prof['family_name']} with {len(valid_schemes)} valid schemes.")
    
    res = optimize_schemes(valid_schemes, prof)
    
    print("Optimizer status:", res["status"], res["solver_status"])
    print("Total benefit:", res["total_benefit"])
    print("Chosen schemes:")
    for c in res["chosen"]:
        print(f" - {c['member_name']} -> {c['name']} (Benefit: {c['benefit']})")
        
    print("Done")

if __name__ == "__main__":
    test_opt()
