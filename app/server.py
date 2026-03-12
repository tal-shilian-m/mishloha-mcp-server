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