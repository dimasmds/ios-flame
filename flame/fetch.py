#!/usr/bin/env python3
"""Fetch pinned public Google build inputs into ignored research/ (no Apple files)."""
import base64
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "research/flame-sources"
INPUTS = {
    "sm8150.dtb": ("device/google/coral-kernel", "23efa57f3db9093c186a37cfb5138849afe4ccd9", "sm8150.dtb"),
    "sm8150-v2.dtb": ("device/google/coral-kernel", "23efa57f3db9093c186a37cfb5138849afe4ccd9", "sm8150-v2.dtb"),
    "mkbootimg.py": ("platform/system/tools/mkbootimg", "6cb944b82c819b691bc21d8228e155f1db07a446", "mkbootimg.py"),
    "gki/generate_gki_certificate.py": ("platform/system/tools/mkbootimg", "6cb944b82c819b691bc21d8228e155f1db07a446", "gki/generate_gki_certificate.py"),
    "avbtool.py": ("platform/external/avb", "8261ecd67956f6e9647ff5fd4aeb829f75fb3f66", "avbtool.py"),
}


def main():
    manifest = {}
    for local, (repo, revision, remote) in INPUTS.items():
        url = f"https://android.googlesource.com/{repo}/+/{revision}/{remote}?format=TEXT"
        data = base64.b64decode(urllib.request.urlopen(url, timeout=60).read())
        target = OUT / local
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest[local] = {"url": url, "sha256": hashlib.sha256(data).hexdigest()}
        print(f"{local}: {len(data)} bytes")
    (OUT / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
