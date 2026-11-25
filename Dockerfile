FROM python:3.11-slim

# Instalar FFmpeg y herramientas básicas del sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Crear usuario no-root requerido por Hugging Face Spaces
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Instalar dependencias de Python
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copiar únicamente el motor y la carpeta web
COPY --chown=user Video.py Audio.py ./
COPY --chown=user web ./web

# Hugging Face Spaces expone el puerto 7860
EXPOSE 7860

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "7860"]