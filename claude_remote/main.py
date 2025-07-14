#!/usr/bin/env python3
import asyncio
import signal
import sys
from pathlib import Path
from typing import Dict
from concurrent.futures import ThreadPoolExecutor

from .config import Config
from .hash_file_watcher import HashFileWatcher
from .project_manager import ProjectManager
from .claude_executor import ClaudeExecutor
from .slack_notifier import SlackNotifier

class ClaudeRemote:
    def __init__(self):
        # 設定検証
        Config.validate()
        
        # コンポーネント初期化
        self.file_watcher = HashFileWatcher(Config.GDRIVE_MOUNT_PATH)
        self.project_manager = ProjectManager(Config.PROJECTS_DIR)
        self.slack_notifier = SlackNotifier()
        self.claude_executor = ClaudeExecutor(self.project_manager, self.slack_notifier, self.file_watcher)
        
        # 実行管理
        self.executor_pool = ThreadPoolExecutor(max_workers=Config.MAX_CONCURRENT_EXECUTIONS)
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.shutdown_event = asyncio.Event()
        
    async def process_file_changes(self):
        while not self.shutdown_event.is_set():
            try:
                # ファイル変更を監視（タイムアウト付き）
                change = await asyncio.wait_for(
                    self.file_watcher.watch_files(),
                    timeout=1.0  # 1秒でタイムアウト
                )
                
                if change is None:
                    continue
                    
                # 実行タスクを作成
                file_path = change['file_path']
                task_key = str(file_path)
                
                # 既存のタスクが実行中の場合はスキップ
                if task_key in self.running_tasks and not self.running_tasks[task_key].done():
                    print(f"Task for {file_path} is already running, skipping...")
                    continue
                
                print(f"Processing file change: {file_path}")
                
                # 新しいタスクを作成
                task = asyncio.create_task(
                    self.claude_executor.execute(
                        file_path,
                        change['content'],
                        change.get('diff')
                    )
                )
                
                self.running_tasks[task_key] = task
                
                # タスク完了時のクリーンアップ
                task.add_done_callback(lambda t: self.running_tasks.pop(task_key, None))
                
            except asyncio.TimeoutError:
                # タイムアウトは正常（シャットダウンチェックのため）
                continue
            except Exception as e:
                print(f"Error processing file changes: {e}")
                await asyncio.sleep(1)  # エラー時は少し待機
    
    async def run(self):
        print(f"Claude Remote started")
        print(f"Watching: {Config.GDRIVE_MOUNT_PATH}")
        print(f"Projects: {Config.PROJECTS_DIR}")
        print("Press Ctrl+C to stop")
        
        try:
            # ファイル監視を開始
            self.file_watcher.start()
            # ファイル変更処理を開始
            await self.process_file_changes()
        except asyncio.CancelledError:
            pass
        finally:
            print("\nShutting down...")
            # クリーンアップ
            self.file_watcher.stop()
            
            # 実行中のタスクをキャンセル
            if self.running_tasks:
                print("Cancelling running tasks...")
                for task in self.running_tasks.values():
                    if not task.done():
                        task.cancel()
                # キャンセル完了を待機
                await asyncio.gather(*self.running_tasks.values(), return_exceptions=True)
            
            self.executor_pool.shutdown(wait=False)
    
    def shutdown(self):
        print("\nShutting down Claude Remote...")
        self.shutdown_event.set()
        self.file_watcher.stop()

def main():
    # 初回実行時の設定
    if not Path('.env').exists() and Path('.env.example').exists():
        print("First run detected. Creating .env file from .env.example")
        print("Please edit .env file and configure your settings.")
        
        import shutil
        shutil.copy('.env.example', '.env')
        
        # 監視ディレクトリの選択
        try:
            gdrive_path = input("Enter Google Drive mount path (default: /gdrive/claude-remote): ").strip()
            if not gdrive_path:
                gdrive_path = "/gdrive/claude-remote"
        except EOFError:
            gdrive_path = "/gdrive/claude-remote"
            print(f"Using default path: {gdrive_path}")
        
        # .envファイルを更新
        with open('.env', 'r') as f:
            content = f.read()
        
        content = content.replace('/gdrive/claude-remote', gdrive_path)
        
        with open('.env', 'w') as f:
            f.write(content)
        
        print("\nPlease complete the configuration in .env file before running again.")
        print("Especially set your SLACK_WEBHOOK_URL")
        return
    
    # シグナルハンドリング
    app = ClaudeRemote()
    
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        app.shutdown_event.set()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 実行
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()