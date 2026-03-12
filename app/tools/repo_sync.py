"""Repository sync — clones/pulls GitLab repos to local disk"""
import os
import asyncio
import logging
import yaml
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

REPOS_DIR = Path(os.getenv("REPOS_DIR", "/app/repos"))
REPOS_CONFIG = Path(__file__).parent.parent.parent / "repos.yaml"
SYNC_STATE_FILE = REPOS_DIR / ".sync_state.json"


class RepoSync:
    def __init__(self):
        self.gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")
        self.gitlab_token = os.getenv("GITLAB_TOKEN")
        REPOS_DIR.mkdir(parents=True, exist_ok=True)

    def load_repos_config(self) -> List[dict]:
        """Load repos list from repos.yaml"""
        if not REPOS_CONFIG.exists():
            return []
        with open(REPOS_CONFIG, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("repos", []) or []

    def _get_clone_url(self, repo_url: str) -> str:
        """Convert repo URL to authenticated clone URL"""
        # https://gitlab.com/mishloha/backend → https://oauth2:TOKEN@gitlab.com/mishloha/backend.git
        url = repo_url.rstrip("/")
        if not url.endswith(".git"):
            url += ".git"
        # Insert auth
        if "://" in url:
            proto, rest = url.split("://", 1)
            return f"{proto}://oauth2:{self.gitlab_token}@{rest}"
        return url

    def _repo_dir_name(self, repo_url: str) -> str:
        """Get local directory name for a repo"""
        # https://gitlab.com/mishloha/backend → mishloha__backend
        path = repo_url.rstrip("/").split("//")[-1]  # Remove protocol
        path = path.split("/", 1)[-1]  # Remove domain
        return path.replace("/", "__")

    def sync_repo(self, repo_url: str) -> Dict[str, Any]:
        """Clone or pull a single repo"""
        dir_name = self._repo_dir_name(repo_url)
        repo_path = REPOS_DIR / dir_name
        clone_url = self._get_clone_url(repo_url)

        try:
            if repo_path.exists() and (repo_path / ".git").exists():
                # Pull
                result = subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=str(repo_path),
                    capture_output=True, text=True, timeout=120,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
                )
                action = "pulled"
            else:
                # Clone
                repo_path.mkdir(parents=True, exist_ok=True)
                result = subprocess.run(
                    ["git", "clone", "--depth", "50", clone_url, str(repo_path)],
                    capture_output=True, text=True, timeout=300,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
                )
                action = "cloned"

            if result.returncode != 0:
                return {"url": repo_url, "status": "error", "error": result.stderr[:500]}

            # Get last commit info
            commit_result = subprocess.run(
                ["git", "log", "-1", "--format=%H|%s|%an|%ai"],
                cwd=str(repo_path),
                capture_output=True, text=True, timeout=10
            )
            last_commit = {}
            if commit_result.returncode == 0 and commit_result.stdout.strip():
                parts = commit_result.stdout.strip().split("|", 3)
                if len(parts) == 4:
                    last_commit = {
                        "hash": parts[0][:8],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3][:10]
                    }

            return {
                "url": repo_url,
                "local_path": str(repo_path),
                "dir_name": dir_name,
                "status": "ok",
                "action": action,
                "last_commit": last_commit
            }

        except subprocess.TimeoutExpired:
            return {"url": repo_url, "status": "error", "error": "timeout"}
        except Exception as e:
            return {"url": repo_url, "status": "error", "error": str(e)}

    def sync_all(self) -> Dict[str, Any]:
        """Sync all repos from config"""
        repos = self.load_repos_config()
        if not repos:
            return {"status": "no repos configured", "synced": 0}

        results = []
        for repo in repos:
            url = repo.get("url", "")
            if not url:
                continue
            logger.info(f"Syncing {url}...")
            result = self.sync_repo(url)
            result["name"] = repo.get("name", "")
            results.append(result)

        # Save sync state
        state = {
            "last_sync": datetime.utcnow().isoformat(),
            "repos": results
        }
        with open(SYNC_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        ok = sum(1 for r in results if r["status"] == "ok")
        errors = sum(1 for r in results if r["status"] == "error")

        return {
            "status": "ok",
            "synced": ok,
            "errors": errors,
            "results": results
        }

    def get_repo_path(self, repo_name_or_url: str) -> Path | None:
        """Find local path for a repo by name or URL"""
        repos = self.load_repos_config()

        for repo in repos:
            url = repo.get("url", "")
            name = repo.get("name", "")
            dir_name = self._repo_dir_name(url) if url else ""

            if (repo_name_or_url.lower() in name.lower() or
                repo_name_or_url.lower() in url.lower() or
                repo_name_or_url.lower() in dir_name.lower()):
                path = REPOS_DIR / dir_name
                if path.exists():
                    return path
        return None

    def list_synced_repos(self) -> List[Dict[str, Any]]:
        """List all synced repos with their paths"""
        repos = self.load_repos_config()
        result = []
        for repo in repos:
            url = repo.get("url", "")
            dir_name = self._repo_dir_name(url) if url else ""
            path = REPOS_DIR / dir_name
            result.append({
                "url": url,
                "name": repo.get("name", ""),
                "description": repo.get("description", ""),
                "local_path": str(path),
                "synced": path.exists() and (path / ".git").exists()
            })
        return result
