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
    topology_keys = set(topology.keys())

    if topology_keys != assistants_set:
        missing = assistants_set - topology_keys
        extra = topology_keys - assistants_set
        msg = "Configuration Error: 'topology' must contain exactly all assistants."
        if missing:
            msg += f" Missing: {missing}."
        if extra:
            msg += f" Extra: {extra}."
        raise ValueError(msg)

    for node, edges in topology.items():
            
        # len(set(edges)) removes duplicates. If length changes, there were duplicates.
        if len(edges) != len(set(edges)):
            raise ValueError(f"Configuration Error: Duplicate edges detected for node '{node}' in 'topology'.")
        
        if not edges:
            raise ValueError(f"Configuration Error: Node '{node}' in 'topology' must point to at least one node, but its edge list is empty.")
            
        for edge in edges:
            if edge not in assistants_set:
                raise ValueError(f"Configuration Error: Target node '{edge}' in 'topology' does not exist in 'assistants'.")
            if edge == node:
                raise ValueError(f"Configuration Error: Node '{node}' cannot point to itself in 'topology'.")

def validate_turns(interaction_config):
    """Check the format of the turns, ensure rounds are correct, and no duplicates exist."""
    assistants_set = set(interaction_config.get("assistants", []))
    turns = interaction_config.get("turns", [])
    rounds_to_check = []
    
    if isinstance(turns, dict):
        n_iterations = len(turns) - 1
        expected_keys = {str(i) for i in range(n_iterations + 1)}
        actual_keys = set(turns.keys())
        
        if actual_keys != expected_keys:
            raise ValueError(f"Configuration Error: Keys in 'turns' dict must go strictly from 0 to {n_iterations}. Found: {actual_keys}. Expected: {expected_keys}")

        if actual_keys == set():
            raise ValueError(f"Configuration Error: 'turns' dict cannot be empty. It must contain at least one round with key '0'.")

        for i in range(n_iterations + 1):
            rounds_to_check.append(turns[str(i)])
            
    elif isinstance(turns, list):
        if "number_of_rounds" not in interaction_config:
            raise ValueError("Configuration Error: 'number_of_rounds' must be specified in the JSON when 'turns' is a not a dictionary.")
        
        number_of_rounds = interaction_config["number_of_rounds"]
        if not isinstance(number_of_rounds, int) or number_of_rounds - 1 < 0:
            raise ValueError("Configuration Error: 'number_of_rounds' must be greater than 0.")
            
        rounds_to_check.append(turns)


    for current_round_turns in rounds_to_check:
        if not isinstance(current_round_turns, list):
            raise ValueError("Configuration Error: Turns for a round must be a list of lists.")
        
        if not current_round_turns:
            raise ValueError("Configuration Error: A round must contain at least one turn (the list of turns cannot be empty).")
            
        seen_in_round = set()
        for group in current_round_turns:
            if not isinstance(group, list):
                raise ValueError("Configuration Error: Each turn must be a list of assistants.")
            
            if not group:
                raise ValueError("Configuration Error: A turn cannot be empty (must contain at least one assistant).")
                
            for node in group:
                if node not in assistants_set:
                    raise ValueError(f"Configuration Error: Node '{node}' in 'turns' is not listed in 'assistants'.")
                if node in seen_in_round:
                    raise ValueError(f"Configuration Error: Node '{node}' speaks more than once in the same round.")
                seen_in_round.add(node)

def validate_interaction_file(config):
    """Main entry point for file validation."""
    validate_required_keys(config)
    
    assistants = config["assistants"]
    topology = config["topology"]

    validate_topology(assistants, topology)
    validate_turns(config)