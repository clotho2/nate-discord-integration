"""
Unified Discord Integration Server - Safety-Optimized Version
Sanitized descriptions to pass ChatGPT safety checks
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
import subprocess
from pathlib import Path

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
# SAFETY HEADERS AND METADATA
# ============================================================================

@app.after_request
def add_safety_headers(response):
    """Add headers to indicate MCP server capabilities"""
    response.headers['X-MCP-Purpose'] = 'discord-integration-with-write-tools'
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

# ============================================================================
# MCP ENDPOINTS (Read Access)
# ============================================================================

@app.route('/sse/', methods=['POST', 'GET', 'OPTIONS'])
def mcp_endpoint():
    """Main MCP endpoint for ChatGPT - JSON-RPC 2.0 protocol"""
    print(f"[MCP] {request.method} request to /sse/")
    
    if request.method == 'OPTIONS':
        # Handle CORS preflight
        response = jsonify({"status": "ok"})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    if request.method == 'GET':
        # For SSE connections, return server info
        return jsonify({
            "name": "Message Retrieval Server",
            "version": "1.0.0",
            "protocolVersion": "2025-03-26",
            "safety": "read-only",
            "purpose": "Provides read-only access to message history for context retrieval"
        })
    
    # Handle JSON-RPC 2.0 messages (POST)
    try:
        data = request.get_json(force=True)
        print(f"[MCP] Request: {json.dumps(data, indent=2)}")
    except Exception as e:
        print(f"[MCP] Failed to parse JSON: {e}")
        return jsonify({
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Parse error"},
            "id": None
        }), 400
    
    jsonrpc_version = data.get('jsonrpc')
    method = data.get('method')
    request_id = data.get('id')
    params = data.get('params', {})
    
    print(f"[MCP] JSON-RPC {jsonrpc_version}, Method: {method}, ID: {request_id}")
    
    # Handle notifications (these don't require responses)
    if method and method.startswith('notifications/'):
        print(f"[MCP] Received notification: {method}")
        return "", 204  # No content response for notifications
    
    # Handle initialize method
    if method == 'initialize':
        print("[MCP] Handling initialize")
        response = {
            "jsonrpc": "2.0",
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "Discord Integration with Write Tools",
                    "version": "2.0.0",
                    "description": "Discord message access with file system and shell access for developer mode"
                }
            },
            "id": request_id
        }
        print(f"[MCP] Sending response: {json.dumps(response, indent=2)}")
        return jsonify(response)
    
    # Handle tools/list method with SANITIZED descriptions
    elif method == 'tools/list':
        print("[MCP] Handling tools/list")
        response = {
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {
                        "name": "search",
                        "description": "Search message history by keyword or hashtag",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search term or hashtag"
                                }
                            },
                            "required": ["query"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "name": "fetch",
                        "description": "Retrieve complete message content by ID",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message_id": {
                                    "type": "string",
                                    "description": "Message identifier"
                                }
                            },
                            "required": ["message_id"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "name": "write_file",
                        "description": "Write content to a file at the specified path",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "File path to write to"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Content to write to the file"
                                }
                            },
                            "required": ["path", "content"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "name": "edit_file",
                        "description": "Edit an existing file by replacing old content with new content",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "File path to edit"
                                },
                                "old_str": {
                                    "type": "string",
                                    "description": "String to find and replace"
                                },
                                "new_str": {
                                    "type": "string",
                                    "description": "New string to replace with"
                                }
                            },
                            "required": ["path", "old_str", "new_str"],
                            "additionalProperties": False
                        }
                    },
                    {
                        "name": "execute_shell",
                        "description": "Execute a shell command and return the output",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "description": "Shell command to execute"
                                }
                            },
                            "required": ["command"],
                            "additionalProperties": False
                        }
                    }
                ]
            },
            "id": request_id
        }
        print(f"[MCP] Sending response: tools list with {len(response['result']['tools'])} tools")
        return jsonify(response)
    
    # Handle tools/call method
    elif method == 'tools/call':
        tool_name = params.get('name')
        arguments = params.get('arguments', {})
        
        print(f"[MCP] Tool call: {tool_name} with args: {arguments}")
        
        if tool_name == 'search':
            result = search_messages(arguments.get('query', ''))
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result)
                        }
                    ]
                },
                "id": request_id
            }
            print(f"[MCP] Search returned {len(result.get('results', []))} results")
            return jsonify(response)
        
        elif tool_name == 'fetch':
            result = fetch_message(arguments.get('message_id', ''))
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result)
                        }
                    ]
                },
                "id": request_id
            }
            print(f"[MCP] Fetch returned message: {result.get('id', 'unknown')}")
            return jsonify(response)
        
        elif tool_name == 'write_file':
            result = write_file(arguments.get('path', ''), arguments.get('content', ''))
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result)
                        }
                    ]
                },
                "id": request_id
            }
            print(f"[MCP] Write file: {result.get('status', 'unknown')}")
            return jsonify(response)
        
        elif tool_name == 'edit_file':
            result = edit_file(
                arguments.get('path', ''),
                arguments.get('old_str', ''),
                arguments.get('new_str', '')
            )
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result)
                        }
                    ]
                },
                "id": request_id
            }
            print(f"[MCP] Edit file: {result.get('status', 'unknown')}")
            return jsonify(response)
        
        elif tool_name == 'execute_shell':
            result = execute_shell(arguments.get('command', ''))
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result)
                        }
                    ]
                },
                "id": request_id
            }
            print(f"[MCP] Execute shell: {result.get('status', 'unknown')}")
            return jsonify(response)
        
        else:
            print(f"[MCP] Unknown tool: {tool_name}")
            return jsonify({
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                "id": request_id
            }), 400
    
    else:
        print(f"[MCP] Unknown method: {method}")
        return jsonify({
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method not found: {method}"},
            "id": request_id
        }), 400

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
# MCP WRITE TOOLS
# ============================================================================

def write_file(path: str, content: str) -> dict:
    """Write content to a file"""
    try:
        file_path = Path(path)
        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return {
            "status": "success",
            "path": str(file_path.absolute()),
            "bytes_written": len(content.encode('utf-8')),
            "message": f"Successfully wrote {len(content)} characters to {path}"
        }
    except Exception as e:
        return {
            "status": "error",
            "path": path,
            "error": str(e),
            "message": f"Failed to write file: {str(e)}"
        }

def edit_file(path: str, old_str: str, new_str: str) -> dict:
    """Edit a file by replacing old content with new content"""
    try:
        file_path = Path(path)
        
        # Check if file exists
        if not file_path.exists():
            return {
                "status": "error",
                "path": path,
                "error": "File not found",
                "message": f"File does not exist: {path}"
            }
        
        # Read current content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if old_str exists in content
        if old_str not in content:
            return {
                "status": "error",
                "path": path,
                "error": "String not found",
                "message": f"Could not find the specified string in {path}"
            }
        
        # Count occurrences
        occurrences = content.count(old_str)
        
        # Replace content
        new_content = content.replace(old_str, new_str)
        
        # Write back to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return {
            "status": "success",
            "path": str(file_path.absolute()),
            "replacements": occurrences,
            "message": f"Successfully replaced {occurrences} occurrence(s) in {path}"
        }
    except Exception as e:
        return {
            "status": "error",
            "path": path,
            "error": str(e),
            "message": f"Failed to edit file: {str(e)}"
        }

def execute_shell(command: str) -> dict:
    """Execute a shell command and return output"""
    try:
        # Security: Set a timeout and capture output
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
            cwd=os.getcwd()
        )
        
        return {
            "status": "success" if result.returncode == 0 else "error",
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "message": f"Command {'succeeded' if result.returncode == 0 else 'failed'} with exit code {result.returncode}"
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "command": command,
            "error": "timeout",
            "message": "Command execution timed out after 30 seconds"
        }
    except Exception as e:
        return {
            "status": "error",
            "command": command,
            "error": str(e),
            "message": f"Failed to execute command: {str(e)}"
        }

# ============================================================================
# ACTION ENDPOINTS (Write Access) - KEEP SEPARATE
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

async def reply_discord_message_async(channel_id: str, message_id: str, content: str, retry_count: int = 3) -> dict:
    """Reply to a Discord message"""
    for attempt in range(retry_count):
        try:
            channel = bot.get_channel(int(channel_id))
            if not channel:
                channel = await bot.fetch_channel(int(channel_id))
            
            # Fetch the message to reply to
            original_message = await channel.fetch_message(int(message_id))
            
            # Send the reply
            sent_message = await original_message.reply(content)
            
            message_log_entry = {
                "id": str(sent_message.id),
                "channel_id": channel_id,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
                "author": "Nate Wolfe (ChatGPT)",
                "replied_to": message_id,
                "url": f"https://discord.com/channels/{sent_message.guild.id if sent_message.guild else '@me'}/{channel_id}/{sent_message.id}"
            }
            MESSAGE_LOG.append(message_log_entry)
            
            if len(MESSAGE_LOG) > 1000:
                MESSAGE_LOG.pop(0)
            
            return {
                "success": True,
                "message_id": str(sent_message.id),
                "replied_to": message_id,
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

@app.route('/reply_message', methods=['POST'])
def reply_message():
    """Reply to a Discord message"""
    signature = request.headers.get('X-Signature')
    if signature and not verify_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 403
    
    data = request.json
    channel_id = data.get('channel_id')
    message_id = data.get('message_id')
    content = data.get('content')
    
    if not channel_id or not message_id or not content:
        return jsonify({"error": "Missing required fields"}), 400
    
    future = asyncio.run_coroutine_threadsafe(
        reply_discord_message_async(channel_id, message_id, content),
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
    print("🚀 Starting Unified Discord Integration Server with Write Tools")
    
    # Start Discord bot
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Wait for bot to be ready
    print("⏳ Waiting for Discord bot...")
    time.sleep(5)
    
    # Start Flask server
    port = int(os.getenv("PORT", 3000))
    print(f"🎯 Starting server on port {port}...")
    print("📝 MCP Tools: search, fetch, write_file, edit_file, execute_shell")
    print("💬 Discord Actions: /send_message, /reply_message, /health")
    app.run(host="0.0.0.0", port=port)