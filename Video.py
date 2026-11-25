import os
import sys
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import yt_dlp


# ============================================================
# CONFIGURACIÓN
# ============================================================

CARPETA_DESCARGAS = "videos"

# Prioridad de codecs.
# Un número MENOR significa mayor prioridad.
PRIORIDAD_CODECS = {
    "avc1": 1,
    "avc": 1,
    "h264": 1,

    "vp9": 2,
    "vp09": 2,

    "av01": 3,
    "av1": 3,

    "vp8": 4,
    "vp08": 4,
}

# Categorías de calidad reconocidas.
# NO representan las calidades disponibles.
# Solamente sirven para clasificar los streams encontrados.
CALIDADES_YOUTUBE = [
    (3800, 2160),
    (2500, 1440),
    (1900, 1080),
    (1200, 720),
    (800, 480),
    (600, 360),
    (400, 240),
    (250, 144),
]


# ============================================================
# LOGGER
# ============================================================

class VeloStreaLogger:
    """
    Logger sencillo para mostrar advertencias y errores de yt-dlp
    sin ocultarlos.
    """

    def debug(self, msg):
        # No mostramos todos los mensajes internos de debug.
        pass

    def warning(self, msg):
        print()
        print("[ADVERTENCIA yt-dlp]")
        print(msg)
        print()

    def error(self, msg):
        print()
        print("[ERROR yt-dlp]")
        print(msg)
        print()


# ============================================================
# LIMPIAR URL
# ============================================================

def limpiar_url(url):
    """
    Elimina parámetros innecesarios y conserva únicamente
    el parámetro 'v' de una URL de YouTube.

    Ejemplo:

    https://www.youtube.com/watch?v=ABC123&list=XYZ&index=4

    se convierte en:

    https://www.youtube.com/watch?v=ABC123
    """

    url = url.strip()

    if not url:
        raise ValueError("La URL está vacía.")

    try:
        parsed = urlparse(url)

        # ----------------------------------------------------
        # YouTube normal:
        # youtube.com/watch?v=XXXXXXXX
        # ----------------------------------------------------
        if parsed.hostname:
            hostname = parsed.hostname.lower()

            if "youtube.com" in hostname:
                parametros = parse_qs(parsed.query)

                video_id = parametros.get("v", [None])[0]

                if not video_id:
                    raise ValueError(
                        "No se encontró el parámetro 'v' en la URL de YouTube."
                    )

                return urlunparse((
                    "https",
                    "www.youtube.com",
                    "/watch",
                    "",
                    urlencode({"v": video_id}),
                    ""
                ))

            # ------------------------------------------------
            # youtu.be/XXXXXXXX
            # ------------------------------------------------
            if "youtu.be" in hostname:
                video_id = parsed.path.strip("/").split("/")[0]

                if not video_id:
                    raise ValueError(
                        "No se pudo obtener el ID del video."
                    )

                return (
                    "https://www.youtube.com/watch?"
                    + urlencode({"v": video_id})
                )

        raise ValueError("La URL no parece ser una URL válida de YouTube.")

    except Exception as e:
        raise ValueError(f"No se pudo limpiar la URL: {e}")


# ============================================================
# OBTENER INFORMACIÓN
# ============================================================

def obtener_info(url):
    """
    Consulta yt-dlp y devuelve toda la información disponible
    del video sin descargarlo.
    """

    ydl_opts = {
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "logger": VeloStreaLogger(),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise RuntimeError(
                "yt-dlp no devolvió información del video."
            )

        return info

    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(
            f"Error de yt-dlp al obtener información:\n{e}"
        )

    except Exception as e:
        raise RuntimeError(
            f"Error al obtener información del video:\n{e}"
        )

# ============================================================
# DETECTAR PLAYLIST
# ============================================================

def detectar_playlist(url):
    """
    Detecta si la URL corresponde a una playlist de YouTube
    y devuelve sus videos.
    """

    opciones = {
        "extract_flat": "in_playlist",
        "quiet": False,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=False)

        if info.get("_type") != "playlist":
            return None

        entradas = []

        for video in info.get("entries", []):
            if not video:
                continue

            video_id = video.get("id")

            if not video_id:
                continue

            entradas.append({
                "id": video_id,
                "title": video.get("title", "Sin título"),
                "url": (
                    "https://www.youtube.com/watch?"
                    + urlencode({"v": video_id})
                )
            })

        return {
            "id": info.get("id"),
            "title": info.get("title", "Playlist sin título"),
            "entries": entradas
        }

    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(
            f"Error al detectar la playlist:\n{e}"
        )

# ============================================================
# IDENTIFICAR CALIDAD DE YOUTUBE
# ============================================================

def calidad_youtube(width, height=None):
    """
    Determina la categoría de calidad de YouTube utilizando
    principalmente el ancho real del stream.

    Esto permite casos como:

        1920x810  -> 1080p
        2560x1080 -> 1440p
        3840x1620 -> 2160p

    NO utiliza height directamente como nombre de calidad.
    """

    if not width:
        return None

    try:
        width = int(width)
    except (ValueError, TypeError):
        return None

    for ancho_minimo, calidad in CALIDADES_YOUTUBE:
        if width >= ancho_minimo:
            return calidad

    return None


# ============================================================
# OBTENER PRIORIDAD DEL CODEC
# ============================================================

def prioridad_codec(vcodec):
    """
    Devuelve la prioridad numérica del codec.

    AVC/H.264 -> 1
    AV1       -> 2
    VP9       -> 3
    Otros     -> 99
    """

    if not vcodec:
        return 99

    codec = vcodec.lower()

    # Buscar coincidencias conocidas.
    for nombre, prioridad in PRIORIDAD_CODECS.items():
        if codec.startswith(nombre):
            return prioridad

    return 99



def puntuacion_formato(candidato, bitrate_maximo):
    """
    Calcula una puntuación equilibrada para seleccionar
    la mejor variante dentro de una misma calidad.

    No permite que codec, protocolo o bitrate sean
    absolutamente dominantes.

    Se consideran:

        - Compatibilidad del codec
        - Bitrate
        - Protocolo
        - Resolución real
        - FPS
    """

    # --------------------------------------------------------
    # BITRATE
    #
    # Se normaliza respecto al bitrate más alto encontrado
    # dentro de la misma calidad.
    # --------------------------------------------------------

    bitrate = candidato["tbr"]

    if bitrate_maximo > 0:
        porcentaje_bitrate = bitrate / bitrate_maximo
    else:
        porcentaje_bitrate = 0

    # --------------------------------------------------------
    # CODEC
    #
    # H.264 obtiene una pequeña ventaja por compatibilidad.
    # VP9 y AV1 pueden competir mediante bitrate.
    # --------------------------------------------------------

    p_codec = candidato["prioridad_codec"]

    if p_codec == 1:
        bonus_codec = 0.15
    elif p_codec == 2:
        bonus_codec = 0.05
    elif p_codec == 3:
        bonus_codec = 0.00
    else:
        bonus_codec = -0.10

    # --------------------------------------------------------
    # PROTOCOLO
    #
    # HTTPS/DASH se prefiere ligeramente sobre M3U8/HLS.
    #
    # Importante:
    # No eliminamos M3U8.
    # Solamente recibe una pequeña penalización.
    # --------------------------------------------------------

    protocolo = (candidato["protocol"] or "").lower()

    if protocolo in ("https", "http"):
        bonus_protocolo = 0.10
    elif protocolo in ("m3u8", "m3u8_native", "m3u8"):
        bonus_protocolo = -0.05
    else:
        bonus_protocolo = 0.00

    # --------------------------------------------------------
    # RESOLUCIÓN
    #
    # Se utiliza como pequeño desempate.
    # La calidad ya fue filtrada anteriormente.
    # --------------------------------------------------------

    resolucion = candidato["width"] * candidato["height"]

    # La resolución se normaliza de forma sencilla.
    #
    # No queremos que una diferencia mínima de resolución
    # domine sobre bitrate o codec.
    # --------------------------------------------------------

    bonus_resolucion = min(resolucion / 8_294_400, 1.0) * 0.05

    # --------------------------------------------------------
    # FPS
    #
    # Pequeña ventaja para FPS altos.
    # --------------------------------------------------------

    fps = candidato["fps"]

    if fps >= 60:
        bonus_fps = 0.05
    elif fps >= 30:
        bonus_fps = 0.025
    else:
        bonus_fps = 0.00

    # --------------------------------------------------------
    # PUNTUACIÓN FINAL
    #
    # El bitrate tiene mucho peso.
    # Codec y protocolo aportan ventajas pequeñas.
    # --------------------------------------------------------

    puntuacion = (
        porcentaje_bitrate * 0.70
        + bonus_codec
        + bonus_protocolo
        + bonus_resolucion
        + bonus_fps
    )

    return puntuacion





# ============================================================
# OBTENER CALIDADES
# ============================================================

def obtener_calidades(info):
    """
    Analiza info['formats'], elimina formatos que no sirven
    para video y agrupa los streams por calidad de YouTube.

    La selección se realiza únicamente entre formatos
    pertenecientes a la misma calidad.

    Ejemplo:

        3840x2160 -> 2160p

    Un formato 1080p nunca podrá competir contra uno 2160p.

    La elección final considera conjuntamente:

        - video-only
        - protocolo
        - codec
        - bitrate
        - resolución
        - FPS
    """

    formatos = info.get("formats", [])

    if not formatos:
        raise RuntimeError(
            "yt-dlp no proporcionó formatos para este video."
        )

    # --------------------------------------------------------
    # Primero agrupamos TODOS los candidatos por calidad.
    # --------------------------------------------------------

    grupos_candidatos = {}

    for formato in formatos:

        format_id = formato.get("format_id")
        width = formato.get("width")
        height = formato.get("height")
        vcodec = formato.get("vcodec")
        acodec = formato.get("acodec")
        ext = formato.get("ext")
        fps = formato.get("fps")
        tbr = formato.get("tbr")
        protocol = formato.get("protocol")

        # ----------------------------------------------------
        # Formato válido.
        # ----------------------------------------------------

        if not format_id:
            continue

        if not width or not height:
            continue

        # ----------------------------------------------------
        # Debe contener video.
        # ----------------------------------------------------

        if not vcodec or vcodec == "none":
            continue

        # ----------------------------------------------------
        # Determinar calidad.
        # ----------------------------------------------------

        calidad = calidad_youtube(width, height)

        if calidad is None:
            continue

        # ----------------------------------------------------
        # Debe tener protocolo.
        # ----------------------------------------------------

        if not protocol:
            continue

        # ----------------------------------------------------
        # Determinar si tiene audio.
        # ----------------------------------------------------

        tiene_audio = (
            acodec is not None
            and acodec != "none"
        )

        # ----------------------------------------------------
        # Preferimos video-only.
        #
        # Esto se mantiene igual que en tu lógica original.
        # ----------------------------------------------------

        prioridad_audio = 1 if not tiene_audio else 2

        # ----------------------------------------------------
        # Codec.
        # ----------------------------------------------------

        p_codec = prioridad_codec(vcodec)

        # ----------------------------------------------------
        # Bitrate.
        # ----------------------------------------------------

        try:
            bitrate = float(tbr or 0)
        except (ValueError, TypeError):
            bitrate = 0

        # ----------------------------------------------------
        # FPS.
        # ----------------------------------------------------

        try:
            fps_num = float(fps or 0)
        except (ValueError, TypeError):
            fps_num = 0

        # ----------------------------------------------------
        # Crear candidato.
        # ----------------------------------------------------

        candidato = {
            "format_id": str(format_id),
            "calidad": calidad,
            "width": int(width),
            "height": int(height),
            "fps": fps_num,
            "vcodec": vcodec,
            "acodec": acodec,
            "ext": ext or "unknown",
            "tbr": bitrate,
            "protocol": protocol,
            "tiene_audio": tiene_audio,
            "prioridad_codec": p_codec,
            "prioridad_audio": prioridad_audio,
            "formato_original": formato,
        }

        # ----------------------------------------------------
        # Agrupar por calidad.
        # ----------------------------------------------------

        if calidad not in grupos_candidatos:
            grupos_candidatos[calidad] = []

        grupos_candidatos[calidad].append(candidato)

    # --------------------------------------------------------
    # Verificar que encontramos formatos.
    # --------------------------------------------------------

    if not grupos_candidatos:
        raise RuntimeError(
            "No se encontraron formatos de video compatibles."
        )

    # --------------------------------------------------------
    # Seleccionar el mejor candidato de cada calidad.
    # --------------------------------------------------------

    grupos = {}

    for calidad, candidatos in grupos_candidatos.items():

        # ----------------------------------------------------
        # Primero damos preferencia a video-only.
        #
        # Si existe al menos un video-only, no competirá
        # contra formatos que ya tengan audio.
        # ----------------------------------------------------

        candidatos_video_only = [
            c for c in candidatos
            if not c["tiene_audio"]
        ]

        if candidatos_video_only:
            candidatos = candidatos_video_only

        # ----------------------------------------------------
        # Obtener bitrate máximo dentro de ESTA calidad.
        # ----------------------------------------------------

        bitrate_maximo = max(
            (c["tbr"] for c in candidatos),
            default=0
        )

        # ----------------------------------------------------
        # Calcular puntuación.
        # ----------------------------------------------------

        mejor = None
        mejor_puntuacion = None

        for candidato in candidatos:

            puntuacion = puntuacion_formato(
                candidato,
                bitrate_maximo
            )

            # ------------------------------------------------
            # Desempate:
            #
            # 1. puntuación
            # 2. bitrate
            # 3. resolución
            # 4. FPS
            #
            # El codec NO vuelve a ser criterio absoluto.
            # ------------------------------------------------

            if mejor is None:
                mejor = candidato
                mejor_puntuacion = puntuacion
                continue

            if puntuacion > mejor_puntuacion:
                mejor = candidato
                mejor_puntuacion = puntuacion
                continue

            if puntuacion == mejor_puntuacion:

                if candidato["tbr"] > mejor["tbr"]:
                    mejor = candidato
                    mejor_puntuacion = puntuacion
                    continue

                if (
                    candidato["tbr"] == mejor["tbr"]
                    and (
                        candidato["width"]
                        * candidato["height"]
                    )
                    > (
                        mejor["width"]
                        * mejor["height"]
                    )
                ):
                    mejor = candidato
                    mejor_puntuacion = puntuacion
                    continue

                if (
                    candidato["tbr"] == mejor["tbr"]
                    and candidato["fps"] > mejor["fps"]
                ):
                    mejor = candidato
                    mejor_puntuacion = puntuacion

        if mejor is not None:
            grupos[calidad] = mejor

    # --------------------------------------------------------
    # Ordenar calidades.
    # --------------------------------------------------------

    return dict(sorted(grupos.items()))


# ============================================================
# MOSTRAR CALIDADES
# ============================================================

def mostrar_calidades(calidades):
    """
    Muestra las calidades encontradas dinámicamente.
    """

    print()
    print("=" * 70)
    print(" CALIDADES DISPONIBLES")
    print("=" * 70)

    opciones = list(calidades.items())

    for indice, (calidad, formato) in enumerate(opciones, start=1):

        fps = formato["fps"]

        if fps:
            fps_texto = f"{fps:g} FPS"
        else:
            fps_texto = "FPS N/D"

        codec = formato["vcodec"]

        print(
            f"[{indice}] "
            f"{calidad}p | "
            f"{formato['width']}x{formato['height']} | "
            f"{fps_texto} | "
            f"{codec} | "
            f"{formato['ext'].upper()}"
        )

    print()

    return opciones


# ============================================================
# SELECCIONAR CALIDAD
# ============================================================

def seleccionar_calidad(opciones):
    """
    Permite al usuario seleccionar una calidad de la lista.
    """

    while True:

        try:
            entrada = input("Selecciona la calidad: ").strip()

            if not entrada:
                print("Debes seleccionar una opción.")
                continue

            numero = int(entrada)

            if numero < 1 or numero > len(opciones):
                print("Opción fuera de rango.")
                continue

            calidad, formato = opciones[numero - 1]

            return calidad, formato

        except ValueError:
            print("Introduce solamente el número de la opción.")


# ============================================================
# BUSCAR CALIDAD
# ============================================================

def buscar_calidad(calidades, calidad):
    """
    Busca una calidad específica dentro de las calidades
    disponibles de un video.
    """

    if calidad not in calidades:
        raise RuntimeError(
            f"El video no dispone de calidad {calidad}p."
        )

    return calidades[calidad]

# ============================================================
# DESCARGAR VIDEO
# ============================================================

def descargar_video(url, calidad, formato):
    """
    Descarga el formato de video seleccionado y lo combina
    con el mejor audio disponible.

    Se utiliza:

        video_format_id + bestaudio

    evitando seleccionar una calidad de video superior.
    """

    os.makedirs(CARPETA_DESCARGAS, exist_ok=True)

    format_id = formato["format_id"]

    print()
    print("=" * 70)
    print(f" DESCARGANDO {calidad}p")
    print("=" * 70)

    print(f"Format ID seleccionado : {format_id}")
    print(f"Resolución real        : "
        f"{formato['width']}x{formato['height']}")

    print(f"Codec                  : {formato['vcodec']}")

    print(f"Bitrate                : "
        f"{formato['tbr']:g} kbps")

    print(f"Protocolo              : "
        f"{formato['protocol']}")

    print(f"Contenedor video       : "
        f"{formato['ext']}")

    # --------------------------------------------------------
    # Primero intentamos:
    #
    # VIDEO EXACTO SELECCIONADO + MEJOR AUDIO M4A
    #
    # Si no existe m4a, usamos cualquier mejor audio.
    #
    # Finalmente existe fallback a un formato combinado.
    # --------------------------------------------------------

    selector = (
        f"{format_id}+bestaudio[ext=m4a]/"
        f"{format_id}+bestaudio/"
        f"{format_id}"
    )

    ydl_opts = {
        "format": selector,

        "noplaylist": True,

        "outtmpl": os.path.join(
            CARPETA_DESCARGAS,
            "%(title)s.%(ext)s"
        ),

        # ----------------------------------------------------
        # FFmpeg se encargará de realizar la combinación.
        # ----------------------------------------------------
        "merge_output_format": "mp4",

        # ----------------------------------------------------
        # Evitar que yt-dlp intente descargar playlists.
        # ----------------------------------------------------
        "playlist_items": "1",

        # ----------------------------------------------------
        # Logger.
        # ----------------------------------------------------
        "logger": VeloStreaLogger(),

        # ----------------------------------------------------
        # Mostrar progreso.
        # ----------------------------------------------------
        "progress_hooks": [progreso_descarga],

        # ----------------------------------------------------
        # Continúa descargas parciales cuando sea posible.
        # ----------------------------------------------------
        "continuedl": True,

        # ----------------------------------------------------
        # Reintentos.
        # ----------------------------------------------------
        "retries": 10,

        # ----------------------------------------------------
        # FFmpeg debe estar disponible en PATH.
        # Si no está en PATH, yt-dlp mostrará el error.
        # ----------------------------------------------------
    }

    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            resultado = ydl.download([url])

        if resultado != 0:
            raise RuntimeError(
                f"yt-dlp terminó con código de salida {resultado}."
            )

        print()
        print("=" * 70)
        print(" DESCARGA COMPLETADA")
        print("=" * 70)
        print(f"Calidad : {calidad}p")
        print("Formato : MP4")
        print(f"Carpeta : {CARPETA_DESCARGAS}")
        print()

    except yt_dlp.utils.DownloadError as e:

        mensaje = str(e)

        print()
        print("=" * 70)
        print(" ERROR DURANTE LA DESCARGA")
        print("=" * 70)
        print(mensaje)
        print()

        if "ffmpeg" in mensaje.lower():
            print("Posible problema con FFmpeg.")
            print("Verifica que FFmpeg esté instalado y disponible")
            print("en el PATH del sistema.")

        raise RuntimeError(
            "La descarga no pudo completarse."
        )

    except Exception as e:

        print()
        print("=" * 70)
        print(" ERROR")
        print("=" * 70)
        print(str(e))
        print()

        raise RuntimeError(
            "Ocurrió un error durante la descarga."
        )


# ============================================================
# PROGRESO
# ============================================================

def progreso_descarga(d):
    """
    Muestra información del progreso de yt-dlp.
    """

    estado = d.get("status")

    if estado == "downloading":

        porcentaje = d.get("_percent_str", "").strip()
        velocidad = d.get("_speed_str", "").strip()
        eta = d.get("_eta_str", "").strip()

        print(
            f"\rDescargando: {porcentaje} | "
            f"Velocidad: {velocidad} | "
            f"ETA: {eta}",
            end="",
            flush=True
        )

    elif estado == "finished":

        print()
        print("Descarga del stream terminada.")
        print("FFmpeg procesará los streams si es necesario.")


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(" VELOSTREA YOUTUBE DOWNLOADER")
    print("=" * 70)
    print()

    try:

        # ----------------------------------------------------
        # URL
        # ----------------------------------------------------

        url_original = input(
            "Pega el enlace de YouTube:\n\n> "
        ).strip()

        if not url_original:
            raise ValueError("No se introdujo ninguna URL.")

        # ----------------------------------------------------
        # DETECTAR PLAYLIST ANTES DE LIMPIAR URL
        # ----------------------------------------------------

        playlist = detectar_playlist(url_original)

        # ====================================================
        # PLAYLIST
        # ====================================================

        if playlist:

            entradas = playlist["entries"]

            if not entradas:
                raise RuntimeError(
                    "La playlist no contiene videos disponibles."
                )

            print()
            print("=" * 70)
            print(" PLAYLIST DETECTADA")
            print("=" * 70)
            print(f"Título : {playlist['title']}")
            print(f"Videos : {len(entradas)}")
            print("=" * 70)

            # ------------------------------------------------
            # Analizar primer video para seleccionar calidad
            # ------------------------------------------------

            primer_video = entradas[0]

            print()
            print("=" * 70)
            print(" ANALIZANDO PRIMER VIDEO")
            print("=" * 70)
            print()

            info = obtener_info(primer_video["url"])

            titulo = info.get(
                "title",
                primer_video["title"]
            )

            print(f"Título:\n{titulo}")

            calidades = obtener_calidades(info)

            opciones = mostrar_calidades(calidades)

            calidad, formato = seleccionar_calidad(opciones)

            print()
            print(f"Calidad seleccionada para la playlist: {calidad}p")

            # ------------------------------------------------
            # Descargar todos los videos
            # ------------------------------------------------

            for numero, video in enumerate(entradas, start=1):

                print()
                print("=" * 70)
                print(
                    f" VIDEO {numero}/{len(entradas)}"
                )
                print("=" * 70)
                print(f"Título: {video['title']}")
                print()

                try:

                    # ----------------------------------------
                    # El primer video ya fue analizado
                    # ----------------------------------------

                    if numero == 1:

                        formato_video = formato

                    else:

                        info_video = obtener_info(
                            video["url"]
                        )

                        calidades_video = obtener_calidades(
                            info_video
                        )

                        formato_video = buscar_calidad(
                            calidades_video,
                            calidad
                        )

                    # ----------------------------------------
                    # Usar tu función actual
                    # ----------------------------------------

                    descargar_video(
                        video["url"],
                        calidad,
                        formato_video
                    )

                except Exception as e:

                    print()
                    print("=" * 70)
                    print(" ERROR EN ESTE VIDEO")
                    print("=" * 70)
                    print(f"Título: {video['title']}")
                    print(f"Error: {e}")
                    print()
                    print("Continuando con el siguiente video...")
                    print()

            print()
            print("=" * 70)
            print(" PLAYLIST FINALIZADA")
            print("=" * 70)
            print()

            return

        # ====================================================
        # VIDEO INDIVIDUAL
        # ====================================================

        url = limpiar_url(url_original)

        print()
        print("URL original:")
        print(url_original)

        print()
        print("URL limpia:")
        print(url)

        print()
        print("=" * 70)
        print(" ANALIZANDO VIDEO")
        print("=" * 70)
        print()

        info = obtener_info(url)

        titulo = info.get("title", "Título desconocido")

        print(f"Título:\n{titulo}")

        calidades = obtener_calidades(info)

        opciones = mostrar_calidades(calidades)

        calidad, formato = seleccionar_calidad(opciones)

        print()
        print(f"Has seleccionado: {calidad}p")
        print(
            f"Stream: {formato['format_id']} "
            f"({formato['width']}x{formato['height']})"
        )

        descargar_video(
            url,
            calidad,
            formato
        )

    except KeyboardInterrupt:

        print()
        print()
        print("Operación cancelada por el usuario.")

    except Exception as e:

        print()
        print("=" * 70)
        print(" PROGRAMA FINALIZADO CON ERROR")
        print("=" * 70)
        print(str(e))

    finally:

        print()
        input("Presiona ENTER para cerrar...")

# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()