from sanic import Sanic, response
from sanic_cors import CORS
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import aiohttp
from urllib.parse import urlencode

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from common.database import DatabaseManager

app = Sanic("discord_config_api")
CORS(app, supports_credentials=True)

db = DatabaseManager(
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT')
)

DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI')
DISCORD_API_ENDPOINT = 'https://discord.com/api/v10'

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")

app.static("/static", DASHBOARD_DIR)

def get_session_from_request(request):
    return request.cookies.get('session_id')

def get_user_from_session(session_id):
    if not session_id:
        return None
    return db.get_session(session_id)

@app.get("/")
async def index(request):
    return await response.file(os.path.join(DASHBOARD_DIR, "index.html"))

@app.get("/invite")
async def invite_bot(request):
    permissions = 8  
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions={permissions}&scope=bot%20applications.commands"
    return response.redirect(invite_url)

@app.get("/auth/login")
async def auth_login(request):
    params = {
        'client_id': DISCORD_CLIENT_ID,
        'redirect_uri': DISCORD_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'identify guilds'
    }
    
    discord_auth_url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return response.redirect(discord_auth_url)

@app.get("/auth/callback")
async def auth_callback(request):
    code = request.args.get('code')
    
    if not code:
        return response.html("<h1>❌ Hiba: Hiányzó authorization code</h1>", status=400)
    
    async with aiohttp.ClientSession() as session:
        data = {
            'client_id': DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': DISCORD_REDIRECT_URI
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        async with session.post(f'{DISCORD_API_ENDPOINT}/oauth2/token', data=data, headers=headers) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                print(f"❌ Token exchange hiba: {error_text}")
                return response.html(f"<h1>❌ Authentication hiba</h1><p>{error_text}</p>", status=400)
            
            token_data = await resp.json()
        
        auth_header = {
            'Authorization': f"{token_data['token_type']} {token_data['access_token']}"
        }
        
        async with session.get(f'{DISCORD_API_ENDPOINT}/users/@me', headers=auth_header) as resp:
            if resp.status != 200:
                return response.html("<h1>❌ Nem sikerült lekérni a user adatokat</h1>", status=400)
            user_data = await resp.json()
        
        async with session.get(f'{DISCORD_API_ENDPOINT}/users/@me/guilds', headers=auth_header) as resp:
            if resp.status != 200:
                guilds_data = []
            else:
                guilds_data = await resp.json()
        
        session_id = db.create_session(user_data, token_data)
        
        if not session_id:
            return response.html("<h1>❌ Nem sikerült létrehozni a session-t</h1>", status=500)
        
        db.sync_user_guilds(int(user_data['id']), guilds_data)
        
        resp = response.redirect('/dashboard')
        resp.add_cookie(
            'session_id',
            session_id,
            httponly=True,
            samesite='Lax',
            max_age=604800
        )
        
        return resp

@app.get("/auth/logout")
async def auth_logout(request):
    session_id = get_session_from_request(request)
    
    if session_id:
        db.delete_session(session_id)
    
    resp = response.redirect('/')
    resp.add_cookie('session_id', '', max_age=0)
    
    return resp

@app.get("/dashboard")
async def dashboard(request):
    return await response.file(os.path.join(DASHBOARD_DIR, "dashboard.html"))

@app.get("/api/me")
async def get_current_user(request):
    session_id = get_session_from_request(request)
    user = get_user_from_session(session_id)
    
    if not user:
        return response.json({'success': False, 'error': 'Nem vagy bejelentkezve'}, status=401)
    
    return response.json({
        'success': True,
        'user': {
            'id': str(user['user_id']),
            'username': user['username'],
            'discriminator': user['discriminator'],
            'avatar': user['avatar']
        }
    })

@app.get("/api/guilds")
async def get_guilds(request):
    session_id = get_session_from_request(request)
    user = get_user_from_session(session_id)
    
    if not user:
        return response.json({'success': False, 'error': 'Nem vagy bejelentkezve'}, status=401)
    
    guilds = db.get_user_guilds(user['user_id'], manageable_only=True)
    
    guilds_with_bot_status = []
    for g in guilds:
        guild_data = {
            'id': str(g['guild_id']),
            'name': g['guild_name'],
            'icon': g['guild_icon'],
            'owner': g['owner'],
            'permissions': g['permissions'],
            'bot_in_guild': db.is_bot_in_guild(g['guild_id'])
        }
        guilds_with_bot_status.append(guild_data)
    
    return response.json({
        'success': True,
        'guilds': guilds_with_bot_status
    })

@app.get("/api/config/<guild_id>")
async def get_config(request, guild_id):
    session_id = get_session_from_request(request)
    user = get_user_from_session(session_id)
    
    if not user:
        return response.json({'success': False, 'error': 'Nem vagy bejelentkezve'}, status=401)
    
    try:
        guild_id = int(guild_id)
    except ValueError:
        return response.json({'success': False, 'error': 'Érvénytelen guild_id'}, status=400)
    
    if not db.check_user_guild_permission(user['user_id'], guild_id):
        return response.json({'success': False, 'error': 'Nincs jogosultságod ehhez a szerverhez'}, status=403)
    
    try:
        test_message = db.get_test_message(guild_id)
        if test_message:
            return response.json({'success': True, 'test_message': test_message})
        else:
            return response.json({'success': True, 'test_message': ''})
    except Exception as e:
        print(f"❌ Hiba a config lekérése során: {e}")
        return response.json({'success': False, 'error': str(e)}, status=500)

@app.post("/api/config/<guild_id>")
async def save_config(request, guild_id):
    session_id = get_session_from_request(request)
    user = get_user_from_session(session_id)
    
    if not user:
        return response.json({'success': False, 'error': 'Nem vagy bejelentkezve'}, status=401)
    
    try:
        guild_id = int(guild_id)
    except ValueError:
        return response.json({'success': False, 'error': 'Érvénytelen guild_id'}, status=400)
    
    if not db.check_user_guild_permission(user['user_id'], guild_id):
        return response.json({'success': False, 'error': 'Nincs jogosultságod ehhez a szerverhez'}, status=403)
    
    try:
        data = request.json
        test_message = data.get('test_message')
        
        if not test_message:
            return response.json({'success': False, 'error': 'Hiányzó test_message'}, status=400)
        
        success = db.insert_or_update_message(guild_id, test_message)
        
        if success:
            db.log_action(
                user['user_id'],
                guild_id,
                'config_update',
                f"Test message frissítve",
                request.ip
            )
            
            return response.json({'success': True, 'message': 'Sikeresen mentve'})
        else:
            return response.json({'success': False, 'error': 'Nem sikerült menteni'}, status=500)
            
    except Exception as e:
        print(f"❌ Hiba a mentés során: {e}")
        return response.json({'success': False, 'error': str(e)}, status=500)

if __name__ == "__main__":
    print(f"""
    ╔══════════════════════════════════════════════╗
    ║  Discord OAuth2 Dashboard                   ║
    ╠══════════════════════════════════════════════╣
    ║  Client ID: {DISCORD_CLIENT_ID[:20]}...          ║
    ║  Redirect URI: {DISCORD_REDIRECT_URI[:30]}... ║
    ║  Bot Invite: http://localhost:8000/invite    ║
    ╚══════════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=8000)