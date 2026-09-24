#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")" && pwd)"
python3 "$root_dir/generate_smoke_kernel.py"
docker run --rm \
  -v /root/.kaggle/kaggle.json:/root/.kaggle/kaggle.json:ro \
  -v "$root_dir":/work \
  -w /work \
  python:3.12-slim \
  bash -lc 'python -m pip install --quiet kaggle==2.2.4 && kaggle kernels push -p /work --accelerator NvidiaTeslaT4 --timeout 32400'
