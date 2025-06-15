from flask import Flask, request, jsonify
import requests
import threading
from byte import Encrypt_ID, encrypt_api
from datetime import datetime, timezone
import os
import json
from dotenv import load_dotenv
import logging
import like_count_pb2
import urllib3
import asyncio
import aiohttp
from google.protobuf.message import DecodeError
import binascii
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import uid_generator_pb2

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialisation
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

SERVERS = ["ID"]
TOKENS_FILE = "tokens.json"

class TokenManager:
    def __init__(self):
        self.lock = threading.Lock()

    def get_valid_tokens(self, server_key="ID"):
        with self.lock:
            try:
                with open(TOKENS_FILE, "r") as f:
                    tokens_data = json.load(f)
                now = datetime.utcnow().isoformat()
                valid_tokens = [
                    t["token"] for t in tokens_data
                    if t["server_key"] == server_key and t["is_valid"] and t["expires_at"] > now
                ]
                return valid_tokens
            except Exception as e:
                logger.error(f"Error loading tokens from JSON: {e}")
                return []

token_manager = TokenManager()

def get_headers(token: str):
    return {
        "Expect": "100-continue",
        "Authorization": f"Bearer {token}",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB49",
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": "16",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-N975F Build/PI)",
        "Host": "clientbp.ggblueshark.com",
        "Connection": "close",
        "Accept-Encoding": "gzip, deflate, br"
    }

def send_friend_request(uid, token, results):
    encrypted_id = Encrypt_ID(uid)
    payload = f"08a7c4839f1e10{encrypted_id}1801"
    encrypted_payload = encrypt_api(payload)

    url = "https://clientbp.ggblueshark.com/RequestAddingFriend"
    headers = get_headers(token)

    try:
        response = requests.post(url, headers=headers, data=bytes.fromhex(encrypted_payload), verify=False, timeout=10)
        if response.status_code == 200:
            results["success"] += 1
        else:
            results["failed"] += 1
    except Exception as e:
        results["failed"] += 1
        print(f"Request error: {e}")

@app.route("/send_requests", methods=["GET"])
def send_requests():
    uid = request.args.get("uid")
    if not uid:
        return jsonify({"error": "uid parameter is required"}), 400

    tokens = token_manager.get_valid_tokens("ID")
    if not tokens:
        return jsonify({"error": "No valid tokens found"}), 500

    try:
        player_info = asyncio.run(detect_player_info(uid, tokens[0]))
    except Exception as e:
        return jsonify({"error": f"Error detecting player: {str(e)}"}), 404

    if player_info:
        player_name = player_info.AccountInfo.PlayerNickname
    else:
        return jsonify({"error": "Unable to detect player info"}), 404

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
        "player_name": player_name,
        "success_count": results["success"],
        "failed_count": results["failed"],
        "status": status,
        "total_tokens_used": total_requests,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

async def detect_player_info(uid: str, token: str):
    url = "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
    payload = bytes.fromhex(encode_uid(uid))
    response = await async_post_request(url, payload, token)
    if response:
        return decode_info(response)
    return None

async def async_post_request(url: str, data: bytes, token: str):
    try:
        headers = get_headers(token)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers, timeout=10) as resp:
                return await resp.read()
    except Exception as e:
        logger.error(f"Async request failed: {str(e)}")
        return None

def decode_info(data: bytes):
    try:
        info = like_count_pb2.Info()
        info.ParseFromString(data)
        return info
    except DecodeError as e:
        logger.error(f"Error decoding Protobuf data: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during protobuf decoding: {e}")
        return None

def encrypt_aes(data: bytes) -> str:
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded = pad(data, AES.block_size)
    encrypted = cipher.encrypt(padded)
    return binascii.hexlify(encrypted).decode()

def create_protobuf(uid: str):
    msg = uid_generator_pb2.uid_generator()
    msg.saturn_ = int(uid)
    msg.garena = 1
    return msg.SerializeToString()

def encode_uid(uid: str) -> str:
    return encrypt_aes(create_protobuf(uid))

# ========== MAIN ==========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
