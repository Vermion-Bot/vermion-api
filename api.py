from sanic import Sanic
from sanic.response import json, file
from sanic_cors import CORS
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.database.database import DatabaseManager

app = Sanic("discord_config_api")
CORS(app)

db = DatabaseManager(
    dbname='vermion',
    user='postgres',
    password='',
    host='localhost',
    port='5432'
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")

@app.get("/")
async def index(request):
    return await file(os.path.join(DASHBOARD_DIR, "index.html"))

@app.get("/script.js")
async def serve_js(request):
    return await file(os.path.join(DASHBOARD_DIR, "script.js"))

@app.get("/styles.css")
async def serve_css(request):
    return await file(os.path.join(DASHBOARD_DIR, "styles.css"))

@app.post("/api/config")
async def save_config(request):
    try:
        data = request.json
        guild_id = int(data.get('guild_id'))
        test_message = data.get('test_message')
        
        if not guild_id or not test_message:
            return json({'success': False, 'error': 'Hiányzó adatok'}, status=400)
        
        db.insert_or_update_message(guild_id, test_message)
        return json({'success': True, 'message': 'Sikeresen mentve'})
    except Exception as e:
        return json({'success': False, 'error': str(e)}, status=500)

@app.get("/api/config/<guild_id:int>")
async def get_config(request, guild_id):
    try:
        test_message = db.get_test_message(guild_id)
        
        if test_message:
            return json({'guild_id': guild_id, 'test_message': test_message})
        else:
            return json({'guild_id': guild_id, 'test_message': None}, status=404)
    except Exception as e:
        return json({'error': str(e)}, status=500)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)