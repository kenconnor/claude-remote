import asyncio
import subprocess
import json
import time
import os
import shlex
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime
import docker
from .slack_notifier import SlackNotifier
from .config import Config

class ClaudeExecutor:
    def __init__(self, project_manager, slack_notifier: SlackNotifier, file_watcher=None):
        self.project_manager = project_manager
        self.slack_notifier = slack_notifier
        self.docker_client = docker.from_env()
        self.file_watcher = file_watcher
        
    async def execute(self, markdown_file: Path, content: str, diff: Optional[str] = None) -> Tuple[bool, str]:
        # プロジェクトを取得または作成
        project_path = self.project_manager.get_project_by_source(markdown_file)
        if not project_path:
            print(f"Creating new project for: {markdown_file}")
            project_path = self.project_manager.create_project(markdown_file)
        else:
            print(f"Using existing project: {project_path}")
        
        project_name = self.project_manager.get_project_name(project_path)
        project_info = self.project_manager.get_project_info(project_path)
        
        print(f"Project info: {project_info}")
        
        # タスクサマリーを作成
        task_summary = content[:200] if len(content) > 200 else content
        
        # 実行開始通知
        print(f"Starting Claude Code execution for project: {project_name}")
        try:
            self.slack_notifier.notify_start(project_name, task_summary, str(markdown_file))
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
        
        # 実行ログファイル
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = project_path / 'logs' / f'execution_{timestamp}.log'
        
        try:
            # Claude Codeコマンドを構築（必要なツールを許可）
            # プロンプトは一つの引数として渡すため、引用符は不要（リストで適切に分割される）
            cmd_parts = ['claude', '--allowedTools', 'Write,Edit,MultiEdit,Read,Bash,Glob,Grep', '--print', content]
            
            print(f"Claude command: {' '.join(cmd_parts[:-1])} [prompt content]")
            print(f"Prompt preview: {content[:100]}...")
            print(f"Full command args: {cmd_parts}")
            print(f"Content length: {len(content)} chars")
            
            # 作業ディレクトリで実行（絶対パスに変換）
            working_dir = Path(project_info['working_directory'])
            if not working_dir.is_absolute():
                working_dir = Path.cwd() / working_dir
            working_dir = working_dir.resolve()
            print(f"Working directory: {working_dir}")
            
            # 直接実行（シェル経由）
            result = await self._run_direct(cmd_parts, working_dir, log_file)
            
            print(f"Claude Code execution result: success={result['success']}")
            if 'logs' in result and result['logs']:
                print(f"Execution logs: {result['logs'][:500]}...")
            
            if result['success']:
                print(f"Execution completed successfully: {result['summary']}")
                
                # 質問や追加情報が必要かチェック
                await self._check_and_append_questions(markdown_file, result['logs'], result['summary'])
                
                try:
                    self.slack_notifier.notify_complete(project_name, result['summary'], str(markdown_file))
                except Exception as e:
                    print(f"Failed to send Slack completion notification: {e}")
                return True, result['summary']
            else:
                print(f"Execution failed: {result['error']}")
                # エラー処理
                await self._handle_error(project_name, result, markdown_file)
                return False, result['error']
                
        except Exception as e:
            error_msg = str(e)
            self.slack_notifier.notify_error(
                project_name,
                "critical",
                "Claude Code実行中に予期しないエラーが発生しました",
                error_msg,
                "システム管理者に連絡してください"
            )
            return False, error_msg
    
    async def _run_direct(self, cmd_parts: list, working_dir: Path, log_file: Path) -> Dict:
        """直接実行（テスト用）"""
        try:
            # 作業ディレクトリを作成
            working_dir.mkdir(parents=True, exist_ok=True)
            
            # プロンプトをダブルクォーテーションで囲んでシェルコマンドとして構築
            prompt = cmd_parts[-1]
            # 確実にダブルクォーテーションで囲む
            quoted_prompt = f'"{prompt}"'
            shell_cmd_parts = cmd_parts[:-1] + [quoted_prompt]
            shell_cmd = ' '.join(shell_cmd_parts)
            
            print(f"Shell command: {shell_cmd}")
            
            # Claude Codeをシェル経由で実行
            process = await asyncio.create_subprocess_shell(
                shell_cmd,
                cwd=str(working_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            # タイムアウト付きで実行を待機
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=Config.CLAUDE_TIMEOUT
                )
                logs = stdout.decode('utf-8')
            except asyncio.TimeoutError:
                process.kill()
                logs = "Claude Code execution timed out"
                return {
                    'success': False,
                    'error': 'timeout',
                    'logs': logs
                }
            
            # ログファイルに保存
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'w') as f:
                f.write(logs)
            
            # 実行結果を解析
            if process.returncode == 0:
                return {
                    'success': True,
                    'summary': self._extract_summary(logs),
                    'logs': logs
                }
            elif process.returncode == 129:  # トークン制限
                return {
                    'success': False,
                    'error': 'token_limit',
                    'logs': logs
                }
            else:
                return {
                    'success': False,
                    'error': f'Exit code: {process.returncode}',
                    'logs': logs
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'logs': ''
            }
    
    async def _run_in_docker(self, cmd_parts: list, working_dir: Path, log_file: Path) -> Dict:
        try:
            # ホームディレクトリのClaude設定をマウント
            home_dir = os.path.expanduser("~")
            claude_config_dir = os.path.join(home_dir, ".claude")
            claude_json_file = os.path.join(home_dir, ".claude.json")
            
            volumes = {
                str(working_dir): {'bind': '/workspace', 'mode': 'rw'},
            }
            
            # Claude設定ファイルをマウント（書き込み可能）
            if os.path.exists(claude_config_dir):
                volumes[claude_config_dir] = {'bind': '/root/.claude', 'mode': 'rw'}
            if os.path.exists(claude_json_file):
                volumes[claude_json_file] = {'bind': '/root/.claude.json', 'mode': 'rw'}
            
            # Dockerコンテナ設定
            container_config = {
                'image': Config.DOCKER_IMAGE_NAME,
                'command': cmd_parts,
                'working_dir': '/workspace',
                'volumes': volumes,
                'detach': False,  # 同期実行に変更
                'remove': False,  # 一時的に残す
                'network_mode': Config.DOCKER_NETWORK_NAME,
                'mem_limit': '4g',
                'cpu_period': 100000,
                'cpu_quota': 200000,  # 2 CPUs
            }
            
            # コンテナ実行
            try:
                # detach=Falseで同期実行 - 戻り値はbytes
                logs_bytes = self.docker_client.containers.run(**container_config)
                logs = logs_bytes.decode('utf-8')
                exit_code = 0  # 正常終了
                
            except docker.errors.ContainerError as e:
                # コンテナが非0で終了
                logs = e.stderr.decode('utf-8') if e.stderr else str(e)
                exit_code = e.exit_status
                
            except Exception as e:
                logs = f"Docker execution failed: {str(e)}"
                exit_code = 1
            
            # ログファイルに保存
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'w') as f:
                f.write(logs)
            
            if exit_code == 0:
                return {
                    'success': True,
                    'summary': self._extract_summary(logs),
                    'logs': logs
                }
            elif exit_code == 129:  # トークン制限
                return {
                    'success': False,
                    'error': 'token_limit',
                    'logs': logs
                }
            else:
                return {
                    'success': False,
                    'error': f'Exit code: {exit_code}',
                    'logs': logs
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'logs': ''
            }
    
    async def _handle_error(self, project_name: str, result: Dict, markdown_file: Path):
        if result['error'] == 'token_limit':
            # トークン制限の場合は再試行
            for retry_count in range(1, Config.MAX_TOKEN_RETRIES + 1):
                self.slack_notifier.notify_token_retry(project_name, retry_count)
                await asyncio.sleep(Config.TOKEN_RETRY_INTERVAL)
                
                # 再実行
                retry_result = await self._run_in_docker(
                    result.get('cmd_parts', []),
                    result.get('working_dir', Path('.')),
                    result.get('log_file', Path('./retry.log'))
                )
                
                if retry_result['success']:
                    self.slack_notifier.notify_complete(project_name, retry_result['summary'])
                    return
        else:
            # その他のエラー
            self.slack_notifier.notify_error(
                project_name,
                "major",
                f"Claude Code実行エラー: {result['error']}",
                result.get('logs', '')[:500],
                "ログを確認して問題を修正してください"
            )
    
    def _extract_summary(self, logs: str) -> str:
        # ログから実行サマリーを抽出（簡易実装）
        lines = logs.strip().split('\n')
        if len(lines) > 10:
            return '\n'.join(lines[-10:])
        return logs[:500]
    
    async def _check_and_append_questions(self, markdown_file: Path, logs: str, summary: str):
        """Claudeからの質問や追加情報要求をマークダウンファイルに追記"""
        try:
            # Claudeの応答から質問を検出するパターン
            question_patterns = [
                r'(?:質問|Question|クエスチョン)[:：]?\s*(.+)',
                r'(?:確認|Confirm|コンファーム)[:：]?\s*(.+)', 
                r'(?:詳細|Details|詳しく)[:：]?\s*(.+)',
                r'(?:どの|Which|どちら).*[？?]',
                r'(?:何|What|なに).*[？?]',
                r'(?:いつ|When|どこ|Where|なぜ|Why|どうやって|How).*[？?]',
                r'(?:してください|お聞かせください|教えてください|please|Please).*[？?]?',
                r'(?:必要です|required|需要|ください).*(?:情報|information|詳細|details)',
            ]
            
            import re
            questions = []
            
            # ログと要約から質問を抽出
            for text in [logs, summary]:
                for pattern in question_patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
                    questions.extend(matches)
            
            # 質問らしい行を直接検出
            for line in logs.split('\n'):
                line = line.strip()
                if line and (line.endswith('?') or line.endswith('？')):
                    if len(line) > 10 and len(line) < 200:  # 適度な長さの質問
                        questions.append(line)
            
            # 重複を除去し、有効な質問のみを保持
            unique_questions = []
            for q in questions:
                q = q.strip()
                if q and len(q) > 5 and q not in unique_questions:
                    unique_questions.append(q)
            
            if unique_questions:
                # マークダウンファイルに質問を追記
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                with open(markdown_file, 'a', encoding='utf-8') as f:
                    f.write('\n\n---\n')
                    f.write(f'## Claude からの質問 ({timestamp})\n\n')
                    
                    for i, question in enumerate(unique_questions, 1):
                        f.write(f'{i}. {question}\n')
                    
                    f.write('\n*上記の質問に回答してファイルを更新してください*\n')
                
                print(f"Claudeからの質問をマークダウンファイルに追記しました: {len(unique_questions)}件")
                
                # ファイル監視にシステム変更を通知
                if self.file_watcher and hasattr(self.file_watcher, 'mark_file_as_system_modified'):
                    self.file_watcher.mark_file_as_system_modified(markdown_file)
            else:
                print("Claudeからの追加質問は検出されませんでした")
                
        except Exception as e:
            print(f"質問の追記中にエラーが発生しました: {e}")