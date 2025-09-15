import os
import asyncio
import json
import requests
import pandas as pd
import time
import smtplib
from datetime import datetime
from email.message import EmailMessage
from dotenv import load_dotenv

import discord
from discord.ext import commands, tasks
from discord import app_commands, ui

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

class UserConfig:
    """Store user-specific configuration"""
    def __init__(self):
        self.users = {}
    
    def set_config(self, user_id, config):
        self.users[user_id] = config
    
    def get_config(self, user_id):
        return self.users.get(user_id)

# Cookie upload modal
class CookieUploadModal(ui.Modal, title='Upload LinkedIn Cookies'):
    def __init__(self, user_id):
        super().__init__(timeout=300.0)
        self.user_id = user_id

    cookies_json = ui.TextInput(
        label='LinkedIn Cookies (JSON format)',
        placeholder='Paste your exported LinkedIn cookies JSON here...',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate JSON format
            cookies = json.loads(self.cookies_json.value)
            
            # Save cookies to user-specific file
            cookies_file = f'linkedin_cookies_{self.user_id}.json'
            with open(cookies_file, 'w') as f:
                json.dump(cookies, f)
            
            embed = discord.Embed(
                title="✅ Cookies Saved!",
                description="Your LinkedIn cookies have been saved successfully.",
                color=0x00ff00
            )
            embed.add_field(name="Next Step", value="Now run `/setup` to configure your job preferences!", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except json.JSONDecodeError:
            await interaction.response.send_message("❌ Invalid JSON format. Please check your cookies and try again.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error saving cookies: {str(e)}", ephemeral=True)

# Configuration modal for user setup
class JobConfigModal(ui.Modal, title='LinkedIn Job Agent Setup'):
    def __init__(self):
        super().__init__(timeout=300.0)

    # Input fields for user configuration
    email_receiver = ui.TextInput(
        label='Your Email Address',
        placeholder='Enter your email to receive job links...',
        required=True,
        max_length=100
    )
    
    roles = ui.TextInput(
        label='Job Roles (comma separated)',
        placeholder='Software Developer, Python Developer, Backend Developer',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )
    
    experience_levels = ui.TextInput(
        label='Experience Levels',
        placeholder='1 for Intern, 2 for Entry Level, 3 for Associate (comma separated)',
        default='1,2',
        required=True,
        max_length=10
    )
    
    locations = ui.TextInput(
        label='Locations (comma separated)', 
        placeholder='Mumbai, Bangalore, Remote, India',
        default='Remote, India, Mumbai, Bangalore',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Check if cookies exist first
        cookies_file = f'linkedin_cookies_{interaction.user.id}.json'
        if not os.path.exists(cookies_file):
            embed = discord.Embed(
                title="⚠️ LinkedIn Cookies Required",
                description="Please run `/cookies` first to upload your LinkedIn cookies.",
                color=0xff9900
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Parse and validate user input
        try:
            roles_list = [role.strip() for role in self.roles.value.split(',')]
            exp_levels = [int(x.strip()) for x in self.experience_levels.value.split(',')]
            locations_list = [loc.strip() for loc in self.locations.value.split(',')]
            
            user_config = {
                'email_receiver': self.email_receiver.value,
                'roles': roles_list,
                'experience_levels': exp_levels,
                'locations': locations_list,
                'configured_at': datetime.now().isoformat(),
                'cookies_file': cookies_file
            }
            
            # Store user configuration
            bot.user_configs.set_config(interaction.user.id, user_config)
            
            embed = discord.Embed(
                title="✅ Configuration Saved!",
                description="Your job agent has been configured successfully.",
                color=0x00ff00
            )
            embed.add_field(name="Email", value=self.email_receiver.value, inline=False)
            embed.add_field(name="Roles", value=", ".join(roles_list[:3]) + ("..." if len(roles_list) > 3 else ""), inline=False)
            embed.add_field(name="Experience Levels", value=", ".join(map(str, exp_levels)), inline=True)
            embed.add_field(name="Next Steps", value="Use `/start` to begin job scraping!", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Configuration error: {str(e)}", ephemeral=True)

class LinkedInJobAgent:
    """Core job scraping functionality"""
    def __init__(self, config):
        self.config = config
        self.applied_jobs_file = f'applied_jobs_{config["email_receiver"].replace("@", "_at_")}.txt'
        self.scraped_jobs_file = f'scraped_jobs_{config["email_receiver"].replace("@", "_at_")}.txt'
        self.applied_jobs = self.load_applied_jobs()
        self.scraped_jobs = self.load_scraped_jobs()

    def load_applied_jobs(self):
        if os.path.exists(self.applied_jobs_file):
            with open(self.applied_jobs_file, 'r') as f:
                return set(line.strip() for line in f.readlines())
        return set()

    def load_scraped_jobs(self):
        if os.path.exists(self.scraped_jobs_file):
            with open(self.scraped_jobs_file, 'r') as f:
                return set(line.strip() for line in f.readlines())
        return set()

    def save_scraped_jobs(self, job_urls):
        with open(self.scraped_jobs_file, 'a') as f:
            for url in job_urls:
                if url not in self.scraped_jobs:
                    f.write(f"{url}\n")
                    self.scraped_jobs.add(url)

    def get_links(self, scrolls=10):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Use user-specific cookies file
        cookies_file = self.config['cookies_file']
        driver.get('https://www.linkedin.com')
        
        if os.path.exists(cookies_file):
            cookies = json.load(open(cookies_file, 'r'))
            for cookie in cookies:
                cookie.pop('sameSite', None)
                cookie.pop('hostOnly', None)
                try:
                    driver.add_cookie(cookie)
                except:
                    continue
        driver.refresh()
        time.sleep(3)
        
        all_links = []
        for keyword in self.config['roles']:
            for exp in self.config['experience_levels']:
                url = (
                    f'https://www.linkedin.com/jobs/search/?'
                    f'keywords={keyword.replace(" ", "%20")}&location=India&f_E={exp}'
                )
                driver.get(url)
                time.sleep(3)
                
                for _ in range(scrolls):
                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_DOWN)
                    time.sleep(1)
                
                cards = driver.find_elements(By.CSS_SELECTOR, 'div.job-card-container--clickable')
                
                for card in cards:
                    try:
                        a_tag = card.find_element(By.TAG_NAME, 'a')
                        link = a_tag.get_attribute('href')
                        if link and link.startswith('https://www.linkedin.com/jobs/view/'):
                            all_links.append(link)
                    except Exception:
                        continue
        
        driver.quit()
        
        # Filter for new jobs only
        unique_links = list(set(all_links))
        new_jobs = [link for link in unique_links if link not in self.applied_jobs and link not in self.scraped_jobs]
        
        if new_jobs:
            self.save_scraped_jobs(new_jobs)
            
        return new_jobs

    def send_email_with_attachment(self, filename):
        try:
            msg = EmailMessage()
            msg['Subject'] = 'New LinkedIn Job Links (Filtered)'
            msg['From'] = os.getenv('EMAIL_SENDER')
            msg['To'] = self.config['email_receiver']
            msg.set_content('Find attached new LinkedIn job links CSV.')
            
            with open(filename, 'rb') as f:
                msg.add_attachment(f.read(), maintype='application', subtype='octet-stream', filename=filename)
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(os.getenv('EMAIL_SENDER'), os.getenv('EMAIL_PASSWORD'))
                smtp.send_message(msg)
            return True
        except Exception as e:
            print(f"Email error: {e}")
            return False

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
bot.user_configs = UserConfig()

@bot.event
async def on_ready():
    print(f'{bot.user} is ready and online!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="cookies", description="Upload your LinkedIn cookies")
async def cookies(interaction: discord.Interaction):
    """Upload LinkedIn cookies"""
    await interaction.response.send_modal(CookieUploadModal(interaction.user.id))

@bot.tree.command(name="setup", description="Configure your LinkedIn job agent")
async def setup(interaction: discord.Interaction):
    """Setup command to configure user preferences"""
    await interaction.response.send_modal(JobConfigModal())

@bot.tree.command(name="start", description="Start job scraping with your configuration")
async def start(interaction: discord.Interaction):
    """Start the job scraping process"""
    config = bot.user_configs.get_config(interaction.user.id)
    
    if not config:
        embed = discord.Embed(
            title="⚠️ Configuration Required",
            description="Please run `/cookies` first, then `/setup` to configure your job preferences.",
            color=0xff9900
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    try:
        # Create job agent with user config
        agent = LinkedInJobAgent(config)
        
        # Start scraping
        links = agent.get_links()
        
        if not links:
            embed = discord.Embed(
                title="📭 No New Jobs Found",
                description="No new job links were found (all were duplicates or already applied).",
                color=0x808080
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Save and email results
        csv_name = f"new_linkedin_jobs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        pd.DataFrame({"url": links}).to_csv(csv_name, index=False)
        
        email_sent = agent.send_email_with_attachment(csv_name)
        
        # Create results embed
        embed = discord.Embed(
            title="🎯 Job Scraping Complete!",
            description=f"Found {len(links)} new job links",
            color=0x00ff00
        )
        embed.add_field(name="Email Status", 
                        value="✅ Sent" if email_sent else "❌ Failed", 
                        inline=True)
        embed.add_field(name="CSV File", value=csv_name, inline=True)
        embed.add_field(name="Roles Searched", 
                        value=", ".join(config['roles'][:3]) + ("..." if len(config['roles']) > 3 else ""), 
                        inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Clean up CSV file
        if os.path.exists(csv_name):
            os.remove(csv_name)
            
    except Exception as e:
        await interaction.followup.send(f"❌ Error during job scraping: {str(e)}", ephemeral=True)

@bot.tree.command(name="status", description="Check your configuration and stats")
async def status(interaction: discord.Interaction):
    """Show user's current configuration and statistics"""
    config = bot.user_configs.get_config(interaction.user.id)
    
    if not config:
        embed = discord.Embed(
            title="⚠️ Not Configured",
            description="Run `/cookies` first, then `/setup` to configure your job agent.",
            color=0xff9900
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Check if cookies file exists
    cookies_status = "✅ Present" if os.path.exists(config['cookies_file']) else "❌ Missing"
    
    embed = discord.Embed(
        title="📊 Your Job Agent Status",
        color=0x0099ff
    )
    embed.add_field(name="LinkedIn Cookies", value=cookies_status, inline=True)
    embed.add_field(name="Email", value=config['email_receiver'], inline=False)
    embed.add_field(name="Roles", value=", ".join(config['roles']), inline=False)
    embed.add_field(name="Experience Levels", value=", ".join(map(str, config['experience_levels'])), inline=True)
    embed.add_field(name="Locations", value=", ".join(config['locations']), inline=False)
    embed.add_field(name="Configured", value=config.get('configured_at', 'Unknown'), inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="help", description="Show available commands")
async def help_command(interaction: discord.Interaction):
    """Show help information"""
    embed = discord.Embed(
        title="🤖 LinkedIn Job Agent Commands",
        description="Configure and run your personal LinkedIn job scraper",
        color=0x0052cc
    )
    embed.add_field(
        name="/cookies", 
        value="Upload your exported LinkedIn cookies (JSON format)", 
        inline=False
    )
    embed.add_field(
        name="/setup", 
        value="Configure your job preferences (roles, experience, email)", 
        inline=False
    )
    embed.add_field(
        name="/start", 
        value="Start job scraping and send results to your email", 
        inline=False
    )
    embed.add_field(
        name="/status", 
        value="View your current configuration", 
        inline=False
    )
    embed.add_field(
        name="Setup Process", 
        value="1. Export LinkedIn cookies from browser\n2. Run `/cookies` and paste JSON\n3. Run `/setup` to configure preferences\n4. Run `/start` to scrape jobs", 
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Run the bot
if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_BOT_TOKEN'))
