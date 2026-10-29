# Hermes Model Presets

Named model, provider and reasoning presets for Hermes messaging.

```text
/model deep
→ /model gpt-5 --provider openai --reasoning high --session
```

## Setup

```sh
hermes plugins install will-lynas/hermes-model-presets --enable
hermes plugins doctor model-presets --ci
```

Add presets to your profile's `config.yaml`, then restart the gateway:

```yaml
plugins:
  entries:
    model-presets:
      settings:
        aliases:
          deep:
            model: gpt-5
            provider: openai
            reasoning_effort: high
```

## Usage

```text
/model deep                   # this session only
/model deep --reasoning low   # override the preset's effort
/model deep --global          # save as the default
/model another-model          # unconfigured names pass through
```

Names match exactly, including case. `reasoning_effort` is optional.

Requires Hermes 0.22.5+ and Python 3.11+. Messaging only, not local CLI/TUI,
Desktop or API turns. `--once` and smart-dash flags aren't expanded.
Reapply session presets after a gateway restart.

[Development](DEVELOPMENT.md) · [MIT](LICENSE)
