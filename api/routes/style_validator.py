"""
Style validation to ensure projects use correct models
"""

PROJECT_STYLE_RULES = {
    "tokyo_debt": {
        "required_checkpoint_contains": ["realisticVision", "photoreal"],
        "forbidden_checkpoint_contains": ["anime", "counterfeit", "AOM3"],
        "allowed_loras": ["mei_working_v1"],
        "style": "photorealistic"
    },
    "cyberpunk": {
        "required_checkpoint_contains": ["counterfeit", "animagine", "anything"],
        "forbidden_checkpoint_contains": ["realisticVision", "photoreal"],
        "allowed_loras": ["arcane_offset", "arcane"],
        "style": "stylized_anime"
    },
    "goblin_slayer": {
        "required_checkpoint_contains": ["counterfeit", "AOM3", "animagine"],
        "forbidden_checkpoint_contains": ["realisticVision", "photoreal"],
        "allowed_loras": ["arcane_offset"],
        "style": "stylized_anime"
    }
}

def validate_project_style(project_name: str, checkpoint: str, lora: str = None) -> bool:
    """
    Ensure projects use correct style models
    Raises ValueError if validation fails
    """
    # Normalize project name
    project_lower = project_name.lower()

    # Find matching rule
    matching_rule = None
    for rule_key in PROJECT_STYLE_RULES:
        if rule_key in project_lower:
            matching_rule = PROJECT_STYLE_RULES[rule_key]
            break

    if not matching_rule:
        return True  # Unknown project, no validation

    rules = matching_rule
    checkpoint_lower = checkpoint.lower() if checkpoint else ""

    # Check required checkpoint patterns
    if rules.get("required_checkpoint_contains"):
        found_required = False
        for required in rules["required_checkpoint_contains"]:
            if required.lower() in checkpoint_lower:
                found_required = True
                break

        if not found_required:
            raise ValueError(
                f"Project '{project_name}' requires checkpoint containing one of {rules['required_checkpoint_contains']}, "
                f"but got '{checkpoint}'"
            )

    # Check forbidden checkpoint patterns
    if rules.get("forbidden_checkpoint_contains"):
        for forbidden in rules["forbidden_checkpoint_contains"]:
            if forbidden.lower() in checkpoint_lower:
                raise ValueError(
                    f"Project '{project_name}' cannot use checkpoint containing '{forbidden}', "
                    f"but got '{checkpoint}'"
                )

    # Check LoRA if specified
    if lora and rules.get("allowed_loras"):
        lora_lower = lora.lower()
        lora_ok = any(allowed.lower() in lora_lower for allowed in rules["allowed_loras"])
        if not lora_ok:
            raise ValueError(
                f"Project '{project_name}' requires LoRA from {rules['allowed_loras']}, "
                f"but got '{lora}'"
            )

    return True