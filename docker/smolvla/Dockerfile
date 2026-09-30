# SmolVLA policy training image. Each policy gets its own independent
# image so their dependency sets never collide (spec section 2).
#
# CUDA runtime matched to the training host's driver (RTX 4090, driver
# 580.126.09 / CUDA 13.0 -- forward-compatible with this older cu12.8 build).
# Ubuntu 24.04 for a stock Python 3.12: `lerobot` >=0.5 requires it, and no
# pytorch/pytorch base image ships both cu128 and py312 together.
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv
RUN python3.12 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /workspace

# Match lerobot's pinned torch range (>=2.7,<2.12) with a CUDA 12.8 wheel
# before installing lerobot itself, so pip's resolver finds it already
# satisfied instead of pulling a CPU-only build from the default index.
RUN pip install --no-cache-dir torch==2.7.1 torchvision==0.22.1 \
        --index-url https://download.pytorch.org/whl/cu128
# `lerobot[dataset,smolvla]` (not `[training]`): we drive our own single-GPU
# training loop directly (see train_entrypoint.py) rather than lerobot's own
# accelerate/wandb-based `lerobot-train` CLI, so that extra is skipped --
# `smolvla` itself is still required, it pulls in the `transformers` model
# code SmolVLA's VLM backbone is built from.
RUN pip install --no-cache-dir "lerobot[dataset,smolvla]==0.6.1"

# The worker runs this container as its own uid:gid, not root (see
# worker/docker_runner.py), so anything written outside the bind-mounted
# /workspace/input and /workspace/output needs to be world-writable up
# front -- in particular HF_HOME, which the base-model download below
# populates as root at build time.
ENV HOME=/workspace \
    HF_HOME=/workspace/.cache/huggingface

# SmolVLA finetunes the official pretrained base checkpoint rather than
# training a VLM from random weights (see train_entrypoint.py docstring).
# Bake it into the image at build time so every job starts training
# immediately, instead of re-downloading it from the Hub per job -- and so
# training itself needs no network access at run time. Two repos are
# needed: `lerobot/smolvla_base` (the finetunable policy checkpoint) *and*
# `HuggingFaceTB/SmolVLM2-500M-Video-Instruct` (the VLM backbone's own
# `transformers` config/tokenizer/processor -- SmolVLAConfig.vlm_model_name
# -- which `transformers.AutoConfig.from_pretrained` loads independently of
# the policy checkpoint even though load_vlm_weights=False skips its
# pretrained *weights*).
RUN mkdir -p "$HF_HOME" && \
    python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('lerobot/smolvla_base'); \
snapshot_download('HuggingFaceTB/SmolVLM2-500M-Video-Instruct')"

RUN chmod -R 0777 /workspace
ENV HF_HUB_OFFLINE=1

COPY train_entrypoint.py /workspace/train_entrypoint.py

ENTRYPOINT ["python", "/workspace/train_entrypoint.py"]
