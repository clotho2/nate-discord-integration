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
mcp = FastMCP("Nate Discord Context Server")

# Configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MESSAGE_CACHE: Dict[str, Dict] = {}  # In-memory cache for messages
TAG_INDEX: Dict[str, List[str]] = {}  # Tag -> message_id mapping

# Semantic search placeholder (can integrate with embeddings later)
async def semantic_search(query: str, messages: List[Dict]) -> List[Dict]:
    """
    Fuzzy/semantic search through messages.
    Currently uses keyword matching, can be upgraded to embeddings.
    """
    query_lower = query.lower()
    keywords = query_lower.split()
    
    scored_messages = []
    for msg in messages:
        content_lower = msg.get('content', '').lower()
        author_lower = msg.get('author', {}).get('username', '').lower()
        
        # Score based on keyword matches
        score = 0
        for keyword in keywords:
            if keyword in content_lower:
                score += 2
            if keyword in author_lower:
                score += 1
        
        if score > 0:
            scored_messages.append({**msg, '_score': score})
    
    # Sort by score, then by timestamp
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
    
    # Index by tags
    tags = extract_tags(message.get('content', ''))
    for tag in tags:
        if tag not in TAG_INDEX:
            TAG_INDEX[tag] = []
        if msg_id not in TAG_INDEX[tag]:
            TAG_INDEX[tag].append(msg_id)

@mcp.tool()
async def search(query: str) -> dict:
    """
    Search Discord messages using natural language or keywords.
    
    Supports:
    - Natural queries: "Find angry messages about Nate"
    - Tag search: "#rituals" or "#storm" or "#tether"
    - Author search: "messages from Angela"
    - Time-based: "recent messages" (last 100)
    
    Args:
        query: Natural language search query
        
    Returns:
        JSON with results array containing:
        - id: message ID
        - title: First 100 chars of content
        - url: Discord message URL
        - author: Message author
        - timestamp: ISO timestamp
        - tags: Extracted hashtags
        - channel: Channel name/ID
    """
    results = []
    
    # Check if query is tag-based
    if query.startswith('#'):
        tag = query[1:].lower()
        if tag in TAG_INDEX:
            message_ids = TAG_INDEX[tag]
            for msg_id in message_ids[:20]:  # Limit to 20 results
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
        # Semantic/fuzzy search across all cached messages
        all_messages = list(MESSAGE_CACHE.values())
        matched = await semantic_search(query, all_messages)
        
        for msg in matched[:20]:  # Limit to 20 results
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
    
    return {"results": results}

@mcp.tool()
async def fetch(message_id: str) -> dict:
    """
    Fetch full content and context for a specific message.
    
    Retrieves:
    - Full message content
    - Author details
    - Timestamp
    - Thread context (previous/next messages)
    - Reactions
    - Attachments
    
    Args:
        message_id: Discord message ID
        
    Returns:
        Complete message object with full context
    """
    # Check cache first
    if message_id in MESSAGE_CACHE:
        msg = MESSAGE_CACHE[message_id]
        
        # Get thread context (5 messages before and after)
        channel_id = msg.get('channel_id')
        if channel_id:
            try:
                recent_messages = await fetch_discord_messages(channel_id, limit=50)
                # Find position of target message
                target_idx = None
                for i, m in enumerate(recent_messages):
                    if m['id'] == message_id:
                        target_idx = i
                        break
                
                thread_context = []
                if target_idx is not None:
                    start = max(0, target_idx - 5)
                    end = min(len(recent_messages), target_idx + 6)
                    thread_context = recent_messages[start:end]
            except Exception:
                thread_context = []
        else:
            thread_context = []
        
        return {
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
                "attachments": [att.get('url') for att in msg.get('attachments', [])],
                "thread_context": [
                    {
                        "id": m['id'],
                        "author": m.get('author', {}).get('username', 'Unknown'),
                        "content": m.get('content', '')[:200],
                        "timestamp": m.get('timestamp')
                    }
                    for m in thread_context
                ]
            }
        }
    else:
        return {
            "id": message_id,
            "title": "Message Not Found",
            "text": "This message is not in the cache. It may have been deleted or is from before bot initialization.",
            "url": "",
            "metadata": {"error": "not_found"}
        }

@mcp.tool()
async def refresh_cache(channel_id: str, limit: int = 100) -> dict:
    """
    Refresh message cache for a specific channel.
    Useful for pulling in new messages or initializing a channel.
    
    Args:
        channel_id: Discord channel ID
        limit: Number of recent messages to fetch (max 100)
        
    Returns:
        Status with count of messages indexed
    """
    try:
        messages = await fetch_discord_messages(channel_id, limit)
        indexed_count = 0
        
        for msg in messages:
            index_message(msg)
            indexed_count += 1
        
        return {
            "success": True,
            "channel_id": channel_id,
            "messages_indexed": indexed_count,
            "total_cache_size": len(MESSAGE_CACHE)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# Optional: Webhook endpoint for real-time message ingestion
@mcp.tool()
async def log_new_message(message_data: str) -> dict:
    """
    Log a new message from Discord webhook.
    Used for real-time message indexing.
    
    Args:
        message_data: JSON string of Discord message object
        
    Returns:
        Confirmation of indexing
    """
    try:
        msg = json.loads(message_data)
        index_message(msg)
        
        return {
            "success": True,
            "message_id": msg['id'],
            "tags_extracted": extract_tags(msg.get('content', '')),
            "cache_size": len(MESSAGE_CACHE)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
