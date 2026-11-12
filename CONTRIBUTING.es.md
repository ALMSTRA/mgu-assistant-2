# Cómo contribuir

[English](CONTRIBUTING.md) | **Español**

Gracias por ayudar. Lo más valioso son los reportes desde coches reales: guarda el log de la consola
de la app ("Guardar log"; ya sale censurado) y describe el coche y la versión de software del head
unit.

## Entorno de desarrollo

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m mgua2 --demo
```

Corre las pruebas antes de abrir un pull request:

```
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python -m pyflakes mgua2 tests
.venv\Scripts\python -m pytest -m "not net"
```

## Reglas

- Nunca subas VIN, llaves SSH, tokens ni logs sin censurar. En las pruebas usa el VIN falso
  `WBS12345678901234`.
- No agregues nada que flashee, pase `--force`/`--yes` o escriba codificación en el coche. El
  flasheo sigue siendo un paso manual en la GUI oficial.
- Si la app interpreta salida de upstream, agrega una prueba con las líneas reales.
- Todo texto visible va en los dos idiomas: `tr("texto en español", "English text")`.
- Las nuevas fuentes de la comunidad van en `mgua2/services/sources.py` solo después de comprobar
  que el repo tiene un formato que la Store puede leer (`mgu-repo.json`, `apps/`, o Releases con
  `mgu-store.json` / `catalog.json`).
