# 1. Usa a imagem que você já tem em cache (Runtime)
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

# 2. Configurações de Proxy (Único modo que sua rede aceita)
ENV http_proxy="http://rafael.goncalves:Rafa280202@proxy.seti.parana:8080"
ENV https_proxy="http://rafael.goncalves:Rafa280202@proxy.seti.parana:8080"
ENV no_proxy="localhost,127.0.0.1,.parana,pr.gov.br"

# 3. Variáveis de ambiente Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive 

WORKDIR /app

# 4. Configuração do APT para atravessar o proxy corporativo
RUN echo "Acquire::http::Verify-Peer \"false\";" > /etc/apt/apt.conf.d/99verify-peer.conf && \
    echo 'Acquire::http::Proxy "http://rafael.goncalves:Rafa280202@proxy.seti.parana:8080";' > /etc/apt/apt.conf.d/proxy.conf && \
    echo 'Acquire::https::Proxy "http://rafael.goncalves:Rafa280202@proxy.seti.parana:8080";' >> /etc/apt/apt.conf.d/proxy.conf && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    tesseract-ocr \
    tesseract-ocr-por \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

COPY requirements.txt .

# 5. Instalação do llama-cpp-python via binário pronto (Wheel)
# Isso ignora a compilação e resolve o erro de "CMake build failed"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir llama-cpp-python \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu122 \
    --trusted-host abetlen.github.io \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org

# 6. Instala as demais dependências
RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

# 7. Finalização do Image
COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]