"""
Claude Remote - Obsidianで作成したメモを元にClaude Codeを自動実行するシステム

AndroidのObsidianで音声入力したメモがGoogle Drive経由で同期され、
Ubuntu PC上で自動的にClaude Codeが実行される開発支援ツールです。
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .main import main

__all__ = ["main"]