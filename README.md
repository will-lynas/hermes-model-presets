# Hermes Model Presets

Named model, provider and reasoning presets for Hermes **gateway messaging**.
Uses the existing `/model` command: exact aliases expand, everything else passes
through unchanged. No core patch, private Hermes API, monkeypatch, or extra
slash command.

```text
/model deep
→ /model your-model-id --provider your-provider --reasoning high --session
```

The model and provider above are placeholders, not working provider credentials
or recommended model IDs. Choose values already configured in your Hermes profile.

## Install

Requires Hermes **0.22.5 or newer** with the documented
[`pre_gateway_dispatch` hook](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks#pre_gateway_dispatch)
and native `/model --reasoning` support. Python 3.11+; no third-party Python
dependencies. Compatibility is tested against 0.22.5, not every future release.

```sh
hermes plugins install will-lynas/hermes-model-presets --enable
hermes plugins doctor model-presets --ci
```

Review the source before enabling any plugin. Restart your gateway after
installation so its process loads the plugin. Installing does **not** configure
any aliases or change the selected model.

## Configure

Settings belong to the **active profile**, under
`plugins.entries.model-presets.settings.aliases` in its `config.yaml`.
They are not stored in the plugin directory and are not sent to this repository.
Use Hermes's config command, replacing the placeholder model and provider:

```sh
hermes config set plugins.entries.model-presets.settings.aliases '{"deep":{"model":"your-model-id","provider":"your-provider","reasoning_effort":"high"}}'
```

That command sets the entire alias map; include any existing aliases you want to
keep. The equivalent settings structure is:

```yaml
plugins:
  entries:
    model-presets:
      settings:
        aliases:
          deep:
            model: your-model-id
            provider: your-provider
            reasoning_effort: high
          quick:
            model: your-model-id
            provider: your-provider
            reasoning_effort: low
```

- Alias names match **exactly and case-sensitively**. Use a single non-flag token.
- `model` and `provider` are required nonempty command tokens, not shell strings.
  Spaces, control characters and flag-like values are rejected.
- `reasoning_effort` is optional. Supported spellings are `none`, `minimal`,
  `low`, `medium`, `high`, `xhigh`, `max` and `ultra`. Hermes determines what a
  particular model/provider actually supports. Omission leaves the host's effort
  behavior unchanged.
- The default alias map is empty. Invalid settings leave the command unchanged;
  no partial preset is applied. The plugin reads current settings for each match.
- Never put API keys or credentials in presets. Configure providers through
  Hermes normally.

## Commands

```text
/model deep                         # preset, this session only
/model deep --reasoning low         # explicit effort overrides the preset
/model deep --provider other        # explicit provider overrides the preset
/model deep --global                # explicitly persist through native Hermes
/model deep --refresh               # retain the native refresh flag
```

Recognized flags may appear before or after the alias. Repeated value flags keep
Hermes's last-value-wins behavior. Explicit scope flags are retained; otherwise
`--session` is added even when Hermes is configured to persist switches by default.
If both `--session` and `--global` are supplied, Hermes's session precedence wins.

These are left untouched:

- `/model` (the standard picker/status behavior).
- `/model` with a real model ID or any unconfigured name.
- Other commands and ordinary messages.
- Malformed commands, unknown flags, extra positional arguments, or invalid presets.
- Commands containing `--once`: one-turn reasoning presets are deliberately not
  supported because Hermes 0.22.5 does not apply the reasoning flag on that path.
- Smart-dash flags: use plain ASCII `--`, not typographic en/em dashes. These
  commands pass through unchanged rather than silently losing or repairing flags.

Alias names can shadow an identically named real model. Choose short, distinctive
names. Removing an alias restores native handling of that name.

## Scope and safety

Only the documented plugin contract is used:

```python
ctx.get_config("aliases", {})
ctx.register_hook("pre_gateway_dispatch", handler)
# handler returns {"action": "rewrite", "text": "/model ..."} or None
```

The plugin does **not** replace `/model`, mutate the event/session/gateway, call a
model provider, access credentials, write configuration, read transcripts, send
messages, or make network requests. It reads incoming text and its own settings,
then returns text to Hermes. Normal authorization and native command handling
still run; existing busy-session rejection is unchanged. Hermes itself may log
or persist the resulting command under its normal policies.

- **Gateway only:** the hook does not run for local CLI, TUI, Desktop, API-server
  turns or startup model selection. This is not a replacement for core model aliases.
- The messaging platform must deliver the `/model` command to Hermes. No new
  platform slash command needs registering. The plugin itself does not implement
  platform-specific command spellings or menus.
- Preset definitions persist in profile settings. Session reasoning overrides in
  Hermes 0.22.5 are in-memory; reapply the preset after a gateway restart. This
  plugin does not add persistence or change native `--global` behavior.
- Other ingress plugins can affect results: Hermes uses the first recognized hook
  action. This plugin returns `None` for anything it does not expand.

## Development

```sh
python -m unittest discover -s tests -v
hermes plugins doctor . --ci
hermes plugins validate .
```

The unit suite uses only the Python standard library and a minimal implementation
of the two public context methods. Doctor validates real Hermes discovery,
registration and hook signatures using an isolated temporary profile. Neither
suite requires provider credentials or live messaging access. They are not a
claim of a live Slack/Telegram test.

Runtime code lives entirely in [`__init__.py`](__init__.py). The manifest declares
one hook and one settings map. No bundled personal presets, telemetry or setup
scripts. See the [Hermes plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/)
for the host API contract.

## License

[MIT](LICENSE).
