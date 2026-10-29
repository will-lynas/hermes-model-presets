"""Behavioral tests through the public plugin registration boundary."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest


def load_plugin():
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location("model_presets", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PluginContext:
    """Only the two public APIs this plugin is allowed to use."""

    __slots__ = ("settings", "hooks")

    def __init__(self, aliases):
        self.settings: Any = {"aliases": aliases}
        self.hooks = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, callback):
        if name in self.hooks:
            raise AssertionError("duplicate hook")
        self.hooks[name] = callback


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.context = PluginContext({
            "deep": {"model": "fixture-model", "provider": "fixture-provider"},
        })
        load_plugin().register(self.context)
        self.assertEqual(set(self.context.hooks), {"pre_gateway_dispatch"})
        self.callback = self.context.hooks["pre_gateway_dispatch"]

    def dispatch(self, text):
        event = SimpleNamespace(text=text)
        result = self.callback(event=event)
        self.assertEqual(event.text, text, "the plugin must not mutate the event")
        return result

    def test_exact_alias_expands_model_and_provider_with_session_scope(self):
        self.assertEqual(self.dispatch("/model deep"), {
            "action": "rewrite",
            "text": "/model fixture-model --provider fixture-provider --session",
        })

    def test_non_exact_commands_are_unchanged(self):
        for text in (
            "", "ordinary deep", "/model", "/model ", "/model missing",
            "/model Deep", "/model deeper", "/model deep-ish", "/m deep",
            "/models deep", "/MODEL deep", "say /model deep", "/model deep extra",
            "/model 'deep'", '/model "deep"', "/model deep\n/model deep",
        ):
            with self.subTest(text=text):
                self.assertIsNone(self.dispatch(text))

    def test_optional_reasoning_is_in_the_same_rewrite(self):
        for effort in ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"):
            with self.subTest(effort=effort):
                self.context.settings["aliases"]["deep"]["reasoning_effort"] = effort
                self.assertEqual(self.dispatch("/model deep"), {
                    "action": "rewrite",
                    "text": "/model fixture-model --provider fixture-provider"
                            f" --reasoning {effort} --session",
                })

    def test_unsafe_preset_values_fail_open(self):
        valid = {"model": "fixture-model", "provider": "fixture-provider"}
        unsafe = (
            "two words", "", " leading", "trailing ", "tab\tvalue", "new\nline",
            "carriage\rreturn", "nul\0value", "delete\x7f", "escape\x1b", "c1\x85",
            "hidden\u200b", "bidi\u202e", "space\u00a0value", "--global", "-flag",
            "\u2012global", "\u2013global", "\u2014global", "\u2015global", "\u2212flag",
            None, False, 0, [], {},
        )
        for key in ("model", "provider"):
            for value in unsafe:
                with self.subTest(key=key, value=value):
                    self.context.settings["aliases"]["deep"] = {**valid, key: value}
                    self.assertIsNone(self.dispatch("/model deep"))

    def test_invalid_configured_reasoning_fails_open(self):
        for value in ("invalid", "", "HIGH", "high --global", None, False, 0, [], {}):
            with self.subTest(value=value):
                self.context.settings["aliases"]["deep"]["reasoning_effort"] = value
                self.assertIsNone(self.dispatch("/model deep"))

    def test_malformed_configuration_fails_open(self):
        for aliases in (None, False, 7, "not-a-map", [], {}, {"deep": None},
                        {"deep": []}, {"deep": "not-a-preset"}, {"deep": {}},
                        {"deep": {"model": "fixture-model"}},
                        {"deep": {"provider": "fixture-provider"}}):
            with self.subTest(aliases=aliases):
                self.context.settings["aliases"] = aliases
                self.assertIsNone(self.dispatch("/model deep"))
        self.context.settings.clear()
        self.assertIsNone(self.dispatch("/model deep"))

    def test_boolean_flags_keep_the_requested_scope_and_refresh(self):
        cases = (
            ("/model --global deep", "--global"),
            ("/model deep --global", "--global"),
            ("/model --session deep", "--session"),
            ("/model deep --session", "--session"),
            ("/model --refresh deep", "--refresh --session"),
            ("/model deep --refresh", "--refresh --session"),
            ("/model --global deep --session --refresh", "--global --session --refresh"),
            ("/model --session --refresh deep --global", "--session --refresh --global"),
            ("/model deep --global --global", "--global --global"),
        )
        for text, flags in cases:
            with self.subTest(text=text):
                self.assertEqual(self.dispatch(text), {
                    "action": "rewrite",
                    "text": f"/model fixture-model --provider fixture-provider {flags}",
                })

    def test_explicit_provider_and_reasoning_use_last_flag_wins(self):
        self.context.settings["aliases"]["deep"]["reasoning_effort"] = "high"
        for text, provider, effort in (
            ("/model deep --provider override-provider", "override-provider", "high"),
            ("/model --provider override-provider deep", "override-provider", "high"),
            ("/model deep --reasoning low", "fixture-provider", "low"),
            ("/model --reasoning low deep", "fixture-provider", "low"),
            ("/model deep --reasoning HIGH", "fixture-provider", "HIGH"),
            ("/model --provider earlier-provider --reasoning max deep"
             " --reasoning none --provider final-provider", "final-provider", "none"),
            ("/model --reasoning invalid deep --reasoning ultra", "fixture-provider", "ultra"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.dispatch(text), {
                    "action": "rewrite",
                    "text": f"/model fixture-model --provider {provider}"
                            f" --reasoning {effort} --session",
                })

    def test_malformed_flags_fail_open_without_dropping_any_tokens(self):
        for text in (
            "/model deep --provider", "/model deep --reasoning",
            "/model --provider", "/model --reasoning", "/model --refresh",
            "/model deep --provider --global", "/model deep --reasoning --session",
            "/model deep --provider --provider final-provider",
            "/model deep --reasoning invalid", "/model deep --reasoning high --reasoning invalid",
            "/model deep --provider bad\0value", "/model deep --provider hidden\u200bvalue",
            "/model deep --provider -bad", "/model deep --provider \u2014global",
            "/model deep --reasoning high --unknown", "/model deep --unknown value",
            "/model deep --provider=fixture-provider", "/model deep --global=true",
            "/model --provider fixture-provider deep extra", "/model deep deep --session",
            "/model deep --", "/model deep -p fixture-provider", "/model deep --GLOBAL",
            "/model --once deep", "/model deep --once", "/model deep --reasoning high --once",
        ):
            with self.subTest(text=text):
                self.assertIsNone(self.dispatch(text))
        for alias in ("--once", "--unknown", "-p", "\u2014global", "deep\0value"):
            with self.subTest(alias=alias):
                self.context.settings["aliases"][alias] = self.context.settings["aliases"]["deep"]
                self.assertIsNone(self.dispatch(f"/model {alias}"))

    def test_unreadable_configuration_fails_open_without_exposing_it(self):
        class UnreadableConfiguration:
            def get(self, key, default=None):
                raise ValueError("fixture-config-error")

        self.context.settings = UnreadableConfiguration()
        self.assertIsNone(self.dispatch("/model deep"))

    def test_non_text_events_are_unchanged(self):
        for text in (None, b"/model deep", 7, [], {}):
            with self.subTest(text=text):
                self.assertIsNone(self.dispatch(text))

    def test_unicode_dash_flags_pass_through_unchanged(self):
        for dash in ("\u2012", "\u2013", "\u2014", "\u2015"):
            for flag in ("global", "session", "refresh", "once",
                         "provider override-provider", "reasoning low"):
                for text in (f"/model {dash}{flag} deep", f"/model deep {dash}{flag}"):
                    with self.subTest(text=text):
                        self.assertIsNone(self.dispatch(text))

    def test_current_configuration_is_read_without_mutating_it(self):
        self.assertIsNotNone(self.dispatch("/model deep"))
        replacement = {"aliases": {
            "deep": {"model": "vendor/fixture-model:2.1", "provider": "fixture-provider-2",
                     "reasoning_effort": "low"},
            "unselected": {"model": "bad config value"},
        }}
        self.context.settings = replacement
        self.assertEqual(self.dispatch("/model deep"), {
            "action": "rewrite",
            "text": "/model vendor/fixture-model:2.1 --provider fixture-provider-2"
                    " --reasoning low --session",
        })
        self.assertEqual(replacement["aliases"]["deep"], {
            "model": "vendor/fixture-model:2.1", "provider": "fixture-provider-2",
            "reasoning_effort": "low",
        })
        self.context.settings = {"aliases": {}}
        self.assertIsNone(self.dispatch("/model deep"))

    def test_alias_matching_is_case_sensitive_without_normalization(self):
        self.context.settings["aliases"]["Deep"] = {
            "model": "other-fixture-model", "provider": "other-fixture-provider",
        }
        self.assertEqual(self.dispatch("/model Deep"), {
            "action": "rewrite",
            "text": "/model other-fixture-model --provider other-fixture-provider --session",
        })
        self.assertIsNone(self.dispatch("/model DEEP"))
        self.assertIn("/model fixture-model ", self.dispatch("/model deep")["text"])

    def test_overrides_do_not_rescue_invalid_presets(self):
        for preset in ({"model": "fixture-model"},
                       {"model": "fixture-model", "provider": "bad provider"},
                       {"model": "fixture-model", "provider": "fixture-provider",
                        "reasoning_effort": "invalid"}):
            with self.subTest(preset=preset):
                self.context.settings["aliases"]["deep"] = preset
                self.assertIsNone(self.dispatch(
                    "/model deep --provider override-provider --reasoning low"))

    def test_hook_ignores_all_other_gateway_arguments(self):
        event = SimpleNamespace(text="/model deep")
        self.assertEqual(self.callback(event=event, gateway=object(), session_store=object()),
                         self.dispatch("/model deep"))
        self.assertEqual(event.text, "/model deep")


if __name__ == "__main__":
    unittest.main()
