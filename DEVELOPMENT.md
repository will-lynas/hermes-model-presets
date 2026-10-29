# Development

## Setup

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
```

## Checks

```sh
ruff check .
ruff format --check .
ty check .
python -m pytest -q
```

Run a single parameterised case with `pytest -k case-name`.

With Hermes installed:

```sh
hermes plugins doctor . --ci
hermes plugins validate .
```

## Update dependencies

Edit the direct pins in `requirements-dev.in`, then regenerate the lock:

```sh
uv pip compile requirements-dev.in --output-file requirements-dev.txt --generate-hashes --universal --python-version 3.11
```
