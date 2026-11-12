# Changelog

## 2.0.0-beta.2 (2026-11-12)

- English interface, with a language selector in the header and `--lang en|es`
  (Spanish stays the default on Spanish systems). / Interfaz en inglés, con selector de idioma en la
  cabecera y `--lang en|es`.
- Privacy: the Windows user name is hidden in the console, log files and status bar. / Privacidad:
  el nombre de usuario de Windows se oculta en la consola, los logs y la barra de estado.
- README, SECURITY and CONTRIBUTING in English and Spanish; new screenshots in both languages.

## 2.0.0-beta.1 (2026-11-12)

First public release. Rewritten from scratch after the first real-car runs on a 2021 X4 M (F98).

- Exe-as-interpreter bridge: the official SSH tool runs with the bundled interpreter, so the laptop
  needs no Python. Upstream exceptions are reported as one clean error line.
- Automatic, verified downloads of the SSH tool, `MGU-SSH.exe`, `mgu-install` and the app
  repositories. Stub or truncated files are no longer treated as installed.
- Diagnostics show the coding (CAFD). An erased coding (`FFFFFFFF`) blocks the Store step with
  recode instructions; the Doctor recognises the installer's "coding is missing" refusal.
- ENET: retry with the last gateway seen on that car, link report (adapter, ARP neighbours, port-22
  probe) and a "Locate unit" button for when the unit's IP changes.
- SSH test: quoted `known_hosts` path, automatic clean-and-retry when the unit regenerates its host
  key, VIN taken from diagnostics for `enable`, warning that `enable` resets profiles.
- Resume: an existing enrollment is detected on start.
- Single "I accept" button instead of checkbox lists and a typed phrase.
- 78 verified community sources; repositories that overwrite official tools or the Store are
  blocked.
- Demo mode always runs in a temporary folder.
