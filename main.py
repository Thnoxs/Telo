import sys
import asyncio
import os
import uvicorn
from telethon import TelegramClient
from telethon.sessions import StringSession
from fastapi import FastAPI, Response, Request
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
import re
from contextlib import asynccontextmanager

# --- LOGGING ---
def log(msg):
    print(f"[TeloView] {msg}")

# --- ENVIRONMENT VARIABLES (Render Friendly) ---
# Local testing ke liye hardcode kar sakte ho, par Render par Env Vars use karna.
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

client = None

# --- GLOBAL CACHE ---
# Entity aur structure ko cache karenge taki bar-bar fetch na karna pade
entity_cache = {} 
structure_cache = {}

# --- CHANNEL RESOLVER ---
async def resolve_channel(user_input):
    user_input = user_input.strip()
    # Handle full URLs
    if "t.me/c/" in user_input:
        parts = user_input.split("t.me/c/")
        if len(parts) > 1: 
            try:
                chat_id = parts[1].split('/')[0]
                return int(f"-100{chat_id}")
            except: pass
    if "t.me/" in user_input:
        return user_input.replace("https://t.me/", "").replace("t.me/", "").split("/")[0]
    
    # Handle numeric IDs
    if re.match(r'^-?\d+$', user_input):
        return int(user_input)
        
    return user_input

# --- TITLE CLEANER ---
def clean_title(name):
    if not name: return "Untitled Lesson"
    name = re.sub(r'\.(mp4|mkv|mov|avi|webm)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'@\w+\s*[-_|]?\s*', '', name)
    name = re.sub(r'^(Copy of|Forwarded)\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^[-_|\s]+', '', name)
    return name.strip()

# --- LIFESPAN (Connection Logic) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    log("🚀 Server Starting...")
    
    # Check credentials
    if not API_ID or not API_HASH or not SESSION_STRING:
        log("❌ ERROR: API_ID, API_HASH, or SESSION_STRING missing in Environment Variables.")
    
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    log("✅ Telegram Client Connected!")
    
    yield
    if client: await client.disconnect()

app = FastAPI(lifespan=lifespan)

# --- SERVE STATIC FILES ---
@app.get("/icon.png")
async def serve_icon_file():
    if os.path.exists("icon.png"): return FileResponse("icon.png")
    return Response(status_code=404)

@app.get("/logo.png")
async def serve_logo_file():
    if os.path.exists("logo.png"): return FileResponse("logo.png")
    return Response(status_code=404)

# --- HOMEPAGE (New Logic) ---
@app.get("/", response_class=HTMLResponse)
async def homepage():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TeloView - Home</title>
        <link rel="icon" type="image/png" href="/icon.png">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
        <style>
            body { background: #0a0a0a; color: #fff; font-family: 'Inter', sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .container { width: 90%; max-width: 500px; text-align: center; }
            h1 { font-weight: 800; letter-spacing: -1px; margin-bottom: 2rem; }
            .input-group { display: flex; gap: 10px; margin-bottom: 2rem; }
            input { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #333; background: #111; color: #fff; outline: none; transition: 0.2s; }
            input:focus { border-color: #3b82f6; }
            button { padding: 12px 24px; background: #3b82f6; border: none; border-radius: 8px; color: #fff; font-weight: 600; cursor: pointer; }
            button:hover { background: #2563eb; }
            .history { text-align: left; margin-top: 2rem; border-top: 1px solid #222; padding-top: 1rem; }
            .history h3 { font-size: 0.9rem; color: #666; text-transform: uppercase; letter-spacing: 1px; }
            .history-item { display: flex; align-items: center; justify-content: space-between; padding: 10px; background: #111; margin-bottom: 8px; border-radius: 6px; cursor: pointer; transition: 0.2s; }
            .history-item:hover { background: #1a1a1a; }
            .history-name { font-size: 0.9rem; font-weight: 500; }
            .history-id { font-size: 0.75rem; color: #555; }
            .loader { border: 3px solid #111; border-top: 3px solid #3b82f6; border-radius: 50%; width: 20px; height: 20px; animation: spin 1s linear infinite; display: none; margin: 0 auto; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>TELO VIEW</h1>
            <div class="input-group">
                <input type="text" id="channelInput" placeholder="Enter Telegram Link or Channel ID...">
                <button onclick="loadCourse()">GO</button>
            </div>
            <div class="loader" id="loader"></div>
            
            <div class="history">
                <h3>Recent Courses</h3>
                <div id="historyList"></div>
            </div>
        </div>
        <script>
            // --- HISTORY LOGIC ---
            function renderHistory() {
                const list = document.getElementById('historyList');
                const history = JSON.parse(localStorage.getItem('teloHistory') || '[]');
                list.innerHTML = '';
                if(history.length === 0) list.innerHTML = '<div style="color:#444; font-size:0.8rem;">No recent courses</div>';
                
                history.forEach(item => {
                    const el = document.createElement('div');
                    el.className = 'history-item';
                    el.innerHTML = `<div><div class="history-name">${item.title}</div><div class="history-id">${item.id}</div></div><span>→</span>`;
                    el.onclick = () => window.location.href = `/course/${item.id}`;
                    list.appendChild(el);
                });
            }

            async function loadCourse() {
                const input = document.getElementById('channelInput').value.trim();
                if(!input) return;
                
                // Extract simple logic to handle full URL pasting
                let channelId = input;
                if(input.includes("t.me/")) {
                    const parts = input.split('/');
                    channelId = parts[parts.length - 1]; 
                }
                
                document.getElementById('loader').style.display = 'block';
                // Redirect - The backend will handle resolution
                window.location.href = `/course/${encodeURIComponent(channelId)}`;
            }

            renderHistory();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

# --- COURSE PLAYER LOGIC (Dynamic) ---
@app.get("/course/{channel_identifier}", response_class=HTMLResponse)
async def course_player(channel_identifier: str, request: Request):
    try:
        # Resolve Identifier
        real_id = await resolve_channel(channel_identifier)
        str_id = str(real_id)
        
        # Cache Check (Optional: Clear cache if needed)
        # currently fetching fresh to ensure updates, can be optimized later
        try:
            entity = await client.get_entity(real_id)
            entity_cache[str_id] = entity
        except ValueError:
            return HTMLResponse(f"<h1>Channel Not Found</h1><p>Ensure the bot account has joined: {channel_identifier}</p>", status_code=404)

        channel_title = getattr(entity, 'title', 'Unknown Course')
        
        # Build Structure
        current_module = "🗂️ Course Content"
        structure = {current_module: []}
        
        # Fetch Messages (Limit 500)
        all_msgs = []
        async for msg in client.iter_messages(entity, limit=500):
            all_msgs.append(msg)
        all_msgs.reverse()

        for msg in all_msgs:
            if msg.message and not msg.media and msg.message.strip():
                text = msg.message.strip()
                if "MODULE:" in text.upper() or len(text) < 50:
                    clean_name = text.replace("MODULE:", "").replace("Module:", "").strip()
                    clean_name = re.sub(r'^[-_|\s]+', '', clean_name)
                    current_module = clean_name
                    if current_module not in structure: 
                        structure[current_module] = []
            
            elif msg.media and hasattr(msg, 'file'):
                raw_name = getattr(msg.file, 'name', None)
                if not raw_name: raw_name = f"Lesson {msg.id}"
                
                if raw_name.lower().endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm')) or (msg.file and msg.file.mime_type.startswith('video/')):
                     final_title = clean_title(raw_name)
                     structure[current_module].append({ "id": msg.id, "title": final_title })

        structure = {k: v for k, v in structure.items() if v}
        structure_cache[str_id] = structure # Save for later if needed
        
        # Generate Sidebar HTML (UI Preserved)
        sidebar_html = ""
        icon_circle = '<svg viewBox="0 0 24 24" class="icon icon-status"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path></svg>'
        
        for i, (module_name, videos) in enumerate(structure.items()):
            is_first = (i == 0)
            display_style = "block" if is_first else "none"
            header_class = "section-header" if is_first else "section-header collapsed"
            
            sidebar_html += f'''
            <div class="section-container" data-module-index="{i}">
                <div class="{header_class}" onclick="toggleSection(this)">
                    <div class="header-left"><span class="section-title">{module_name}</span></div>
                    <span class="arrow">▼</span>
                </div>
                <div class="section-videos" style="display: {display_style};">
            '''
            for vid in videos:
                sidebar_html += f'''
                <div class="lesson-item" id="lesson-{vid['id']}" data-id="{vid['id']}" onclick="loadVideo({vid['id']}, '{vid['title']}', this)">
                    <div class="status-icon-wrapper" onclick="toggleCompletion(event, {vid['id']})">
                        {icon_circle}
                    </div>
                    <div class="lesson-content">
                        <span class="lesson-title">{vid['title']}</span>
                    </div>
                    <div class="progress-track"><div class="progress-fill" id="progress-{vid['id']}"></div></div>
                </div>'''
            sidebar_html += "</div></div>"

        # Injecting History Saving Logic via JS
        history_script = f"""
            const currentCourse = {{ id: '{channel_identifier}', title: '{channel_title}' }};
            const history = JSON.parse(localStorage.getItem('teloHistory') || '[]');
            // Remove if exists
            const filtered = history.filter(h => h.id !== currentCourse.id);
            // Add to top
            filtered.unshift(currentCourse);
            localStorage.setItem('teloHistory', JSON.stringify(filtered));
        """

        # HTML Return (Embedding Stream URL with Channel ID)
        return generate_player_html(channel_title, sidebar_html, len(structure), str_id, history_script)

    except Exception as e:
        log(f"Error loading course: {e}")
        return HTMLResponse(f"<h1>Error</h1><p>{e}</p>", status_code=500)

def generate_player_html(page_title, sidebar_html, module_count, channel_id, history_script):
    return f""" <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{page_title}</title>
        <link rel="icon" type="image/png" href="/icon.png">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
        <link href="https://vjs.zencdn.net/7.20.3/video-js.css" rel="stylesheet" />
        <link href="https://unpkg.com/@videojs/themes@1.0.1/dist/city/index.css" rel="stylesheet">
        <style>
            :root {{ 
                --bg-main: #0a0a0a; --bg-sidebar: #111111; --bg-header: #111111; 
                --bg-hover: #1e1e1e; --bg-active: #1f1f1f; --text-primary: #ededed; 
                --text-secondary: #a0a0a0; --accent: #3b82f6; --border: 1px solid #262626; 
                --font-stack: 'Inter', sans-serif; 
            }}
            * {{ box-sizing: border-box; outline: none; -webkit-tap-highlight-color: transparent; }}
            ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
            ::-webkit-scrollbar-track {{ background: transparent; }}
            ::-webkit-scrollbar-thumb {{ background: #333; border-radius: 3px; }}
            body {{ margin: 0; background: var(--bg-main); font-family: var(--font-stack); color: var(--text-primary); display: flex; flex-direction: column; height: 100vh; overflow: hidden; font-size: 14px; }}
            
            /* Navbar */
            .navbar {{ height: 60px; background: var(--bg-header); border-bottom: var(--border); display: flex; align-items: center; justify-content: space-between; padding: 0 24px; z-index: 50; flex-shrink: 0; }}
            .brand {{ display: flex; align-items: center; gap: 12px; text-decoration: none; cursor: pointer; }}
            .brand img {{ width: 28px; height: 28px; filter: invert(1); }}
            .brand-text {{ font-weight: 800; font-size: 1.2rem; letter-spacing: 1px; color: #fff; }}
            .brand-course {{ font-weight: 400; color: #666; margin-left: 10px; font-size: 0.9rem; border-left: 1px solid #333; padding-left: 10px; }}
            
            /* Layout */
            .app-container {{ display: flex; flex: 1; overflow: hidden; }}
            #sidebar {{ width: 350px; background: var(--bg-sidebar); display: flex; flex-direction: column; border-right: var(--border); z-index: 40; min-width: 250px; max-width: 500px; user-select: none; }}
            #curriculum {{ flex: 1; overflow-y: auto; overflow-x: hidden; position: relative; }}
            .footer {{ font-size: 11px; color: #555; text-align: center; padding: 12px; border-top: var(--border); background: var(--bg-sidebar); }}
            
            /* Sections */
            .section-header {{ padding: 16px 20px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; background: var(--bg-sidebar); border-bottom: 1px solid #1a1a1a; }}
            .section-header:hover {{ background: var(--bg-hover); }}
            .section-title {{ font-weight: 600; font-size: 0.9rem; color: #e0e0e0; }}
            .arrow {{ font-size: 10px; color: #666; transition: transform 0.3s; }}
            .section-header.collapsed .arrow {{ transform: rotate(-90deg); }}
            
            /* Lesson Items */
            .lesson-item {{ padding: 14px 20px; cursor: pointer; display: flex; gap: 14px; align-items: flex-start; position: relative; background: #0f0f0f; transition: all 0.2s; border-bottom: 1px solid #161616; }}
            .lesson-item:hover {{ background: var(--bg-hover); }}
            .lesson-item.active {{ background: var(--bg-active); }}
            .lesson-item.active .lesson-title {{ color: var(--accent); font-weight: 500; }}
            .lesson-title {{ font-size: 0.9rem; color: var(--text-secondary); line-height: 1.4; flex: 1; }}
            .status-icon-wrapper {{ width: 20px; min-width: 20px; margin-top: 2px; display: flex; justify-content: center; align-items: center; cursor: pointer; z-index: 10; }}
            .icon-status {{ width: 16px; height: 16px; color: #444; }}
            .progress-track {{ position: absolute; bottom: 0; left: 0; width: 100%; height: 2px; background: transparent; pointer-events: none; }}
            .progress-fill {{ height: 100%; background: var(--accent); width: 0%; transition: width 0.3s linear; box-shadow: 0 0 10px var(--accent); }}
            
            /* Video Area */
            .video-js.vjs-user-inactive .vjs-control-bar {{ opacity: 1 !important; visibility: visible !important; display: flex !important; }}
            body.cinema .video-js.vjs-user-inactive .vjs-control-bar {{ opacity: 0 !important; visibility: hidden !important; }}
            
            .wave-container {{ display: flex; align-items: flex-end; justify-content: center; gap: 2px; height: 14px; width: 16px; }}
            .wave-bar {{ width: 3px; background: var(--accent); animation: wave-bounce 1s infinite ease-in-out; border-radius: 1px; }}
            .wave-bar:nth-child(1) {{ animation-delay: 0.0s; height: 40%; }}
            .wave-bar:nth-child(2) {{ animation-delay: 0.2s; height: 80%; }}
            .wave-bar:nth-child(3) {{ animation-delay: 0.4s; height: 50%; }}
            @keyframes wave-bounce {{ 0%, 100% {{ height: 30%; }} 50% {{ height: 100%; }} }}

            #main {{ flex: 1; display: flex; flex-direction: column; background: #000; position: relative; }}
            #video-header {{ height: 45px; display: flex; align-items: center; justify-content: center; background: #000; color: #fff; font-size: 0.95rem; font-weight: 500; border-top: 1px solid #111; letter-spacing: 0.5px; text-align: center; padding: 0 20px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
            .player-wrapper {{ flex: 1; width: 100%; display: flex; justify-content: center; align-items: center; background: #000; }}
            .control-bar {{ height: 60px; display: none; align-items: center; justify-content: center; gap: 16px; flex-shrink: 0; }}
            .nav-btn {{ background: #1f1f1f; border: 1px solid #333; color: #ccc; padding: 8px 20px; border-radius: 6px; cursor: pointer; transition: 0.2s; font-weight: 500; }}
            .nav-btn:hover {{ background: #333; color: white; border-color: #555; }}
            
            #resizer {{ width: 4px; background: #111; cursor: col-resize; z-index: 55; border-left: 1px solid #222; }}
            #resizer:hover {{ background: var(--accent); }}
            
            body.cinema .navbar, body.cinema #sidebar, body.cinema #resizer, body.cinema #video-header {{ display: none; }}
            body.cinema #main {{ position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 100; }}
            body.cinema .control-bar {{ position: absolute; bottom: 0; width: 100%; background: linear-gradient(to top, rgba(0,0,0,0.9), transparent); border: none; opacity: 0; }}
            body.cinema #main:hover .control-bar {{ opacity: 1; }}
        </style>
    </head>
    <body>
       <nav class="navbar">
            <a href="/" class="brand">
                <img src="/logo.png" onerror="this.src='/icon.png'; this.onerror=null;">
                <span class="brand-text">TELO</span>
                <span class="brand-course">{page_title}</span>
            </a>
            <div style="font-size: 0.8rem; color: #666;">{module_count} Modules</div>
        </nav>

        <div class="app-container">
            <div id="sidebar">
                <div id="curriculum">{sidebar_html}</div>
                <div class="footer">Made with <span style="color:#e91e63;">&#10084;</span> by <b>Thnoxs</b></div>
            </div>
            <div id="resizer"></div>
            <div id="main">
                <div class="player-wrapper">
                    <video id="vid" class="video-js vjs-big-play-centered" controls preload="auto"></video>
                </div>
                <div class="control-bar">
                    <button class="nav-btn" onclick="playPrev()">Previous</button>
                    <button class="nav-btn" onclick="toggleCinema()">Theater Mode</button>
                    <button class="nav-btn" onclick="playNext()">Next</button>
                </div>
                 <div id="video-header">Select a video to start</div>
            </div>
        </div>
        
        <script src="https://vjs.zencdn.net/7.20.3/video.js"></script>
        <script>
            // --- INJECTED HISTORY LOGIC ---
            {history_script}

            const CHANNEL_ID = "{channel_id}";
            const ICON_CIRCLE = '<svg viewBox="0 0 24 24" class="icon icon-status"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path></svg>';
            const ICON_CHECK = '<svg viewBox="0 0 24 24" class="icon icon-status"><path fill="#3b82f6" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"></path></svg>';
            const WAVE_HTML = `<div class="wave-container"><div class="wave-bar"></div><div class="wave-bar"></div><div class="wave-bar"></div></div>`;

            var player = videojs('vid', {{ fluid: false, fill: true, playbackRates: [0.75, 1, 1.25, 1.5, 2] }});
            var currentId = null;

            player.on('timeupdate', () => {{
                if(!currentId) return;
                const percent = (player.currentTime() / player.duration()) * 100;
                const progressBar = document.getElementById('progress-' + currentId);
                if(progressBar) progressBar.style.width = percent + '%';
            }});

            // URL Param Handling logic
            window.onload = function() {{ 
                const urlParams = new URLSearchParams(window.location.search);
                const videoParam = urlParams.get('video');
                
                if(videoParam) {{
                    const target = document.getElementById('lesson-' + videoParam);
                    if(target) target.click();
                }} else {{
                    const first = document.querySelector('.lesson-item'); 
                    if(first) first.click(); 
                }}
            }};

            function loadVideo(id, title, element) {{
                if(currentId === id) {{ player.paused() ? player.play() : player.pause(); return; }}
                currentId = id; 

                // Update Browser URL without reload
                const newUrl = window.location.protocol + "//" + window.location.host + window.location.pathname + '?video=' + id;
                window.history.pushState({{path:newUrl}}, '', newUrl);

                // UI Resets
                document.querySelectorAll('.lesson-item').forEach(el => {{ 
                    el.classList.remove('active');
                    const prog = el.querySelector('.progress-fill');
                    const iconWrap = el.querySelector('.status-icon-wrapper');
                    if(prog.style.width !== '100%') iconWrap.innerHTML = ICON_CIRCLE;
                    else iconWrap.innerHTML = ICON_CHECK;
                }});
                
                element.classList.add('active'); 
                const iconWrap = element.querySelector('.status-icon-wrapper');
                if(element.querySelector('.progress-fill').style.width !== '100%') iconWrap.innerHTML = WAVE_HTML;

                document.getElementById('video-header').innerText = title;

                // Accordion
                const parentSection = element.closest('.section-videos');
                document.querySelectorAll('.section-videos').forEach(sec => {{
                    if (sec !== parentSection) {{ sec.style.display = 'none'; sec.previousElementSibling.classList.add('collapsed'); }}
                }});
                if (parentSection) {{ parentSection.style.display = 'block'; parentSection.previousElementSibling.classList.remove('collapsed'); }}

                // Updated Stream URL logic
                player.src({{ src: '/stream/' + CHANNEL_ID + '/' + id, type: 'video/mp4' }}); 
                player.play();
            }}

            function toggleCompletion(e, id) {{
                e.stopPropagation();
                const el = document.getElementById('lesson-' + id);
                const iconWrap = el.querySelector('.status-icon-wrapper');
                const progress = el.querySelector('.progress-fill');
                
                if (progress.style.width === '100%') {{
                    progress.style.width = '0%';
                    iconWrap.innerHTML = (currentId === id) ? WAVE_HTML : ICON_CIRCLE;
                }} else {{
                    progress.style.width = '100%';
                    iconWrap.innerHTML = ICON_CHECK;
                }}
            }}

            player.on('ended', () => {{
                const el = document.getElementById('lesson-' + currentId);
                if(el) {{
                    el.querySelector('.status-icon-wrapper').innerHTML = ICON_CHECK;
                    el.querySelector('.progress-fill').style.width = '100%';
                }}
                playNext();
            }});

            function toggleSection(header) {{ 
                const content = header.nextElementSibling; 
                const isCollapsed = content.style.display === 'none'; 
                content.style.display = isCollapsed ? 'block' : 'none'; 
                header.classList.toggle('collapsed', !isCollapsed); 
            }}
            function getAllIds() {{ return Array.from(document.querySelectorAll('.lesson-item')).map(el => parseInt(el.getAttribute('data-id'))); }}
            function playNext() {{ 
                const ids = getAllIds(); 
                const next = ids[ids.indexOf(currentId) + 1]; 
                if (next) document.getElementById('lesson-'+next).click(); 
            }}
            function playPrev() {{ 
                const ids = getAllIds(); 
                const prev = ids[ids.indexOf(currentId) - 1]; 
                if (prev) document.getElementById('lesson-'+prev).click(); 
            }}
            function toggleCinema() {{ document.body.classList.toggle('cinema'); player.trigger('resize'); }}
            
            const resizer = document.getElementById('resizer');
            resizer.addEventListener('mousedown', (e) => {{
                e.preventDefault();
                document.addEventListener('mousemove', resize);
                document.addEventListener('mouseup', () => document.removeEventListener('mousemove', resize));
            }});
            function resize(e) {{
                if(e.clientX > 250 && e.clientX < 600) document.getElementById('sidebar').style.width = e.clientX + 'px';
            }}
            
            document.addEventListener('keydown', (e) => {{
                if (e.code === 'Space') {{ e.preventDefault(); player.paused() ? player.play() : player.pause(); }}
                if (e.key === 'ArrowRight') {{ if(e.metaKey) playNext(); else player.currentTime(player.currentTime() + 5); }}
                if (e.key === 'ArrowLeft') {{ if(e.metaKey) playPrev(); else player.currentTime(player.currentTime() - 5); }}
                if (e.key === 'f') toggleCinema();
            }});
        </script>
    </body>
    </html>
    """

# --- STREAMING ENGINE (Dynamic) ---
@app.get("/stream/{channel_id}/{msg_id}")
async def stream_video(channel_id: str, msg_id: int, request: Request):
    try:
        # Resolve/Get Entity from Cache if possible, else fetch
        real_id = await resolve_channel(channel_id)
        
        # Check cache logic
        entity = entity_cache.get(str(real_id))
        if not entity:
             entity = await client.get_entity(real_id)
             entity_cache[str(real_id)] = entity

        msg = await client.get_messages(entity, ids=msg_id)
        if not msg or not msg.media: return Response("Not Found", status_code=404)
        
        file_size = msg.file.size
        range_header = request.headers.get("Range")
        
        async def iter_file(msg_media, start_byte, total_to_send):
            bytes_sent = 0
            async for chunk in client.iter_download(msg_media, offset=start_byte, request_size=1024*1024):
                if bytes_sent >= total_to_send: break
                left_to_send = total_to_send - bytes_sent
                chunk = chunk[:left_to_send] if len(chunk) > left_to_send else chunk
                yield chunk
                bytes_sent += len(chunk)

        if range_header:
            byte_match = re.search(r"bytes=(\d+)-(\d*)", range_header)
            start = int(byte_match.group(1))
            end = int(byte_match.group(2)) if byte_match.group(2) else file_size - 1
            content_length = end - start + 1
            return StreamingResponse(iter_file(msg.media, start, content_length), status_code=206, headers={"Content-Range": f"bytes {start}-{end}/{file_size}", "Accept-Ranges": "bytes", "Content-Length": str(content_length), "Content-Type": "video/mp4"})
        return StreamingResponse(iter_file(msg.media, 0, file_size), media_type="video/mp4")
    except Exception as e:
        log(f"Stream Error: {e}")
        return Response("Error", status_code=500)

# --- CLI LOGIN HANDLER ---
async def do_login(api_id, api_hash, phone):
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print(f"Sending OTP to {phone}...")
        await client.send_code_request(phone)
        otp = input("Enter Telegram OTP here > ")
        await client.sign_in(phone, otp)
    print("\n✅ LOGIN SUCCESS! Copy the string below for Render ENV 'SESSION_STRING':")
    print(client.session.save())
    print("\n")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        asyncio.run(do_login(sys.argv[2], sys.argv[3], sys.argv[4]))
    else:
        # Local Development Start
        if os.path.exists("session.txt"): # legacy check
             with open("session.txt", "r") as f: os.environ["SESSION_STRING"] = f.read().strip()
        uvicorn.run(app, host="127.0.0.1", port=8000)