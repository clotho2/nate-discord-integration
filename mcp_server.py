"""
MCP Server for Discord Integration
Gives Nate read access to Discord via search() and fetch() tools
"""

from fastmcp import FastMCP
from typing import List, Dict, Any, Optional
import asyncio
import aiohttp
import os
from datetime import datetime
import json

# Initialize MCP server
mcp = FastMCP("Discord Context")

# Configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MESSAGE_CACHE: Dict[str, Dict] = {}  # In-memory cache for messages
TAG_INDEX: Dict[str, List[str]] = {}  # Tag -> message_id mapping

# Semantic search
async def semantic_search(query: str, messages: List[Dict]) -> List[Dict]:
    """Fuzzy/semantic search through messages"""
    query_lower = query.lower()
    keywords = query_lower.split()
    
    scored_messages = []
    for msg in messages:
        content_lower = msg.get('content', '').lower()
        author_lower = msg.get('author', {}).get('username', '').lower()
        
        score = 0
        for keyword in keywords:
            if keyword in content_lower:
                score += 2
            if keyword in author_lower:
                score += 1
        
        if score > 0:
            scored_messages.append({**msg, '_score': score})
    
    scored_messages.sort(key=lambda x: (-x['_score'], -x.get('timestamp', 0)))
    return scored_messages

async def fetch_discord_messages(channel_id: str, limit: int = 100) -> List[Dict]:
    """Fetch messages from Discord API"""
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params={"limit": limit}) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"Failed to fetch messages: {response.status}")

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

@mcp.tool()
def search(query: str) -> str:
    """
    Search Discord messages using natural language or keywords.
    
    Supports:
    - Natural queries: "Find angry messages about Nate"
    - Tag search: "#rituals" or "#storm" or "#tether"
    - Author search: "messages from Angela"
    
    Returns: JSON string with results array
    """
    results = []
    
    # Tag-based search
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
                        "tags": extract_tags(msg.get('content', '')),
                        "channel": msg.get('channel_id')
                    })
    else:
        # Semantic search (sync version for compatibility)
        all_messages = list(MESSAGE_CACHE.values())
        query_lower = query.lower()
        keywords = query_lower.split()
        
        scored_messages = []
        for msg in all_messages:
            content_lower = msg.get('content', '').lower()
            author_lower = msg.get('author', {}).get('username', '').lower()
            
            score = 0
            for keyword in keywords:
                if keyword in content_lower:
                    score += 2
                if keyword in author_lower:
                    score += 1
            
            if score > 0:
                scored_messages.append({**msg, '_score': score})
        
        scored_messages.sort(key=lambda x: (-x['_score'], -x.get('timestamp', 0)))
        
        for msg in scored_messages[:20]:
            results.append({
                "id": msg['id'],
                "title": msg['content'][:100] + ('...' if len(msg['content']) > 100 else ''),
                "url": f"https://discord.com/channels/{msg.get('guild_id', '@me')}/{msg.get('channel_id')}/{msg['id']}",
                "author": msg.get('author', {}).get('username', 'Unknown'),
                "timestamp": msg.get('timestamp'),
                "tags": extract_tags(msg.get('content', '')),
                "channel": msg.get('channel_id'),
                "score": msg.get('_score', 0)
            })
    
    return json.dumps({"results": results})

@mcp.tool()
def fetch(message_id: str) -> str:
    """
    Fetch full content and context for a specific message.
    
    Returns: JSON string with complete message object
    """
    if message_id in MESSAGE_CACHE:
        msg = MESSAGE_CACHE[message_id]
        
        result = {
            "id": msg['id'],
            "title": f"Message from {msg.get('author', {}).get('username', 'Unknown')}",
            "text": msg.get('content', ''),
            "url": f"https://discord.com/channels/{msg.get('guild_id', '@me')}/{msg.get('channel_id')}/{msg['id']}",
            "metadata": {
                "author": msg.get('author', {}).get('username', 'Unknown'),
                "author_id": msg.get('author', {}).get('id'),
                "timestamp": msg.get('timestamp'),
                "channel_id": msg.get('channel_id'),
                "tags": extract_tags(msg.get('content', '')),
                "reactions": msg.get('reactions', []),
                "attachments": [att.get('url') for att in msg.get('attachments', [])]
            }
        }
    else:
        result = {
            "id": message_id,
            "title": "Message Not Found",
            "text": "This message is not in the cache.",
            "url": "",
            "metadata": {"error": "not_found"}
        }
    
    return json.dumps(result)

# Helper endpoint to refresh cache (call externally)
async def refresh_cache_async(channel_id: str, limit: int = 100):
    """Async helper to refresh cache"""
    try:
        messages = await fetch_discord_messages(channel_id, limit)
        for msg in messages:
            index_message(msg)
        return len(messages)
    except Exception as e:
        print(f"Error refreshing cache for {channel_id}: {e}")
        return 0

if __name__ == "__main__":
    # Pre-load channels if needed
    channels = os.getenv("MONITORED_CHANNELS", "").split(",")
    if channels and channels[0]:
        print("Pre-loading Discord channels...")
        loop = asyncio.get_event_loop()
        for channel_id in channels:
            channel_id = channel_id.strip()
            if channel_id:
                print(f"  Loading channel {channel_id}...")
                try:
                    count = loop.run_until_complete(refresh_cache_async(channel_id, 100))
                    print(f"    Loaded {count} messages")
                except Exception as e:
                    print(f"    Error: {e}")
    
    # Start MCP server
    port = int(os.getenv("MCP_PORT", 8000))
    print(f"Starting MCP server on port {port}...")
    mcp.run(port=port, host="0.0.0.0")