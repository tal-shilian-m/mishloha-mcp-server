"""GitLab integration tools for MCP server"""
import os
import httpx
from typing import Dict, List, Any, Optional
from mcp.server import Server
from mcp.types import Tool, TextContent
import json

class GitLabClient:
    def __init__(self):
        self.base_url = os.getenv("GITLAB_URL", "https://gitlab.com").rstrip('/')
        self.token = os.getenv("GITLAB_TOKEN")
        if not self.token:
            raise ValueError("GITLAB_TOKEN environment variable is required")
        
        self.headers = {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json"
        }
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make authenticated request to GitLab API"""
        url = f"{self.base_url}/api/v4{endpoint}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    timeout=30.0,
                    **kwargs
                )
                response.raise_for_status()
                return response.json() if response.content else {}
            except httpx.HTTPError as e:
                return {"error": f"GitLab API request failed: {str(e)}"}
            except Exception as e:
                return {"error": f"Unexpected error: {str(e)}"}

def register_gitlab_tools(server: Server):
    """Register all GitLab tools with the MCP server"""
    gitlab = GitLabClient()
    
    @server.call_tool()
    async def gitlab_search_code(query: str, scope: Optional[str] = None) -> List[TextContent]:
        """חיפוש קוד במאגרי הקוד של GitLab
        
        Args:
            query: מונח החיפוש
            scope: היקף החיפוש (blobs, commits, issues, merge_requests, milestones, snippet_titles, users, wiki_blobs)
        """
        params = {"search": query}
        if scope:
            params["scope"] = scope
        
        result = await gitlab._make_request("GET", "/search", params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def gitlab_get_file(project_id: str, file_path: str, branch: Optional[str] = "main") -> List[TextContent]:
        """קריאת קובץ ממאגר GitLab
        
        Args:
            project_id: מזהה הפרויקט
            file_path: נתיב הקובץ
            branch: שם הענף (ברירת מחדל: main)
        """
        params = {"ref": branch} if branch else {}
        endpoint = f"/projects/{project_id}/repository/files/{file_path.replace('/', '%2F')}"
        
        result = await gitlab._make_request("GET", endpoint, params=params)
        
        if "content" in result:
            try:
                import base64
                content = base64.b64decode(result["content"]).decode("utf-8")
                result["decoded_content"] = content
            except Exception as e:
                result["decode_error"] = str(e)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def gitlab_list_projects(owned: Optional[bool] = None, search: Optional[str] = None) -> List[TextContent]:
        """רשימת פרויקטים ב-GitLab
        
        Args:
            owned: האם להציג רק פרויקטים בבעלות המשתמש
            search: מונח חיפוש לסינון פרויקטים
        """
        params = {}
        if owned is not None:
            params["owned"] = str(owned).lower()
        if search:
            params["search"] = search
        
        result = await gitlab._make_request("GET", "/projects", params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]
    
    @server.call_tool()
    async def gitlab_get_file_tree(project_id: str, path: Optional[str] = "", branch: Optional[str] = "main") -> List[TextContent]:
        """עיון במבנה התיקיות והקבצים במאגר
        
        Args:
            project_id: מזהה הפרויקט
            path: נתיב התיקייה (ריק לשורש)
            branch: שם הענף (ברירת מחדל: main)
        """
        params = {"ref": branch, "recursive": False}
        if path:
            params["path"] = path
        
        endpoint = f"/projects/{project_id}/repository/tree"
        result = await gitlab._make_request("GET", endpoint, params=params)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False)
        )]