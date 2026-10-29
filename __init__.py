"""Expand configured model aliases through the public gateway hook."""

import unicodedata
from collections.abc import Mapping
from typing import Literal, Protocol, TypedDict, TypeGuard

_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")


class GatewayEvent(Protocol):
    """The read-only event field used by the documented gateway hook."""

    @property
    def text(self) -> object: ...


class Rewrite(TypedDict):
    """A documented gateway rewrite directive."""

    action: Literal["rewrite"]
    text: str


class GatewayHook(Protocol):
    def __call__(self, event: GatewayEvent, **kwargs: object) -> Rewrite | None: ...


class PluginContext(Protocol):
    """Only the documented context methods consumed by this plugin."""

    def get_config(self, key: str, default: object = None) -> object: ...

    def register_hook(self, name: str, callback: GatewayHook) -> object: ...


def _is_config_dict(value: object) -> TypeGuard[Mapping[object, object]]:
    """Expose dictionary input read-only without assuming its keys or values."""
    return isinstance(value, dict)


def _safe_token(value: object) -> TypeGuard[str]:
    """Validate one native whitespace-delimited token without repairing it."""
    return (
        isinstance(value, str)
        and bool(value)
        and value[0] not in "-\u2212"
        and unicodedata.category(value[0]) != "Pd"
        and not any(char.isspace() or unicodedata.category(char).startswith("C") for char in value)
    )


def register(ctx: PluginContext) -> None:
    """Register a read-only, fail-open rewrite using current plugin settings."""

    def rewrite(event: GatewayEvent, **kwargs: object) -> Rewrite | None:
        if not isinstance(event.text, str):
            return None
        tokens = event.text.split()
        if not tokens or tokens[0] != "/model":
            return None
        flags: list[str] = []
        targets: list[str] = []
        overrides: dict[str, str] = {}
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
        if not _is_config_dict(aliases):
            return None
        preset = aliases.get(targets[0])
        if not _is_config_dict(preset):
            return None
        model = preset.get("model")
        configured_provider = preset.get("provider")
        if not _safe_token(model) or not _safe_token(configured_provider):
            return None
        configured_effort: object = None
        if "reasoning_effort" in preset:
            configured_effort = preset["reasoning_effort"]
            if not isinstance(configured_effort, str) or configured_effort not in _EFFORTS:
                return None
        provider = overrides.get("--provider", configured_provider)
        effort = overrides.get("--reasoning", configured_effort)
        if effort is not None and effort.lower() not in _EFFORTS:
            return None
        text = f"/model {model} --provider {provider}"
        if effort is not None:
            text += f" --reasoning {effort}"
        if "--global" not in flags and "--session" not in flags:
            flags.append("--session")
        return {"action": "rewrite", "text": " ".join([text, *flags])}

    ctx.register_hook("pre_gateway_dispatch", rewrite)
