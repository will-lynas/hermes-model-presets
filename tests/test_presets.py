"""Behavioral tests through the public plugin registration boundary."""

from collections import UserString
from dataclasses import dataclass
from typing import Never, Protocol

import pytest

import __init__ as plugin


class Configuration(Protocol):
    """A readable settings source, including sources that raise on access."""

    def get(self, key: str, default: object, /) -> object: ...


class PluginContext:
    """Only the two public APIs this plugin is allowed to use."""

    __slots__ = ("settings", "hooks")

    def __init__(self, settings: Configuration) -> None:
        self.settings = settings
        self.hooks: dict[str, plugin.GatewayHook] = {}

    def get_config(self, key: str, default: object = None) -> object:
        return self.settings.get(key, default)

    def register_hook(self, name: str, callback: plugin.GatewayHook) -> None:
        if name in self.hooks:
            raise AssertionError("duplicate hook")
        self.hooks[name] = callback


@dataclass(slots=True)
class Event:
    text: object


@dataclass(slots=True)
class RegisteredPlugin:
    preset: dict[str, object]
    aliases: dict[str, object]
    settings: dict[str, object]
    context: PluginContext
    callback: plugin.GatewayHook

    def dispatch(self, text: object) -> plugin.Rewrite | None:
        event = Event(text=text)
        result = self.callback(event=event)
        assert event.text == text, "the plugin must not mutate the event"
        return result


@pytest.fixture
def registered() -> RegisteredPlugin:
    preset: dict[str, object] = {"model": "fixture-model", "provider": "fixture-provider"}
    aliases: dict[str, object] = {"deep": preset}
    settings: dict[str, object] = {"aliases": aliases}
    context = PluginContext(settings)
    plugin.register(context)
    assert set(context.hooks) == {"pre_gateway_dispatch"}
    return RegisteredPlugin(
        preset, aliases, settings, context, context.hooks["pre_gateway_dispatch"]
    )


def test_exact_alias_expands_model_and_provider_with_session_scope(
    registered: RegisteredPlugin,
) -> None:
    assert registered.dispatch("/model deep") == {
        "action": "rewrite",
        "text": "/model fixture-model --provider fixture-provider --session",
    }


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param("ordinary deep", id="ordinary-text"),
        pytest.param("/model", id="no-argument"),
        pytest.param("/model ", id="blank-argument"),
        pytest.param("/model missing", id="unknown-alias"),
        pytest.param("/model Deep", id="alias-case-mismatch"),
        pytest.param("/model deeper", id="alias-prefix"),
        pytest.param("/model deep-ish", id="alias-suffix"),
        pytest.param("/m deep", id="abbreviated-command"),
        pytest.param("/models deep", id="plural-command"),
        pytest.param("/MODEL deep", id="command-case-mismatch"),
        pytest.param("say /model deep", id="embedded-command"),
        pytest.param("/model deep extra", id="extra-target"),
        pytest.param("/model 'deep'", id="single-quoted-alias"),
        pytest.param('/model "deep"', id="double-quoted-alias"),
        pytest.param("/model deep\n/model deep", id="multiple-commands"),
    ],
)
def test_non_exact_commands_are_unchanged(registered: RegisteredPlugin, text: str) -> None:
    assert registered.dispatch(text) is None


@pytest.mark.parametrize(
    "effort", ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
)
def test_optional_reasoning_is_in_the_same_rewrite(
    registered: RegisteredPlugin, effort: str
) -> None:
    registered.preset["reasoning_effort"] = effort
    assert registered.dispatch("/model deep") == {
        "action": "rewrite",
        "text": f"/model fixture-model --provider fixture-provider --reasoning {effort} --session",
    }


@pytest.mark.parametrize("key", ("model", "provider"))
@pytest.mark.parametrize(
    "value",
    [
        pytest.param("two words", id="embedded-space"),
        pytest.param("", id="empty"),
        pytest.param(" leading", id="leading-space"),
        pytest.param("trailing ", id="trailing-space"),
        pytest.param("tab\tvalue", id="tab"),
        pytest.param("new\nline", id="newline"),
        pytest.param("carriage\rreturn", id="carriage-return"),
        pytest.param("nul\0value", id="nul"),
        pytest.param("delete\x7f", id="delete"),
        pytest.param("escape\x1b", id="escape"),
        pytest.param("c1\x85", id="c1-control"),
        pytest.param("hidden\u200b", id="zero-width-space"),
        pytest.param("bidi\u202e", id="bidi-control"),
        pytest.param("space\u00a0value", id="nonbreaking-space"),
        pytest.param("--global", id="long-flag"),
        pytest.param("-flag", id="short-flag"),
        pytest.param("\u2012global", id="figure-dash"),
        pytest.param("\u2013global", id="en-dash"),
        pytest.param("\u2014global", id="em-dash"),
        pytest.param("\u2015global", id="horizontal-bar"),
        pytest.param("\u2212flag", id="minus-sign"),
        pytest.param(None, id="null"),
        pytest.param(False, id="boolean"),
        pytest.param(0, id="integer"),
        pytest.param([], id="list"),
        pytest.param({}, id="map"),
    ],
)
def test_unsafe_preset_values_fail_open(
    registered: RegisteredPlugin, key: str, value: object
) -> None:
    valid = {"model": "fixture-model", "provider": "fixture-provider"}
    registered.aliases["deep"] = {**valid, key: value}
    assert registered.dispatch("/model deep") is None


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("invalid", id="unknown-effort"),
        pytest.param("", id="empty"),
        pytest.param("HIGH", id="uppercase"),
        pytest.param("high --global", id="flag-injection"),
        pytest.param(UserString("high"), id="non-string-wrapper"),
        pytest.param(None, id="null"),
        pytest.param(False, id="boolean"),
        pytest.param(0, id="integer"),
        pytest.param([], id="list"),
        pytest.param({}, id="map"),
    ],
)
def test_invalid_configured_reasoning_fails_open(
    registered: RegisteredPlugin, value: object
) -> None:
    registered.preset["reasoning_effort"] = value
    assert registered.dispatch("/model deep") is None


@pytest.mark.parametrize(
    "aliases",
    [
        pytest.param(None, id="null-aliases"),
        pytest.param(False, id="boolean-aliases"),
        pytest.param(7, id="integer-aliases"),
        pytest.param("not-a-map", id="string-aliases"),
        pytest.param([], id="list-aliases"),
        pytest.param({}, id="empty-aliases"),
        pytest.param({"deep": None}, id="null-preset"),
        pytest.param({"deep": []}, id="list-preset"),
        pytest.param({"deep": "not-a-preset"}, id="string-preset"),
        pytest.param({"deep": {}}, id="empty-preset"),
        pytest.param({"deep": {"model": "fixture-model"}}, id="missing-provider"),
        pytest.param({"deep": {"provider": "fixture-provider"}}, id="missing-model"),
    ],
)
def test_malformed_configuration_fails_open(registered: RegisteredPlugin, aliases: object) -> None:
    registered.settings["aliases"] = aliases
    assert registered.dispatch("/model deep") is None


def test_missing_configuration_fails_open(registered: RegisteredPlugin) -> None:
    registered.settings.clear()
    assert registered.dispatch("/model deep") is None


@pytest.mark.parametrize(
    ("text", "flags"),
    [
        pytest.param("/model --global deep", "--global", id="global-before-alias"),
        pytest.param("/model deep --global", "--global", id="global-after-alias"),
        pytest.param("/model --session deep", "--session", id="session-before-alias"),
        pytest.param("/model deep --session", "--session", id="session-after-alias"),
        pytest.param("/model --refresh deep", "--refresh --session", id="refresh-before-alias"),
        pytest.param("/model deep --refresh", "--refresh --session", id="refresh-after-alias"),
        pytest.param(
            "/model --global deep --session --refresh",
            "--global --session --refresh",
            id="global-then-session-and-refresh",
        ),
        pytest.param(
            "/model --session --refresh deep --global",
            "--session --refresh --global",
            id="session-and-refresh-then-global",
        ),
        pytest.param("/model deep --global --global", "--global --global", id="repeated-global"),
    ],
)
def test_boolean_flags_keep_the_requested_scope_and_refresh(
    registered: RegisteredPlugin, text: str, flags: str
) -> None:
    assert registered.dispatch(text) == {
        "action": "rewrite",
        "text": f"/model fixture-model --provider fixture-provider {flags}",
    }


@pytest.mark.parametrize(
    ("text", "provider", "effort"),
    [
        pytest.param(
            "/model deep --provider override-provider",
            "override-provider",
            "high",
            id="provider-after-alias",
        ),
        pytest.param(
            "/model --provider override-provider deep",
            "override-provider",
            "high",
            id="provider-before-alias",
        ),
        pytest.param(
            "/model deep --reasoning low", "fixture-provider", "low", id="effort-after-alias"
        ),
        pytest.param(
            "/model --reasoning low deep", "fixture-provider", "low", id="effort-before-alias"
        ),
        pytest.param(
            "/model deep --reasoning HIGH", "fixture-provider", "HIGH", id="uppercase-effort"
        ),
        pytest.param(
            "/model --provider earlier-provider --reasoning max deep"
            " --reasoning none --provider final-provider",
            "final-provider",
            "none",
            id="last-provider-and-effort-win",
        ),
        pytest.param(
            "/model --reasoning invalid deep --reasoning ultra",
            "fixture-provider",
            "ultra",
            id="last-effort-rescues-earlier-invalid-flag",
        ),
    ],
)
def test_explicit_provider_and_reasoning_use_last_flag_wins(
    registered: RegisteredPlugin, text: str, provider: str, effort: str
) -> None:
    registered.preset["reasoning_effort"] = "high"
    assert registered.dispatch(text) == {
        "action": "rewrite",
        "text": f"/model fixture-model --provider {provider} --reasoning {effort} --session",
    }


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("/model deep --provider", id="missing-provider-value"),
        pytest.param("/model deep --reasoning", id="missing-effort-value"),
        pytest.param("/model --provider", id="provider-without-value-or-alias"),
        pytest.param("/model --reasoning", id="reasoning-without-value-or-alias"),
        pytest.param("/model --refresh", id="refresh-without-alias"),
        pytest.param("/model deep --provider --global", id="provider-is-global-flag"),
        pytest.param("/model deep --reasoning --session", id="effort-is-session-flag"),
        pytest.param(
            "/model deep --provider --provider final-provider", id="provider-is-provider-flag"
        ),
        pytest.param("/model deep --reasoning invalid", id="invalid-effort"),
        pytest.param(
            "/model deep --reasoning high --reasoning invalid", id="last-effort-is-invalid"
        ),
        pytest.param("/model deep --provider bad\0value", id="provider-contains-nul"),
        pytest.param(
            "/model deep --provider hidden\u200bvalue", id="provider-contains-zero-width-space"
        ),
        pytest.param("/model deep --provider -bad", id="provider-is-short-flag"),
        pytest.param("/model deep --provider \u2014global", id="provider-is-unicode-flag"),
        pytest.param("/model deep --reasoning high --unknown", id="unknown-flag-after-effort"),
        pytest.param("/model deep --unknown value", id="unknown-flag-with-value"),
        pytest.param("/model deep --provider=fixture-provider", id="provider-equals-form"),
        pytest.param("/model deep --global=true", id="global-equals-form"),
        pytest.param(
            "/model --provider fixture-provider deep extra", id="provider-with-extra-target"
        ),
        pytest.param("/model deep deep --session", id="repeated-target"),
        pytest.param("/model deep --", id="end-of-options"),
        pytest.param("/model deep -p fixture-provider", id="short-provider-flag"),
        pytest.param("/model deep --GLOBAL", id="uppercase-global"),
        pytest.param("/model --once deep", id="once-before-alias"),
        pytest.param("/model deep --once", id="once-after-alias"),
        pytest.param("/model deep --reasoning high --once", id="once-with-effort"),
    ],
)
def test_malformed_flags_fail_open_without_dropping_any_tokens(
    registered: RegisteredPlugin, text: str
) -> None:
    assert registered.dispatch(text) is None


@pytest.mark.parametrize(
    "alias",
    [
        pytest.param("--once", id="once-flag"),
        pytest.param("--unknown", id="unknown-flag"),
        pytest.param("-p", id="short-flag"),
        pytest.param("\u2014global", id="unicode-flag"),
        pytest.param("deep\0value", id="nul"),
    ],
)
def test_unsafe_aliases_fail_open(registered: RegisteredPlugin, alias: str) -> None:
    registered.aliases[alias] = registered.preset
    assert registered.dispatch(f"/model {alias}") is None


def test_unreadable_configuration_fails_open_without_exposing_it(
    registered: RegisteredPlugin,
) -> None:
    class UnreadableConfiguration:
        def get(self, key: str, default: object = None, /) -> Never:
            raise ValueError("fixture-config-error")

    registered.context.settings = UnreadableConfiguration()
    assert registered.dispatch("/model deep") is None


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(None, id="null"),
        pytest.param(b"/model deep", id="bytes"),
        pytest.param(7, id="integer"),
        pytest.param([], id="list"),
        pytest.param({}, id="map"),
    ],
)
def test_non_text_events_are_unchanged(registered: RegisteredPlugin, text: object) -> None:
    assert registered.dispatch(text) is None


@pytest.mark.parametrize(
    "dash",
    [
        pytest.param("\u2012", id="figure-dash"),
        pytest.param("\u2013", id="en-dash"),
        pytest.param("\u2014", id="em-dash"),
        pytest.param("\u2015", id="horizontal-bar"),
    ],
)
@pytest.mark.parametrize(
    "flag",
    [
        pytest.param("global", id="global"),
        pytest.param("session", id="session"),
        pytest.param("refresh", id="refresh"),
        pytest.param("once", id="once"),
        pytest.param("provider override-provider", id="provider"),
        pytest.param("reasoning low", id="reasoning"),
    ],
)
@pytest.mark.parametrize("before_alias", [True, False], ids=["before-alias", "after-alias"])
def test_unicode_dash_flags_pass_through_unchanged(
    registered: RegisteredPlugin, dash: str, flag: str, before_alias: bool
) -> None:
    text = f"/model {dash}{flag} deep" if before_alias else f"/model deep {dash}{flag}"
    assert registered.dispatch(text) is None


def test_current_configuration_is_read_without_mutating_it(registered: RegisteredPlugin) -> None:
    assert registered.dispatch("/model deep") is not None
    replacement = {
        "aliases": {
            "deep": {
                "model": "vendor/fixture-model:2.1",
                "provider": "fixture-provider-2",
                "reasoning_effort": "low",
            },
            "unselected": {"model": "bad config value"},
        }
    }
    registered.context.settings = replacement
    assert registered.dispatch("/model deep") == {
        "action": "rewrite",
        "text": "/model vendor/fixture-model:2.1 --provider fixture-provider-2"
        " --reasoning low --session",
    }
    assert replacement["aliases"]["deep"] == {
        "model": "vendor/fixture-model:2.1",
        "provider": "fixture-provider-2",
        "reasoning_effort": "low",
    }
    registered.context.settings = {"aliases": {}}
    assert registered.dispatch("/model deep") is None


def test_alias_matching_is_case_sensitive_without_normalization(
    registered: RegisteredPlugin,
) -> None:
    registered.aliases["Deep"] = {
        "model": "other-fixture-model",
        "provider": "other-fixture-provider",
    }
    assert registered.dispatch("/model Deep") == {
        "action": "rewrite",
        "text": "/model other-fixture-model --provider other-fixture-provider --session",
    }
    assert registered.dispatch("/model DEEP") is None
    result = registered.dispatch("/model deep")
    assert result is not None
    assert "/model fixture-model " in result["text"]


@pytest.mark.parametrize(
    "preset",
    [
        pytest.param({"model": "fixture-model"}, id="missing-provider"),
        pytest.param({"model": "fixture-model", "provider": "bad provider"}, id="unsafe-provider"),
        pytest.param(
            {
                "model": "fixture-model",
                "provider": "fixture-provider",
                "reasoning_effort": "invalid",
            },
            id="invalid-effort",
        ),
    ],
)
def test_overrides_do_not_rescue_invalid_presets(
    registered: RegisteredPlugin, preset: dict[str, object]
) -> None:
    registered.aliases["deep"] = preset
    assert registered.dispatch("/model deep --provider override-provider --reasoning low") is None


def test_hook_ignores_all_other_gateway_arguments(registered: RegisteredPlugin) -> None:
    event = Event(text="/model deep")
    assert registered.callback(
        event=event, gateway=object(), session_store=object()
    ) == registered.dispatch("/model deep")
    assert event.text == "/model deep"
