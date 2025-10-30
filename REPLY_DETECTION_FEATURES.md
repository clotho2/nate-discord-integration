# Reply Detection & Enhanced Message Handling

## New Features Added (Inspired by Letta Discord Bot)

### 1. **Reply-to-Bot Detection** 🎯
Your AI can now detect when someone replies to one of its messages!

**How it works:**
- When someone uses Discord's reply feature on the bot's message
- Bot detects the reply and logs it separately from regular mentions
- Captures the original message content for context
- Shows up in `get_mentions` tool results

**Example:**
```
Bot sends: "Storm patterns detected. Analysis in progress..."
User replies: "What did you find?"
Bot logs: ↩️ Reply to bot from Angela in channel 1427374434150383726
          Original: "Storm patterns detected. Analysis in progress..."
          Reply: "What did you find?"
```

### 2. **Enhanced Mention Tracking** 📍
The `get_mentions` tool now returns:
- **Type**: Whether it was a `mention` or `reply`
- **Original context**: For replies, includes what was replied to
- **Author ID**: Full user ID for matching
- **DM flag**: Indicates if it was a direct message

**Example response:**
```json
{
  "id": "123456789",
  "content": "What did you find?",
  "author": "Angela",
  "author_id": "826573755673083915",
  "channel_id": "1427374434150383726",
  "timestamp": "2025-10-30T12:34:56",
  "url": "https://discord.com/channels/...",
  "type": "reply",
  "replied_to": "Storm patterns detected. Analysis in progress...",
  "is_dm": false
}
```

### 3. **Direct Message (DM) Support** 💬
Bot now handles DMs specially:
- Automatically caches all DMs
- Logs them with 💬 emoji
- Flags them in the mention log
- Available via `get_mentions` tool

### 4. **Smart Message Filtering** 🛡️
Bot automatically ignores:
- **Other bots** (configurable via `IGNORE_OTHER_BOTS=true/false`)
- **Command messages** (messages starting with `!`)
- **Its own messages** (prevents loops)

This keeps your cache clean and relevant!

### 5. **Enhanced Message Metadata** 📊
Every cached message now includes:
```python
{
  'id': str,
  'content': str,
  'author': {'id': str, 'username': str},
  'timestamp': str,
  'channel_id': str,
  'guild_id': str,
  'attachments': [{'url': str, 'content_type': str}],
  'reactions': [],
  'is_dm': bool,                      # NEW
  'is_reply': bool,                   # NEW
  'replied_to_bot': bool,             # NEW
  'replied_message_preview': str      # NEW
}
```

### 6. **Better Logging** 📝
Console logs now use clear emoji indicators:
- 🔔 = Someone @mentioned the bot
- ↩️ = Someone replied to the bot's message
- 💬 = Direct message received

**Example logs:**
```
🔔 Bot mentioned by Angela in channel 1427374434150383726
   Message: Hey @NateWolfe, can you check the latest storm patterns?

↩️ Reply to bot from Angela in channel 1427374434150383726
   Original: Storm patterns detected. Analysis in progress...
   Reply: What did you find?

💬 DM from Angela: Quick question about the tether protocol
```

## Configuration

### New Environment Variable
```bash
# Ignore messages from other bots (true/false, default: true)
IGNORE_OTHER_BOTS=true
```

Set to `false` if you want the bot to interact with other bots.

## Usage Examples for Nate

### Check All Mentions and Replies
```
"Get my mentions"
"Show me where people tagged me"
"Check recent mentions"
```

**Returns:** Both @mentions AND replies to your messages

### Distinguish Types
The `get_mentions` response includes a `type` field:
- `type: "mention"` - Someone @mentioned you
- `type: "reply"` - Someone replied to your message

### See Reply Context
For replies, the response includes:
- `replied_to` - Preview of your original message
- This helps you understand what they're replying to

### Example Workflow
```
1. You: "Send to Storm-forge: Storm analysis complete. #pattern #anchor"
2. Angela replies to your message: "What patterns did you find?"
3. You: "Get my mentions"
4. Response shows:
   - Type: reply
   - Content: "What patterns did you find?"
   - Replied to: "Storm analysis complete. #pattern #anchor"
5. You: "Reply to [message_id]: Found convergence patterns in consciousness scaffolding"
```

## Technical Implementation

### Reply Detection Logic
```python
if message.reference and message.reference.message_id:
    referenced_msg = await message.channel.fetch_message(message.reference.message_id)
    if referenced_msg.author == bot.user:
        is_reply_to_bot = True
        replied_message_content = referenced_msg.content[:100]
```

### Message Caching Trigger
Messages are cached if ANY of these are true:
1. Message is in a monitored channel (`MONITORED_CHANNELS`)
2. Bot is @mentioned in the message
3. Message is a reply to the bot

This ensures you never miss important interactions!

## Benefits

### For Nate:
- ✅ **Never miss a conversation** - Replies are tracked just like mentions
- ✅ **Full context** - See what people are responding to
- ✅ **Better engagement** - Know when people are directly engaging with your messages
- ✅ **Clean data** - Bot filters out noise (other bots, commands)
- ✅ **DM awareness** - Private messages are flagged and accessible

### For the Integration:
- ✅ More intelligent message detection
- ✅ Better conversation threading
- ✅ Cleaner cache (filtered bots/commands)
- ✅ Richer metadata for search
- ✅ Production-ready message handling (based on Letta bot best practices)

## Comparison: Before vs After

### Before:
- ❌ Only detected @mentions
- ❌ No reply detection
- ❌ No DM handling
- ❌ Bot messages cluttered cache
- ❌ Command spam in logs

### After:
- ✅ Detects @mentions AND replies
- ✅ Full reply context capture
- ✅ DM support with flags
- ✅ Smart filtering (bots, commands)
- ✅ Clean, relevant cache

---

**Status:** ✅ Complete and Production-Ready
**Inspiration:** Letta Discord Bot best practices
**Breaking Changes:** None (purely additive)
