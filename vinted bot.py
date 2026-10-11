"""
Bot Discord Vinted : poste les nouvelles annonces qui correspondent à tes recherches.

Installation :  pip install discord.py aiohttp
Lancement    :  DISCORD_TOKEN=xxx CHANNEL_ID=123 python vinted_bot.py
"""
import os
import aiohttp
import discord
from discord.ext import tasks

TOKEN = os.getenv("DISCORD_TOKEN", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
DOMAIN = "www.vinted.fr"   # vinted.de, vinted.es, etc. si besoin
INTERVAL = 60              # secondes entre chaque vérification (ne descends pas trop bas)

# ---- TES RECHERCHES ----
SEARCHES = [
    {
        "name": "Nike Tech Fleece",
        "query": "nike tech fleece",
        "max_price": 35,
        "exclude": ["enfant", "kids", "junior"],  # mots à ignorer dans le titre
    },
    {
        "name": "Veste Carhartt",
        "query": "veste carhartt",
        "max_price": 40,
        "exclude": [],
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

intents = discord.Intents.default()
client = discord.Client(intents=intents)
session: aiohttp.ClientSession | None = None
seen: dict[str, set] = {s["name"]: set() for s in SEARCHES}
first_run: dict[str, bool] = {s["name"]: True for s in SEARCHES}


async def refresh_cookies():
    """Vinted exige des cookies de session : on les récupère via la page d'accueil."""
    async with session.get(f"https://{DOMAIN}/") as r:
        await r.read()


async def fetch_items(search: dict, retry: bool = True):
    params = {
        "search_text": search["query"],
        "price_to": search["max_price"],
        "order": "newest_first",
        "per_page": 20,
    }
    url = f"https://{DOMAIN}/api/v2/catalog/items"
    async with session.get(url, params=params) as r:
        if r.status in (401, 403) and retry:
            await refresh_cookies()
            return await fetch_items(search, retry=False)
        if r.status != 200:
            print(f"[{search['name']}] HTTP {r.status}")
            return []
        data = await r.json()
        return data.get("items", [])


def get_price(item: dict) -> str:
    p = item.get("price")
    if isinstance(p, dict):  # nouveau format
        return f"{p.get('amount')} {p.get('currency_code', '€')}"
    return f"{p} {item.get('currency', '€')}"


def build_embed(item: dict, search_name: str) -> discord.Embed:
    embed = discord.Embed(
        title=item.get("title", "Annonce"),
        url=item.get("url") or f"https://{DOMAIN}/items/{item['id']}",
        description=f"🔎 {search_name}",
        color=0x09B1BA,
    )
    embed.add_field(name="💰 Prix", value=get_price(item), inline=True)
    if item.get("size_title"):
        embed.add_field(name="📏 Taille", value=item["size_title"], inline=True)
    if item.get("brand_title"):
        embed.add_field(name="🏷️ Marque", value=item["brand_title"], inline=True)
    if item.get("status"):
        embed.add_field(name="✨ État", value=item["status"], inline=True)
    photo = (item.get("photo") or {}).get("url")
    if photo:
        embed.set_image(url=photo)
    return embed


@tasks.loop(seconds=INTERVAL)
async def check_vinted():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("Salon introuvable : vérifie CHANNEL_ID et les permissions du bot.")
        return

    for search in SEARCHES:
        name = search["name"]
        try:
            items = await fetch_items(search)
        except Exception as e:
            print(f"[{name}] erreur : {e}")
            continue

        new_items = [i for i in items if str(i["id"]) not in seen[name]]
        for item in new_items:
            seen[name].add(str(item["id"]))

        # Au 1er passage on mémorise sans poster, pour éviter de spammer
        if first_run[name]:
            first_run[name] = False
            continue

        for item in reversed(new_items):  # du plus ancien au plus récent
            title = item.get("title", "").lower()
            if any(w.lower() in title for w in search["exclude"]):
                continue
            await channel.send(embed=build_embed(item, name))


@client.event
async def on_ready():
    global session
    print(f"Connecté en tant que {client.user}")
    session = aiohttp.ClientSession(headers=HEADERS)
    await refresh_cookies()
    check_vinted.start()


if __name__ == "__main__":
    client.run(TOKEN)
