# -*- coding: utf-8 -*-
"""引擎自检：直接运行本文件，或执行 python app.py --selftest。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import selftest  # noqa: E402

if __name__ == "__main__":
    selftest()
