"""Repository indexer — scans GitLab repos and builds deep descriptions for Claude"""
import os
import json
import httpx
import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path

INDEX_FILE = Path(__file__).parent.parent.parent / "repo_index.json"
REPOS_FILE = Path(__file__).parent.parent.parent / "repos.yaml"


class RepoIndexer:
    def __init__(self):
        self.gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")
        self.gitlab_token = os.getenv("GITLAB_TOKEN")
        self.headers = {"PRIVATE-TOKEN": self.gitlab_token}
    
    def load_repos_config(self) -> List[dict]:
        """Load repos list from repos.yaml"""
        if not REPOS_FILE.exists():
            return []
        with open(REPOS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("repos", []) or []
    
    def load_index(self) -> Dict[str, Any]:
        """Load existing index"""
        if INDEX_FILE.exists():
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"repos": {}}
    
    def save_index(self, index: Dict[str, Any]):
        """Save index to file"""
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    
    def _extract_project_path(self, url: str) -> str:
        """Extract GitLab project path from URL"""
        # https://gitlab.com/mishloha/backend → mishloha/backend
        url = url.rstrip("/")
        if "gitlab.com/" in url:
            return url.split("gitlab.com/")[1]
        elif self.gitlab_url.replace("https://", "") in url:
            return url.split(self.gitlab_url.replace("https://", "") + "/")[1]
        return url
    
    async def _api_get(self, endpoint: str) -> Any:
        """Make GitLab API request"""
        url = f"{self.gitlab_url}/api/v4{endpoint}"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, headers=self.headers, timeout=30.0)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return {"error": str(e)}
    
    async def scan_repo(self, repo_url: str, name: str = "", description: str = "") -> Dict[str, Any]:
        """Scan a single repo and build deep description"""
        project_path = self._extract_project_path(repo_url)
        encoded_path = project_path.replace("/", "%2F")
        
        # 1. Get project info
        project = await self._api_get(f"/projects/{encoded_path}")
        if "error" in project:
            return {"error": f"Failed to fetch project: {project['error']}"}
        
        project_id = project.get("id")
        
        # 2. Get file tree (top level + important dirs)
        tree = await self._api_get(f"/projects/{project_id}/repository/tree?per_page=100&recursive=false")
        
        # 3. Read README if exists
        readme_content = ""
        for item in (tree if isinstance(tree, list) else []):
            if item.get("name", "").lower() in ("readme.md", "readme.txt", "readme"):
                readme_data = await self._api_get(
                    f"/projects/{project_id}/repository/files/{item['name']}/raw?ref=main"
                )
                if not isinstance(readme_data, dict) or "error" not in readme_data:
                    # Raw file content comes as text, re-fetch properly
                    async with httpx.AsyncClient() as client:
                        try:
                            resp = await client.get(
                                f"{self.gitlab_url}/api/v4/projects/{project_id}/repository/files/{item['name']}/raw",
                                headers=self.headers,
                                params={"ref": project.get("default_branch", "main")},
                                timeout=30.0
                            )
                            readme_content = resp.text[:3000]  # Limit size
                        except:
                            pass
                break
        
        # 4. Get recent commits
        commits = await self._api_get(f"/projects/{project_id}/repository/commits?per_page=10")
        recent_commits = []
        if isinstance(commits, list):
            for c in commits[:10]:
                recent_commits.append({
                    "message": c.get("title", ""),
                    "author": c.get("author_name", ""),
                    "date": c.get("created_at", "")[:10]
                })
        
        # 5. Get languages
        languages = await self._api_get(f"/projects/{project_id}/languages")
        
        # 6. Get branches
        branches = await self._api_get(f"/projects/{project_id}/repository/branches?per_page=20")
        branch_names = [b.get("name") for b in (branches if isinstance(branches, list) else [])]
        
        # 7. Get open MRs count
        mrs = await self._api_get(f"/projects/{project_id}/merge_requests?state=opened&per_page=1")
        
        # 8. Build file structure summary
        file_structure = []
        if isinstance(tree, list):
            for item in tree:
                icon = "📁" if item.get("type") == "tree" else "📄"
                file_structure.append(f"{icon} {item.get('name', '')}")
        
        # Build the deep description
        repo_info = {
            "url": repo_url,
            "name": name or project.get("name", ""),
            "user_description": description,
            "gitlab_description": project.get("description", ""),
            "default_branch": project.get("default_branch", "main"),
            "languages": languages if isinstance(languages, dict) else {},
            "file_structure": file_structure,
            "readme_summary": readme_content[:2000],
            "recent_commits": recent_commits,
            "branches": branch_names,
            "open_mrs": len(mrs) if isinstance(mrs, list) else 0,
            "created_at": project.get("created_at", "")[:10],
            "last_activity": project.get("last_activity_at", "")[:10],
            "visibility": project.get("visibility", ""),
            "project_id": project_id,
        }
        
        return repo_info
    
    async def rebuild_index(self) -> Dict[str, Any]:
        """Scan all repos from repos.yaml and rebuild the index"""
        repos_config = self.load_repos_config()
        if not repos_config:
            return {"status": "no repos configured", "count": 0}
        
        index = {"repos": {}}
        errors = []
        
        for repo in repos_config:
            url = repo.get("url", "")
            name = repo.get("name", "")
            desc = repo.get("description", "")
            
            if not url:
                continue
            
            result = await self.scan_repo(url, name, desc)
            if "error" in result:
                errors.append({"url": url, "error": result["error"]})
            else:
                index["repos"][url] = result
        
        self.save_index(index)
        
        return {
            "status": "ok",
            "repos_scanned": len(index["repos"]),
            "errors": errors
        }
    
    def get_index_summary(self) -> str:
        """Get a text summary of all indexed repos for Claude context"""
        index = self.load_index()
        if not index.get("repos"):
            return "אין repositories מוגדרים. הוסף repos ב-repos.yaml והרץ rebuild."
        
        lines = ["# Repositories מוכרים\n"]
        for url, info in index["repos"].items():
            lines.append(f"## {info.get('name', 'Unknown')} ({url})")
            if info.get("user_description"):
                lines.append(f"**תיאור:** {info['user_description']}")
            if info.get("gitlab_description"):
                lines.append(f"**תיאור GitLab:** {info['gitlab_description']}")
            if info.get("languages"):
                langs = ", ".join(f"{k} ({v}%)" for k, v in info["languages"].items())
                lines.append(f"**שפות:** {langs}")
            if info.get("file_structure"):
                lines.append("**מבנה:**")
                for f in info["file_structure"][:20]:
                    lines.append(f"  {f}")
            if info.get("readme_summary"):
                lines.append(f"**README:**\n{info['readme_summary'][:500]}...")
            if info.get("recent_commits"):
                lines.append("**commits אחרונים:**")
                for c in info["recent_commits"][:5]:
                    lines.append(f"  - {c['date']}: {c['message']} ({c['author']})")
            lines.append("")
        
        return "\n".join(lines)
