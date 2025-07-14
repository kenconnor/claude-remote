import asyncio
import os
import time
from pathlib import Path
from typing import Dict, Set
from datetime import datetime

class SimpleFileWatcher:
    def __init__(self, watch_path: Path):
        self.watch_path = watch_path
        self.last_modified: Dict[str, float] = {}
        self.running = False
        
    async def watch_files(self) -> Dict:
        """シンプルなポーリングベースのファイル監視"""
        try:
            # .mdファイルを検索
            for md_file in self.watch_path.rglob("*.md"):
                if not self.running:
                    return None
                    
                if md_file.is_file():
                    current_mtime = md_file.stat().st_mtime
                    file_path_str = str(md_file)
                    
                    # 新規ファイルまたは更新されたファイル
                    if (file_path_str not in self.last_modified or 
                        current_mtime > self.last_modified[file_path_str]):
                        
                        self.last_modified[file_path_str] = current_mtime
                        
                        # ファイル内容を読み込み
                        try:
                            with open(md_file, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            return {
                                'file_path': md_file,
                                'content': content,
                                'diff': None,  # 簡略化のため差分は無効
                                'change_type': 'modified',
                                'timestamp': datetime.now()
                            }
                        except Exception as e:
                            print(f"Failed to read file {md_file}: {e}")
                            continue
            
            # 1秒待機
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"Error during file watching: {e}")
            await asyncio.sleep(5)
        
        return None
    
    def start(self):
        self.running = True
        
    def stop(self):
        self.running = False