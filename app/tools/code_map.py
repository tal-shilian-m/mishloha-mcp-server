"""Code Map generator — builds a high-level map of the entire codebase for Claude"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

REPOS_DIR = Path(os.getenv("REPOS_DIR", "/app/repos"))

# File extensions we care about
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".cs", ".java", ".go", ".rb", ".php",
    ".html", ".css", ".scss", ".vue", ".svelte",
    ".sql", ".graphql", ".proto",
    ".yaml", ".yml", ".json", ".toml",
    ".md", ".txt", ".rst",
    ".sh", ".bash", ".dockerfile",
    ".env.example", ".gitignore",
}

# Directories to skip
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    "vendor", "packages", ".idea", ".vscode", "bin", "obj",
    "migrations",  # Usually auto-generated
}

# Max file size to read (50KB)
MAX_FILE_SIZE = 50_000


def _should_include(path: Path) -> bool:
    """Check if file should be included in code map"""
    if any(skip in path.parts for skip in SKIP_DIRS):
        return False
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in CODE_EXTENSIONS:
        return True
    if name in {"dockerfile", "makefile", "procfile", "rakefile", ".env.example"}:
        return True
    return False


def _extract_file_summary(file_path: Path) -> Dict[str, Any]:
    """Extract a concise summary of a code file"""
    try:
        stat = file_path.stat()
        if stat.st_size > MAX_FILE_SIZE:
            return {
                "size": stat.st_size,
                "summary": f"[קובץ גדול — {stat.st_size // 1024}KB, דורש קריאה ישירה]",
                "type": file_path.suffix
            }

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")
        total_lines = len(lines)

        info: Dict[str, Any] = {
            "size": stat.st_size,
            "lines": total_lines,
            "type": file_path.suffix
        }

        # Extract based on file type
        suffix = file_path.suffix.lower()

        if suffix in (".py",):
            info.update(_summarize_python(lines))
        elif suffix in (".js", ".ts", ".jsx", ".tsx"):
            info.update(_summarize_javascript(lines))
        elif suffix in (".cs",):
            info.update(_summarize_csharp(lines))
        elif suffix in (".html", ".vue", ".svelte"):
            info["summary"] = f"Template/markup, {total_lines} שורות"
        elif suffix in (".css", ".scss"):
            info["summary"] = f"Stylesheet, {total_lines} שורות"
        elif suffix in (".sql",):
            info["summary"] = _summarize_sql(lines)
        elif suffix in (".md", ".txt", ".rst"):
            # First meaningful line as summary
            for line in lines[:10]:
                stripped = line.strip().lstrip("#").strip()
                if stripped:
                    info["summary"] = stripped[:100]
                    break
        elif suffix in (".json",):
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    info["summary"] = f"JSON object, keys: {', '.join(list(data.keys())[:10])}"
                elif isinstance(data, list):
                    info["summary"] = f"JSON array, {len(data)} items"
            except:
                info["summary"] = f"JSON file, {total_lines} שורות"
        elif suffix in (".yaml", ".yml"):
            info["summary"] = f"YAML config, {total_lines} שורות"
        else:
            info["summary"] = f"{total_lines} שורות"

        return info

    except Exception as e:
        return {"error": str(e)}


def _summarize_python(lines: List[str]) -> Dict[str, Any]:
    """Extract Python file summary"""
    classes = []
    functions = []
    imports = []
    docstring = ""

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("class ") and "(" in stripped:
            name = stripped.split("class ")[1].split("(")[0].strip()
            classes.append(name)
        elif stripped.startswith("def ") and "(" in stripped:
            name = stripped.split("def ")[1].split("(")[0].strip()
            if not name.startswith("_") or name == "__init__":
                functions.append(name)
        elif stripped.startswith(("import ", "from ")) and i < 30:
            imports.append(stripped)
        elif stripped.startswith('"""') and i < 5 and not docstring:
            # Module docstring
            if stripped.count('"""') >= 2:
                docstring = stripped.strip('"').strip()
            else:
                # Multi-line docstring
                doc_lines = [stripped.lstrip('"')]
                for j in range(i + 1, min(i + 5, len(lines))):
                    if '"""' in lines[j]:
                        doc_lines.append(lines[j].strip().rstrip('"'))
                        break
                    doc_lines.append(lines[j].strip())
                docstring = " ".join(doc_lines).strip()

    result = {}
    if docstring:
        result["summary"] = docstring[:150]
    if classes:
        result["classes"] = classes[:10]
    if functions:
        result["functions"] = functions[:15]

    if not result:
        result["summary"] = f"Python module, {len(lines)} שורות"

    return result


def _summarize_javascript(lines: List[str]) -> Dict[str, Any]:
    """Extract JS/TS file summary"""
    exports = []
    functions = []
    components = []

    for line in lines:
        stripped = line.strip()
        if "export " in stripped:
            if "function " in stripped:
                name = stripped.split("function ")[1].split("(")[0].strip()
                exports.append(name)
            elif "class " in stripped:
                name = stripped.split("class ")[1].split(" ")[0].split("{")[0].strip()
                exports.append(name)
            elif "const " in stripped:
                name = stripped.split("const ")[1].split("=")[0].split(":")[0].strip()
                exports.append(name)
        elif stripped.startswith("function "):
            name = stripped.split("function ")[1].split("(")[0].strip()
            functions.append(name)

    result = {}
    if exports:
        result["exports"] = exports[:15]
    if functions:
        result["functions"] = functions[:10]
    if not result:
        result["summary"] = f"JS/TS module, {len(lines)} שורות"

    return result


def _summarize_csharp(lines: List[str]) -> Dict[str, Any]:
    """Extract C# file summary"""
    classes = []
    methods = []
    namespace = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("namespace "):
            namespace = stripped.split("namespace ")[1].rstrip("{").strip()
        elif " class " in stripped:
            parts = stripped.split("class ")
            if len(parts) > 1:
                name = parts[1].split(":")[0].split("{")[0].strip()
                classes.append(name)
        elif ("public " in stripped or "private " in stripped) and "(" in stripped and ")" in stripped:
            # Method signature
            for keyword in ("public ", "private ", "protected ", "internal "):
                stripped = stripped.replace(keyword, "")
            for keyword in ("static ", "async ", "virtual ", "override ", "abstract "):
                stripped = stripped.replace(keyword, "")
            if "(" in stripped:
                name = stripped.split("(")[0].strip().split(" ")[-1]
                if name and not name.startswith("."):
                    methods.append(name)

    result = {}
    if namespace:
        result["namespace"] = namespace
    if classes:
        result["classes"] = classes[:10]
    if methods:
        result["methods"] = methods[:15]
    if not result:
        result["summary"] = f"C# file, {len(lines)} שורות"

    return result


def _summarize_sql(lines: List[str]) -> str:
    """Extract SQL summary"""
    tables = []
    for line in lines:
        upper = line.strip().upper()
        if "CREATE TABLE" in upper:
            parts = line.strip().split()
            for i, p in enumerate(parts):
                if p.upper() in ("TABLE", "EXISTS") and i + 1 < len(parts):
                    name = parts[i + 1].strip("(").strip("`").strip('"')
                    if name.upper() not in ("IF", "NOT", "EXISTS"):
                        tables.append(name)
                        break
    if tables:
        return f"SQL: tables {', '.join(tables[:10])}"
    return f"SQL file, {len(lines)} שורות"


def generate_code_map(repo_path: Path) -> Dict[str, Any]:
    """Generate a complete code map for a repository"""
    if not repo_path.exists():
        return {"error": f"Path {repo_path} does not exist"}

    file_map = {}
    total_files = 0
    total_lines = 0

    for file_path in sorted(repo_path.rglob("*")):
        if not file_path.is_file():
            continue
        if not _should_include(file_path):
            continue

        rel_path = str(file_path.relative_to(repo_path))
        summary = _extract_file_summary(file_path)
        file_map[rel_path] = summary
        total_files += 1
        total_lines += summary.get("lines", 0)

    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "files": file_map
    }


def generate_all_code_maps() -> Dict[str, Any]:
    """Generate code maps for all synced repos"""
    if not REPOS_DIR.exists():
        return {"error": "repos directory does not exist"}

    maps = {}
    for repo_dir in sorted(REPOS_DIR.iterdir()):
        if repo_dir.is_dir() and (repo_dir / ".git").exists():
            logger.info(f"Generating code map for {repo_dir.name}...")
            maps[repo_dir.name] = generate_code_map(repo_dir)

    # Save to disk
    map_file = REPOS_DIR / ".code_maps.json"
    with open(map_file, "w", encoding="utf-8") as f:
        json.dump(maps, f, indent=2, ensure_ascii=False)

    return maps


def search_code(query: str, repo_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Full-text search across all synced repos"""
    results = []
    query_lower = query.lower()

    for repo_dir in sorted(REPOS_DIR.iterdir()):
        if not repo_dir.is_dir() or not (repo_dir / ".git").exists():
            continue
        if repo_name and repo_name.lower() not in repo_dir.name.lower():
            continue

        for file_path in repo_dir.rglob("*"):
            if not file_path.is_file() or not _should_include(file_path):
                continue
            if file_path.stat().st_size > MAX_FILE_SIZE:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if query_lower in content.lower():
                    # Find matching lines
                    matches = []
                    for i, line in enumerate(content.split("\n"), 1):
                        if query_lower in line.lower():
                            matches.append({"line": i, "text": line.strip()[:200]})
                            if len(matches) >= 5:
                                break

                    results.append({
                        "repo": repo_dir.name,
                        "file": str(file_path.relative_to(repo_dir)),
                        "matches": matches
                    })

                    if len(results) >= 20:
                        return results
            except:
                continue

    return results
