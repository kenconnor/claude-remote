import requests
import json
from datetime import datetime
from typing import Dict, Optional
from .config import Config

class SlackNotifier:
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or Config.SLACK_WEBHOOK_URL
        
    def send_message(self, message: Dict) -> bool:
        try:
            response = requests.post(
                self.webhook_url,
                json=message,
                headers={'Content-Type': 'application/json'}
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send Slack message: {e}")
            return False
    
    def notify_start(self, project_name: str, task_summary: str, source_file: str = None):
        fields = [
            {
                "type": "mrkdwn",
                "text": f"*プロジェクト:*\n{project_name}"
            },
            {
                "type": "mrkdwn",
                "text": f"*タスク:*\n{task_summary[:100]}..."
            }
        ]
        
        if source_file:
            fields.insert(0, {
                "type": "mrkdwn",
                "text": f"*ファイル:*\n{source_file}"
            })
        
        message = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚀 Claude Code実行開始"
                    }
                },
                {
                    "type": "section",
                    "fields": fields
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    ]
                }
            ]
        }
        return self.send_message(message)
    
    def notify_complete(self, project_name: str, result_summary: str, source_file: str = None):
        fields = [
            {
                "type": "mrkdwn",
                "text": f"*プロジェクト:*\n{project_name}"
            },
            {
                "type": "mrkdwn",
                "text": f"*結果:*\n{result_summary[:200]}..."
            }
        ]
        
        if source_file:
            fields.insert(0, {
                "type": "mrkdwn",
                "text": f"*ファイル:*\n{source_file}"
            })
        
        message = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Claude Code実行完了"
                    }
                },
                {
                    "type": "section",
                    "fields": fields
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    ]
                }
            ]
        }
        return self.send_message(message)
    
    def notify_error(self, project_name: str, error_level: str, 
                    error_summary: str, error_detail: Optional[str] = None,
                    suggestion: Optional[str] = None):
        emoji = {
            "minor": "⚠️",
            "major": "❌",
            "critical": "🚨"
        }.get(error_level, "❓")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} エラーが発生しました"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*プロジェクト:*\n{project_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*エラー概要:*\n{error_summary}"
                    }
                ]
            }
        ]
        
        if error_detail:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*詳細:*\n```{error_detail[:500]}```"
                }
            })
        
        if suggestion:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*対処方法:*\n{suggestion}"
                }
            })
        
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"発生時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })
        
        return self.send_message({"blocks": blocks})
    
    def notify_token_retry(self, project_name: str, retry_count: int):
        message = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⏳ *トークン制限により待機中*\nプロジェクト: {project_name}\n再試行: {retry_count}/{Config.MAX_TOKEN_RETRIES}"
                    }
                }
            ]
        }
        return self.send_message(message)