# SmolVLA policy training image. Each policy gets its own independent
# image so their dependency sets never collide (spec section 2).
#
# NOTE: see docker/act/Dockerfile — same stub-entrypoint caveat applies.
FROM python:3.11-slim

WORKDIR /workspace

COPY train_entrypoint.py /workspace/train_entrypoint.py

ENTRYPOINT ["python", "/workspace/train_entrypoint.py"]
