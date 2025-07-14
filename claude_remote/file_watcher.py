import asyncio
import git
from pathlib import Path
from typing import Optional, Set, Dict
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, queue: asyncio.Queue, git_repo: git.Repo, loop):
        self.queue = queue
        self.git_repo = git_repo
        self.processed_files: Set[str] = set()
        self.loop = loop
        
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.md'):
            asyncio.run_coroutine_threadsafe(
                self._handle_file_change(event.src_path, 'created'), 
                self.loop
            )
    
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.md'):
            asyncio.run_coroutine_threadsafe(
                self._handle_file_change(event.src_path, 'modified'), 
                self.loop
            )
    
    async def _handle_file_change(self, file_path: str, change_type: str):
        file_path = Path(file_path)
        
        # 短時間の重複イベントを防ぐ
        file_key = f"{file_path}_{change_type}"
        if file_key in self.processed_files:
            return
        
        self.processed_files.add(file_key)
        await asyncio.sleep(1)  # デバウンス
        self.processed_files.discard(file_key)
        
        # ファイル内容を読み込む
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Failed to read file {file_path}: {e}")
            return
        
        # Git差分を取得
        diff = self._get_git_diff(file_path) if change_type == 'modified' else None
        
        # キューに追加
        await self.queue.put({
            'file_path': file_path,
            'content': content,
            'diff': diff,
            'change_type': change_type,
            'timestamp': datetime.now()
        })
    
    def _get_git_diff(self, file_path: Path) -> Optional[str]:
        try:
            # ファイルをGitに追加（未追跡の場合）
            relative_path = file_path.relative_to(self.git_repo.working_dir)
            
            if str(relative_path) not in [item.a_path for item in self.git_repo.index.entries]:
                self.git_repo.index.add([str(relative_path)])
                self.git_repo.index.commit(f"Auto-add {relative_path}")
            
            # 差分を取得
            diff = self.git_repo.git.diff('HEAD', str(relative_path))
            
            # 現在の変更をコミット
            if self.git_repo.is_dirty(path=str(relative_path)):
                self.git_repo.index.add([str(relative_path)])
                self.git_repo.index.commit(f"Update {relative_path}")
            
            return diff
        except Exception as e:
            print(f"Failed to get git diff for {file_path}: {e}")
            return None

class FileWatcher:
    def __init__(self, watch_path: Path):
        self.watch_path = watch_path
        self.queue = asyncio.Queue()
        self.observer = Observer()
        
        # Git初期化
        self.git_repo = self._init_git_repo()
        
    def _init_git_repo(self) -> git.Repo:
        try:
            repo = git.Repo(self.watch_path)
        except git.InvalidGitRepositoryError:
            # Gitリポジトリが存在しない場合は初期化
            repo = git.Repo.init(self.watch_path)
            
            # .gitignoreを作成
            gitignore_path = self.watch_path / '.gitignore'
            with open(gitignore_path, 'w') as f:
                f.write("*.log\n*.tmp\n.DS_Store\n")
            
            repo.index.add(['.gitignore'])
            repo.index.commit("Initial commit")
        
        return repo
    
    def start(self, loop):
        handler = FileChangeHandler(self.queue, self.git_repo, loop)
        self.observer.schedule(handler, str(self.watch_path), recursive=True)
        self.observer.start()
    
    def stop(self):
        self.observer.stop()
        self.observer.join()
    
    async def get_changes(self) -> Dict:
        return await self.queue.get()