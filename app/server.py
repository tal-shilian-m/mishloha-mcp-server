"""Main MCP Server for Mishloha development tools"""
import os
import json
import asyncio
import logging
from typing import List
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Resource, TextResourceContents, Tool

from .tools.gitlab_tools import register_gitlab_tools
from .tools.jira_tools import register_jira_tools
from .tools.figma_tools import register_figma_tools
from .tools.repo_indexer import RepoIndexer
from .tools.repo_sync import RepoSync, REPOS_DIR
from .tools.code_map import generate_code_map, generate_all_code_maps, search_code

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthenticatedSseServerTransport(SseServerTransport):
    """SSE transport with Bearer token authentication"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        super().__init__(host=host, port=port)
        self.auth_token = os.getenv("MCP_AUTH_TOKEN")
        if not self.auth_token:
            raise ValueError("MCP_AUTH_TOKEN environment variable is required")
    
    async def handle_request(self, request: Request) -> Response:
        """Override to add authentication"""
        # Skip auth for health check
        if request.url.path in ["/health", "/"]:
            return await self._handle_health_check(request)
        
        # Check authentication
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return Response(
                content="Missing or invalid authorization header",
                status_code=401,
                headers={"Content-Type": "text/plain"}
            )
        
        token = auth_header.split(" ")[1]
        if token != self.auth_token:
            return Response(
                content="Invalid authentication token", 
                status_code=401,
                headers={"Content-Type": "text/plain"}
            )
        
        # Call parent handler for authenticated requests
        return await super().handle_request(request)
    
    async def _handle_health_check(self, request: Request) -> Response:
        """Handle health check endpoint"""
        if request.url.path == "/health":
            return Response(
                content='{"status": "healthy", "service": "mishloha-mcp-server"}',
                headers={"Content-Type": "application/json"}
            )
        elif request.url.path == "/":
            return Response(
                content='{"service": "Mishloha MCP Server", "status": "running"}',
                headers={"Content-Type": "application/json"}  
            )
        else:
            return Response(content="Not Found", status_code=404)

class MishlohaServer:
    def __init__(self):
        self.server = Server("mishloha-mcp-server")
        self.setup_server()
        
    def setup_server(self):
        """Setup the MCP server with all tools and handlers"""
        
        @self.server.list_resources()
        async def list_resources() -> List[Resource]:
            """List available resources"""
            return [
                Resource(
                    uri="health://status", 
                    name="Server Health Status",
                    description="Current status of the MCP server",
                    mimeType="text/plain"
                )
            ]
        
        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read a specific resource"""
            if uri == "health://status":
                return TextResourceContents(
                    uri=uri,
                    mimeType="text/plain",
                    text="MCP Server is running and healthy"
                )
            else:
                raise ValueError(f"Unknown resource: {uri}")
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List all available tools"""
            tools = []
            
            # GitLab tools
            tools.extend([
                Tool(
                    name="gitlab_search_code",
                    description="חיפוש קוד במאגרי הקוד של GitLab",
                    inputSchema={
                        "type": "object", 
                        "properties": {
                            "query": {"type": "string", "description": "מונח החיפוש"},
                            "scope": {"type": "string", "description": "היקף החיפוש", "enum": ["blobs", "commits", "issues", "merge_requests", "milestones", "snippet_titles", "users", "wiki_blobs"]}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="gitlab_get_file",
                    description="קריאת קובץ ממאגר GitLab", 
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string", "description": "מזהה הפרויקט"},
                            "file_path": {"type": "string", "description": "נתיב הקובץ"},
                            "branch": {"type": "string", "description": "שם הענף", "default": "main"}
                        },
                        "required": ["project_id", "file_path"]
                    }
                ),
                Tool(
                    name="gitlab_list_projects",
                    description="רשימת פרויקטים ב-GitLab",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "owned": {"type": "boolean", "description": "האם להציג רק פרויקטים בבעלות המשתמש"},
                            "search": {"type": "string", "description": "מונח חיפוש לסינון פרויקטים"}
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="gitlab_get_file_tree",
                    description="עיון במבנה התיקיות והקבצים במאגר",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string", "description": "מזהה הפרויקט"},
                            "path": {"type": "string", "description": "נתיב התיקייה", "default": ""},
                            "branch": {"type": "string", "description": "שם הענף", "default": "main"}
                        },
                        "required": ["project_id"]
                    }
                )
            ])
            
            # Jira tools
            tools.extend([
                Tool(
                    name="jira_search_issues",
                    description="חיפוש issues ב-Jira באמצעות JQL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "jql": {"type": "string", "description": "שאילתת JQL"},
                            "max_results": {"type": "integer", "description": "מספר תוצאות מקסימלי", "default": 50}
                        },
                        "required": ["jql"]
                    }
                ),
                Tool(
                    name="jira_get_issue",
                    description="קבלת פרטי issue ספציפי",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {"type": "string", "description": "מפתח ה-issue"}
                        },
                        "required": ["issue_key"]
                    }
                ),
                Tool(
                    name="jira_list_sprints",
                    description="רשימת ספרינטים בלוח",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "board_id": {"type": "string", "description": "מזהה הלוח"}
                        },
                        "required": ["board_id"]
                    }
                ),
                Tool(
                    name="jira_get_sprint_issues",
                    description="קבלת כל ה-issues בספרינט",
                    inputSchema={
                        "type": "object", 
                        "properties": {
                            "sprint_id": {"type": "string", "description": "מזהה הספרינט"}
                        },
                        "required": ["sprint_id"]
                    }
                ),
                Tool(
                    name="jira_get_board",
                    description="סקירה של לוח Jira",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "board_id": {"type": "string", "description": "מזהה הלוח"}
                        },
                        "required": ["board_id"]
                    }
                )
            ])
            
            # Figma tools
            tools.extend([
                Tool(
                    name="figma_get_file",
                    description="קבלת מבנה קובץ Figma (עמודים ופריימים)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_key": {"type": "string", "description": "מזהה הקובץ ב-Figma"},
                            "depth": {"type": "integer", "description": "עומק הנתונים", "default": 1}
                        },
                        "required": ["file_key"]
                    }
                ),
                Tool(
                    name="figma_get_comments",
                    description="קבלת הערות על קובץ Figma",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_key": {"type": "string", "description": "מזהה הקובץ ב-Figma"}
                        },
                        "required": ["file_key"]
                    }
                ),
                Tool(
                    name="figma_search_components", 
                    description="חיפוש רכיבים בצוות",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "team_id": {"type": "string", "description": "מזהה הצוות"},
                            "query": {"type": "string", "description": "מונח חיפוש"}
                        },
                        "required": ["team_id"]
                    }
                ),
                Tool(
                    name="figma_get_frame_image",
                    description="יצוא תמונה של פריים/רכיב",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_key": {"type": "string", "description": "מזהה הקובץ ב-Figma"},
                            "node_ids": {"type": "string", "description": "מזהי הצמתים (מופרדים בפסיק)"},
                            "format": {"type": "string", "description": "פורמט התמונה", "enum": ["png", "jpg", "svg", "pdf"], "default": "png"},
                            "scale": {"type": "string", "description": "רמת זום", "default": "1"}
                        },
                        "required": ["file_key", "node_ids"]
                    }
                ),
                Tool(
                    name="figma_get_file_nodes",
                    description="קבלת פרטי צמתים ספציפיים בקובץ",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_key": {"type": "string", "description": "מזהה הקובץ ב-Figma"},
                            "node_ids": {"type": "string", "description": "מזהי הצמתים (מופרדים בפסיק)"},
                            "depth": {"type": "integer", "description": "עומק הנתונים", "default": 1}
                        },
                        "required": ["file_key", "node_ids"]
                    }
                )
            ])
            
            # Code tools (local repos)
            tools.extend([
                Tool(
                    name="code_sync_repos",
                    description="סנכרון כל ה-repositories מ-repos.yaml — clone או pull. הרץ פעם ביום או אחרי הוספת repos חדשים",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                Tool(
                    name="code_get_map",
                    description="מפת הקוד המלאה — כל הקבצים בכל ה-repos עם תיאור: classes, functions, exports. השתמש בזה ראשון כדי להבין מה יש בקוד",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repo": {"type": "string", "description": "שם ה-repo (אופציונלי — בלי זה מחזיר הכל)"}
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="code_search",
                    description="חיפוש טקסט חופשי בכל הקוד — מוצא קבצים ושורות שמכילים את מונח החיפוש",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "מונח חיפוש (שם פונקציה, class, טקסט)"},
                            "repo": {"type": "string", "description": "סינון ל-repo ספציפי (אופציונלי)"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="code_read_file",
                    description="קריאת קובץ מלא מה-repo המקומי. השתמש אחרי code_get_map או code_search כדי לצלול לקובץ ספציפי",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repo": {"type": "string", "description": "שם ה-repo"},
                            "file_path": {"type": "string", "description": "נתיב הקובץ בתוך ה-repo"},
                            "start_line": {"type": "integer", "description": "שורה התחלה (אופציונלי)"},
                            "end_line": {"type": "integer", "description": "שורה סיום (אופציונלי)"}
                        },
                        "required": ["repo", "file_path"]
                    }
                ),
                Tool(
                    name="code_list_repos",
                    description="רשימת כל ה-repos המסונכרנים עם סטטוס",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
            ])
            
            # Repo Index tools
            tools.extend([
                Tool(
                    name="repo_index_rebuild",
                    description="סריקת כל ה-repositories מ-repos.yaml ובניית אינדקס מעמיק. הרץ אחרי הוספת repos חדשים",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                Tool(
                    name="repo_index_lookup",
                    description="חיפוש repository לפי שם או תיאור — מחזיר מידע מעמיק על הrepo (מבנה, שפות, commits, README)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "שם או מילת חיפוש"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="repo_index_list",
                    description="רשימת כל ה-repositories המוכרים עם תיאור מעמיק של כל אחד",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                )
            ])
            
            return tools
        
        # Register code tools
        repo_sync = RepoSync()
        
        @self.server.call_tool()
        async def code_sync_repos() -> list:
            """סנכרון repos"""
            from mcp.types import TextContent
            result = repo_sync.sync_all()
            # After sync, regenerate code maps
            if result.get("synced", 0) > 0:
                generate_all_code_maps()
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
        
        @self.server.call_tool()
        async def code_get_map(repo: str = None) -> list:
            """מפת הקוד"""
            from mcp.types import TextContent
            from pathlib import Path as P
            
            map_file = REPOS_DIR / ".code_maps.json"
            if not map_file.exists():
                # Generate on first request
                maps = generate_all_code_maps()
            else:
                with open(map_file, "r", encoding="utf-8") as f:
                    maps = json.load(f)
            
            if repo:
                # Filter to specific repo
                filtered = {k: v for k, v in maps.items() if repo.lower() in k.lower()}
                if not filtered:
                    return [TextContent(type="text", text=f"לא נמצא repo שתואם '{repo}'. repos קיימים: {', '.join(maps.keys())}")]
                maps = filtered
            
            # Format for Claude
            output = []
            for repo_name, code_map in maps.items():
                output.append(f"## 📁 {repo_name}")
                output.append(f"קבצים: {code_map.get('total_files', 0)} | שורות: {code_map.get('total_lines', 0)}")
                output.append("")
                for file_path, info in code_map.get("files", {}).items():
                    line = f"  {file_path}"
                    if info.get("summary"):
                        line += f" — {info['summary']}"
                    if info.get("classes"):
                        line += f" | classes: {', '.join(info['classes'])}"
                    if info.get("functions"):
                        line += f" | functions: {', '.join(info['functions'][:8])}"
                    if info.get("exports"):
                        line += f" | exports: {', '.join(info['exports'][:8])}"
                    output.append(line)
                output.append("")
            
            return [TextContent(type="text", text="\n".join(output))]
        
        @self.server.call_tool()
        async def code_search(query: str, repo: str = None) -> list:
            """חיפוש בקוד"""
            from mcp.types import TextContent
            results = search_code(query, repo)
            if not results:
                return [TextContent(type="text", text=f"לא נמצאו תוצאות ל-'{query}'")]
            
            output = [f"נמצאו {len(results)} קבצים עם '{query}':\n"]
            for r in results:
                output.append(f"📄 {r['repo']}/{r['file']}")
                for m in r["matches"]:
                    output.append(f"  L{m['line']}: {m['text']}")
                output.append("")
            
            return [TextContent(type="text", text="\n".join(output))]
        
        @self.server.call_tool()
        async def code_read_file(repo: str, file_path: str, start_line: int = None, end_line: int = None) -> list:
            """קריאת קובץ מקומי"""
            from mcp.types import TextContent
            from pathlib import Path as P
            
            # Find repo directory
            target = None
            for repo_dir in sorted(REPOS_DIR.iterdir()):
                if repo_dir.is_dir() and repo.lower() in repo_dir.name.lower():
                    target = repo_dir
                    break
            
            if not target:
                return [TextContent(type="text", text=f"לא נמצא repo '{repo}'")]
            
            full_path = target / file_path
            if not full_path.exists():
                return [TextContent(type="text", text=f"קובץ לא נמצא: {file_path}")]
            
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                lines = content.split("\n")
                
                if start_line or end_line:
                    start = (start_line or 1) - 1
                    end = end_line or len(lines)
                    lines = lines[start:end]
                    header = f"# {file_path} (שורות {start+1}-{end})\n\n"
                else:
                    header = f"# {file_path} ({len(lines)} שורות)\n\n"
                
                return [TextContent(type="text", text=header + "\n".join(lines))]
            except Exception as e:
                return [TextContent(type="text", text=f"שגיאה בקריאת הקובץ: {e}")]
        
        @self.server.call_tool()
        async def code_list_repos() -> list:
            """רשימת repos"""
            from mcp.types import TextContent
            repos = repo_sync.list_synced_repos()
            return [TextContent(type="text", text=json.dumps(repos, indent=2, ensure_ascii=False))]
        
        # Register repo index tools
        indexer = RepoIndexer()
        
        @self.server.call_tool()
        async def repo_index_rebuild() -> list:
            """סריקת כל ה-repos ובניית אינדקס"""
            from mcp.types import TextContent
            result = await indexer.rebuild_index()
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
        
        @self.server.call_tool()
        async def repo_index_lookup(query: str) -> list:
            """חיפוש repo לפי שם או תיאור"""
            from mcp.types import TextContent
            index = indexer.load_index()
            query_lower = query.lower()
            results = []
            for url, info in index.get("repos", {}).items():
                name = info.get("name", "").lower()
                desc = (info.get("user_description", "") + " " + info.get("gitlab_description", "")).lower()
                readme = info.get("readme_summary", "").lower()
                if query_lower in name or query_lower in desc or query_lower in readme or query_lower in url.lower():
                    results.append(info)
            if not results:
                return [TextContent(type="text", text=f"לא נמצא repo שתואם '{query}'. הרץ repo_index_list לראות את כל ה-repos המוכרים.")]
            return [TextContent(type="text", text=json.dumps(results, indent=2, ensure_ascii=False))]
        
        @self.server.call_tool()
        async def repo_index_list() -> list:
            """רשימת כל ה-repos עם תיאור מעמיק"""
            from mcp.types import TextContent
            summary = indexer.get_index_summary()
            return [TextContent(type="text", text=summary)]
        
        # Register tool implementations
        try:
            register_gitlab_tools(self.server)
            register_jira_tools(self.server) 
            register_figma_tools(self.server)
            logger.info("All tools registered successfully")
        except Exception as e:
            logger.error(f"Failed to register tools: {e}")
            raise
    
    async def run(self, host: str = "0.0.0.0", port: int = 8000):
        """Run the server with authenticated SSE transport"""
        transport = AuthenticatedSseServerTransport(host=host, port=port)
        
        logger.info(f"Starting Mishloha MCP Server on {host}:{port}")
        logger.info("Environment variables required:")
        logger.info("- GITLAB_URL, GITLAB_TOKEN")
        logger.info("- JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN")
        logger.info("- FIGMA_TOKEN")
        logger.info("- MCP_AUTH_TOKEN (for API authentication)")
        
        await self.server.run(transport)

async def main():
    """Main entry point"""
    port = int(os.getenv("PORT", 8000))
    server = MishlohaServer()
    await server.run(port=port)

if __name__ == "__main__":
    asyncio.run(main())