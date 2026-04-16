from typing import List, Dict, Any

def validate_required_keys(config):
    """Check that mandatory attributes exist and have the correct type."""
    required_keys = ["assistants", "topology", "turns"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Configuration Error: Missing mandatory attribute '{key}' in interaction file.")
            
    if not isinstance(config["assistants"], list):
        raise ValueError("Configuration Error: 'assistants' must be a list.")
    if not isinstance(config["topology"], dict):
        raise ValueError("Configuration Error: 'topology' must be a dictionary.")
    if not isinstance(config["turns"], (list, dict)):
        raise ValueError("Configuration Error: 'turns' must be a list or a dictionary.")

def validate_topology(assistants, topology):
    """Check that the topology uses valid names and prevents duplicate edges or self-references."""
    assistants_set = set(assistants)
    for node, edges in topology.items():
        if node not in assistants_set:
            raise ValueError(f"Configuration Error: Source node '{node}' in 'topology' does not exist in 'assistants'.")
            
        # len(set(edges)) removes duplicates. If length changes, there were duplicates.
        if len(edges) != len(set(edges)):
            raise ValueError(f"Configuration Error: Duplicate edges detected for node '{node}' in 'topology'.")
            
        for edge in edges:
            if edge not in assistants_set:
                raise ValueError(f"Configuration Error: Target node '{edge}' in 'topology' does not exist in 'assistants'.")
            if edge == node:
                raise ValueError(f"Configuration Error: Node '{node}' cannot point to itself in 'topology'.")

def validate_turns(assistants, turns, n_iterations):
    """Check the format of the turns, ensure rounds match exactly 0 to N, and no duplicates exist."""
    assistants_set = set(assistants)
    rounds_to_check = []
    
    if isinstance(turns, dict):
        # Rounds must go strictly from 0 to n_iterations (inclusive)
        expected_rounds = n_iterations + 1
        actual_keys = set(turns.keys())
        expected_keys = {str(i) for i in range(expected_rounds)}
        
        missing_keys = expected_keys - actual_keys
        if missing_keys:
            raise ValueError(f"Configuration Error: Missing turns for rounds {missing_keys}. Expected exactly 0 to {n_iterations}.")
            
        extra_keys = actual_keys - expected_keys
        if extra_keys:
            raise ValueError(f"Configuration Error: Invalid or extra rounds detected {extra_keys}. Expected exactly 0 to {n_iterations}.")
            
        for i in range(expected_rounds):
            rounds_to_check.append(turns[str(i)])
            
    elif isinstance(turns, list):
        # Same turns for all rounds
        rounds_to_check.append(turns)

    for current_round_turns in rounds_to_check:
        if not isinstance(current_round_turns, list):
            raise ValueError("Configuration Error: Turns for a round must be a list of lists.")
            
        seen_in_round = set()
        for group in current_round_turns:
            if not isinstance(group, list):
                raise ValueError("Configuration Error: Each turn must be a list of assistants.")
                
            for node in group:
                if node not in assistants_set:
                    raise ValueError(f"Configuration Error: Node '{node}' in 'turns' is not listed in 'assistants'.")
                if node in seen_in_round:
                    raise ValueError(f"Configuration Error: Node '{node}' speaks more than once in the same round.")
                seen_in_round.add(node)

def validate_interaction_file(config, n_iterations):
    """Main entry point for file validation."""
    validate_required_keys(config)
    
    assistants = config["assistants"]
    topology = config["topology"]
    turns = config["turns"]

    validate_topology(assistants, topology)
    validate_turns(assistants, turns, n_iterations)