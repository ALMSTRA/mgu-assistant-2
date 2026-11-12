# Security policy

**English** | [Español](SECURITY.es.md)

## Scope

MGU Assistant 2 orchestrates third-party tools that enable root SSH on a BMW iDrive 7 (MGU) head
unit and install the MGU Store. The only step that writes software to the car is the flash, and it
is always done by the official `MGU-SSH.exe`, started by the user. This app must never:

- flash, force (`--force`/`--yes`) or bypass the upstream BTLD/NBT safety gates,
- write coding to the car,
- leak vehicle identifiers or secrets (VIN, SSH private keys, GitHub tokens, the user's Windows
  user name) to logs, the console, screenshots or any network service,
- run code downloaded from a community source without the user enabling that source,
- overwrite the user's real tools or data from demo mode.

Anything that breaks one of these is a security issue for this project.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Use GitHub's private vulnerability
reporting on this repository (the "Security" tab, then "Report a vulnerability"). If that is not
available to you, open an issue titled "Security contact request" without details.

Include the version or commit, the head unit software version if relevant, steps to reproduce,
whether a car was involved, and the impact you observed. Never attach unredacted logs, VINs or
keys.

## Supported versions

Only the latest release and the `main` branch receive fixes.

## Safety reminder

Work on a parked car with a regulated power supply. Make a coding backup (the app's preflight plus
E-Sys or BimmerCode) before flashing, and be ready to recode `HU_MGU` afterwards. Flash only once.
