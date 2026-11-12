"""MGU Assistant 2: asistente automatizado para BMW iDrive 7 (MGU ID7).

Orquesta los proyectos oficiales (idrive7-8-ssh-root, mgu-store y los repos de
apps) descargandolos y verificandolos por si mismo. No reimplementa el
protocolo de flasheo: el flasheo se hace en la GUI oficial prebuilt; el resto
(diagnostico, respaldo de codificacion, instalacion del Store, catalogo, USB)
se automatiza desde esta aplicacion.
"""

__version__ = "2.0.0"
APP_NAME = "MGU Assistant 2"
APP_ID = "mgua2"
# Nombre del ejecutable de consola que acompana a la GUI (ver packaging).
CLI_EXE_NAME = "mgua2-cli.exe"
