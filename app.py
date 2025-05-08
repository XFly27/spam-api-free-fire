from flask import Flask, request, jsonify
import requests
import json
import threading
from byte import Encrypt_ID, encrypt_api
import psycopg2
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)

class TokenManager:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.lock = threading.Lock()

    def get_valid_tokens(self, server_key="IND"):
        """Récupère les tokens valides depuis la base de données"""
        try:
            conn = psycopg2.connect(self.db_url)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT token FROM tokens 
                WHERE server_key = %s 
                AND expires_at > NOW() AT TIME ZONE 'UTC'
                AND is_valid = TRUE
                ORDER BY last_refresh DESC
               
            ''', (server_key,))
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"Error fetching tokens from DB: {e}")
            return []
        finally:
            if 'conn' in locals():
                conn.close()

# Initialisation du gestionnaire de tokens
token_manager = TokenManager()

def send_friend_request(uid, token, results):
    encrypted_id = Encrypt_ID(uid)
    payload = f"08a7c4839f1e10{encrypted_id}1801"
    encrypted_payload = encrypt_api(payload)

    url = "https://client.ind.freefiremobile.com/RequestAddingFriend"
    # url ="https://clientbp.ggblueshark.com/RequestAddingFriend"
    # headers = {
    #     "Expect": "100-continue",
    #     "Authorization": f"Bearer {token}",
    #     "X-Unity-Version": "2018.4.11f1",
    #     "X-GA": "v1 1",
    #     "ReleaseVersion": "OB48",
    #     "Content-Type": "application/x-www-form-urlencoded",
    #     "Content-Length": "16",
    #     "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-N975F Build/PI)",
    #     "Host": "clientbp.ggblueshark.com",
    #     "Connection": "close",
    #     "Accept-Encoding": "gzip, deflate, br"
    # }
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB48"
    }

    try:
        response = requests.post(url, headers=headers, data=bytes.fromhex(encrypted_payload), timeout=10)
        if response.status_code == 200:
            results["success"] += 1
        else:
            results["failed"] += 1
            print(f"Request failed with status {response.status_code}")
    except Exception as e:
        results["failed"] += 1
        print(f"Request error: {e}")

@app.route("/send_requests", methods=["GET"])
def send_requests():
    uid = request.args.get("uid")

    if not uid:
        return jsonify({"error": "uid parameter is required"}), 400

    tokens = token_manager.get_valid_tokens()
    if not tokens:
        return jsonify({"error": "No valid tokens found in database"}), 500

    results = {"success": 0, "failed": 0}
    threads = []

    for token in tokens:
        thread = threading.Thread(target=send_friend_request, args=(uid, token, results))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    total_requests = results["success"] + results["failed"]
    status = 1 if results["success"] > 0 else 2

    return jsonify({
        "success_count": results["success"],
        "failed_count": results["failed"],
        "status": status,
        "total_tokens_used": total_requests,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)