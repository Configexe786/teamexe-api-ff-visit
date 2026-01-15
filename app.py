# Updated by Gemini - Set target_success to 10 for testing
from flask import Flask, jsonify
import aiohttp
import asyncio
import json
from byte import encrypt_api, Encrypt_ID
from visit_count_pb2 import Info

app = Flask(__name__)

def load_tokens(server_name):
    try:
        if server_name == "IND":
            path = "token_ind.json"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            path = "token_br.json"
        else:
            path = "token_bd.json"

        with open(path, "r") as f:
            data = json.load(f)

        tokens = [item["token"] for item in data if "token" in item and item["token"] not in ["", "N/A"]]
        return tokens
    except Exception as e:
        app.logger.error(f"❌ Token load error for {server_name}: {e}")
        return []

def get_url(server_name):
    if server_name == "IND":
        return "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        return "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    else:
        return "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"

def parse_protobuf_response(response_data):
    try:
        info = Info()
        info.ParseFromString(response_data)
        
        player_data = {
            "uid": info.AccountInfo.UID if info.AccountInfo.UID else 0,
            "nickname": info.AccountInfo.PlayerNickname if info.AccountInfo.PlayerNickname else "",
            "likes": info.AccountInfo.Likes if info.AccountInfo.Likes else 0,
            "region": info.AccountInfo.PlayerRegion if info.AccountInfo.PlayerRegion else "",
            "level": info.AccountInfo.Levels if info.AccountInfo.Levels else 0
        }
        return player_data
    except Exception as e:
        return None

async def visit(session, url, token, uid, data):
    headers = {
        "ReleaseVersion": "OB52",
        "X-GA": "v1 1",
        "Authorization": f"Bearer {token}",
        "Host": url.replace("https://", "").split("/")[0]
    }
    try:
        async with session.post(url, headers=headers, data=data, ssl=False) as resp:
            if resp.status == 200:
                response_data = await resp.read()
                return True, response_data
            else:
                return False, None
    except Exception as e:
        return False, None

async def send_until_target_success(tokens, uid, server_name, target_success=10):
    url = get_url(server_name)
    connector = aiohttp.TCPConnector(limit=0)
    total_success = 0
    total_sent = 0
    player_info = None

    async with aiohttp.ClientSession(connector=connector) as session:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)

        while total_success < target_success:
            batch_size = min(target_success - total_success, len(tokens))
            tasks = [
                asyncio.create_task(visit(session, url, tokens[i % len(tokens)], uid, data))
                for i in range(batch_size)
            ]
            results = await asyncio.gather(*tasks)
            
            for success, response in results:
                if success and response is not None and player_info is None:
                    player_info = parse_protobuf_response(response)
                if success:
                    total_success += 1
            
            total_sent += batch_size
            if total_sent >= len(tokens) * 2: # Stop if we looped through tokens twice without success
                break

    return total_success, total_sent, player_info

@app.route('/<string:server>/<int:uid>', methods=['GET'])
def send_visits(server, uid):
    server = server.upper()
    tokens = load_tokens(server)
    # Testing ke liye limit 10 kar di hai
    target_success = 10 

    if not tokens:
        return jsonify({"error": "❌ No valid tokens found"}), 500

    total_success, total_sent, player_info = asyncio.run(send_until_target_success(
        tokens, uid, server,
        target_success=target_success
    ))

    if player_info:
        return jsonify({
            "status": "success",
            "uid": player_info.get("uid"),
            "nickname": player_info.get("nickname"),
            "region": player_info.get("region"),
            "level": player_info.get("level"),
            "likes": player_info.get("likes"),
            "visits_sent": total_success,
            "target": target_success
        }), 200
    else:
        return jsonify({"error": "Could not decode player info or visits failed"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
        
