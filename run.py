#!/usr/bin/env python3
"""
Claude Remote 実行スクリプト
"""
import sys
import os
from pathlib import Path

# claude_remoteディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent / 'claude_remote'))

from main import main

if __name__ == "__main__":
    main()