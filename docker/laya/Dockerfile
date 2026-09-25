FROM python@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b

ARG TORCH_INDEX=cu128
ARG TORCH_VERSION=2.11.0

ENV HF_HOME=/home/laya/.cache/huggingface \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    USE_TF=0 \
    USE_TORCH=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install "torch==${TORCH_VERSION}" --index-url "https://download.pytorch.org/whl/${TORCH_INDEX}" \
    && python -m pip install "laya[serve]==0.3.11" \
    && python -m pip check \
    && python -I -c "import laya; assert laya.__version__ == '0.3.11'"

RUN groupadd --gid 10001 laya \
    && useradd --uid 10001 --gid laya --create-home laya \
    && mkdir -p /home/laya/.cache/huggingface \
    && chown -R laya:laya /home/laya

USER laya
WORKDIR /home/laya
COPY --chown=laya:laya server.py /home/laya/server.py
EXPOSE 8000

ENTRYPOINT ["python", "/home/laya/server.py"]
