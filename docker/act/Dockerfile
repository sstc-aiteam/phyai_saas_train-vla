# ACT policy training image. Each policy gets its own independent image so
# their dependency sets never collide (spec section 2).
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
# `lerobot[dataset]` (not `[training]`): we drive our own single-GPU training
# loop directly (see train_entrypoint.py) rather than lerobot's own
# accelerate/wandb-based `lerobot-train` CLI, so those extras are skipped.
RUN pip install --no-cache-dir "lerobot[dataset]==0.6.1"

# The worker runs this container as its own uid:gid, not root (see
# worker/docker_runner.py), so anything written outside the bind-mounted
# /workspace/input and /workspace/output needs to be world-writable up
# front -- in particular TORCH_HOME, which the backbone download below
# populates as root at build time.
ENV HOME=/workspace \
    TORCH_HOME=/workspace/.cache/torch

# ACT's default vision backbone is a torchvision ResNet-18 pretrained on
# ImageNet (ACTConfig.pretrained_backbone_weights), fetched via torch.hub --
# a separate mechanism from the HF Hub, so HF_HUB_OFFLINE below doesn't
# cover it. Bake it in at build time so every job starts training
# immediately and no job needs network access at run time.
RUN python -c "\
import torchvision.models as m; \
m.resnet18(weights=m.ResNet18_Weights.IMAGENET1K_V1)"

RUN chmod -R 0777 /workspace
# ACT trains from scratch and reads its dataset straight off the mounted
# /workspace/input -- no HF Hub access needed at all, so force offline
# mode to fail fast instead of hanging on the training host's network.
ENV HF_HOME=/workspace/.cache/huggingface \
    HF_HUB_OFFLINE=1

COPY train_entrypoint.py /workspace/train_entrypoint.py

ENTRYPOINT ["python", "/workspace/train_entrypoint.py"]
