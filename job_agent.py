import os
import json
import time
import pandas as pd
import smtplib
from datetime import datetime
from email.message import EmailMessage
from dotenv import load_dotenv

import discord
from discord.ext import commands
from discord import ui

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

class UserConfig:
    def __init__(self):
        self.users = {}
    def set_config(self, user_id, cfg):
        self.users[user_id] = cfg
    def get_config(self, user_id):
        return self.users.get(user_id)

class CookieUploadModal(ui.Modal, title="Upload LinkedIn Cookies"):
    cookies_json = ui.TextInput(
        label="LinkedIn Cookies (JSON)",
        placeholder="Paste your LinkedIn cookies JSON",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000
    )
    def __init__(self, user_id):
        super().__init__(timeout=300.0)
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        path = os.path.join(DATA_DIR, f"linkedin_cookies_{self.user_id}.json")
        try:
            cookies = json.loads(self.cookies_json.value)
            with open(path, "w") as f:
                json.dump(cookies, f)
            await interaction.response.send_message(f"✅ Saved cookies at `{path}`", ephemeral=True)
        except json.JSONDecodeError:
            await interaction.response.send_message("❌ Invalid JSON.", ephemeral=True)

class JobConfigModal(ui.Modal, title="Setup Job Agent"):
    email_receiver = ui.TextInput(label="Email", required=True, max_length=100)
    roles          = ui.TextInput(label="Roles (comma sep)", style=discord.TextStyle.paragraph, required=True)
    locations      = ui.TextInput(label="Locations (comma sep)", style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        cookies_file = os.path.join(DATA_DIR, f"linkedin_cookies_{interaction.user.id}.json")
        if not os.path.exists(cookies_file):
            return await interaction.response.send_message("⚠️ Run `/cookies` first.", ephemeral=True)
        cfg = {
            "email_receiver": self.email_receiver.value,
            "roles": [r.strip() for r in self.roles.value.split(",")],
            "locations": [l.strip() for l in self.locations.value.split(",")],
            "cookies_file": cookies_file,
            "configured_at": datetime.now().isoformat()
        }
        bot.user_configs.set_config(interaction.user.id, cfg)
        await interaction.response.send_message(
            "Select your years of experience:",
            view=ExperienceSelect(interaction.user.id),
            ephemeral=True
        )

class ExperienceDropdown(ui.Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = [
            discord.SelectOption(label=f"{i} year{'s' if i != 1 else ''}", value=str(i))
            for i in range(0, 11)
        ]
        super().__init__(
            placeholder="Years of experience (0–10)",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="exp_years"
        )
    async def callback(self, interaction: discord.Interaction):
        years = int(self.values[0])
        if years == 0:
            codes = [1, 2]
        elif years < 3:
            codes = [2, 3]
        elif years < 5:
            codes = [3, 4]
        else:
            codes = [4, 5, 6]
        cfg = bot.user_configs.get_config(self.user_id)
        cfg["experience_levels"] = codes
        bot.user_configs.set_config(self.user_id, cfg)
        await interaction.response.edit_message(
            content=f"✅ Experience set to {years} year(s) → filter codes {codes}\nRun `/start` to scrape.",
            view=None
        )

class ExperienceSelect(ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300.0)
        self.add_item(ExperienceDropdown(user_id))

class LinkedInJobAgent:
    def __init__(self, cfg):
        self.cfg = cfg
        key = cfg["email_receiver"].replace("@", "_at_")
        self.applied_file = os.path.join(DATA_DIR, f"applied_{key}.txt")
        self.scraped_file = os.path.join(DATA_DIR, f"scraped_{key}.txt")
        self.applied = self._load(self.applied_file)
        self.scraped = self._load(self.scraped_file)

    def _load(self, path):
        if os.path.exists(path):
            return set(line.strip() for line in open(path))
        return set()

    def _save(self, path, items):
        with open(path, "a") as f:
            for u in items:
                if u not in self._load(path):
                    f.write(u + "\n")

    def get_links(self, scrolls=10):
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

        driver.get("https://www.linkedin.com")
        for c in json.load(open(self.cfg["cookies_file"])):
            c.pop("sameSite", None)
            c.pop("hostOnly", None)
            try:
                driver.add_cookie(c)
            except:
                pass
        driver.refresh()
        time.sleep(2)

        links = []
        for role in self.cfg["roles"]:
            for exp in self.cfg["experience_levels"]:
                url = (
                    f"https://www.linkedin.com/jobs/search/?"
                    f"keywords={role.replace(' ', '%20')}&location=India&f_E={exp}"
                )
                driver.get(url)
                time.sleep(2)
                for _ in range(scrolls):
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
                    time.sleep(0.5)
                for card in driver.find_elements(By.CSS_SELECTOR, "div.job-card-container--clickable"):
                    try:
                        href = card.find_element(By.TAG_NAME, "a").get_attribute("href")
                        if "linkedin.com/jobs/view/" in href:
                            links.append(href)
                    except:
                        pass
        driver.quit()
        unique = list(set(links))
        new = [l for l in unique if l not in self.applied and l not in self.scraped]
        if new:
            self._save(self.scraped_file, new)
            self._save(self.applied_file, new)
        return new

    def send_email(self, csv_path):
        msg = EmailMessage()
        msg["Subject"] = "New LinkedIn Jobs"
        msg["From"] = os.getenv("EMAIL_SENDER")
        msg["To"] = self.cfg["email_receiver"]
        msg.set_content("Attached job links.")
        with open(csv_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="application",
                subtype="octet-stream",
                filename=os.path.basename(csv_path),
            )
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
                s.login(os.getenv("EMAIL_SENDER"), os.getenv("EMAIL_PASSWORD"))
                s.send_message(msg)
            return True
        except Exception as e:
            print("Email error:", e)
            return False

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
bot.user_configs = UserConfig()

@bot.event
async def on_ready():
    print(f"{bot.user} online")
    await bot.tree.sync()

@bot.tree.command(name="cookies", description="Upload LinkedIn cookies")
async def cookies_cmd(interaction: discord.Interaction):
    await interaction.response.send_modal(CookieUploadModal(interaction.user.id))

@bot.tree.command(name="setup", description="Configure job agent")
async def setup_cmd(interaction: discord.Interaction):
    await interaction.response.send_modal(JobConfigModal())

@bot.tree.command(name="start", description="Run scraper")
async def start_cmd(interaction: discord.Interaction):
    cfg = bot.user_configs.get_config(interaction.user.id)
    if not cfg or "experience_levels" not in cfg:
        return await interaction.response.send_message(
            "⚠️ Ensure you ran `/cookies`, `/setup`, and selected experience.", ephemeral=True
        )
    await interaction.response.defer(ephemeral=True)
    agent = LinkedInJobAgent(cfg)
    new = agent.get_links()
    if not new:
        return await interaction.followup.send("No new jobs found", ephemeral=True)
    csv = f"jobs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    path = os.path.join(DATA_DIR, csv)
    pd.DataFrame({"url": new}).to_csv(path, index=False)
    ok = agent.send_email(path)
    await interaction.followup.send(f"Found {len(new)} jobs, emailed: {ok}", ephemeral=True)
    print("CSV saved at", path)

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
