# Contributing

**English** | [Español](CONTRIBUTING.es.md)

Thanks for helping. Bug reports from real cars are the most valuable contribution: save the console
log from the app ("Guardar log"; it is already redacted) and describe the car and head unit software.

## Development setup

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m mgua2 --demo
```

Run the tests before opening a pull request:

```
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python -m pyflakes mgua2 tests
.venv\Scripts\python -m pytest -m "not net"
```

## Rules

- Never commit VINs, SSH keys, tokens or unredacted logs. Use the fake VIN `WBS12345678901234` in
  tests.
- Do not add anything that flashes, passes `--force`/`--yes` or writes coding to the car. The flash
  stays a manual step in the official GUI.
- When the app parses upstream output, add a test with the real output lines.
- Every user-facing text is written in both languages: `tr("texto en español", "English text")`.
  Code comments may be Spanish or English.
- New community sources go in `mgua2/services/sources.py` only after checking that the repository
  has a layout the Store can read (`mgu-repo.json`, `apps/`, or Releases with `mgu-store.json` /
  `catalog.json`).
