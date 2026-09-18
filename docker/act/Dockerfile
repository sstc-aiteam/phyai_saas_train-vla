# ACT policy training image. Each policy gets its own independent image so
# their dependency sets never collide (spec section 2).
#
# NOTE: this installs no ML dependencies yet — train_entrypoint.py is a
# contract stub (writes progress.json / a checkpoint dir on the expected
# schedule) rather than a real ACT training run. Swap the base image /
# `pip install` line for a CUDA image + `lerobot[act]` (or equivalent) once
# real training is wired in, without changing the CLI contract the worker
# depends on.
FROM python:3.11-slim

WORKDIR /workspace

COPY train_entrypoint.py /workspace/train_entrypoint.py

ENTRYPOINT ["python", "/workspace/train_entrypoint.py"]
