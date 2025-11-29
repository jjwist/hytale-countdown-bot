import os
import datetime
import asyncio
import urllib.parse

import requests
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from zoneinfo import ZoneInfo  # Python 3.9+

# Carica variabili da .env se esiste (utile in locale, su Railway useremo env del pannello)
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
SCREENSHOT_KEY = os.getenv("SCREENSHOT_KEY")

# Orario italiano in cui vuoi l'invio ogni giorno (es. 15:00)
SEND_HOUR = 15
SEND_MINUTE = 0

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def build_screenshot_url() -> str:
    """
    Costruisce l'URL per l'API di ScreenshotMachine per la pagina Hytale countdown.
    Docs: https://api.screenshotmachine.com/?key=...&url=...&dimension=...
    """
    if not SCREENSHOT_KEY:
        raise RuntimeError("La variabile d'ambiente SCREENSHOT_KEY non è impostata")

    base_url = "https://api.screenshotmachine.com/"
    params = {
        "key": SCREENSHOT_KEY,
        "url": "https://hytale.com/countdown",
        "dimension": "1366xfull",  # tutta la pagina
        "device": "desktop",
        "format": "png",
        "cacheLimit": "0",   # sempre fresco
        "delay": "2000",     # aspetta 2 secondi prima di catturare
        "zoom": "100",
    }
    return base_url + "?" + urllib.parse.urlencode(params)


def download_screenshot(output_path: str):
    """Scarica lo screenshot da ScreenshotMachine e lo salva come file locale."""
    api_url = build_screenshot_url()
    resp = requests.get(api_url, stream=True, timeout=60)
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(8192):
            if chunk:
                f.write(chunk)


async def fetch_screenshot_async(output_path: str = "hytale_countdown.png"):
    """Wrapper asincrono per non bloccare il loop di Discord."""
    await asyncio.to_thread(download_screenshot, output_path)


@tasks.loop(hours=24)
async def daily_screenshot_task():
    """Task che ogni 24 ore fa lo screenshot e lo manda sul canale configurato."""
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("❌ Channel non trovato, controlla CHANNEL_ID")
        return

    file_path = "hytale_countdown.png"

    try:
        print("📸 Scarico lo screenshot del countdown...")
        await fetch_screenshot_async(file_path)
        await channel.send(
            content="Ecco lo stato del countdown di oggi:",
            file=discord.File(file_path)
        )
        print("✅ Screenshot inviato")
    except Exception as e:
        print(f"Errore durante screenshot/invio: {e}")


@daily_screenshot_task.before_loop
async def before_daily_screenshot_task():
    """Aspetta che il bot sia pronto e si sincronizza con l'orario (Europe/Rome)."""
    await bot.wait_until_ready()
    print("Bot pronto, mi sincronizzo con l'orario desiderato...")

    rome_tz = ZoneInfo("Europe/Rome")
    now_rome = datetime.datetime.now(rome_tz)

    target_today_rome = now_rome.replace(
        hour=SEND_HOUR, minute=SEND_MINUTE, second=0, microsecond=0
    )

    if target_today_rome <= now_rome:
        # se l'orario di oggi è già passato, vai a domani
        target_today_rome += datetime.timedelta(days=1)

    wait_seconds = (target_today_rome - now_rome).total_seconds()
    print(f"Prossimo invio tra circa {wait_seconds/60:.1f} minuti")
    await asyncio.sleep(wait_seconds)


@bot.event
async def on_ready():
    print(f"✅ Loggato come {bot.user} ({bot.user.id})")
    if not daily_screenshot_task.is_running():
        daily_screenshot_task.start()


# Comando manuale per testare subito: !testscreen
@bot.command()
async def testscreen(ctx):
    file_path = "hytale_countdown_test.png"
    await ctx.send("📸 Faccio lo screenshot di prova...")
    try:
        await fetch_screenshot_async(file_path)
        await ctx.send(
            content="Ecco lo screenshot di prova:",
            file=discord.File(file_path)
        )
    except Exception as e:
        await ctx.send(f"Errore durante lo screenshot: `{e}`")


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN non impostato")
    if not CHANNEL_ID:
        raise RuntimeError("CHANNEL_ID non impostato o non valido")
    bot.run(DISCORD_TOKEN)
