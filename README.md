# Mishloha MCP Server

שרת Remote MCP המחבר את Claude Teams לכלי הפיתוח של משלוחה: GitLab, Jira ו-Figma.

## מבנה הפרויקט

```
mishloha-mcp-server/
├── app/
│   ├── server.py          # שרת MCP ראשי
│   ├── auth.py            # אימות Bearer token
│   └── tools/
│       ├── gitlab_tools.py    # כלי GitLab
│       ├── jira_tools.py      # כלי Jira
│       └── figma_tools.py     # כלי Figma
├── requirements.txt
├── Dockerfile
├── railway.toml
└── README.md
```

## כלים זמינים

### GitLab (קריאה בלבד)
- `gitlab_search_code` — חיפוש קוד במאגרים
- `gitlab_get_file` — קריאת קובץ ספציפי
- `gitlab_list_projects` — רשימת פרויקטים
- `gitlab_get_file_tree` — עיון במבנה תיקיות

### Jira  
- `jira_search_issues` — חיפוש issues עם JQL
- `jira_get_issue` — פרטי issue ספציפי
- `jira_list_sprints` — רשימת ספרינטים
- `jira_get_sprint_issues` — issues בספרינט
- `jira_get_board` — סקירת לוח

### Figma
- `figma_get_file` — מבנה קובץ Figma  
- `figma_get_comments` — הערות על קובץ
- `figma_search_components` — חיפוש רכיבים
- `figma_get_frame_image` — יצוא תמונה
- `figma_get_file_nodes` — פרטי צמתים

## התקנה מקומית

1. **שכפול הפרויקט:**
   ```bash
   git clone https://github.com/tal-shilian-m/mishloha-mcp-server.git
   cd mishloha-mcp-server
   ```

2. **התקנת תלויות:**
   ```bash
   pip install -r requirements.txt
   ```

3. **הגדרת משתני סביבה:**
   ```bash
   cp .env.example .env
   # ערוך את .env עם הטוקנים שלך
   ```

4. **הרצה:**
   ```bash
   python -m app.server
   ```

## פריסה ב-Railway

1. **חיבור למאגר:**
   - התחבר ל-Railway
   - צור פרויקט חדש מ-GitHub
   - בחר את המאגר `mishloha-mcp-server`

2. **הגדרת משתני סביבה ב-Railway:**
   ```bash
   # GitLab
   GITLAB_URL=https://gitlab.com
   GITLAB_TOKEN=glpat-your-token
   
   # Jira  
   JIRA_URL=https://mishloha.atlassian.net
   JIRA_EMAIL=tal@mishloha.co.il
   JIRA_API_TOKEN=your-jira-token
   
   # Figma
   FIGMA_TOKEN=your-figma-token
   
   # אימות
   MCP_AUTH_TOKEN=your-secure-random-token
   ```

3. **פריסה:** Railway יפרוס אוטומטית מהמאגר

## חיבור ל-Claude Teams

1. **קבל את ה-URL של השרת:** `https://your-app.railway.app`

2. **הוסף Remote MCP Server ב-Claude Teams:**
   - לך להגדרות Claude Teams
   - הוסף MCP Server חדש
   - סוג: Remote Server
   - URL: `https://your-app.railway.app`
   - Authentication: Bearer Token
   - Token: הערך של `MCP_AUTH_TOKEN`

3. **בדוק חיבור:** `GET https://your-app.railway.app/health`

## קבלת טוקנים

### GitLab Personal Access Token
1. לך ל-GitLab → Settings → Access Tokens
2. צור טוקן עם הרשאות: `read_repository`, `read_api`
3. העתק את הטוקן ל-`GITLAB_TOKEN`

### Jira API Token  
1. לך ל-Atlassian Account → Security → API tokens
2. צור טוקן חדש
3. העתק ל-`JIRA_API_TOKEN`

### Figma Personal Access Token
1. לך ל-Figma → Settings → Personal Access Tokens
2. צור טוקן חדש
3. העתק ל-`FIGMA_TOKEN`

## אבטחה

- השרת דורש Bearer Token לכל הבקשות
- יצור טוקן חזק ואקראי ל-`MCP_AUTH_TOKEN`
- כל הטוקנים נשמרים כמשתני סביבה ב-Railway
- השרת לא שומר נתונים - כל הבקשות עוברות דרך APIs

## פתרון בעיות

### בעיות חיבור
- וודא שכל משתני הסביבה מוגדרים
- בדוק שהטוקנים תקפים ולא פגו
- וודא שה-Bearer Token נכון ב-Claude Teams

### שגיאות API
- בדוק לוגים ב-Railway Dashboard
- וודא שהרשאות הטוקנים מספיקות
- שים לב למגבלות קצב של APIs

### בדיקת בריאות
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" https://your-app.railway.app/health
```

## פיתוח

לפיתוח מקומי:
```bash
# התקנה במצב פיתוח
pip install -e .

# הרצה עם debug
python -m app.server --debug

# בדיקות
python -m pytest tests/
```

## תרומה

1. Fork הפרויקט
2. צור feature branch  
3. Commit השינויים
4. פתח Pull Request

## רישיון

MIT License - ראה קובץ LICENSE למידע נוסף.