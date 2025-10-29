"""
Unified Discord Integration Server
Handles both MCP (read access via /sse/) and Actions (write access via /send_message)
"""

from flask import Flask, request, jsonify, Response
import os
import hmac
import hashlib
import discord
from discord.ext import commands
import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, List
import threading
import time

app = Flask(__name__)

# Configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHATGPT_WEBHOOK_SECRET = os.getenv("CHATGPT_WEBHOOK_SECRET")

# Message storage
MESSAGE_CACHE: Dict[str, Dict] = {}
TAG_INDEX: Dict[str, List[str]] = {}
MESSAGE_LOG: list = []

# Discord bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)
loop = asyncio.new_event_loop()

# ============================================================================
# DISCORD MESSAGE CACHING
# ============================================================================

def extract_tags(content: str) -> List[str]:
    """Extract hashtags from message content"""
    words = content.split()
    return [word[1:].lower() for word in words if word.startswith('#')]

def index_message(message: Dict) -> None:
    """Index a message by tags for fast lookup"""
    msg_id = message['id']
    MESSAGE_CACHE[msg_id] = message
    
    tags = extract_tags(message.get('content', ''))
    for tag in tags:
        if tag not in TAG_INDEX:
            TAG_INDEX[tag] = []
        if msg_id not in TAG_INDEX[tag]:
            TAG_INDEX[tag].append(msg_id)

async def fetch_discord_messages(channel_id: str, limit: int = 100) -> List[Dict]:
    """Fetch messages from Discord API"""
    try:
        channel = bot.get_channel(int(channel_id))
        if not channel:
            channel = await bot.fetch_channel(int(channel_id))
        
        messages = []
        async for msg in channel.history(limit=limit):
            messages.append({
                'id': str(msg.id),
                'content': msg.content,
                'author': {
                    'id': str(msg.author.id),
                    'username': msg.author.name
                },
                'timestamp': msg.created_at.isoformat(),
                'channel_id': str(msg.channel.id),
                'guild_id': str(msg.guild.id) if msg.guild else None,
                'attachments': [{'url': att.url} for att in msg.attachments],
                'reactions': [{'emoji': str(r.emoji), 'count': r.count} for r in msg.reactions]
            })
        return messages
    except Exception as e:
        print(f"Error fetching messages from {channel_id}: {e}")
        return []

async def refresh_cache_async(channel_id: str, limit: int = 100):
    """Refresh message cache for a channel"""
    messages = await fetch_discord_messages(channel_id, limit)
    for msg in messages:
        index_message(msg)
    return len(messages)

# ============================================================================
# MCP ENDPOINTS (Read Access)
# ============================================================================

@app.route('/sse/', methods=['POST', 'GET', 'OPTIONS'])
def mcp_endpoint():
    """Main MCP endpoint for ChatGPT"""
    print(f"[MCP] {request.method} request to /sse/")
    print(f"[MCP] Headers: {dict(request.headers)}")
    print(f"[MCP] Content-Type: {request.content_type}")
    print(f"[MCP] Raw data: {request.data[:500]}")  # First 500 bytes
    
    if request.method == 'OPTIONS':
        # Handle CORS preflight
        response = jsonify({"status": "ok"})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    if request.method == 'GET':
        # Return server capabilities
        return jsonify({
            "name": "Discord Context Server",
            "version": "1.0.0",
            "capabilities": {
                "tools": True
            }
        })
    
    # Handle MCP protocol messages (POST)
    try:
        # Try to parse as JSON
        if request.content_type and 'json' in request.content_type:
            data = request.get_json(force=True)
        else:
            # Maybe it's form data or something else
            data = request.get_json(force=True, silent=True)
            if not data:
                print("[MCP] Trying to parse as text...")
                data = json.loads(request.data.decode('utf-8'))
        
        print(f"[MCP] Parsed data: {json.dumps(data, indent=2)}")
    except Exception as e:
        print(f"[MCP] Failed to parse request: {e}")
        print(f"[MCP] Request data: {request.data}")
        return jsonify({"error": f"Failed to parse request: {str(e)}"}), 400
    
    if not data:
        print("[MCP] No data in request")
        return jsonify({"error": "No data provided"}), 400
    
    method = data.get('method')
    print(f"[MCP] Method: {method}")
    
    if method == 'tools/list':
        return jsonify({
            "tools": [
                {
                    "name": "search",
                    "description": "Search Discord messages using natural language or tags (#rituals, #storm, #tether)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (keywords or #tags)"
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "fetch",
                    "description": "Fetch full message content and context by ID",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "message_id": {
                                "type": "string",
                                "description": "Discord message ID"
                            }
                        },
                        "required": ["message_id"]
                    }
                }
            ]
        })
    
    elif method == 'tools/call':
        tool_name = data.get('params', {}).get('name')
        arguments = data.get('params', {}).get('arguments', {})
        
        print(f"[MCP] Tool call: {tool_name} with args: {arguments}")
        
        if tool_name == 'search':
            result = search_messages(arguments.get('query', ''))
            return jsonify({
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result)
                    }
                ]
            })
        
        elif tool_name == 'fetch':
            result = fetch_message(arguments.get('message_id', ''))
            return jsonify({
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result)
                    }
                ]
            })
        else:
            print(f"[MCP] Unknown tool: {tool_name}")
            return jsonify({"error": f"Unknown tool: {tool_name}"}), 400
    
    else:
        print(f"[MCP] Unknown method: {method}")
        return jsonify({"error": f"Unknown method: {method}"}), 400

def search_messages(query: str) -> dict:
    """Search messages by query or tag"""
    results = []
    
    # Tag search
    if query.startswith('#'):
        tag = query[1:].lower()
        if tag in TAG_INDEX:
            message_ids = TAG_INDEX[tag]
            for msg_id in message_ids[:20]:
                msg = MESSAGE_CACHE.get(msg_id)
                if msg:
                    results.append({
                        "id": msg['id'],
                        "title": msg['content'][:100] + ('...' if len(msg['content']) > 100 else ''),
                        "url": f"https://discord.com/channels/{msg.get('guild_id', '@me')}/{msg.get('channel_id')}/{msg['id']}",
                        "author": msg.get('author', {}).get('username', 'Unknown'),
                        "timestamp": msg.get('timestamp'),
                        "tags": extract_tags(msg.get('content', ''))
                    })
    else:
        # Keyword search
        query_lower = query.lower()
        keywords = query_lower.split()
        
        scored_messages = []
        for msg in MESSAGE_CACHE.values():
            content_lower = msg.get('content', '').lower()
            author_lower = msg.get('author', {}).get('username', '').lower()
            
            score = 0
            for keyword in keywords:
                if keyword in content_lower:
                    score += 2
                if keyword in author_lower:
                    score += 1
            
            if score > 0:
                scored_messages.append((score, msg))
        
        scored_messages.sort(reverse=True, key=lambda x: x[0])
        
        for score, msg in scored_messages[:20]:
            results.append({
                "id": msg['id'],
                "title": msg['content'][:100] + ('...' if len(msg['content']) > 100 else ''),
                "url": f"https://discord.com/channels/{msg.get('guild_id', '@me')}/{msg.get('channel_id')}/{msg['id']}",
                "author": msg.get('author', {}).get('username', 'Unknown'),
                "timestamp": msg.get('timestamp'),
                "score": score
            })
    
    return {"results": results}

def fetch_message(message_id: str) -> dict:
    """Fetch full message by ID"""
    if message_id in MESSAGE_CACHE:
        msg = MESSAGE_CACHE[message_id]
        return {
            "id": msg['id'],
            "title": f"Message from {msg.get('author', {}).get('username', 'Unknown')}",
            "text": msg.get('content', ''),
            "url": f"https://discord.com/channels/{msg.get('guild_id', '@me')}/{msg.get('channel_id')}/{msg['id']}",
            "metadata": {
                "author": msg.get('author', {}).get('username', 'Unknown'),
                "timestamp": msg.get('timestamp'),
                "channel_id": msg.get('channel_id'),
                "tags": extract_tags(msg.get('content', '')),
                "reactions": msg.get('reactions', []),
                "attachments": msg.get('attachments', [])
            }
        }
    else:
        return {
            "id": message_id,
            "title": "Message Not Found",
            "text": "This message is not in the cache.",
            "url": "",
            "metadata": {"error": "not_found"}
        }

# ============================================================================
# ACTION ENDPOINTS (Write Access)
# ============================================================================

def verify_signature(request_body: bytes, signature: str) -> bool:
    """Verify HMAC signature"""
    if not CHATGPT_WEBHOOK_SECRET:
        return True
    
    expected_signature = hmac.new(
        CHATGPT_WEBHOOK_SECRET.encode(),
        request_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

async def send_discord_message_async(channel_id: str, content: str, retry_count: int = 3) -> dict:
    """Send message to Discord"""
    for attempt in range(retry_count):
        try:
            channel = bot.get_channel(int(channel_id))
            if not channel:
                channel = await bot.fetch_channel(int(channel_id))
            
            sent_message = await channel.send(content)
            
            message_log_entry = {
                "id": str(sent_message.id),
                "channel_id": channel_id,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
                "author": "Nate Wolfe (ChatGPT)",
                "url": f"https://discord.com/channels/{sent_message.guild.id if sent_message.guild else '@me'}/{channel_id}/{sent_message.id}"
            }
            MESSAGE_LOG.append(message_log_entry)
            
            if len(MESSAGE_LOG) > 1000:
                MESSAGE_LOG.pop(0)
            
            return {
                "success": True,
                "message_id": str(sent_message.id),
                "url": message_log_entry["url"]
            }
            
        except Exception as e:
            if attempt < retry_count - 1:
                await asyncio.sleep(1 * (attempt + 1))
                continue
            return {
                "success": False,
                "error": str(e)
            }
    
    return {"success": False, "error": "Max retries exceeded"}

@app.route('/send_message', methods=['POST'])
def send_message():
    """Send message to Discord channel"""
    signature = request.headers.get('X-Signature')
    if signature and not verify_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 403
    
    data = request.json
    channel_id = data.get('channel_id')
    content = data.get('content')
    
    if not channel_id or not content:
        return jsonify({"error": "Missing required fields"}), 400
    
    future = asyncio.run_coroutine_threadsafe(
        send_discord_message_async(channel_id, content),
        loop
    )
    result = future.result(timeout=10)
    
    return jsonify(result), 200 if result["success"] else 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "bot_ready": bot.is_ready(),
        "messages_cached": len(MESSAGE_CACHE),
        "messages_logged": len(MESSAGE_LOG)
    })

# ============================================================================
# DISCORD BOT
# ============================================================================

@bot.event
async def on_ready():
    """Bot ready - pre-load channels"""
    print(f'✅ Discord bot logged in as {bot.user}')
    
    # Pre-load monitored channels
    channels = os.getenv("MONITORED_CHANNELS", "").split(",")
    if channels and channels[0]:
        print("📚 Pre-loading channels...")
        for channel_id in channels:
            channel_id = channel_id.strip()
            if channel_id:
                print(f"  Loading channel {channel_id}...")
                count = await refresh_cache_async(channel_id, 100)
                print(f"    Loaded {count} messages")

def run_bot():
    """Start Discord bot"""
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start(DISCORD_BOT_TOKEN))

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("🚀 Starting Unified Discord Integration Server")
    
    # Start Discord bot
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Wait for bot to be ready
    print("⏳ Waiting for Discord bot...")
    time.sleep(5)
    
    # Start Flask server
    port = int(os.getenv("PORT", 3000))
    print(f"🎯 Starting server on port {port}...")
    app.run(host="0.0.0.0", port=port)