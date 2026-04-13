FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

ENV http_proxy="http://rafael.goncalves:Rafa280202@proxy.seti.parana:8080"
ENV https_proxy="http://rafael.goncalves:Rafa280202@proxy.seti.parana:8080"
ENV no_proxy="localhost,127.0.0.1,.parana,pr.gov.br"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive 
ENV CMAKE_ARGS="-DGGML_CUDA=on"

WORKDIR /app

RUN echo "Acquire::http::Verify-Peer \"false\";" > /etc/apt/apt.conf.d/99verify-peer.conf && \
    echo 'Acquire::http::Proxy "http://rafael.goncalves:Rafa280202@proxy.seti.parana:8080";' > /etc/apt/apt.conf.d/proxy.conf && \
    echo 'Acquire::https::Proxy "http://rafael.goncalves:Rafa280202@proxy.seti.parana:8080";' >> /etc/apt/apt.conf.d/proxy.conf && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    tesseract-ocr \
    tesseract-ocr-por \
    poppler-utils \
    git \
    cmake \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

COPY requirements.txt .
COPY wheels/ ./wheels/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ./wheels/*.whl

RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt \
    pycryptodome

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]