#!/usr/bin/env python3
"""List available edge-tts voices, optionally filtered by locale.

Usage:
    python list_voices.py           # all voices
    python list_voices.py zh        # only zh-* voices (Mandarin, Cantonese, etc.)
    python list_voices.py zh-CN     # only Mandarin (mainland China)
"""
import asyncio
import sys

import edge_tts


async def main() -> None:
    prefix = sys.argv[1] if len(sys.argv) > 1 else ""
    voices = await edge_tts.list_voices()
    for v in sorted(voices, key=lambda v: v["ShortName"]):
        if v["ShortName"].startswith(prefix):
            print(f"{v['ShortName']:28s} {v['Gender']:8s} {v['Locale']}")


if __name__ == "__main__":
    asyncio.run(main())
