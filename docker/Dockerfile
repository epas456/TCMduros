# durosTCM (servidor + interfaz). La GPU la aportan los contenedores de ComfyUI/Ollama.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu fonts-inter espeak-ng && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY durostcm ./durostcm
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir "kokoro>=0.9" soundfile || true
ENV DUROSTCM_HOME=/data
EXPOSE 7777
CMD ["python", "-m", "durostcm", "serve", "--host", "0.0.0.0", "--port", "7777", "--no-browser"]
