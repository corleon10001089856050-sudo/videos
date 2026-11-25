import os
import sys
import uuid
import shutil
import threading
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import Video as video_engine
import Audio as audio_engine

app = FastAPI(title="VeloStrea Web - Prueba 2")

CARPETA_TEMP_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "temp_descargas"))
os.makedirs(CARPETA_TEMP_BASE, exist_ok=True)

# Lock simple para evitar colisiones al cambiar la carpeta global en Video.py / Audio.py
_lock_descarga = threading.Lock()


class SolicitudUrl(BaseModel):
    url: str


class SolicitudDescarga(BaseModel):
    url: str
    tipo: str          # "video" o "audio"
    calidad: int       # ej. 480, 360 o 320, 128
    formato_audio: str = "mp3"


def limpiar_carpeta_temp(ruta_carpeta: str):
    shutil.rmtree(ruta_carpeta, ignore_errors=True)


@app.get("/", response_class=HTMLResponse)
def inicio():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>VeloStrea Web - Prueba 2</title>
        <style>
            body { background: #141619; color: #F3F4F6; font-family: sans-serif; padding: 40px; max-width: 720px; margin: auto; }
            .box { background: #1C1F24; border: 1px solid #2F353F; border-radius: 8px; padding: 20px; }
            .row { display: flex; gap: 8px; margin-bottom: 12px; }
            input, select { padding: 10px; background: #141619; border: 1px solid #2F353F; color: #fff; border-radius: 4px; }
            input { flex: 1; }
            button { padding: 10px 16px; background: #3B82F6; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
            button:disabled { background: #374151; cursor: not-allowed; }
            .btn-verde { background: #22C55E; color: #052E16; }
            .card { background: #141619; border: 1px solid #2F353F; padding: 15px; border-radius: 6px; margin-top: 15px; display: none; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>VeloStrea Web — Prueba 2 (Análisis + Descarga)</h2>
            <div class="row">
                <input type="text" id="url" placeholder="Pega un enlace de YouTube...">
                <button id="btnAnalizar" onclick="analizar()">Analizar</button>
            </div>
            <p id="estado" style="color: #9CA3AF; font-size: 14px;"></p>

            <div id="panelDescarga" class="card">
                <h3 id="titulo" style="margin-top:0;"></h3>
                <p id="canal" style="color: #9CA3AF; font-size: 13px;"></p>

                <div class="row">
                    <select id="tipo" onchange="actualizarOpciones()">
                        <option value="video">Video (MP4)</option>
                        <option value="audio">Audio</option>
                    </select>
                    <select id="calidad"></select>
                    <select id="formatoAudio" style="display:none;">
                        <option value="mp3">MP3</option>
                        <option value="m4a">M4A</option>
                        <option value="wav">WAV</option>
                    </select>
                    <button id="btnDescargar" class="btn-verde" onclick="descargar()">Descargar</button>
                </div>
            </div>
        </div>

        <script>
            let datosActuales = null;

            async function analizar() {
                const url = document.getElementById("url").value.trim();
                const btn = document.getElementById("btnAnalizar");
                const estado = document.getElementById("estado");
                const panel = document.getElementById("panelDescarga");

                if (!url) return alert("Pega una URL primero");

                btn.disabled = true;
                panel.style.display = "none";
                estado.textContent = "Analizando enlace...";

                try {
                    const resp = await fetch("/api/analizar", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ url })
                    });
                    const data = await resp.json();
                    if (!resp.ok) throw new Error(data.detail || "Error al analizar");

                    datosActuales = data;
                    document.getElementById("titulo").textContent = data.titulo;
                    document.getElementById("canal").textContent = "Canal: " + data.canal;
                    actualizarOpciones();

                    panel.style.display = "block";
                    estado.textContent = "✅ Listo para descargar";
                } catch (err) {
                    estado.textContent = "❌ " + err.message;
                } finally {
                    btn.disabled = false;
                }
            }

            function actualizarOpciones() {
                if (!datosActuales) return;
                const tipo = document.getElementById("tipo").value;
                const selCal = document.getElementById("calidad");
                const selFmt = document.getElementById("formatoAudio");
                selCal.innerHTML = "";

                if (tipo === "video") {
                    selFmt.style.display = "none";
                    datosActuales.calidades_video.forEach(c => {
                        const opt = document.createElement("option");
                        opt.value = c;
                        opt.textContent = c + "p";
                        selCal.appendChild(opt);
                    });
                } else {
                    selFmt.style.display = "inline-block";
                    [320, 256, 192, 128].forEach(c => {
                        const opt = document.createElement("option");
                        opt.value = c;
                        opt.textContent = c + " kbps";
                        selCal.appendChild(opt);
                    });
                }
            }

            async function descargar() {
                const btn = document.getElementById("btnDescargar");
                const estado = document.getElementById("estado");
                const payload = {
                    url: datosActuales.url_limpia,
                    tipo: document.getElementById("tipo").value,
                    calidad: parseInt(document.getElementById("calidad").value),
                    formato_audio: document.getElementById("formatoAudio").value
                };

                btn.disabled = true;
                estado.textContent = "⏳ Descargando y procesando con FFmpeg en el servidor... (espera un momento)";

                try {
                    const resp = await fetch("/api/descargar", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                    });

                    if (!resp.ok) {
                        const errData = await resp.json();
                        throw new Error(errData.detail || "Error en descarga");
                    }

                    // Obtener nombre de archivo desde la cabecera Content-Disposition
                    const disp = resp.headers.get("Content-Disposition") || "";
                    let filename = payload.tipo === "video" ? "video.mp4" : "audio." + payload.formato_audio;
                    const match = disp.match(/filename\*=UTF-8''(.+)/i) || disp.match(/filename="(.+)"/i);
                    if (match && match[1]) filename = decodeURIComponent(match[1]);

                    const blob = await resp.blob();
                    const link = document.createElement("a");
                    link.href = URL.createObjectURL(blob);
                    link.download = filename;
                    document.body.appendChild(link);
                    link.click();
                    link.remove();

                    estado.textContent = "✅ ¡Descarga entregada al navegador y temporal limpiado!";
                } catch (err) {
                    estado.textContent = "❌ " + err.message;
                } finally {
                    btn.disabled = false;
                }
            }
        </script>
    </body>
    </html>
    """


@app.post("/api/analizar")
def analizar_video(datos: SolicitudUrl):
    try:
        url_limpia = video_engine.limpiar_url(datos.url)
        info = video_engine.obtener_info(url_limpia)
        calidades_vid = video_engine.obtener_calidades(info)
        formatos_aud = audio_engine.obtener_formatos_audio(info)

        return {
            "url_limpia": url_limpia,
            "titulo": info.get("title", "Sin título"),
            "canal": info.get("uploader") or info.get("channel") or "Desconocido",
            "calidades_video": sorted(calidades_vid.keys(), reverse=True),
            "streams_audio_detectados": len(formatos_aud),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/descargar")
def descargar_archivo(datos: SolicitudDescarga, background_tasks: BackgroundTasks):
    id_trabajo = uuid.uuid4().hex[:10]
    carpeta_trabajo = os.path.join(CARPETA_TEMP_BASE, id_trabajo)
    os.makedirs(carpeta_trabajo, exist_ok=True)

    try:
        url_limpia = video_engine.limpiar_url(datos.url)
        info = video_engine.obtener_info(url_limpia)

        with _lock_descarga:
            if datos.tipo == "video":
                calidades = video_engine.obtener_calidades(info)
                formato = video_engine.buscar_calidad(calidades, datos.calidad)

                carpeta_orig = video_engine.CARPETA_DESCARGAS
                try:
                    video_engine.CARPETA_DESCARGAS = carpeta_trabajo
                    video_engine.descargar_video(url_limpia, datos.calidad, formato)
                finally:
                    video_engine.CARPETA_DESCARGAS = carpeta_orig

            elif datos.tipo == "audio":
                formatos_aud = audio_engine.obtener_formatos_audio(info)
                fmt_sel = audio_engine.seleccionar_audio_mas_cercano(formatos_aud, datos.calidad)
                fmt_dict = {
                    "format_id": fmt_sel["format_id"],
                    "formato_salida": datos.formato_audio.upper(),
                    "extension_salida": datos.formato_audio.lower(),
                }

                carpeta_orig = audio_engine.CARPETA_AUDIO
                try:
                    audio_engine.CARPETA_AUDIO = carpeta_trabajo
                    audio_engine.descargar_audio(url_limpia, datos.calidad, fmt_dict)
                finally:
                    audio_engine.CARPETA_AUDIO = carpeta_orig
            else:
                raise ValueError("Tipo inválido. Usa 'video' o 'audio'.")

        archivos = os.listdir(carpeta_trabajo)
        if not archivos:
            raise RuntimeError("No se generó ningún archivo tras la descarga.")

        ruta_final = os.path.join(carpeta_trabajo, archivos[0])

        # Programar borrado de la carpeta temporal justo después de enviar el archivo
        background_tasks.add_task(limpiar_carpeta_temp, carpeta_trabajo)

        return FileResponse(
            path=ruta_final,
            filename=archivos[0],
            media_type="application/octet-stream",
        )

    except Exception as e:
        limpiar_carpeta_temp(carpeta_trabajo)
        raise HTTPException(status_code=400, detail=str(e))
