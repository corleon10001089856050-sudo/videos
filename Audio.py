import os
import sys
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import yt_dlp


# ============================================================
# CONFIGURACIÓN
# ============================================================

CARPETA_AUDIO = "audio"

# Calidades que verá el usuario.
# NO representan necesariamente las calidades reales de YouTube.
CALIDADES_AUDIO = [
    320,
    256,
    192,
    160,
    128,
    96,
    64,
]

# Formatos de salida disponibles.
FORMATOS_SALIDA = [
    ("MP3", "mp3"),
    ("M4A", "m4a"),
    ("WAV", "wav"),
    ("FLAC", "flac"),
    ("OPUS", "opus"),
    ("AAC", "aac"),
]


# ============================================================
# LOGGER
# ============================================================

class VeloStreaLogger:
    """
    Logger sencillo para mostrar advertencias y errores de yt-dlp
    sin mostrar mensajes internos innecesarios.
    """

    def debug(self, msg):
        # No mostramos mensajes internos de debug.
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

        raise ValueError(
            "La URL no parece ser una URL válida de YouTube."
        )

    except Exception as e:
        raise ValueError(f"No se pudo limpiar la URL: {e}")


# ============================================================
# DETECTAR PLAYLIST
# ============================================================

def detectar_playlist(url):
    """
    Detecta si la URL corresponde a una playlist de YouTube.
    Si es playlist, devuelve sus videos.
    Si no es playlist, devuelve None.
    """

    opciones = {
        "extract_flat": "in_playlist",
        "quiet": True,
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
                "title": video.get(
                    "title",
                    "Título desconocido"
                ),
                "url": (
                    "https://www.youtube.com/watch?"
                    + urlencode({"v": video_id})
                ),
            })

        return {
            "id": info.get("id"),
            "title": info.get(
                "title",
                "Playlist sin título"
            ),
            "entries": entradas,
        }

    except Exception as e:
        raise RuntimeError(
            f"No se pudo analizar la playlist:\n{e}"
        )

# ============================================================
# PROCESAR VIDEO DE AUDIO
# ============================================================

def procesar_video_audio(
    url,
    calidad_solicitada,
    formato_descarga
):
    """
    Analiza un video, selecciona el stream de audio más cercano
    y utiliza la función actual descargar_audio().
    """

    info = obtener_info(url)

    titulo = info.get(
        "title",
        "Título desconocido"
    )

    print()
    print("=" * 70)
    print(" ANALIZANDO AUDIO")
    print("=" * 70)
    print()
    print(f"Título:\n{titulo}")

    formatos_audio = obtener_formatos_audio(info)

    formato_seleccionado = (
        seleccionar_audio_mas_cercano(
            formatos_audio,
            calidad_solicitada
        )
    )

    formato_descarga["format_id"] = (
        formato_seleccionado["format_id"]
    )

    descargar_audio(
        url,
        calidad_solicitada,
        formato_descarga
    )    



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
# OBTENER FORMATOS DE AUDIO
# ============================================================

def obtener_formatos_audio(info):
    """
    Analiza info['formats'] y obtiene únicamente formatos
    que contienen audio.

    Se prefieren los streams de audio independientes.
    Si no existen, se permite utilizar un formato que también
    contenga video.

    La información técnica queda oculta al usuario.
    """

    formatos = info.get("formats", [])

    if not formatos:
        raise RuntimeError(
            "yt-dlp no proporcionó formatos para este video."
        )

    audio_only = []
    audio_con_video = []

    for formato in formatos:

        format_id = formato.get("format_id")
        acodec = formato.get("acodec")
        vcodec = formato.get("vcodec")

        if not format_id:
            continue

        # ----------------------------------------------------
        # Debe contener audio.
        # ----------------------------------------------------

        if not acodec or acodec == "none":
            continue

        # ----------------------------------------------------
        # Obtener bitrate de audio.
        #
        # Normalmente yt-dlp proporciona 'abr'.
        # Como respaldo utilizamos 'tbr'.
        # ----------------------------------------------------

        abr = formato.get("abr")

        try:
            bitrate = float(abr or 0)
        except (ValueError, TypeError):
            bitrate = 0

        if bitrate <= 0:
            tbr = formato.get("tbr")

            try:
                bitrate = float(tbr or 0)
            except (ValueError, TypeError):
                bitrate = 0

        if bitrate <= 0:
            continue

        candidato = {
            "format_id": str(format_id),
            "bitrate": bitrate,
            "acodec": acodec,
            "vcodec": vcodec,
            "formato_original": formato,
        }

        # ----------------------------------------------------
        # Preferimos streams exclusivamente de audio.
        # ----------------------------------------------------

        if not vcodec or vcodec == "none":
            audio_only.append(candidato)
        else:
            audio_con_video.append(candidato)

    # --------------------------------------------------------
    # Si existen streams exclusivamente de audio,
    # utilizamos solamente esos.
    # --------------------------------------------------------

    if audio_only:
        candidatos = audio_only
    else:
        candidatos = audio_con_video

    if not candidatos:
        raise RuntimeError(
            "No se encontraron streams de audio compatibles."
        )

    return candidatos


# ============================================================
# SELECCIONAR AUDIO MÁS CERCANO
# ============================================================

def seleccionar_audio_mas_cercano(formatos_audio, calidad_solicitada):
    """
    Selecciona el stream real cuyo bitrate esté más cerca
    de la calidad solicitada.

    Ejemplo:

        Solicitado: 192
        Disponibles: 143, 256

        Resultado: 143

    Otro ejemplo:

        Solicitado: 128
        Disponibles: 129, 160

        Resultado: 129

    Si existe un empate, se prefiere el bitrate mayor.
    """

    if not formatos_audio:
        raise RuntimeError(
            "No hay formatos de audio disponibles."
        )

    mejor = None
    mejor_distancia = None

    for candidato in formatos_audio:

        bitrate = candidato["bitrate"]

        distancia = abs(bitrate - calidad_solicitada)

        if mejor is None:
            mejor = candidato
            mejor_distancia = distancia
            continue

        # ----------------------------------------------------
        # Primera prioridad:
        # menor distancia respecto a la calidad solicitada.
        # ----------------------------------------------------

        if distancia < mejor_distancia:
            mejor = candidato
            mejor_distancia = distancia
            continue

        # ----------------------------------------------------
        # Desempate:
        # si están a la misma distancia, preferimos
        # el bitrate mayor.
        # ----------------------------------------------------

        if distancia == mejor_distancia:
            if bitrate > mejor["bitrate"]:
                mejor = candidato
                mejor_distancia = distancia

    return mejor


# ============================================================
# MOSTRAR CALIDADES DE AUDIO
# ============================================================

def mostrar_calidades_audio():
    """
    Muestra únicamente las calidades estándar que verá
    el usuario.

    No muestra información técnica de YouTube.
    """

    print()
    print("=" * 70)
    print(" CALIDAD DE AUDIO")
    print("=" * 70)

    for indice, calidad in enumerate(CALIDADES_AUDIO, start=1):
        print(f"[{indice}] {calidad} kbps")

    print()


# ============================================================
# SELECCIONAR CALIDAD DE AUDIO
# ============================================================

def seleccionar_calidad_audio():
    """
    Permite seleccionar una calidad estándar.
    """

    while True:

        try:
            entrada = input(
                "Selecciona la calidad: "
            ).strip()

            if not entrada:
                print("Debes seleccionar una opción.")
                continue

            numero = int(entrada)

            if numero < 1 or numero > len(CALIDADES_AUDIO):
                print("Opción fuera de rango.")
                continue

            calidad = CALIDADES_AUDIO[numero - 1]

            return calidad

        except ValueError:
            print(
                "Introduce solamente el número de la opción."
            )


# ============================================================
# MOSTRAR FORMATOS DE SALIDA
# ============================================================

def mostrar_formatos_salida():
    """
    Muestra los formatos de conversión disponibles.
    """

    print()
    print("=" * 70)
    print(" FORMATO DE SALIDA")
    print("=" * 70)

    for indice, (nombre, extension) in enumerate(
        FORMATOS_SALIDA,
        start=1
    ):
        print(f"[{indice}] {nombre}")

    print()


# ============================================================
# SELECCIONAR FORMATO
# ============================================================

def seleccionar_formato():
    """
    Permite seleccionar el formato final del archivo.
    """

    while True:

        try:
            entrada = input(
                "Selecciona el formato: "
            ).strip()

            if not entrada:
                print("Debes seleccionar una opción.")
                continue

            numero = int(entrada)

            if numero < 1 or numero > len(FORMATOS_SALIDA):
                print("Opción fuera de rango.")
                continue

            nombre, extension = FORMATOS_SALIDA[numero - 1]

            return nombre, extension

        except ValueError:
            print(
                "Introduce solamente el número de la opción."
            )


# ============================================================
# PROGRESO
# ============================================================

def progreso_descarga(d):
    """
    Muestra información del progreso de descarga.
    """

    estado = d.get("status")

    if estado == "downloading":

        porcentaje = d.get(
            "_percent_str",
            ""
        ).strip()

        velocidad = d.get(
            "_speed_str",
            ""
        ).strip()

        eta = d.get(
            "_eta_str",
            ""
        ).strip()

        print(
            f"\rDescargando: {porcentaje} | "
            f"Velocidad: {velocidad} | "
            f"ETA: {eta}",
            end="",
            flush=True
        )

    elif estado == "finished":

        print()
        print("Descarga del audio terminada.")
        print("FFmpeg procesará el formato seleccionado.")


# ============================================================
# DESCARGAR AUDIO
# ============================================================

def descargar_audio(
    url,
    calidad_solicitada,
    formato_audio
):
    """
    Descarga el stream de audio seleccionado y lo convierte
    al formato final elegido por el usuario.
    """

    os.makedirs(CARPETA_AUDIO, exist_ok=True)

    format_id = formato_audio["format_id"]

    nombre_formato = formato_audio["formato_salida"]

    extension_salida = formato_audio["extension_salida"]

    print()
    print("=" * 70)
    print(" DESCARGANDO AUDIO")
    print("=" * 70)

    print(
        f"Calidad solicitada: "
        f"{calidad_solicitada} kbps"
    )

    print(
        "Audio disponible más cercano seleccionado."
    )

    print(
        f"Formato de salida: "
        f"{nombre_formato}"
    )

    print()

    # --------------------------------------------------------
    # Opciones específicas de FFmpeg.
    # --------------------------------------------------------

    ydl_opts = {
        # ----------------------------------------------------
        # Utilizamos EXACTAMENTE el stream seleccionado.
        # ----------------------------------------------------

        "format": format_id,

        # ----------------------------------------------------
        # No descargar playlists.
        # ----------------------------------------------------

        "noplaylist": True,

        "playlist_items": "1",

        # ----------------------------------------------------
        # Carpeta y nombre del archivo.
        # ----------------------------------------------------

        "outtmpl": os.path.join(
            CARPETA_AUDIO,
            "%(title)s.%(ext)s"
        ),

        # ----------------------------------------------------
        # Conversión mediante FFmpeg.
        # ----------------------------------------------------

        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": extension_salida,
                "preferredquality": str(
                    int(calidad_solicitada)
                ),
            }
        ],

        # ----------------------------------------------------
        # Logger.
        # ----------------------------------------------------

        "logger": VeloStreaLogger(),

        # ----------------------------------------------------
        # Progreso.
        # ----------------------------------------------------

        "progress_hooks": [
            progreso_descarga
        ],

        # ----------------------------------------------------
        # Continuar descargas parciales.
        # ----------------------------------------------------

        "continuedl": True,

        # ----------------------------------------------------
        # Reintentos.
        # ----------------------------------------------------

        "retries": 10,

        # ----------------------------------------------------
        # Nombres compatibles con Windows.
        # ----------------------------------------------------

        "windowsfilenames": True,
    }

    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            resultado = ydl.download([url])

        if resultado != 0:
            raise RuntimeError(
                f"yt-dlp terminó con código de salida "
                f"{resultado}."
            )

        print()
        print("=" * 70)
        print(" DESCARGA COMPLETADA")
        print("=" * 70)

        print(
            f"Calidad solicitada : "
            f"{calidad_solicitada} kbps"
        )

        print(
            f"Formato            : "
            f"{nombre_formato}"
        )

        print(
            f"Carpeta            : "
            f"{CARPETA_AUDIO}"
        )

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
            print(
                "Verifica que FFmpeg esté instalado "
                "y disponible en el PATH del sistema."
            )

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
# MAIN
# ============================================================

# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(" VELOSTREA AUDIO")
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
            raise ValueError(
                "No se introdujo ninguna URL."
            )

        # ----------------------------------------------------
        # DETECTAR PLAYLIST ANTES DE LIMPIAR URL
        # ----------------------------------------------------

        playlist = detectar_playlist(url_original)

        # ====================================================
        # PLAYLIST
        # ====================================================

        if playlist:

            entradas = playlist["entries"]

            print()
            print("=" * 70)
            print(" PLAYLIST DETECTADA")
            print("=" * 70)
            print(f"ID:      {playlist['id']}")
            print(f"Título:  {playlist['title']}")
            print(f"Videos:  {len(entradas)}")
            print("=" * 70)
            print()

            if not entradas:
                raise RuntimeError(
                    "La playlist no contiene videos disponibles."
                )

            # ------------------------------------------------
            # CALIDAD
            # ------------------------------------------------

            mostrar_calidades_audio()

            calidad_solicitada = seleccionar_calidad_audio()

            # ------------------------------------------------
            # FORMATO
            # ------------------------------------------------

            mostrar_formatos_salida()

            nombre_formato, extension = seleccionar_formato()

            formato_descarga = {
                "format_id": None,
                "formato_salida": nombre_formato,
                "extension_salida": extension,
            }

            # ------------------------------------------------
            # PROCESAR VIDEOS
            # ------------------------------------------------

            total = len(entradas)

            for numero, video in enumerate(
                entradas,
                start=1
            ):

                url_video = video["url"]
                titulo = video["title"]

                print()
                print("=" * 70)
                print(
                    f" VIDEO {numero} DE {total}"
                )
                print("=" * 70)
                print(f"Título: {titulo}")
                print()

                try:

                    procesar_video_audio(
                        url_video,
                        calidad_solicitada,
                        formato_descarga
                    )

                except Exception as e:

                    print()
                    print("=" * 70)
                    print(" ERROR EN ESTE VIDEO")
                    print("=" * 70)
                    print(f"Título: {titulo}")
                    print(f"Error: {e}")
                    print()
                    print(
                        "Continuando con el siguiente video..."
                    )
                    print()

                    continue

            print()
            print("=" * 70)
            print(" PLAYLIST FINALIZADA")
            print("=" * 70)
            print()

        # ====================================================
        # VIDEO INDIVIDUAL
        # ====================================================

        else:

            # ------------------------------------------------
            # Limpiar URL solamente para video individual.
            # ------------------------------------------------

            url = limpiar_url(url_original)

            print()
            print("URL original:")
            print(url_original)

            print()
            print("URL limpia:")
            print(url)

            # ------------------------------------------------
            # Analizar video
            # ------------------------------------------------

            print()
            print("=" * 70)
            print(" ANALIZANDO AUDIO")
            print("=" * 70)
            print()

            info = obtener_info(url)

            titulo = info.get(
                "title",
                "Título desconocido"
            )

            print(f"Título:\n{titulo}")

            # ------------------------------------------------
            # Obtener streams de audio
            # ------------------------------------------------

            formatos_audio = obtener_formatos_audio(info)

            # ------------------------------------------------
            # Seleccionar calidad
            # ------------------------------------------------

            mostrar_calidades_audio()

            calidad_solicitada = seleccionar_calidad_audio()

            formato_seleccionado = (
                seleccionar_audio_mas_cercano(
                    formatos_audio,
                    calidad_solicitada
                )
            )

            # ------------------------------------------------
            # Confirmación
            # ------------------------------------------------

            print()
            print(
                f"Calidad solicitada: "
                f"{calidad_solicitada} kbps"
            )

            print(
                "Audio disponible más cercano seleccionado."
            )

            # ------------------------------------------------
            # Seleccionar formato
            # ------------------------------------------------

            mostrar_formatos_salida()

            nombre_formato, extension = seleccionar_formato()

            # ------------------------------------------------
            # Preparar descarga
            # ------------------------------------------------

            formato_descarga = {
                "format_id":
                    formato_seleccionado["format_id"],
                "formato_salida":
                    nombre_formato,
                "extension_salida":
                    extension,
            }

            # ------------------------------------------------
            # Descargar
            # ------------------------------------------------

            descargar_audio(
                url,
                calidad_solicitada,
                formato_descarga
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

