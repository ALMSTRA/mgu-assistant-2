# Third-party notices

MGU Assistant 2 does not include the upstream tools in this repository. It downloads them at run
time from their official GitHub locations and runs them unmodified:

| Project | Licence | Used for |
| --- | --- | --- |
| [cauliflowermossgrape/idrive7-8-ssh-root](https://github.com/cauliflowermossgrape/idrive7-8-ssh-root) | Unlicense | `status`, `preflight`, `enable`, `persist`, and the prebuilt `MGU-SSH.exe` for the flash |
| [robertnisipeanu/mgu-store](https://github.com/robertnisipeanu/mgu-store) | GPL-3.0 | `mgu-install` standalone installer and the Store |
| [cauliflowermossgrape/idrive7-apps](https://github.com/cauliflowermossgrape/idrive7-apps) | MIT | App catalog |
| [robertnisipeanu/idrive-apps](https://github.com/robertnisipeanu/idrive-apps) | GPL-3.0 | App catalog |
| [IterioDev/car-apps](https://github.com/IterioDev/car-apps) | see repository | App catalog |

`mgua2/resources/fixtures/` contains copies of app manifest files (`app.json`, `mgu-app.json`,
`mgu-repo.json`, `component.json`) from those repositories, used only by demo mode and the tests.
They remain under their original licences.

Bundled in the Windows build:

| Package | Licence |
| --- | --- |
| [PySide6 / Qt for Python](https://www.qt.io/qt-for-python) | LGPL-3.0 |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 or BSD-3-Clause |
| [PyInstaller](https://pyinstaller.org) bootloader | GPL-2.0 with bootloader exception |
| CPython | PSF License |

Community sources listed in the app belong to their authors and are not verified by this project.
