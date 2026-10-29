"""Expand configured model aliases through the public gateway hook."""

import unicodedata

_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")


def _safe_token(value):
    """Validate one native whitespace-delimited token without repairing it."""
    return (
        isinstance(value, str)
        and bool(value)
        and value[0] not in "-\u2212"
        and unicodedata.category(value[0]) != "Pd"
        and not any(char.isspace() or unicodedata.category(char).startswith("C")
                    for char in value)
    )


def register(ctx):
    """Register a read-only, fail-open rewrite using current plugin settings."""
    def rewrite(event, **kwargs):
        if not isinstance(event.text, str):
            return None
        tokens = event.text.split()
        if not tokens or tokens[0] != "/model":
            return None
        flags = []
        targets = []
        overrides = {}
        arguments = iter(tokens[1:])
        for token in arguments:
            if token in ("--global", "--session", "--refresh"):
                flags.append(token)
            elif token in ("--provider", "--reasoning"):
                value = next(arguments, None)
                if not _safe_token(value):
                    return None
                overrides[token] = value
            else:
                # Unsupported flags, including --once and Unicode dashes, pass through.
                if not _safe_token(token):
                    return None
                targets.append(token)
        if len(targets) != 1:
            return None
        try:
            aliases = ctx.get_config("aliases", {})
        except Exception:
            # Config loading failures must not expose configuration or interrupt ingress.
            return None
        if not isinstance(aliases, dict):
            return None
        preset = aliases.get(targets[0])
        if not isinstance(preset, dict):
            return None
        if not _safe_token(preset.get("model")) or not _safe_token(preset.get("provider")):
            return None
        if "reasoning_effort" in preset and preset["reasoning_effort"] not in _EFFORTS:
            return None
        provider = overrides.get("--provider", preset["provider"])
        effort = overrides.get("--reasoning", preset.get("reasoning_effort"))
        if effort is not None and effort.lower() not in _EFFORTS:
            return None
        text = f"/model {preset['model']} --provider {provider}"
        if effort is not None:
            text += f" --reasoning {effort}"
        if "--global" not in flags and "--session" not in flags:
            flags.append("--session")
        return {"action": "rewrite", "text": " ".join([text, *flags])}

    ctx.register_hook("pre_gateway_dispatch", rewrite)
