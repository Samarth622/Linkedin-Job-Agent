import os
import requests
import pandas as pd
import time
import json
import smtplib
from datetime import datetime
from email.message import EmailMessage
from dotenv import load_dotenv

import discord
from discord.ext import commands
from discord import app_commands, ui

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

# Ensure data directory exists and get its absolute path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

class UserConfig:
    """Store user-specific configuration"""
    def __init__(self):
        self.users = {}
    
    def set_config(self, user_id, config):
        self.users[user_id] = config
    
    def get_config(self, user_id):
        return self.users.get(user_id)

class CookieUploadModal(ui.Modal, title='Upload LinkedIn Cookies'):
    cookies_json = ui.TextInput(
        label='LinkedIn Cookies (JSON format)',
        placeholder='Paste your exported LinkedIn cookies JSON here...',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000
    )

    def __init__(self, user_id):
        super().__init__(timeout=300.0)
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        cookies_file = os.path.join(DATA_DIR, f'linkedin_cookies_{self.user_id}.json')
        try:
            cookies = json.loads(self.cookies_json.value)
            with open(cookies_file, 'w') as f:
                json.dump(cookies, f)
            await interaction.response.send_message(
                f"✅ Cookies saved at `{cookies_file}`", ephemeral=True
            )
        except json.JSONDecodeError:
            await interaction.response.send_message(
                "❌ Invalid JSON. Please paste valid LinkedIn cookies JSON.", ephemeral=True
            )

class JobConfigModal(ui.Modal, title='LinkedIn Job Agent Setup'):
    email_receiver = ui.TextInput(label='Your Email Address', required=True, max_length=100)
    roles = ui.TextInput(label='Job Roles (comma separated)', style=discord.TextStyle.paragraph, required=True)
    experience_levels = ui.TextInput(label='Experience Levels (comma sep)', default='1,2', required=True)
    locations = ui.TextInput(label='Locations (comma separated)', style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cookies_file = os.path.join(DATA_DIR, f'linkedin_cookies_{interaction.user.id}.json')
        if not os.path.exists(cookies_file):
            return await interaction.response.send_message(
                "⚠️ Please run `/cookies` first to upload your LinkedIn cookies.", ephemeral=True
            )
        config = {
            'email_receiver': self.email_receiver.value,
            'roles': [r.strip() for r in self.roles.value.split(',')],
            'experience_levels': [int(x) for x in self.experience_levels.value.split(',')],
            'locations': [l.strip() for l in self.locations.value.split(',')],
            'cookies_file': cookies_file,
            'configured_at': datetime.now().isoformat()
        }
        bot.user_configs.set_config(interaction.user.id, config)
        await interaction.response.send_message(
            "✅ Configuration saved. Run `/start` to begin scraping.", ephemeral=True
        )

class LinkedInJobAgent:
    def __init__(self, config):
        self.config = config
        # Files under data/
        sanitized = config['email_receiver'].replace('@','_at_')
        self.applied_file = os.path.join(DATA_DIR, f'applied_{sanitized}.txt')
        self.scraped_file = os.path.join(DATA_DIR, f'scraped_{sanitized}.txt')
        self.applied = self._load(self.applied_file)
        self.scraped = self._load(self.scraped_file)

    def _load(self, path):
        if os.path.exists(path):
            with open(path,'r') as f:
                return set(map(str.strip,f.readlines()))
        return set()

    def _save(self, path, items):
        with open(path,'a') as f:
            for i in items:
                if i not in self._load(path):
                    f.write(i+'\n')

    def get_links(self, scrolls=10):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.get('https://www.linkedin.com')
        with open(self.config['cookies_file'],'r') as cf:
            cookies = json.load(cf)
        for c in cookies:
            c.pop('sameSite',None)
            c.pop('hostOnly',None)
            try: driver.add_cookie(c)
            except: pass
        driver.refresh()
        time.sleep(2)

        links=[]
        for role in self.config['roles']:
            for exp in self.config['experience_levels']:
                url = (
                    'https://www.linkedin.com/jobs/search/?'
                    f'keywords={role.replace(" ","%20")}&location=India&f_E={exp}'
                )
                driver.get(url)
                time.sleep(2)
                for _ in range(scrolls):
                    driver.find_element(By.TAG_NAME,'body').send_keys(Keys.PAGE_DOWN)
                    time.sleep(0.5)
                cards = driver.find_elements(By.CSS_SELECTOR,'div.job-card-container--clickable')
                for card in cards:
                    try:
                        link=card.find_element(By.TAG_NAME,'a').get_attribute('href')
                        if link and 'linkedin.com/jobs/view/' in link:
                            links.append(link)
                    except: pass
        driver.quit()

        unique = list(set(links))
        new = [l for l in unique if l not in self.applied and l not in self.scraped]
        self._save(self.scraped_file,new)
        return new

    def send_email(self, csv_path):
        msg=EmailMessage()
        msg['Subject']='New LinkedIn Jobs'
        msg['From']=os.getenv('EMAIL_SENDER')
        msg['To']=self.config['email_receiver']
        msg.set_content('Attached are new job links.')
        with open(csv_path,'rb') as f:
            msg.add_attachment(f.read(),maintype='application',subtype='octet-stream',filename=os.path.basename(csv_path))
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com',465) as s:
                s.login(os.getenv('EMAIL_SENDER'),os.getenv('EMAIL_PASSWORD'))
                s.send_message(msg)
            return True
        except Exception as e:
            print('Email error:',e)
            return False

bot_intents=discord.Intents.default()
bot_intents.message_content=True
bot=commands.Bot(command_prefix='/',intents=bot_intents)
bot.user_configs=UserConfig()

@bot.event
async def on_ready():
    print(f'{bot.user} online')
    await bot.tree.sync()

@bot.tree.command(name='cookies',description='Upload LinkedIn cookies')
async def cmd_cookies(interaction):
    await interaction.response.send_modal(CookieUploadModal(interaction.user.id))

@bot.tree.command(name='setup',description='Configure job agent')
async def cmd_setup(interaction):
    await interaction.response.send_modal(JobConfigModal())

@bot.tree.command(name='start',description='Run scraper')
async def cmd_start(interaction):
    config=bot.user_configs.get_config(interaction.user.id)
    if not config:
        return await interaction.response.send_message('Run `/cookies` then `/setup` first',ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    agent=LinkedInJobAgent(config)
    links=agent.get_links()
    if not links:
        return await interaction.followup.send('No new jobs found',ephemeral=True)
    csv_name=f'jobs_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    csv_path=os.path.join(DATA_DIR,csv_name)
    pd.DataFrame({'url':links}).to_csv(csv_path,index=False)
    sent=agent.send_email(csv_path)
    await interaction.followup.send(f'Found {len(links)} jobs, email sent: {sent}',ephemeral=True)
    print('Saved CSV at',csv_path)

bot.run(os.getenv('DISCORD_BOT_TOKEN'))
