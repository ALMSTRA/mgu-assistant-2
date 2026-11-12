# Política de seguridad

[English](SECURITY.md) | **Español**

## Alcance

MGU Assistant 2 orquesta herramientas de terceros que habilitan root SSH en el head unit de un BMW
con iDrive 7 (MGU) e instalan la MGU Store. El único paso que escribe software en el coche es el
flasheo, y siempre lo hace el `MGU-SSH.exe` oficial, lanzado por el usuario. Esta app nunca debe:

- flashear, forzar (`--force`/`--yes`) ni saltarse los bloqueos de seguridad BTLD/NBT de upstream,
- escribir codificación en el coche,
- filtrar identificadores del vehículo o secretos (VIN, llaves SSH privadas, tokens de GitHub,
  tu nombre de usuario) en logs, consola, capturas o servicios de red,
- ejecutar código descargado de una fuente de la comunidad sin que el usuario la active,
- sobrescribir las herramientas o datos reales del usuario desde el modo demo.

Cualquier cosa que rompa una de estas reglas es un problema de seguridad de este proyecto.

## Reportar una vulnerabilidad

**No** abras un issue público para problemas de seguridad. Usa el reporte privado de
vulnerabilidades de GitHub en este repositorio (pestaña "Security" → "Report a vulnerability"). Si
no lo tienes disponible, abre un issue titulado "Security contact request" sin detalles.

Incluye la versión o commit, la versión de software del head unit si aplica, los pasos para
reproducirlo, si había un coche involucrado y el impacto que viste. Nunca adjuntes logs sin
censurar, VIN ni llaves.

## Versiones con soporte

Solo la última release y la rama `main` reciben correcciones.

## Recordatorio de seguridad

Trabaja con el coche estacionado y una fuente de alimentación regulada. Haz un respaldo de la
codificación (el preflight de la app más E-Sys o BimmerCode) antes de flashear y ten listo cómo
recodificar `HU_MGU` después. Flashea una sola vez.
