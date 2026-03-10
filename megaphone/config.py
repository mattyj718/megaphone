"""Configuration loading and validation for Megaphone."""

import os
import yaml


DEFAULT_CONFIG_PATH = "config.yaml"

REQUIRED_KEYS = ["sources", "scoring"]


def load_config(path=None):
    """Load and validate config from YAML file. Returns a dict."""
    path = path or os.environ.get("MEGAPHONE_CONFIG", DEFAULT_CONFIG_PATH)
    with open(path) as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError(f"Config file is empty: {path}")

    for key in REQUIRED_KEYS:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")

    # Defaults
    config.setdefault("llm", {})
    config["llm"].setdefault("scoring_model", "gpt-5-mini")
    config["llm"].setdefault("drafting_model", "claude-sonnet-4-6")

    config["scoring"].setdefault("threshold", 6.0)
    config["scoring"].setdefault("topics", [])

    config.setdefault("gmail", {})

    return config
