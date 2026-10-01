#!/usr/bin/env python3
"""Download quantized MiniLM ONNX (~23MB) + tokenizer into models/minilm/."""
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent / "models" / "minilm"
ROOT.mkdir(parents=True, exist_ok=True)
BASE = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main"
files = {
    "onnx/model_qint8_arm64.onnx": "model_qint8_arm64.onnx",
    "tokenizer.json": "tokenizer.json",
    "tokenizer_config.json": "tokenizer_config.json",
    "vocab.txt": "vocab.txt",
    "config.json": "config.json",
}
for remote, local in files.items():
    dest = ROOT / local
    if dest.exists() and dest.stat().st_size > 1000:
        print("skip", local)
        continue
    url = f"{BASE}/{remote}"
    print("fetch", url)
    urllib.request.urlretrieve(url, dest)
    print("saved", dest, dest.stat().st_size)
print("done — set COHORTOS_EMBED_MODEL_DIR=", ROOT)
