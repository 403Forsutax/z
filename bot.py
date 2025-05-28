#!/usr/bin/env python3
"""
Standalone Telegram Remote System Administration Bot
Complete implementation in a single file with all features
"""

import os
import sys
import subprocess
import requests
import json
import time
import logging
import tempfile
import shutil
import hashlib
import re
import threading
from pathlib import Path
from typing import Dict, Tuple, Optional, List

# Bot Configuration - Hardcoded Token
BOT_TOKEN = "7824283665:AAGHPi9KFrtDHlr0uEASyrcHkjK9H1vnPx8"
TELEGRAM_BASE_URL = "https://api.telegram.org/bot"

# Configuration Constants
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 50MB
COMMAND_TIMEOUT = 600  # 10 minutes
MAX_MESSAGE_LENGTH = 4000

# Emojis for better UX
EMOJIS = {
    'robot': '🤖', 'folder': '📁', 'file': '📄', 'upload': '📤',
    'download': '📥', 'success': '✅', 'error': '❌', 'warning': '⚠️',
    'info': 'ℹ️', 'rocket': '🚀', 'gear': '⚙️', 'terminal': '💻', 'package': '📦'
}

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f"{TELEGRAM_BASE_URL}{token}"
        self.logger = self._setup_logging()
        
        # User session management
        self.user_directories = {}
        self.running_processes = {}
        self.running_bots = {}
        
        # Create necessary directories
        self.scripts_dir = os.path.join(os.getcwd(), 'bot_scripts')
        self.temp_dir = tempfile.mkdtemp(prefix='telegram_bot_')
        self._ensure_directories()
        
        # Install dependencies on startup
        self._install_dependencies()
    
    def _setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('bot.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        return logging.getLogger(__name__)
    
    def _ensure_directories(self):
        """Ensure necessary directories exist"""
        try:
            os.makedirs(self.scripts_dir, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Failed to create directories: {e}")
    
    def _install_dependencies(self):
        """Install required dependencies"""
        try:
            self.logger.info("Installing required dependencies...")
            dependencies = ['requests', 'flask', 'psutil']
            
            for dep in dependencies:
                try:
                    subprocess.run([sys.executable, '-m', 'pip', 'install', dep], 
                                 check=True, capture_output=True)
                    self.logger.info(f"Successfully installed: {dep}")
                except Exception as e:
                    self.logger.warning(f"Failed to install {dep}: {e}")
                    
        except Exception as e:
            self.logger.error(f"Dependency installation failed: {e}")
    
    def escape_markdown(self, text: str) -> str:
        """Escape special characters for Telegram markdown formatting"""
        escape_chars = r'_*~`>#+-=|{}.!'
        return ''.join(f'\\{c}' if c in escape_chars else c for c in text)
    
    def send_message(self, chat_id: int, text: str, parse_mode: str = 'Markdown', 
                    reply_to_message_id: Optional[int] = None) -> Optional[dict]:
        """Send message to Telegram chat"""
        url = f"{self.base_url}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        
        if reply_to_message_id:
            data['reply_to_message_id'] = reply_to_message_id
        
        try:
            # Handle long messages
            if len(text) > MAX_MESSAGE_LENGTH:
                self._send_long_message(chat_id, text, parse_mode, reply_to_message_id)
                return None
            
            response = requests.post(url, json=data, timeout=30)
            return response.json()
            
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return None
    
    def _send_long_message(self, chat_id: int, text: str, parse_mode: str, 
                          reply_to_message_id: Optional[int] = None):
        """Send long message in chunks"""
        chunks = []
        current_chunk = ""
        lines = text.split('\n')
        
        for line in lines:
            if len(current_chunk + line + '\n') > MAX_MESSAGE_LENGTH:
                if current_chunk:
                    chunks.append(current_chunk.rstrip())
                current_chunk = line + '\n'
            else:
                current_chunk += line + '\n'
        
        if current_chunk:
            chunks.append(current_chunk.rstrip())
        
        for i, chunk in enumerate(chunks):
            reply_id = reply_to_message_id if i == 0 else None
            self.send_message(chat_id, chunk, parse_mode, reply_id)
            time.sleep(0.5)
    
    def send_document(self, chat_id: int, file_path: str, caption: Optional[str] = None) -> Optional[dict]:
        """Send document to Telegram chat"""
        url = f"{self.base_url}/sendDocument"
        
        try:
            with open(file_path, 'rb') as file:
                files = {'document': file}
                data = {'chat_id': chat_id}
                if caption:
                    data['caption'] = caption
                
                response = requests.post(url, data=data, files=files, timeout=60)
                return response.json()
                
        except Exception as e:
            self.logger.error(f"Error sending document: {e}")
            return None
    
    def download_file(self, file_id: str, download_path: str) -> tuple:
        """Download file from Telegram"""
        try:
            # Get file info
            url = f"{self.base_url}/getFile"
            response = requests.get(url, params={'file_id': file_id}, timeout=30)
            file_info = response.json()
            
            if not file_info.get('ok'):
                return False, "Failed to get file info"
            
            file_path = file_info['result']['file_path']
            download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            
            # Download the file
            file_response = requests.get(download_url, timeout=120)
            if file_response.status_code == 200:
                with open(download_path, 'wb') as f:
                    f.write(file_response.content)
                return True, "File downloaded successfully"
            else:
                return False, "Failed to download file"
                
        except Exception as e:
            return False, f"Error downloading file: {e}"
    
    def get_updates(self, offset: Optional[int] = None) -> Optional[dict]:
        """Get updates from Telegram"""
        url = f"{self.base_url}/getUpdates"
        params = {'timeout': 10}
        if offset:
            params['offset'] = offset
        
        try:
            response = requests.get(url, params=params, timeout=15)
            return response.json()
        except Exception as e:
            self.logger.error(f"Error getting updates: {e}")
            return None
    
    def get_user_directory(self, user_id: int) -> str:
        """Get current directory for user"""
        if user_id not in self.user_directories:
            self.user_directories[user_id] = os.path.expanduser("~")
        return self.user_directories[user_id]
    
    def set_user_directory(self, user_id: int, directory: str):
        """Set current directory for user"""
        self.user_directories[user_id] = directory
    
    def is_safe_command(self, command: str) -> tuple:
        """Check if command is safe to execute"""
        dangerous_commands = [
            'rm -rf /', 'dd if=', 'mkfs', 'fdisk', 'format',
            ':(){ :|:& };:', 'shutdown', 'reboot', 'halt'
        ]
        
        command_lower = command.lower().strip()
        for dangerous in dangerous_commands:
            if dangerous in command_lower:
                return False, f"Dangerous command detected: {dangerous}"
        return True, "Command is safe"
    
    def execute_command(self, command: str, current_dir: str, user_id: int) -> Tuple[bool, str]:
        """Execute shell command with safety checks"""
        try:
            # Safety check
            is_safe, safety_message = self.is_safe_command(command)
            if not is_safe:
                return False, f"{EMOJIS['error']} {safety_message}"
            
            self.logger.info(f"Executing command: {command} in {current_dir}")
            
            # Handle background processes
            if command.endswith(' &'):
                return self._execute_background_command(command, current_dir, user_id)
            
            # Execute command
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                cwd=current_dir, timeout=COMMAND_TIMEOUT
            )
            
            # Combine stdout and stderr
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                if output:
                    output += "\n"
                output += result.stderr
            
            output = output.strip()
            
            # Provide feedback for commands with no output
            if not output:
                if result.returncode == 0:
                    output = f"Command executed successfully: {command}"
                else:
                    output = f"Command failed with exit code {result.returncode}: {command}"
            
            return True, output
            
        except subprocess.TimeoutExpired:
            return False, f"{EMOJIS['error']} Command timed out after {COMMAND_TIMEOUT} seconds"
        except Exception as e:
            return False, f"{EMOJIS['error']} Command execution failed: {str(e)}"
    
    def _execute_background_command(self, command: str, current_dir: str, user_id: int) -> Tuple[bool, str]:
        """Execute command in background"""
        try:
            clean_command = command.rstrip(' &').strip()
            
            process = subprocess.Popen(
                clean_command, shell=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, cwd=current_dir
            )
            
            process_id = f"{user_id}_{int(time.time())}"
            self.running_processes[process_id] = {
                'process': process, 'command': clean_command, 'started': time.time()
            }
            
            return True, f"{EMOJIS['rocket']} Background process started: {clean_command}\nProcess ID: {process_id}"
            
        except Exception as e:
            return False, f"{EMOJIS['error']} Failed to start background process: {str(e)}"
    
    def handle_cd_command(self, chat_id: int, user_id: int, path: str):
        """Handle directory change command"""
        current_dir = self.get_user_directory(user_id)
        
        # Handle special paths
        if path == "~":
            new_dir = os.path.expanduser("~")
        elif path == "..":
            new_dir = os.path.dirname(current_dir)
        elif path.startswith("/"):
            new_dir = path
        else:
            new_dir = os.path.abspath(os.path.join(current_dir, path))
        
        # Check if directory exists
        if os.path.isdir(new_dir):
            self.set_user_directory(user_id, new_dir)
            self.send_message(chat_id, f"```\nroot@telegrambot:{new_dir}#\n```")
        else:
            self.send_message(chat_id, f"bash: cd: {self.escape_markdown(path)}: No such file or directory")
    
    def handle_file_upload(self, chat_id: int, user_id: int, file_info: dict, message_id: int):
        """Handle file uploads from users"""
        current_dir = self.get_user_directory(user_id)
        
        file_id = file_info['file_id']
        file_name = file_info.get('file_name', f"file_{int(time.time())}")
        file_size = file_info.get('file_size', 0)
        
        # Check file size limit
        if file_size > MAX_UPLOAD_SIZE:
            self.send_message(chat_id, f"{EMOJIS['error']} File too large! Maximum size is 20MB.", 
                            reply_to_message_id=message_id)
            return
        
        # Download file to current directory
        download_path = os.path.join(current_dir, file_name)
        success, message = self.download_file(file_id, download_path)
        
        if success:
            file_info_text = (
                f"{EMOJIS['upload']} File uploaded successfully!\n\n"
                f"📝 *Name:* `{file_name}`\n"
                f"📊 *Size:* `{file_size} bytes`\n"
                f"📂 *Location:* `{download_path}`"
            )
            self.send_message(chat_id, file_info_text, reply_to_message_id=message_id)
        else:
            self.send_message(chat_id, f"{EMOJIS['error']} Upload failed: {message}", 
                            reply_to_message_id=message_id)
    
    def handle_download_command(self, chat_id: int, user_id: int, file_path: str):
        """Handle file download command"""
        current_dir = self.get_user_directory(user_id)
        
        # Handle relative paths
        if not file_path.startswith('/'):
            full_path = os.path.join(current_dir, file_path)
        else:
            full_path = file_path
        
        # Check if file exists
        if not os.path.isfile(full_path):
            self.send_message(chat_id, f"{EMOJIS['error']} File not found: `{self.escape_markdown(file_path)}`")
            return
        
        # Check file size
        file_size = os.path.getsize(full_path)
        if file_size > MAX_DOWNLOAD_SIZE:
            size_mb = file_size / (1024 * 1024)
            self.send_message(chat_id, f"{EMOJIS['error']} File too large! Size: {size_mb:.1f}MB (max 50MB)")
            return
        
        # Send file
        file_name = os.path.basename(full_path)
        caption = f"{EMOJIS['download']} Downloaded: `{file_name}`\n📊 Size: `{file_size} bytes`"
        
        result = self.send_document(chat_id, full_path, caption)
        if not result or not result.get('ok'):
            self.send_message(chat_id, f"{EMOJIS['error']} Failed to send file: `{self.escape_markdown(file_path)}`")
    
    def add_bot_script(self, script_content: str, script_name: str = None) -> Tuple[bool, str]:
        """Add a new bot script"""
        try:
            if not script_name:
                script_hash = hashlib.md5(script_content.encode()).hexdigest()[:8]
                script_name = f"bot_script_{script_hash}.py"
            elif not script_name.endswith('.py'):
                script_name += '.py'
            
            script_path = os.path.join(self.scripts_dir, script_name)
            
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            os.chmod(script_path, 0o755)
            self.logger.info(f"Bot script added: {script_path}")
            
            return True, f"{EMOJIS['success']} Bot script added: `{script_name}`"
            
        except Exception as e:
            return False, f"{EMOJIS['error']} Failed to add bot script: {str(e)}"
    
    def run_bot_script(self, script_name: str, bot_token: str = None) -> Tuple[bool, str]:
        """Run a bot script"""
        try:
            script_path = os.path.join(self.scripts_dir, script_name)
            
            if not os.path.isfile(script_path):
                return False, f"{EMOJIS['error']} Script not found: `{script_name}`"
            
            # Prepare environment
            env = os.environ.copy()
            if bot_token:
                env['BOT_TOKEN'] = bot_token
            
            # Start the script
            process = subprocess.Popen(
                ['python3', script_path], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, env=env, cwd=os.path.dirname(script_path)
            )
            
            bot_id = f"bot_{int(time.time())}"
            self.running_bots[bot_id] = {
                'process': process, 'script_name': script_name,
                'script_path': script_path, 'started': time.time(), 'bot_token': bot_token
            }
            
            self.logger.info(f"Bot script started: {script_name} (ID: {bot_id})")
            
            return True, f"{EMOJIS['rocket']} Bot script started!\n🤖 *Script:* `{script_name}`\n🆔 *Bot ID:* `{bot_id}`"
            
        except Exception as e:
            return False, f"{EMOJIS['error']} Failed to run bot script: {str(e)}"
    
    def handle_addbot_command(self, chat_id: int, user_id: int, script_content: str):
        """Handle add bot command"""
        if not script_content.strip():
            self.send_message(chat_id, f"{EMOJIS['error']} Please provide bot script content after /addbot")
            return
        
        # Add the script
        success, message = self.add_bot_script(script_content)
        self.send_message(chat_id, message)
        
        if success:
            # Extract script name and run it
            script_match = re.search(r'bot_script_\w+\.py', message)
            if script_match:
                script_name = script_match.group()
                success, run_message = self.run_bot_script(script_name, self.token)
                self.send_message(chat_id, run_message)
    
    def list_bots(self) -> str:
        """List all running bots"""
        if not self.running_bots:
            return f"{EMOJIS['info']} No bots currently running"
        
        bot_list = [f"{EMOJIS['robot']} *Running Bots:*\n"]
        
        for bot_id, info in self.running_bots.items():
            runtime = int(time.time() - info['started'])
            status = "Running" if info['process'].poll() is None else "Stopped"
            
            bot_list.append(
                f"🤖 *Bot ID:* `{bot_id}`\n"
                f"📝 *Script:* `{info['script_name']}`\n"
                f"⏱️ *Runtime:* {runtime}s\n"
                f"📊 *Status:* {status}\n"
            )
        
        return '\n'.join(bot_list)
    
    def stop_bot(self, bot_id: str) -> Tuple[bool, str]:
        """Stop a running bot"""
        try:
            if bot_id not in self.running_bots:
                return False, f"{EMOJIS['error']} Bot ID not found: `{bot_id}`"
            
            bot_info = self.running_bots[bot_id]
            process = bot_info['process']
            
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            
            del self.running_bots[bot_id]
            return True, f"{EMOJIS['success']} Bot stopped: `{bot_info['script_name']}`"
            
        except Exception as e:
            return False, f"{EMOJIS['error']} Failed to stop bot: {str(e)}"
    
    def get_system_info(self) -> dict:
        """Get system information"""
        info = {}
        
        try:
            # OS information
            result = subprocess.run(['uname', '-a'], capture_output=True, text=True)
            if result.returncode == 0:
                info['System'] = result.stdout.strip()
            
            # CPU information
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'model name' in line:
                            info['CPU'] = line.split(':')[1].strip()
                            break
            except:
                pass
            
            # Memory information
            try:
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if 'MemTotal' in line:
                            mem_kb = int(line.split()[1])
                            info['Memory'] = f"{mem_kb // 1024} MB"
                            break
            except:
                pass
            
        except Exception as e:
            self.logger.error(f"Failed to get system info: {e}")
        
        return info
    
    def install_package(self, package_name: str) -> Tuple[bool, str]:
        """Install package"""
        try:
            # Try pip first
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', package_name],
                capture_output=True, text=True, timeout=300
            )
            
            if result.returncode == 0:
                return True, f"{EMOJIS['success']} Package installed successfully: {package_name}"
            else:
                # Try apt if pip fails
                try:
                    apt_result = subprocess.run(
                        ['sudo', 'apt', 'install', '-y', package_name],
                        capture_output=True, text=True, timeout=300
                    )
                    if apt_result.returncode == 0:
                        return True, f"{EMOJIS['success']} System package installed: {package_name}"
                except:
                    pass
                
                error_output = result.stderr or result.stdout or "Unknown error"
                return False, f"{EMOJIS['error']} Package installation failed: {error_output}"
                
        except subprocess.TimeoutExpired:
            return False, f"{EMOJIS['error']} Package installation timed out"
        except Exception as e:
            return False, f"{EMOJIS['error']} Package installation failed: {str(e)}"
    
    def handle_start_command(self, chat_id: int):
        """Handle /start command"""
        msg = (
            f"{EMOJIS['robot']} *Overpower Bot by @Kecee_Pyrite* is now active!\n\n"
            f"{EMOJIS['folder']} Current directory: /home/runner\n"
            f"{EMOJIS['rocket']} *Getting Started:*\n"
            "• `ls` — list files\n"
            "• Type any shell command to execute\n\n"
            f"{EMOJIS['terminal']} *Available Commands:*\n"
            "• `/start` — show this message\n"
            "• `/help` — show help information\n"
            "• `/download <file_path>` — download file\n"
            "• `/upload <path>` — set upload directory\n"
            "• `/addbot <script>` — add and run bot script\n"
            "• `/listbots` — list running bots\n"
            "• `/stopbot <id>` — stop running bot\n"
            "• `/install <package>` — install package\n"
            "• `/sysinfo` — show system information\n"
            "• `pwd` — show current directory\n"
            "• `cd <path>` — change directory\n\n"
            f"{EMOJIS['upload']} *File Operations:*\n"
            "• Send any file to upload to current directory\n"
            "• Use `/download filename` to download files\n\n"
            f"{EMOJIS['warning']} *Note:* Commands timeout after 10 minutes\n"
            f"{EMOJIS['info']} *Limits:* Upload max 20MB, Download max 50MB"
        )
        self.send_message(chat_id, msg)
    
    def handle_help_command(self, chat_id: int):
        """Handle /help command"""
        help_msg = (
            f"{EMOJIS['info']} *Bot Help by @Kecee_Pyrite*\n\n"
            "Execute shell commands by sending them as messages.\n\n"
            "*Navigation:*\n"
            "• `cd <dir>`, `cd ~`, `cd ..` — change directory\n"
            "• `pwd` — show current directory\n"
            "• `ls` — list files and directories\n\n"
            "*File Operations:*\n"
            "• `cat <file>` — display file contents\n"
            "• `mkdir <dir>` — create directory\n"
            "• `rm <file>` — remove file\n"
            "• `cp <src> <dst>` — copy file\n"
            "• `mv <src> <dst>` — move/rename file\n\n"
            "*File Transfer:*\n"
            "• Send any file to upload to current directory\n"
            "• `/download <file_path>` — download file from server\n"
            "• `/upload <path>` — set upload directory\n\n"
            "*Bot Management:*\n"
            "• `/addbot <script_content>` — add and run Python bot script\n"
            "• `/listbots` — list all running bots\n"
            "• `/stopbot <bot_id>` — stop a running bot\n\n"
            "*Package Management:*\n"
            "• `/install <package>` — install system/Python package\n"
            "• `git clone <url>` — clone git repository\n\n"
            "*System Information:*\n"
            "• `/sysinfo` — show detailed system information\n"
            "• `ps aux` — show running processes\n"
            "• `df -h` — show disk usage\n"
            "• `free -h` — show memory usage\n\n"
            f"{EMOJIS['warning']} Interactive commands may not work properly"
        )
        self.send_message(chat_id, help_msg)
    
    def process_message(self, message: dict):
        """Process incoming message"""
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        message_id = message['message_id']
        
        # Handle file uploads
        if 'document' in message:
            self.handle_file_upload(chat_id, user_id, message['document'], message_id)
            return
        
        # Handle text messages
        if 'text' not in message:
            return
            
        text = message['text'].strip()
        
        # Handle commands
        if text.startswith('/start'):
            self.handle_start_command(chat_id)
        elif text.startswith('/help'):
            self.handle_help_command(chat_id)
        elif text.startswith('/download '):
            file_path = text[10:].strip()
            self.handle_download_command(chat_id, user_id, file_path)
        elif text.startswith('/upload'):
            path = text[7:].strip() if len(text) > 7 else ""
            current_dir = self.get_user_directory(user_id)
            if path:
                if not path.startswith('/'):
                    full_path = os.path.join(current_dir, path)
                else:
                    full_path = path
                if os.path.isdir(full_path):
                    self.set_user_directory(user_id, full_path)
                    self.send_message(chat_id, f"{EMOJIS['success']} Upload directory set to: `{full_path}`")
                else:
                    self.send_message(chat_id, f"{EMOJIS['error']} Directory not found: `{path}`")
            else:
                self.send_message(chat_id, f"{EMOJIS['folder']} Current upload directory: `{current_dir}`")
        elif text.startswith('/addbot '):
            script_content = text[8:].strip()
            self.handle_addbot_command(chat_id, user_id, script_content)
        elif text.startswith('/listbots'):
            bot_list = self.list_bots()
            self.send_message(chat_id, bot_list)
        elif text.startswith('/stopbot '):
            bot_id = text[9:].strip()
            success, message_text = self.stop_bot(bot_id)
            self.send_message(chat_id, message_text)
        elif text.startswith('/install '):
            package_name = text[9:].strip()
            success, message_text = self.install_package(package_name)
            self.send_message(chat_id, message_text)
        elif text.startswith('/sysinfo'):
            info = self.get_system_info()
            if info:
                formatted_info = f"{EMOJIS['terminal']} *System Information:*\n\n"
                for key, value in info.items():
                    formatted_info += f"• *{key}:* `{value}`\n"
                self.send_message(chat_id, formatted_info)
            else:
                self.send_message(chat_id, f"{EMOJIS['error']} Failed to get system information")
        elif text.startswith('cd '):
            path = text[3:].strip()
            self.handle_cd_command(chat_id, user_id, path)
        elif text == 'pwd':
            current_dir = self.get_user_directory(user_id)
            self.send_message(chat_id, f"```\n{current_dir}\n```")
        else:
            # Handle regular shell commands
            current_dir = self.get_user_directory(user_id)
            success, output = self.execute_command(text, current_dir, user_id)
            
            if success:
                escaped_output = self.escape_markdown(output)
                self.send_message(chat_id, f"```\n{escaped_output}\n```")
            else:
                self.send_message(chat_id, output)
    
    def run(self):
        """Main bot loop"""
        self.logger.info("🤖 Telegram Remote System Administration Bot is running...")
        self.logger.info(f"📁 Working directory: {os.getcwd()}")
        self.logger.info("💻 Send /start to begin")
        
        offset = None
        
        while True:
            try:
                # Get updates from Telegram
                updates = self.get_updates(offset)
                
                if not updates or not updates.get('ok'):
                    time.sleep(1)
                    continue
                
                for update in updates.get('result', []):
                    offset = update['update_id'] + 1
                    
                    if 'message' not in update:
                        continue
                    
                    message = update['message']
                    self.process_message(message)
                    
            except KeyboardInterrupt:
                self.logger.info("Bot stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(5)

def main():
    """Main function to start the bot"""
    if not BOT_TOKEN:
        print("Error: Bot token not provided")
        sys.exit(1)
    
    bot = TelegramBot(BOT_TOKEN)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Bot crashed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
