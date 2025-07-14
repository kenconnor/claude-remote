import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

class ProjectManager:
    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir
        self.projects_dir.mkdir(parents=True, exist_ok=True)
    
    def create_project(self, source_file: Path) -> Path:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_name = f"project_{timestamp}"
        project_path = self.projects_dir / temp_name
        
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / 'src').mkdir(exist_ok=True)
        (project_path / 'logs').mkdir(exist_ok=True)
        
        # プロジェクト情報を保存
        info = {
            'temp_name': temp_name,
            'source_file': str(source_file),
            'created_at': timestamp,
            'official_name': None,
            'working_directory': str(project_path / 'src')
        }
        
        with open(project_path / '.project_info.json', 'w') as f:
            json.dump(info, f, indent=2)
        
        return project_path
    
    def get_project_by_source(self, source_file: Path) -> Optional[Path]:
        for project_dir in self.projects_dir.iterdir():
            if project_dir.is_dir():
                info_file = project_dir / '.project_info.json'
                if info_file.exists():
                    with open(info_file, 'r') as f:
                        info = json.load(f)
                    if info['source_file'] == str(source_file):
                        return project_dir
        return None
    
    def update_project_name(self, project_path: Path, new_name: str):
        info_file = project_path / '.project_info.json'
        if info_file.exists():
            with open(info_file, 'r') as f:
                info = json.load(f)
            
            info['official_name'] = new_name
            
            with open(info_file, 'w') as f:
                json.dump(info, f, indent=2)
    
    def rename_project_directory(self, old_path: Path, new_name: str) -> Path:
        new_path = self.projects_dir / new_name
        if new_path.exists():
            raise ValueError(f"Project {new_name} already exists")
        
        shutil.move(str(old_path), str(new_path))
        
        # プロジェクト情報を更新
        info_file = new_path / '.project_info.json'
        if info_file.exists():
            with open(info_file, 'r') as f:
                info = json.load(f)
            
            info['official_name'] = new_name
            info['working_directory'] = str(new_path / 'src')
            
            with open(info_file, 'w') as f:
                json.dump(info, f, indent=2)
        
        return new_path
    
    def get_project_info(self, project_path: Path) -> Dict:
        info_file = project_path / '.project_info.json'
        if info_file.exists():
            with open(info_file, 'r') as f:
                return json.load(f)
        return {}
    
    def get_project_name(self, project_path: Path) -> str:
        info = self.get_project_info(project_path)
        return info.get('official_name') or info.get('temp_name', project_path.name)