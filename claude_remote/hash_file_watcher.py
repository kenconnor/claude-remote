import asyncio
import os
import time
import json
from pathlib import Path
from typing import Dict, Set, Optional
from datetime import datetime
import hashlib
import logging

# ロガーを設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HashFileWatcher:
    """ハッシュベースのファイル監視システム"""
    
    def __init__(self, watch_path: Path):
        self.watch_path = watch_path
        self.running = False
        self.file_hashes: Dict[str, str] = {}
        self.recently_modified_by_system: Set[str] = set()  # システムが変更したファイル
        
        # キャッシュファイルのパス
        self.cache_dir = Path.home() / '.claude-remote' / 'cache'
        self.cache_file = self.cache_dir / 'file_hashes.json'
        
        # キャッシュを読み込み
        self._load_cache()
    
    def _load_cache(self):
        """キャッシュファイルから MD5 ハッシュを読み込み"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    
                # 監視対象パスのキャッシュのみを読み込み
                watch_path_str = str(self.watch_path)
                if watch_path_str in cached_data:
                    self.file_hashes = cached_data[watch_path_str]
                    logger.info(f"Loaded {len(self.file_hashes)} cached file hashes from {self.cache_file}")
                else:
                    logger.debug(f"No cache found for watch path: {watch_path_str}")
            else:
                logger.debug(f"Cache file does not exist: {self.cache_file}")
                
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            self.file_hashes = {}
    
    def _save_cache(self):
        """MD5 ハッシュをキャッシュファイルに保存"""
        try:
            # キャッシュディレクトリを作成
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            # 既存のキャッシュを読み込み
            cached_data = {}
            if self.cache_file.exists():
                try:
                    with open(self.cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to read existing cache: {e}")
            
            # 現在の監視パスのデータを更新
            watch_path_str = str(self.watch_path)
            cached_data[watch_path_str] = self.file_hashes
            
            # キャッシュファイルに保存
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cached_data, f, indent=2, ensure_ascii=False)
                
            logger.debug(f"Saved {len(self.file_hashes)} file hashes to cache")
            
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
        
    def _get_file_hash(self, file_path: Path) -> str:
        """ファイルの内容ハッシュを計算"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""
    
    def _has_content_changed(self, file_path: Path) -> bool:
        """ファイル内容が実際に変更されたかをチェック"""
        current_hash = self._get_file_hash(file_path)
        file_path_str = str(file_path)
        
        if file_path_str not in self.file_hashes:
            self.file_hashes[file_path_str] = current_hash
            self._save_cache()  # キャッシュを保存
            return True
            
        if current_hash != self.file_hashes[file_path_str]:
            self.file_hashes[file_path_str] = current_hash
            self._save_cache()  # キャッシュを保存
            return True
            
        return False
    
    def mark_file_as_system_modified(self, file_path: Path):
        """ファイルがシステムによって変更されたことをマーク"""
        file_path_str = str(file_path)
        self.recently_modified_by_system.add(file_path_str)
        # ハッシュを更新してシステム変更を無視
        self.file_hashes[file_path_str] = self._get_file_hash(file_path)
        self._save_cache()  # キャッシュを保存
        logger.debug(f"Marked {file_path} as system-modified")
    
    def _is_question_append_change(self, file_path: Path, content: str) -> bool:
        """質問追記による変更かどうかをチェック"""
        # システムによる変更としてマークされているファイルのみ質問追記として扱う
        file_path_str = str(file_path)
        return file_path_str in self.recently_modified_by_system
    
    async def watch_files(self) -> Optional[Dict]:
        """ハッシュベースのファイル監視"""
        try:
            # .mdファイルを検索
            for md_file in self.watch_path.rglob("*.md"):
                if not self.running:
                    return None
                    
                if md_file.is_file():
                    file_path_str = str(md_file)
                    
                    # システムが最近変更したファイルはスキップ
                    if file_path_str in self.recently_modified_by_system:
                        self.recently_modified_by_system.discard(file_path_str)
                        continue
                    
                    # 内容が実際に変更されたかチェック
                    if self._has_content_changed(md_file):
                        # ファイル内容を読み込み
                        try:
                            with open(md_file, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            # 質問追記による変更かチェック
                            if self._is_question_append_change(md_file, content):
                                logger.info(f"Skipping question append change in {md_file}")
                                continue
                            
                            logger.info(f"Detected content change in {md_file}")
                            
                            return {
                                'file_path': md_file,
                                'content': content,
                                'diff': None,
                                'change_type': 'content_modified',
                                'timestamp': datetime.now()
                            }
                        except Exception as e:
                            logger.error(f"Failed to read file {md_file}: {e}")
                            continue
            
            # 1秒待機
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error during file watching: {e}")
            await asyncio.sleep(5)
        
        return None
    
    def start(self) -> bool:
        """監視を開始"""
        self.running = True
        
        # 初回実行時にすべてのファイルのハッシュを計算してキャッシュ
        if not self.file_hashes:
            logger.info("Building initial file hash cache...")
            count = 0
            for md_file in self.watch_path.rglob("*.md"):
                if md_file.is_file():
                    file_path_str = str(md_file)
                    self.file_hashes[file_path_str] = self._get_file_hash(md_file)
                    count += 1
            if count > 0:
                self._save_cache()
                logger.info(f"Built cache for {count} files")
        
        logger.info(f"Started hash-based file watching on {self.watch_path}")
        return True
        
    def stop(self):
        """監視を停止"""
        self.running = False
        # 最終的なキャッシュを保存
        self._save_cache()
        logger.info("Stopped hash-based file watching")
    
    def get_status(self) -> Dict:
        """監視システムの状態を取得"""
        try:
            return {
                "watch_path": str(self.watch_path),
                "running": self.running,
                "tracked_files": len([f for f in self.watch_path.rglob("*.md") if f.is_file()]),
                "cached_hashes": len(self.file_hashes),
                "detection_method": "hash-based",
                "cache_file": str(self.cache_file),
                "cache_exists": self.cache_file.exists()
            }
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return {"error": str(e)}