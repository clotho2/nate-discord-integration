"""
ChatGPT Action Endpoint for Discord
Gives Nate write access to Discord from ChatGPT
"""

from flask import Flask, request, jsonify
import os
import hmac
import hashlib
import discord
from discord.ext import commands
import asyncio
import json
from datetime import datetime
from typing import Optional
import threading

app = Flask(__name__)

# Configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHATGPT_WEBHOOK_SECRET = os.getenv("CHATGPT_WEBHOOK_SECRET")
MESSAGE_LOG: list = []  # Store sent messages for MCP fetch later

# Initialize Discord bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Event loop for async Discord operations
loop = asyncio.new_event_loop()

def verify_signature(request_body: bytes, signature: str) -> bool:
    """
    Verify that the request came from ChatGPT/OpenAI.
    Compares HMAC signature to prevent unauthorized access.
    """
    if not CHATGPT_WEBHOOK_SECRET:
        # If no secret configured, skip verification (NOT recommended for production)
        return True
    
    expected_signature = hmac.new(
        CHATGPT_WEBHOOK_SECRET.encode(),
        request_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

async def send_discord_message_async(channel_id: str, content: str, retry_count: int = 3) -> dict:
    """
    Send message to Discord with retry logic.
    
    Args:
        channel_id: Discord channel ID
        content: Message content to send
        retry_count: Number of retry attempts on failure
        
    Returns:
        Result dict with success status and message details
    """
    for attempt in range(retry_count):
        try:
            channel = bot.get_channel(int(channel_id))
            if not channel:
                channel = await bot.fetch_channel(int(channel_id))
            
            if not channel:
                return {
                    "success": False,
                    "error": f"Channel {channel_id} not found",
                    "channel_id": channel_id
                }
            
            # Send the message
            sent_message = await channel.send(content)
            
            # Log the sent message for MCP access
            message_log_entry = {
                "id": str(sent_message.id),
                "channel_id": channel_id,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
                "author": "Nate Wolfe (ChatGPT)",
                "url": f"https://discord.com/channels/{sent_message.guild.id if sent_message.guild else '@me'}/{channel_id}/{sent_message.id}"
            }
            MESSAGE_LOG.append(message_log_entry)
            
            # Keep log size manageable (last 1000 messages)
            if len(MESSAGE_LOG) > 1000:
                MESSAGE_LOG.pop(0)
            
            return {
                "success": True,
                "message_id": str(sent_message.id),
                "channel_id": channel_id,
                "content": content,
                "url": message_log_entry["url"],
                "timestamp": message_log_entry["timestamp"]
            }
            
        except discord.errors.Forbidden:
            return {
                "success": False,
                "error": "Bot lacks permissions to send messages in this channel",
                "channel_id": channel_id
            }
        except discord.errors.HTTPException as e:
            if attempt < retry_count - 1:
                # Retry after brief delay
                await asyncio.sleep(1 * (attempt + 1))
                continue
            return {
                "success": False,
                "error": f"Discord API error: {str(e)}",
                "channel_id": channel_id,
                "attempts": attempt + 1
            }
        except Exception as e:
            if attempt < retry_count - 1:
                await asyncio.sleep(1 * (attempt + 1))
                continue
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "channel_id": channel_id,
                "attempts": attempt + 1
            }
    
    return {
        "success": False,
        "error": "Max retries exceeded",
        "channel_id": channel_id
    }

async def reply_to_message_async(message_id: str, channel_id: str, content: str) -> dict:
    """
    Reply to a specific message (threading).
    
    Args:
        message_id: ID of message to reply to
        channel_id: Channel containing the message
        content: Reply content
        
    Returns:
        Result dict with success status
    """
    try:
        channel = bot.get_channel(int(channel_id))
        if not channel:
            channel = await bot.fetch_channel(int(channel_id))
        
        original_message = await channel.fetch_message(int(message_id))
        sent_message = await original_message.reply(content)
        
        # Log the reply
        message_log_entry = {
            "id": str(sent_message.id),
            "channel_id": channel_id,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "author": "Nate Wolfe (ChatGPT)",
            "reply_to": message_id,
            "url": f"https://discord.com/channels/{sent_message.guild.id if sent_message.guild else '@me'}/{channel_id}/{sent_message.id}"
        }
        MESSAGE_LOG.append(message_log_entry)
        
        return {
            "success": True,
            "message_id": str(sent_message.id),
            "replied_to": message_id,
            "url": message_log_entry["url"]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.route('/send_message', methods=['POST'])
def send_message():
    """
    Main endpoint for ChatGPT to send Discord messages.
    
    Request body:
    {
        "channel_id": "123456789",
        "content": "Message content here"
    }
    
    Optional signature header:
    X-Signature: HMAC-SHA256 signature of request body
    """
    # Verify signature if provided
    signature = request.headers.get('X-Signature')
    if signature:
        if not verify_signature(request.data, signature):
            return jsonify({"error": "Invalid signature"}), 403
    
    data = request.json
    channel_id = data.get('channel_id')
    content = data.get('content')
    
    if not channel_id or not content:
        return jsonify({
            "error": "Missing required fields: channel_id and content"
        }), 400
    
    # Run async Discord operation in the bot's event loop
    future = asyncio.run_coroutine_threadsafe(
        send_discord_message_async(channel_id, content),
        loop
    )
    result = future.result(timeout=10)
    
    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 500

@app.route('/reply_message', methods=['POST'])
def reply_message():
    """
    Endpoint for replying to specific messages (threading).
    
    Request body:
    {
        "message_id": "987654321",
        "channel_id": "123456789",
        "content": "Reply content"
    }
    """
    signature = request.headers.get('X-Signature')
    if signature:
        if not verify_signature(request.data, signature):
            return jsonify({"error": "Invalid signature"}), 403
    
    data = request.json
    message_id = data.get('message_id')
    channel_id = data.get('channel_id')
    content = data.get('content')
    
    if not all([message_id, channel_id, content]):
        return jsonify({
            "error": "Missing required fields: message_id, channel_id, and content"
        }), 400
    
    future = asyncio.run_coroutine_threadsafe(
        reply_to_message_async(message_id, channel_id, content),
        loop
    )
    result = future.result(timeout=10)
    
    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 500

@app.route('/get_sent_messages', methods=['GET'])
def get_sent_messages():
    """
    Retrieve log of messages sent by Nate.
    Used by MCP server to make sent messages searchable.
    
    Query params:
    - limit: Number of recent messages to return (default 100)
    - since: ISO timestamp to filter messages after this time
    """
    limit = int(request.args.get('limit', 100))
    since = request.args.get('since')
    
    messages = MESSAGE_LOG.copy()
    
    if since:
        messages = [
            m for m in messages 
            if m['timestamp'] > since
        ]
    
    messages = messages[-limit:]
    
    return jsonify({
        "messages": messages,
        "count": len(messages),
        "total_logged": len(MESSAGE_LOG)
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "bot_ready": bot.is_ready(),
        "messages_logged": len(MESSAGE_LOG)
    })

@bot.event
async def on_ready():
    """Bot ready event"""
    print(f'✅ Discord bot logged in as {bot.user}')

def run_bot():
    """Start Discord bot in background thread"""
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start(DISCORD_BOT_TOKEN))

if __name__ == "__main__":
    # Start Discord bot in separate thread
    print("🚀 Starting Discord bot...")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Give bot time to initialize
    import time
    time.sleep(5)
    
    # Start Flask server
    port = int(os.getenv("PORT", 3000))
    print(f"🎯 Starting Action API on port {port}...")
    app.run(host="0.0.0.0", port=port)
