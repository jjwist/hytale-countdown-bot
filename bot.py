import os
import datetime
import asyncio
import urllib.parse
import threading

import requests
import discord
from discord.ext import commands
from zoneinfo import ZoneInfo
from aiohttp import web

# =========================
# CONFIG
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
SCREENSHOT_KEY = os.getenv("SCREENSHOT_KEY")

# Orario italiano in cui vuoi l'invio ogni giorno (es. 15:00)
SEND_HOUR = 17
SEND_MINUTE = 0

# =========================
# DISCORD BOT
# =========================

intents = discord.Intents.default()
intents.message_content = True  # così puoi usare anche !testscreen se ti va
bot = commands.Bot(command_prefix="!", intents=intents)


def build_screenshot_url() -> str:
    """Costruisce l'URL per l'API di ScreenshotMachine per la pagina Hytale countdown."""
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


async def send_screenshot():
    """Invia lo screenshot nel canale configurato."""
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("❌ Channel non trovato, controlla CHANNEL_ID")
        return

    file_path = "hytale_countdown.png"

    try:
        print("📸 Scarico lo screenshot del countdown...")
        await fetch_screenshot_async(file_path)
        await channel.send(
            content="Ecco lo stato del countdown:",
            file=discord.File(file_path)
        )
        print("✅ Screenshot inviato")
    except Exception as e:
        print(f"Errore durante screenshot/invio: {e}")


async def daily_scheduler():
    """Scheduler che ogni giorno alle SEND_HOUR:SEND_MINUTE invia lo screenshot."""
    await bot.wait_until_ready()
    rome_tz = ZoneInfo("Europe/Rome")

    while not bot.is_closed():
        now_rome = datetime.datetime.now(rome_tz)
        target = now_rome.replace(
            hour=SEND_HOUR, minute=SEND_MINUTE, second=0, microsecond=0
        )
        if target <= now_rome:
            target += datetime.timedelta(days=1)

        wait_seconds = (target - now_rome).total_seconds()
        print(f"Prossimo invio giornaliero tra circa {wait_seconds/60:.1f} minuti")
        await asyncio.sleep(wait_seconds)
        await send_screenshot()


async def test_once():
    """Invia UNO screenshot di test dopo 10 secondi dall'avvio."""
    await bot.wait_until_ready()
    print("Modalità TEST: invio uno screenshot tra 10 secondi...")
    await asyncio.sleep(10)
    await send_screenshot()
    print("Modalità TEST: screenshot di test inviato (se tutto è ok).")


@bot.event
async def on_ready():
    print(f"✅ Loggato come {bot.user} ({bot.user.id})")

    # Avvio lo scheduler giornaliero SOLO una volta
    if not hasattr(bot, "scheduler_started"):
        bot.scheduler_started = True
        bot.loop.create_task(daily_scheduler())
        bot.loop.create_task(test_once())  # screenshot di test all'avvio


# Comando manuale (opzionale)
@bot.command()
async def testscreen(ctx):
    await ctx.send("📸 Faccio lo screenshot di prova...")
    await send_screenshot()


# =========================
# MINI WEBSERVER PER KEEP-ALIVE (UPTIME ROBOT / REPLIT)
# =========================

async def handle(request):
    return web.Response(text="Bot UP")

def run_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, port=port)

def start_webserver():
    thread = threading.Thread(target=run_webserver)
    thread.daemon = True
    thread.start()


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN non impostato")
    if not CHANNEL_ID:
        raise RuntimeError("CHANNEL_ID non impostato o non valido")
    if not SCREENSHOT_KEY:
        raise RuntimeError("SCREENSHOT_KEY non impostato")

    # Avvia il webserver (per ping keep-alive)
    start_webserver()

    # Avvia il bot Discord
    bot.run(DISCORD_TOKEN)
