import asyncio
import os
import time
from pathlib import Path
from typing import Dict, Set, Optional
from datetime import datetime
import git
import hashlib
import logging

# ロガーを設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GitDiffFileWatcher:
    """Git差分ベースのファイル監視システム"""
    
    def __init__(self, watch_path: Path):
        self.watch_path = watch_path
        self.running = False
        self.git_repo: Optional[git.Repo] = None
        self.file_hashes: Dict[str, str] = {}
        self.recently_modified_by_system: Set[str] = set()  # システムが変更したファイル
    
        
    def _init_git_repo(self) -> bool:
        """Gitリポジトリを初期化または既存のものを開く"""
        try:
            # まず既存のリポジトリを開くことを試す
            try:
                self.git_repo = git.Repo(self.watch_path)
                logger.info(f"Opened existing Git repository at {self.watch_path}")
                
                # 既存リポジトリの健全性チェック
                try:
                    # HEADが存在するかチェック
                    self.git_repo.head.commit
                    logger.debug("Repository has valid HEAD")
                except:
                    logger.debug("Repository has no commits yet")
                
                return True
                
            except git.InvalidGitRepositoryError:
                # Google Driveマウントでは直接Git管理を避ける
                logger.warning(f"Cannot create Git repository in {self.watch_path} (possibly a mount)")
                logger.info("Falling back to hash-based change detection")
                self.git_repo = None
                return True
                
        except PermissionError as e:
            logger.warning(f"Permission denied when accessing Git repository: {e}")
            logger.info("Falling back to hash-based change detection")
            self.git_repo = None
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize Git repository: {e}")
            logger.info("Falling back to hash-based change detection")
            self.git_repo = None
            return True
    
    def _commit_changes(self, message: str, author_name: str = "Claude Remote", author_email: str = "claude@remote.ai") -> bool:
        """変更をコミット"""
        try:
            if not self.git_repo:
                return False
                
            # 作者情報を設定
            with self.git_repo.config_writer() as git_config:
                git_config.set_value("user", "name", author_name)
                git_config.set_value("user", "email", author_email)
            
            # コミット実行
            commit = self.git_repo.index.commit(message)
            logger.debug(f"Created commit: {commit.hexsha[:8]} - {message}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            return False
    
    def _get_file_hash(self, file_path: Path) -> str:
        """ファイルの内容ハッシュを計算"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""
    
    def _has_content_changed(self, file_path: Path) -> bool:
        """ファイル内容が実際に変更されたかをチェック"""
        # Gitが利用可能な場合はGitで差分チェック
        if self.git_repo:
            try:
                relative_path = file_path.relative_to(self.watch_path)
                
                # HEADが存在するかチェック
                has_commits = False
                try:
                    self.git_repo.head.commit
                    has_commits = True
                except:
                    has_commits = False
                
                # Gitに追跡されているかチェック
                if str(relative_path) in [item[0] for item in self.git_repo.index.entries.keys()]:
                    if has_commits:
                        # Gitで差分があるかチェック
                        try:
                            diff = self.git_repo.git.diff('HEAD', str(relative_path))
                            return bool(diff.strip())
                        except git.GitCommandError as e:
                            logger.warning(f"Git diff failed for {relative_path}: {e}")
                            return self._fallback_hash_check(file_path)
                    else:
                        # コミットがない場合はハッシュで比較
                        return self._fallback_hash_check(file_path)
                else:
                    # 新規ファイル
                    return True
                    
            except Exception as e:
                logger.error(f"Error checking Git content change for {file_path}: {e}")
                return self._fallback_hash_check(file_path)
        else:
            # Gitが利用できない場合はハッシュベースの変更検知
            return self._fallback_hash_check(file_path)
    
    def _fallback_hash_check(self, file_path: Path) -> bool:
        """ハッシュベースのフォールバック変更検知"""
        current_hash = self._get_file_hash(file_path)
        file_path_str = str(file_path)
        
        if file_path_str not in self.file_hashes:
            self.file_hashes[file_path_str] = current_hash
            return True
            
        if current_hash != self.file_hashes[file_path_str]:
            self.file_hashes[file_path_str] = current_hash
            return True
            
        return False
    
    def _track_file_in_git(self, file_path: Path) -> bool:
        """ファイルをGitに追加してコミット"""
        # Gitが利用できない場合は何もしない
        if not self.git_repo:
            logger.debug(f"Git not available, skipping tracking for {file_path}")
            return True
            
        try:
            relative_path = file_path.relative_to(self.watch_path)
            
            # ファイルを追加
            self.git_repo.index.add([str(relative_path)])
            
            # HEADが存在するかチェック
            has_commits = False
            try:
                self.git_repo.head.commit
                has_commits = True
            except:
                has_commits = False
            
            # 変更があればコミット
            if has_commits:
                if self.git_repo.index.diff("HEAD"):
                    commit_message = f"Update {relative_path.name}"
                    self._commit_changes(commit_message)
                    logger.info(f"Committed changes for {relative_path}")
                    return True
                else:
                    logger.debug(f"No changes to commit for {relative_path}")
                    return False
            else:
                # 初回コミットの場合
                commit_message = f"Add {relative_path.name}"
                self._commit_changes(commit_message)
                logger.info(f"Initial commit for {relative_path}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to track file {file_path} in Git: {e}")
            return False
    
    def mark_file_as_system_modified(self, file_path: Path):
        """ファイルがシステムによって変更されたことをマーク"""
        file_path_str = str(file_path)
        self.recently_modified_by_system.add(file_path_str)
        # ハッシュを更新してシステム変更を無視
        self.file_hashes[file_path_str] = self._get_file_hash(file_path)
        logger.debug(f"Marked {file_path} as system-modified")
    
    def _is_question_append_change(self, file_path: Path, content: str) -> bool:
        """質問追記による変更かどうかをチェック"""
        # Gitが利用できない場合は内容をチェック
        if not self.git_repo:
            question_indicators = [
                "## Claude からの質問",
                "--- Claude Remoteからの質問 ---",
                "*上記の質問に回答してファイルを更新してください*"
            ]
            return any(indicator in content for indicator in question_indicators)
            
        try:
            relative_path = file_path.relative_to(self.watch_path)
            
            # HEADが存在しない場合は質問追記ではない
            try:
                self.git_repo.head.commit
            except:
                return False
            
            # 差分を取得
            diff = self.git_repo.git.diff('HEAD', str(relative_path))
            
            # 差分に質問セパレータが含まれているかチェック
            question_indicators = [
                "## Claude からの質問",
                "--- Claude Remoteからの質問 ---",
                "Could you please clarify",
                "What would you like me to help",
                "I'll help you with any programming",
                "*上記の質問に回答してファイルを更新してください*"
            ]
            
            return any(indicator in diff for indicator in question_indicators)
            
        except Exception as e:
            logger.debug(f"Could not check question append for {file_path}: {e}")
            return False
    
    async def watch_files(self) -> Optional[Dict]:
        """Git差分ベースのファイル監視"""
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
                                # Gitで変更を追跡（但し実行はしない）
                                self._track_file_in_git(md_file)
                                continue
                            
                            # Gitで変更を追跡
                            self._track_file_in_git(md_file)
                            
                            logger.info(f"Detected content change in {md_file}")
                            
                            return {
                                'file_path': md_file,
                                'content': content,
                                'diff': None,  # 必要に応じて後で実装
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
        if not self._init_git_repo():
            return False
            
        self.running = True
        logger.info(f"Started Git diff-based file watching on {self.watch_path}")
        return True
        
    def stop(self):
        """監視を停止"""
        self.running = False
        logger.info("Stopped Git diff-based file watching")
    
    def get_status(self) -> Dict:
        """監視システムの状態を取得"""
        try:
            status = {
                "watch_path": str(self.watch_path),
                "running": self.running,
                "git_initialized": self.git_repo is not None,
                "tracked_files": len([f for f in self.watch_path.rglob("*.md") if f.is_file()]),
            }
            
            if self.git_repo:
                try:
                    status.update({
                        "total_commits": len(list(self.git_repo.iter_commits())) if self.git_repo.heads else 0,
                        "dirty_files": self.git_repo.is_dirty(untracked_files=True),
                    })
                except Exception as e:
                    status["git_error"] = str(e)
            else:
                status["fallback_mode"] = "Using hash-based change detection"
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return {"error": str(e)}