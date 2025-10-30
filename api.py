from sanic import Sanic, response
from sanic_cors import CORS
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from common.database import DatabaseManager

app = Sanic("discord_config_api")
CORS(app)

db = DatabaseManager(
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT')
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")

app.static("/static", os.path.join(DASHBOARD_DIR), name="dashboard_static")

@app.get("/")
async def index(request):
    return await response.file(os.path.join(DASHBOARD_DIR, "index.html"))

@app.get("/config")
async def config_page(request):
    guild_id = request.args.get('guild_id')
    token = request.args.get('token')
    
    if not guild_id or not token:
        return response.json({'success': False, 'error': 'Hiányzó guild_id vagy token'}, status=400)
    
    try:
        guild_id = int(guild_id)
    except ValueError:
        return response.json({'success': False, 'error': 'Érvénytelen guild_id'}, status=400)
    
    return await response.file(os.path.join(DASHBOARD_DIR, "index.html"))

@app.get("/api/config/<guild_id>")
async def get_config(request, guild_id):
    try:
        guild_id = int(guild_id)
    except ValueError:
        return response.json({'success': False, 'error': 'Érvénytelen guild_id'}, status=400)
    
    try:
        test_message = db.get_test_message(guild_id)
        if test_message:
            return response.json({'success': True, 'test_message': test_message})
        else:
            return response.json({'success': False, 'error': 'Nincs adat erre a szerverhez'}, status=404)
    except Exception as e:
        print(f"❌ Hiba a config lekérésé során: {e}")
        return response.json({'success': False, 'error': str(e)}, status=500)

@app.post("/api/config")
async def save_config(request):
    try:
        data = request.json
        guild_id_str = data.get('guild_id')
        
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return response.json({'success': False, 'error': 'Érvénytelen guild_id'}, status=400)
        
        token = data.get('token')
        test_message = data.get('test_message')
        
        if not guild_id or not token or not test_message:
            return response.json({'success': False, 'error': 'Hiányzó adatok'}, status=400)
        
        if not db.validate_and_use_token(token, guild_id):
            return response.json({'success': False, 'error': 'Érvénytelen, lejárt vagy már használt token'}, status=403)
        
        db.insert_or_update_message(guild_id, test_message)
        return response.json({'success': True, 'message': 'Sikeresen mentve'})
    except Exception as e:
        return response.json({'success': False, 'error': str(e)}, status=500)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)