from sanic import Sanic
from sanic.response import json, file
from bot.database.database import DatabaseManager

app = Sanic("discord_config_api")

db = DatabaseManager(
    dbname='vermion',
    user='postgres',
    password='',
    host='localhost',
    port='5432'
)

@app.before_server_start
async def setup(app, loop):
    print("🚀 API Server elindult!")

@app.get("/")
async def index(request):
    return await file("vermion-dashboard/index.html")

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