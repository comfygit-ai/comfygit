"""Shared config comparison functions for pyproject.toml diffing.

These pure functions are used by both GitChangeParser (HEAD vs working tree)
and RefDiffAnalyzer (any ref vs any ref) to avoid code duplication.
"""


def flatten_nodes(nodes_config: dict) -> dict:
    """Flatten nodes config, handling legacy 'development' section.

    Args:
        nodes_config: The nodes section from [tool.comfygit.nodes]

    Returns:
        Flat dict mapping node keys to their config dicts
    """
    flat = {}
    for key, value in nodes_config.items():
        if key == "development" and isinstance(value, dict):
            # Legacy development section - flatten nested nodes
            for dev_key, dev_value in value.items():
                if isinstance(dev_value, dict):
                    flat[dev_key] = dev_value
        elif isinstance(value, dict) and "name" in value:
            # Regular node entry
            flat[key] = value
    return flat


def extract_nodes_section(config: dict) -> dict:
    """Extract [tool.comfygit.nodes] section from config.

    Args:
        config: Full pyproject.toml config dict

    Returns:
        Nodes section dict or empty dict if missing
    """
    return config.get("tool", {}).get("comfygit", {}).get("nodes", {})


def extract_models_section(config: dict) -> dict:
    """Extract [tool.comfygit.models] section from config.

    Args:
        config: Full pyproject.toml config dict

    Returns:
        Models section dict or empty dict if missing
    """
    return config.get("tool", {}).get("comfygit", {}).get("models", {})


def compare_node_configs(old_config: dict, new_config: dict) -> dict:
    """Compare node sections between two configs.

    Args:
        old_config: Previous pyproject.toml config
        new_config: Current pyproject.toml config

    Returns:
        Dict with 'nodes_added' and 'nodes_removed' lists
    """
    old_nodes = flatten_nodes(extract_nodes_section(old_config))
    new_nodes = flatten_nodes(extract_nodes_section(new_config))

    old_keys = set(old_nodes.keys())
    new_keys = set(new_nodes.keys())

    nodes_added = []
    for key in new_keys - old_keys:
        node_data = new_nodes[key]
        nodes_added.append({
            "name": node_data.get("name", key),
            "is_development": node_data.get("version") == "dev",
        })

    nodes_removed = []
    for key in old_keys - new_keys:
        node_data = old_nodes[key]
        nodes_removed.append({
            "name": node_data.get("name", key),
            "is_development": node_data.get("version") == "dev",
        })

    return {"nodes_added": nodes_added, "nodes_removed": nodes_removed}


def compare_constraint_configs(old_config: dict, new_config: dict) -> dict:
    """Compare UV constraint dependencies between configs.

    Args:
        old_config: Previous pyproject.toml config
        new_config: Current pyproject.toml config

    Returns:
        Dict with 'constraints_added' and 'constraints_removed' lists
    """
    old_constraints = set(
        old_config.get("tool", {}).get("uv", {}).get("constraint-dependencies", [])
    )
    new_constraints = set(
        new_config.get("tool", {}).get("uv", {}).get("constraint-dependencies", [])
    )

    return {
        "constraints_added": list(new_constraints - old_constraints),
        "constraints_removed": list(old_constraints - new_constraints),
    }
