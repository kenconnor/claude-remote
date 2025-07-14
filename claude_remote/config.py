import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Paths
    GDRIVE_MOUNT_PATH = Path(os.getenv('GDRIVE_MOUNT_PATH', '/gdrive/claude-remote'))
    PROJECTS_DIR = Path(os.getenv('PROJECTS_DIR', './projects'))
    
    # Slack
    SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
    
    # Claude Code settings
    CLAUDE_TIMEOUT = int(os.getenv('CLAUDE_TIMEOUT', 1800))
    MAX_CONCURRENT_EXECUTIONS = int(os.getenv('MAX_CONCURRENT_EXECUTIONS', 3))
    TOKEN_RETRY_INTERVAL = int(os.getenv('TOKEN_RETRY_INTERVAL', 300))
    MAX_TOKEN_RETRIES = int(os.getenv('MAX_TOKEN_RETRIES', 10))
    
    # Docker settings
    DOCKER_IMAGE_NAME = os.getenv('DOCKER_IMAGE_NAME', 'claude-remote')
    DOCKER_NETWORK_NAME = os.getenv('DOCKER_NETWORK_NAME', 'claude-remote-net')
    
    @classmethod
    def validate(cls):
        if not cls.SLACK_WEBHOOK_URL:
            raise ValueError("SLACK_WEBHOOK_URL is required")
        
        cls.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        
        if not cls.GDRIVE_MOUNT_PATH.exists():
            raise ValueError(f"Google Drive mount path does not exist: {cls.GDRIVE_MOUNT_PATH}")
        
        return True