#!/usr/bin/env python3
import os
import platform
import shutil
from pathlib import Path
from uuid import uuid4

if platform.system() == "Linux":
    import memory_tempfile  # type: ignore

    tempfile = memory_tempfile.MemoryTempfile(fallback=True)
else:
    import tempfile
import contextlib
from typing import Optional


@contextlib.contextmanager
def debug_cache_dir(path: str):
    path_random = Path(path, str(uuid4()))
    os.mkdir(path_random)
    try:
        yield path_random
    finally:
        shutil.rmtree(path_random)


class CacheStore:
    @staticmethod
    def get_cache_store(path: Optional[str] = None) -> Path:
        if path:
            return debug_cache_dir(path)
        else:
            return Path(tempfile.TemporaryDirectory())
