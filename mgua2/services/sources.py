"""Fuentes de apps (repositorios GitHub) para el catalogo y el USB.

El MGU Store admite anadir fuentes GitHub (pestana Sources). Aqui:
- las 4 fuentes OFICIALES que el propio Store siembra (deploy/sources.json);
- una INSTANTANEA de repos comunitarios conocidos (8-nov-2026) con sus
  estrellas y descripcion, como punto de partida;
- descubrimiento EN VIVO por la API de busqueda de GitHub;
- fuentes personalizadas (owner/repo) y el conjunto que el usuario activa,
  persistido en state/sources.json.

Las fuentes comunitarias NO estan verificadas: el catalogo las clasifica por
riesgo igual que a las oficiales, y el usuario decide activarlas.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Optional

from ..core.logbus import LogBus
from ..core.paths import DataPaths
from ..i18n import tr
from . import download as dl

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

OFFICIAL_SOURCES: list[tuple[str, str]] = [
    ("mgu-store", "robertnisipeanu/mgu-store"),
    ("idrive7-apps", "cauliflowermossgrape/idrive7-apps"),
    ("idrive-apps", "robertnisipeanu/idrive-apps"),
    ("car-apps", "IterioDev/car-apps"),
]
OFFICIAL_REPOS = {r for _, r in OFFICIAL_SOURCES}

# Repos que NO deben anadirse como fuente (verificado 9-nov-2026): sustituyen herramientas oficiales o el
# propio Store con paquetes del mismo id. add_custom() los rechaza con el motivo.
BLOCKED_SOURCES: dict[str, str] = {
    "mlurker/bmw-idrive7-releases": tr(
        "publica cluster-render, waze-on-cluster y mgu-updater 10.x sin fuente: pisaria las herramientas oficiales",
        "it publishes cluster-render, waze-on-cluster and mgu-updater 10.x without source code: it would "
        "overwrite the official tools"),
    **{r: tr("copia del MGU Store (mismo robertn_store): sustituiria tu Store",
             "a copy of the MGU Store (same robertn_store): it would replace your Store") for r in (
        "hexlay/mgu-store", "vtechnics/mgu-store", "Matiscker/MGU-Store---BMW-iDrive", "ionutz87bc/MGU_store",
        "Adrienbavarian/bavarian-store", "JackieZ123430/mgu-store-cn", "kern4466/mgu-store-ua",
        "mlurker/robertnisipeanu-mgu-store-fork", "bcs-develop/bcs-store", "marilykinson-glitch/mgu-store")},
}


@dataclass
class Source:
    repo: str                 # owner/name
    description: str = ""
    stars: int = 0
    pushed_at: str = ""
    category: str = "comunidad"
    note_es: str = ""
    custom: bool = False

    @property
    def dir_name(self) -> str:
        return self.repo.replace("/", "__")


# Instantanea del ecosistema (busqueda GitHub, 8-nov-2026). Se refresca con discover().
COMMUNITY_SNAPSHOT: list[Source] = [
    Source("bimmer-lab/apps",
           tr("Cluster Themes (GT3, M, Sport, Minimal, Roadster, Track, Drag) + HUD Widgets (marcha, shift lights, "
              "boost, temperaturas, G-meter)",
              "Cluster Themes (GT3, M, Sport, Minimal, Roadster, Track, Drag) + HUD Widgets (gear, shift lights, "
              "boost, temperatures, G-meter)"),
           26, "2026-11-08", "hud",
           tr("Requiere instalar antes cluster-render (idrive-apps).",
              "Requires installing cluster-render (idrive-apps) first.")),
    Source("PenguinDukeYDAuto/idrive7-EVAHUD",
           tr("HUD y cuadro estilo NERV (Evangelion) para iDrive 7",
              "NERV-style (Evangelion) HUD and cluster for iDrive 7"),
           56, "2026-11-07", "hud",
           tr("Se construye uno mismo: solo apps/eva_hud, sin mgu-repo.json ni releases (el Store puede no leerlo).",
              "You build it yourself: only apps/eva_hud, no mgu-repo.json or releases (the Store may not read it).")),
    Source("JustAnotherPU/waze-hud",
           tr("Flechas de Waze en el HUD y el cuadro (lee la guia desde la imagen de CarPlay)",
              "Waze arrows on the HUD and the cluster (reads the guidance from the CarPlay image)"),
           10, "2026-11-08", "hud"),
    Source("JustAnotherPU/mgu-apps", "iDrive Monitor (CPU/RAM/GPU), wireproxy (WireGuard), Node.js 22", 3, "2026-11-08", "tools"),
    Source("NamelsMissing/mgu-apps",
           tr("11 apps para un G21 ID7: DPF monitor, ambient RGB, calefaccion de volante, Game Station (NES/SNES/GB)",
              "11 apps for a G21 ID7: DPF monitor, RGB ambient light, steering wheel heating, Game Station (NES/SNES/GB)"),
           5, "2026-11-08", "apps"),
    Source("robertnisipeanu/idrive7-carplay-multitouch",
           tr("Parche multitouch para CarPlay (instalador Windows ENET/SSH con respaldo; una version exacta de software)",
              "Multitouch patch for CarPlay (Windows ENET/SSH installer with backup; one exact software version)"),
           12, "2026-10-31", "tools",
           tr("NO instalable desde el Store (instalador Windows aparte); requiere root.",
              "NOT installable from the Store (separate Windows installer); requires root.")),
    Source("JustAnotherPU/moonride",
           tr("Streaming de juegos con Moonlight en la pantalla del iDrive 7 a traves de Tailscale",
              "Moonlight game streaming on the iDrive 7 screen over Tailscale"),
           3, "2026-11-08", "juegos",
           tr("Solo estacionado; necesita Tailscale e internet.",
              "Parked only; needs Tailscale and internet.")),
    Source("pinguinooo/idrive7-apps",
           tr("Apps de BMW iDrive 7 para el mgu-store: un repo, una carpeta por app",
              "BMW iDrive 7 apps for the mgu-store: one repo, one folder per app"),
           8, "2026-11-08", "apps"),
    Source("hexlay/idrive7-custom-apps",
           tr("Apps personalizadas para iDrive 7 (incl. la navegacion offline idrive7-geo-map)",
              "Custom apps for iDrive 7 (incl. offline navigation idrive7-geo-map)"),
           8, "2026-11-08", "apps"),
    Source("arefahmad/idrive7-apps",
           tr("Apps de solo lectura: Car Care, Drive Log (calibracion con Dragy), Fault Watch, Car Lyrics",
              "Read-only apps: Car Care, Drive Log (Dragy calibration), Fault Watch, Car Lyrics"),
           7, "2026-11-07", "apps"),
    Source("alexp50/bmw-apps",
           tr("Apps a pantalla completa de BMW iDrive 7 para el MGU Store",
              "Full-screen BMW iDrive 7 apps for MGU Store"),
           3, "2026-11-08", "apps"),
    Source("evangoyuk/mgu-store-apps",
           tr("Gentleman Function (asiento), Exhaust & Start/Stop, Shift Lights — layout Releases",
              "Gentleman Function (seat), Exhaust & Start/Stop, Shift Lights — Releases layout"),
           3, "2026-11-08", "control",
           tr("Controla escape / start-stop / asiento: riesgo rojo.",
              "Controls the exhaust / start-stop / seat: red risk.")),
    Source("sembsa/idrive7-ambient",
           tr("Experimentos de luz ambiente para BMW iDrive 7",
              "Ambient light experiments for BMW iDrive 7"),
           2, "2026-11-08", "apps"),
    Source("MaxxxFoka/IDRIVE7GAMES",
           tr("Seis juegos arcade originales para la unidad BMW MGU (iDrive 7)",
              "Six original arcade games for the BMW MGU head unit (iDrive 7)"),
           2, "2026-11-08", "juegos", tr("Solo estacionado.", "Parked only.")),
    Source("pllanaio/bmw-airplay",
           tr("Receptor AirPlay nativo para BMW MGU / iDrive 7 (app 0.2.6)",
              "Native BMW MGU / iDrive 7 AirPlay receiver (app 0.2.6)"),
           1, "2026-11-08", "media"),
    Source("vc7k77yd77-crypto/mgu-cast",
           tr("Receptor AirPlay nativo experimental para iPhone (beta, solo estacionado)",
              "Experimental native iPhone AirPlay receiver (parked-only beta)"),
           0, "2026-11-08", "media", tr("Beta experimental.", "Experimental beta.")),
    Source("alexpereap/pereaperformance-idrive7-apps",
           tr("Flex Fuel y otras apps de iDrive 7 de Perea Performance",
              "Flex Fuel and other iDrive 7 apps by Perea Performance"),
           0, "2026-11-09", "apps"),
    Source("ao960317li/hdp-idrive7-apps",
           tr("Paneles HDP negro y verde para BMW iDrive 7",
              "HDP black and green dashboards for BMW iDrive 7"),
           0, "2026-11-07", "apps"),
    Source("sergshamiryan/mgu-gear-cluster",
           tr("Gear on Cluster: D1..D8 en el cuadro de instrumentos",
              "Gear on Cluster: D1..D8 on the instrument cluster"),
           0, "2026-11-06", "hud"),
    Source("chriskilagmail/bmw-weather-idrive7",
           tr("App del tiempo para iDrive 7", "Weather app for iDrive 7"),
           0, "2026-11-07", "apps"),
    Source("istt1899/bmw-kaluga-cameras",
           tr("App de radares de velocidad offline (Kaluga) — experimental",
              "Offline speed camera app (Kaluga) — experimental"),
           0, "2026-11-08", "apps"),
    Source("dzooky/bmrmodz",
           tr("Apps personalizadas para la unidad BMW MGU / iDrive 7",
              "Custom apps for the BMW MGU / iDrive 7 head unit"),
           0, "2026-11-08", "apps"),
    # --- Ampliacion 9-nov-2026 (busqueda exhaustiva, layout verificado por repo) ---
    Source("eroobeeroo/idrive7-apps",
           tr("Cluster Info (datos sobre mapa Waze en cluster/HUD), eDrive Live y Light Show de luces exteriores",
              "Cluster Info (data over the Waze map on cluster/HUD), eDrive Live and an exterior-lights Light Show"),
           2, "2026-11-09", "hud",
           tr("Light Show usa tests de luces del BDC; requiere cluster-render.",
              "Light Show uses the BDC light tests; requires cluster-render.")),
    Source("eroobeeroo/idrive7-cluster-info",
           tr("Cluster Info, Cluster Centre y Cluster Layouts: paneles de datos en cluster y HUD",
              "Cluster Info, Cluster Centre and Cluster Layouts: data panels on the cluster and HUD"),
           34, "2026-11-09", "hud",
           tr("Requiere cluster-render / Waze on cluster.",
              "Requires cluster-render / Waze on cluster.")),
    Source("cruzen991/Cluster",
           tr("Relojes redondos clasicos (Tech/Sport/Classic) con shift lights sobre el cluster",
              "Classic round gauges (Tech/Sport/Classic) with shift lights on the cluster"),
           1, "2026-11-09", "hud",
           tr("No validado en coche (solo PC); oculta los relojes de serie.",
              "Not validated in a car (PC only); hides the stock gauges.")),
    Source("cruzen991/HUD",
           tr("Layout de indicadores para el HUD con valores del coche",
              "HUD gauge layout with values from the car"),
           0, "2026-11-05", "hud",
           tr("Requiere cluster-render (target hud).",
              "Requires cluster-render (hud target).")),
    Source("kxrxh/doodle-jump-mgu",
           tr("Juego Doodle Jump para la pantalla central",
              "Doodle Jump game for the central display"),
           0, "2026-11-07", "juegos",
           tr("Incluye mgu-inputgate; solo probado en emulador.",
              "Includes mgu-inputgate; only tested in an emulator.")),
    Source("Vizualyse/idrive-apps",
           tr("Cast al cluster/HUD/pantalla, Chromium, Moonlight y Steam streaming",
              "Cast to the cluster/HUD/display, Chromium, Moonlight and Steam streaming"),
           2, "2026-11-08", "media",
           tr("Hook precargado en CarPlay; demo tecnica en banco, no en coche.",
              "Hook preloaded into CarPlay; tech demo on a bench, not in a car.")),
    Source("Impossible43/vlad-mgu-apps",
           tr("Espejo experimental del mapa de CarPlay Dashboard en el cluster",
              "Experimental mirror of the CarPlay Dashboard map on the cluster"),
           0, "2026-11-04", "hud",
           tr("Experimental; probado parcialmente en X3 G01.",
              "Experimental; partially tested on an X3 G01.")),
    Source("noth4m4d/mgu-hamadstools",
           tr("Espejo de pantalla AirPlay y Waze Cards",
              "AirPlay screen mirroring and Waze Cards"),
           2, "2026-11-05", "media",
           tr("Herramienta root; imagen oculta en marcha por defecto.",
              "Root tool; the image is hidden while driving by default.")),
    Source("aurelmarius/bmw-apps",
           tr("Engine Care (arranques en frio PHEV), Hybrid Cost y calefaccion de volante",
              "Engine Care (PHEV cold starts), Hybrid Cost and steering wheel heating"),
           13, "2026-11-08", "apps",
           tr("Pensado para hibridos enchufables; no validado.",
              "Meant for plug-in hybrids; not validated.")),
    Source("aurelmarius/bmw-games",
           tr("11 juegos GPU a 60 fps: pinball, solitario, snake, blackjack, carreras, arcade",
              "11 GPU games at 60 fps: pinball, solitaire, snake, blackjack, racing, arcade"),
           16, "2026-11-08", "juegos", tr("Solo estacionado.", "Parked only.")),
    Source("aurelmarius/bmw-test-apps",
           tr("Repo de pruebas: AirPlay probe (uxplay) y cliente Emby",
              "Test repo: AirPlay probe (uxplay) and Emby client"),
           0, "2026-11-09", "media",
           tr("Repo de testing, inestable; herramientas root.",
              "Testing repo, unstable; root tools.")),
    Source("benspa900/mon-vitals-idrive7",
           tr("Panel personal basado en M Vitals (README en frances)",
              "Personal dashboard based on M Vitals (README in French)"),
           0, "2026-11-07", "apps",
           tr("No validado en coche.", "Not validated in a car.")),
    Source("JustAnotherPU/ridetube",
           tr("Cliente YouTube no oficial con login TV y suscripciones; vista podcast en marcha",
              "Unofficial YouTube client with TV login and subscriptions; podcast view while driving"),
           6, "2026-11-06", "media",
           tr("Herramienta root; requiere internet (mgu-uplink); probado en X5 G05; viola ToS de YouTube.",
              "Root tool; requires internet (mgu-uplink); tested on an X5 G05; violates YouTube's ToS.")),
    Source("JustAnotherPU/ridewatch",
           tr("Camaras de casa (UniFi Protect/RTSP) en la pantalla central",
              "Home cameras (UniFi Protect/RTSP) on the central display"),
           0, "2026-11-08", "media",
           tr("Solo estacionado; stream sin cifrar, no exponer el puerto.",
              "Parked only; unencrypted stream, do not expose the port.")),
    Source("7amoody1985/mgu-apps",
           tr("Fork de RideTube (stream en RAM) y app mdq_carlink",
              "RideTube fork (stream in RAM) and the mdq_carlink app"),
           0, "2026-11-07", "media",
           tr("Reusa IDs jap_ridetube: choca con JustAnotherPU/ridetube (no activar ambas).",
              "Reuses the jap_ridetube IDs: clashes with JustAnotherPU/ridetube (do not enable both).")),
    Source("pllanaio/mgu-browser",
           tr("Navegador Chromium experimental con navegacion por controlador y pestanas",
              "Experimental Chromium browser with controller navigation and tabs"),
           2, "2026-11-08", "media",
           tr("No validado (audio/DRM); requiere internet; ~2 GB.",
              "Not validated (audio/DRM); requires internet; ~2 GB.")),
    Source("Drake1804/bube-releases",
           tr("Reproductor YouTube personal (bube)", "Personal YouTube player (bube)"),
           5, "2026-11-03", "media",
           tr("Fuente solo en tarballs; herramienta root; internet.",
              "Source code only in tarballs; root tool; internet.")),
    Source("shjeladze/JLTube-MGU",
           tr("JLTube (reproductor de video) y MGU Inspector",
              "JLTube (video player) and MGU Inspector"),
           0, "2026-11-02", "media",
           tr("Sin mgu-repo.json ni releases: el Store puede no leerlo; no validado.",
              "No mgu-repo.json or releases: the Store may not read it; not validated.")),
    Source("iAbadia/idrive-games",
           tr("Juegos para el controlador iDrive: 2048, breakout, invaders, tetris, buscaminas",
              "Games for the iDrive controller: 2048, breakout, invaders, tetris, minesweeper"),
           5, "2026-11-04", "juegos",
           tr("mgu-repo.json solo expone iabadia_m_arcade; no validado.",
              "mgu-repo.json only exposes iabadia_m_arcade; not validated.")),
    Source("mistergahan/mgu-backgammon",
           tr("Backgammon (nardy corto y largo) y Tetris",
              "Backgammon (short and long nardy) and Tetris"),
           0, "2026-11-07", "juegos",
           tr("Solo estacionado; no validado en coche.",
              "Parked only; not validated in a car.")),
    Source("istt1899/x3",
           tr("Catalogo de codificacion X3 G01, descubrimiento ECU, RuTube/VK Video",
              "X3 G01 coding catalog, ECU discovery, RuTube/VK Video"),
           0, "2026-11-09", "control",
           tr("Cambia el coche; reempaqueta IDs de RideTube.",
              "Changes the car; repackages RideTube IDs.")),
    Source("jaimeen77-cmyk/apps",
           tr("Cluster Redline (metricas M, 2 disenos cluster/HUD) e iDrive Circuit",
              "Cluster Redline (M metrics, 2 cluster/HUD designs) and iDrive Circuit"),
           2, "2026-11-09", "hud",
           tr("Requiere cluster-render; README coreano/ingles.",
              "Requires cluster-render; Korean/English README.")),
    Source("DimonPrograms/dimonprograms-apps",
           tr("Set idrive7-apps propio + Track Mode (vueltas) y Battery & Electrical 12V",
              "Its own idrive7-apps set + Track Mode (laps) and Battery & Electrical 12V"),
           1, "2026-11-06", "apps",
           tr("IDs dimon_: convive con idrive7-apps; root; no validado.",
              "dimon_ IDs: coexists with idrive7-apps; root; not validated.")),
    Source("DarkMuse1/idrive7-apps-ru",
           tr("idrive7-apps en ruso + luz ambiente y 'MGU Tools' todo en uno",
              "idrive7-apps in Russian + ambient light and an all-in-one 'MGU Tools'"),
           0, "2026-11-08", "apps",
           tr("Mismos IDs que idrive7-apps (lo reemplaza); trae AA Companion retirado.",
              "Same IDs as idrive7-apps (it replaces it); ships the retired AA Companion.")),
    Source("1031527554/idrive7-apps-zh",
           tr("idrive7-apps compilado en chino simplificado (14 apps)",
              "idrive7-apps built in Simplified Chinese (14 apps)"),
           0, "2026-11-09", "apps",
           tr("Mismos IDs que idrive7-apps: no activar ambas fuentes.",
              "Same IDs as idrive7-apps: do not enable both sources.")),
    Source("solefir-org/penky_g20-mgu",
           tr("Kit idrive7-apps mas la app penky_g20",
              "idrive7-apps kit plus the penky_g20 app"),
           0, "2026-11-05", "apps",
           tr("Mismos IDs que idrive7-apps salvo penky_g20.",
              "Same IDs as idrive7-apps except penky_g20.")),
    Source("Dante1243/dante-idrive-apps",
           tr("Kit idrive7-apps mas app E85 y herramienta dante-slotlab",
              "idrive7-apps kit plus an E85 app and the dante-slotlab tool"),
           0, "2026-11-09", "apps",
           tr("Mismos IDs que idrive7-apps salvo e85.",
              "Same IDs as idrive7-apps except e85.")),
    Source("james10424/idrive7-custom",
           tr("HUD Live2D para iDrive 7 y dash M / Buick Regal 1987 para iDrive 8",
              "Live2D HUD for iDrive 7 and an M / 1987 Buick Regal dash for iDrive 8"),
           0, "2026-11-09", "hud",
           tr("Requiere cluster-render; no validado.",
              "Requires cluster-render; not validated.")),
    Source("asloocod/bmw-mgu-apps-public",
           tr("Flechas de intermitente en el HUD y calentamiento (README ruso)",
              "Turn-signal arrows on the HUD and warm-up (Russian README)"),
           0, "2026-11-07", "hud",
           tr("Solo tools (root); no validado.",
              "Tools only (root); not validated.")),
    Source("SPRNV4/mgu-apps",
           tr("Tarjeta de navegacion en el cluster (cluster_nav_card)",
              "Navigation card on the cluster (cluster_nav_card)"),
           0, "2026-11-08", "hud",
           tr("Requiere cluster-render; no validado.",
              "Requires cluster-render; not validated.")),
    Source("beele/eldrive",
           tr("elDrive: pagina eDrive para BMW 100% electricos",
              "elDrive: eDrive page for fully electric BMWs"),
           0, "2026-11-07", "apps",
           tr("Solo electricos (BEV); no validado.",
              "Fully electric only (BEV); not validated.")),
    Source("Muntadher313-car/MGU-Cluster-App",
           tr("Apex Dash: tema de cluster (basado en bimmer-lab)",
              "Apex Dash: cluster theme (based on bimmer-lab)"),
           0, "2026-11-07", "hud",
           tr("README copiado de bimmer-lab; verificar avisos del cluster.",
              "README copied from bimmer-lab; check the cluster warnings.")),
    Source("hexlay/idrive7-geo-map",
           tr("Navegacion offline OpenStreetMap (osm_nav); mapas en idrive7-geo-map-data",
              "Offline OpenStreetMap navigation (osm_nav); maps in idrive7-geo-map-data"),
           0, "2026-11-08", "apps",
           tr("Muy experimental, nunca probado en coche.",
              "Highly experimental, never tested in a car.")),
    Source("KhiSpec/idrive7-apps",
           tr("G's Dash, G's Music (Spotify) y G's TV (copia del repo de nickgcode)",
              "G's Dash, G's Music (Spotify) and G's TV (copy of nickgcode's repo)"),
           0, "2026-11-02", "media",
           tr("Copia de un repo ya borrado; internet.",
              "Copy of a repo that has since been deleted; internet.")),
    Source("KhiSpec/Juicewrld-Player-App",
           tr("Reproductor de musica Juice WRLD", "Juice WRLD music player"),
           0, "2026-11-04", "media",
           tr("App personal; no validado.", "Personal app; not validated.")),
    Source("EnVires/maxim-errors",
           tr("Slots personales de errores/avisos (README ruso)",
              "Personal error/warning slots (Russian README)"),
           0, "2026-11-05", "apps",
           tr("App personal; no validado.", "Personal app; not validated.")),
    Source("spataionut/mgu",
           tr("Service Book: registro de servicios y reparaciones con odometro",
              "Service Book: service and repair log with odometer"),
           0, "2026-11-08", "apps",
           tr("Incluye sp_probe; no validado.", "Includes sp_probe; not validated.")),
    Source("leschi/mgu-media-client",
           tr("Cliente multimedia para MGU", "Media client for MGU"),
           3, "2026-11-07", "media",
           tr("Trae renderd/inputgate; no validado.", "Ships renderd/inputgate; not validated.")),
    Source("sangriaonur/mgu_apps",
           tr("Android Auto y camara en el cluster (con render bridges)",
              "Android Auto and camera on the cluster (with render bridges)"),
           1, "2026-11-08", "hud",
           tr("Sin mgu-repo.json ni README: el Store puede no leerlo; requiere cluster-render.",
              "No mgu-repo.json or README: the Store may not read it; requires cluster-render.")),
    Source("editlxrd/lci-budiky",
           tr("LCI Budiky: relojes estilo LCI + copias de G's Dash/Music/TV",
              "LCI Budiky: LCI-style gauges + copies of G's Dash/Music/TV"),
           0, "2026-11-06", "hud",
           tr("IDs ng_ duplicados con KhiSpec; no validado.",
              "ng_ IDs duplicated with KhiSpec; not validated.")),
    Source("CarlMeehanIE/climate-strip",
           tr("Calefaccion de asientos/volante como app y utilidades de climatizacion",
              "Seat/steering wheel heating as an app plus climate utilities"),
           0, "2026-11-08", "control",
           tr("iDrive 8; envia ordenes al coche.", "iDrive 8; sends commands to the car.")),
    Source("milosmartinovic/id8_easyentry",
           tr("Entrada facil: mueve el asiento del conductor al abrir la puerta (G87 M2)",
              "Easy entry: moves the driver's seat when the door opens (G87 M2)"),
           0, "2026-11-07", "control",
           tr("iDrive 8; mueve el asiento: riesgo fisico.", "iDrive 8; moves the seat: physical risk.")),
    Source("Gokhant01/BmGuard",
           tr("BmGuard: estado e historial de la alarma (X4 G02)",
              "BmGuard: alarm status and history (X4 G02)"),
           0, "2026-11-01", "apps",
           tr("No validado; README en frances.", "Not validated; README in French.")),
    Source("kruglofed/kf-bmw-apps",
           tr("Kilometraje real, consumo y estilo de conduccion; control de volante",
              "Real mileage, consumption and driving style; steering wheel control"),
           0, "2026-11-09", "apps",
           tr("README ruso; no validado.", "Russian README; not validated.")),
    Source("usharafiev/cluster-yandex-safearea-fix",
           tr("Add-on de waze-on-cluster que corrige el area segura para Yandex Maps",
              "waze-on-cluster add-on that fixes the safe area for Yandex Maps"),
           4, "2026-11-09", "tools",
           tr("Requiere waze-on-cluster; root.", "Requires waze-on-cluster; root.")),
    Source("bloodbenzine/engine-config-45e-test",
           tr("Engine Config experimental para X5 45e (PAD xDrive)",
              "Experimental Engine Config for the X5 45e (PAD xDrive)"),
           0, "2026-11-08", "control",
           tr("Experimental, solo X5 45e; cambia el coche.",
              "Experimental, X5 45e only; changes the car.")),
    Source("bloodbenzine/mgu-capabilities-test",
           tr("Pruebas de capacidades: test de audio y entrada USB",
              "Capability tests: audio test and USB input"),
           0, "2026-11-03", "tools",
           tr("Repo de pruebas; root.", "Test repo; root.")),
    Source("bloodbenzine/id7-service-ru",
           tr("App Service traducida al ruso (bb_service_ru)",
              "Service app translated into Russian (bb_service_ru)"),
           0, "2026-11-04", "apps",
           tr("ID propio; no validado.", "Own ID; not validated.")),
    Source("andrug05/bmwcaminfo",
           tr("Avisos de radares de velocidad (README ruso)",
              "Speed camera alerts (Russian README)"),
           0, "2026-11-09", "apps",
           tr("Usa prefijo aurelm_ ajeno; no validado.",
              "Uses someone else's aurelm_ prefix; not validated.")),
    Source("athar66/iYT",
           tr("Reproductor YouTube nativo con decodificacion H.264 por hardware",
              "Native YouTube player with hardware H.264 decoding"),
           0, "2026-11-09", "media",
           tr("Daemon root; internet; no validado.", "Root daemon; internet; not validated.")),
    Source("dorindumitras/ambient-drive",
           tr("Luz ambiente segun modo de conduccion y posicion M/S",
              "Ambient light by driving mode and M/S position"),
           0, "2026-11-08", "control",
           tr("Envia ordenes de color al coche; no validado.",
              "Sends color commands to the car; not validated.")),
    Source("daniloz095/VMG-Utility",
           tr("M Vitals+: boost, temperaturas, presion de aceite, lambda, detonacion via UDS",
              "M Vitals+: boost, temperatures, oil pressure, lambda, knock via UDS"),
           0, "2026-11-08", "apps",
           tr("Sin mgu-repo.json: el Store puede no leerlo (README indica SSH).",
              "No mgu-repo.json: the Store may not read it (the README says SSH).")),
    Source("HasMan/turnkey-ethanol-blend",
           tr("TurnKey E Blend: monitor de etanol y calculadora de mezcla",
              "TurnKey E Blend: ethanol monitor and blend calculator"),
           0, "2026-11-03", "apps",
           tr("Ruta Store sin validar en coche.", "Store route not validated in a car.")),
    Source("aiden-perkins/id7-hollows-apps",
           tr("Luz ambiente, data logger, visor de datos en vivo y trip data",
              "Ambient light, data logger, live data viewer and trip data"),
           0, "2026-11-08", "apps",
           tr("No validado.", "Not validated.")),
    Source("Max-Mods-LTD/max-mods-hud-mirror",
           tr("Espejo del movil Android en HUD, cluster o pantalla central",
              "Android phone mirroring on the HUD, cluster or central display"),
           0, "2026-11-05", "media",
           tr("Requiere APK Android propia; comercial; no validado.",
              "Requires its own Android APK; commercial; not validated.")),
    Source("Izionloz/app",
           tr("Mapa CarPlay en cluster/HUD ajustable (tamano, zoom, brillo) + eva_cluster",
              "Adjustable CarPlay map on the cluster/HUD (size, zoom, brightness) + eva_cluster"),
           0, "2026-11-09", "hud",
           tr("Proxy root ante waze-on-cluster; requiere cluster-render.",
              "Root proxy in front of waze-on-cluster; requires cluster-render.")),
]

DISCOVER_QUERIES = ("mgu-store", "idrive7-apps", "mgu-app", "idrive7 bmw", "mgu id7 bmw")


class SourcesManager:
    def __init__(self, paths: DataPaths, bus: Optional[LogBus] = None) -> None:
        self.paths = paths
        self.bus = bus
        self._file = paths.state / "sources.json"
        self._data = self._load()

    # Ninguna fuente comunitaria activa por defecto: son opcionales y no verificadas.
    # (Activar una fuente solo la LISTA en el catalogo; nada se instala en el coche.)
    DEFAULT_ENABLED: list[str] = []

    def _load(self) -> dict:
        try:
            return json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:
            return {"enabled": list(self.DEFAULT_ENABLED), "custom": [], "discovered": []}

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def _log(self, lvl: str, msg: str) -> None:
        if self.bus:
            self.bus.log(lvl, msg)

    # -- conjuntos ------------------------------------------------------------
    def enabled(self) -> list[str]:
        return [r for r in self._data.get("enabled", []) if r not in OFFICIAL_REPOS]

    def is_enabled(self, repo: str) -> bool:
        return repo in self._data.get("enabled", [])

    def set_enabled(self, repo: str, on: bool) -> None:
        en = set(self._data.get("enabled", []))
        (en.add if on else en.discard)(repo)
        self._data["enabled"] = sorted(en)
        self._save()

    def add_custom(self, repo: str) -> Source:
        repo = repo.strip().removeprefix("https://github.com/").removesuffix(".git").strip("/")
        if not _REPO_RE.match(repo):
            raise ValueError(tr("Formato esperado: owner/repo", "Expected format: owner/repo"))
        blocked = {k.lower(): v for k, v in BLOCKED_SOURCES.items()}.get(repo.lower())
        if blocked:
            raise ValueError(tr(f"{repo} no se puede anadir: {blocked}.", f"{repo} cannot be added: {blocked}."))
        if repo not in self._data.setdefault("custom", []):
            self._data["custom"].append(repo)
            self._save()
        return Source(repo, custom=True)

    def all_known(self) -> list[Source]:
        seen: dict[str, Source] = {}
        for s in COMMUNITY_SNAPSHOT:
            seen[s.repo] = Source(**asdict(s))
        for d in self._data.get("discovered", []):
            try:
                s = Source(**d)
            except TypeError:
                continue
            if s.repo in seen:
                seen[s.repo].stars, seen[s.repo].pushed_at = s.stars, s.pushed_at
                if s.description:
                    seen[s.repo].description = s.description
            else:
                seen[s.repo] = s
        for r in self._data.get("custom", []):
            seen.setdefault(r, Source(r, custom=True))
        return sorted(seen.values(), key=lambda s: (-s.stars, s.repo.lower()))

    # -- descubrimiento ---------------------------------------------------------
    def discover(self) -> list[Source]:
        """Busca en GitHub repos del ecosistema; excluye oficiales y forks puros."""
        found: dict[str, Source] = {}
        for q in DISCOVER_QUERIES:
            try:
                for ri in dl.github_search_repos(q, per_page=25):
                    if not ri.full_name or ri.full_name in OFFICIAL_REPOS or ri.fork_of:
                        continue
                    low = (ri.full_name + " " + ri.description).lower()
                    if not any(k in low for k in ("mgu", "idrive", "bmw")):
                        continue
                    found[ri.full_name] = Source(ri.full_name, ri.description, ri.stars, ri.pushed_at[:10])
            except dl.DownloadError as e:
                self._log("WARN", tr(f"Descubrimiento '{q}': {e}", f"Discovery '{q}': {e}"))
        self._data["discovered"] = [asdict(s) for s in found.values()]
        self._save()
        new = [r for r in found if r not in {s.repo for s in COMMUNITY_SNAPSHOT}]
        self._log("OK", tr(f"Descubrimiento: {len(found)} repos del ecosistema ({len(new)} nuevos respecto a la instantanea).",
                           f"Discovery: {len(found)} ecosystem repos ({len(new)} new compared with the snapshot)."))
        return self.all_known()
