import asyncio
import json
import os
import re
import time
import traceback
from datetime import datetime, timezone
from typing import Literal

import aiohttp
import discord
from discord import app_commands
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from aiohttp import web

v0 = 1533574360085037278

v1 = {
    "gamepasses": 1533574360529375466,
    "exclusive": 1533574657985347704,
    "powers": 1533574669775540335,
    "corrupt": 1533574681553272872,
    "requests": 1533575613418307827,
    "failed": 1533585424927297706,
}

v2 = {
    1187698029973733388,
    1248180512665767978,
    1266390756973609042,
}

v3 = [
    "[Batarang]",
    "[DooM]",
    "[Genjutsu]",
    "[Grimiore]",
    "[Light Magic]",
    "[Mjolnir]",
    "[River]",
    "AdminBat",
    "BatmanOutfit",
    "Cards",
    "Cat Speed",
    "CatwomanWhip",
    "Dash Punch",
    "Energy Hammer",
    "EnergyBeam",
    "Escape",
    "FirePower",
    "FlashTransformation",
    "Flight",
    "Fly",
    "Ghost",
    "Ghost Ray",
    "Glide",
    "GoblinGlider",
    "GoblinGrenade",
    "GrappleHook",
    "GreenGoblinOutfit",
    "GreenLanternOutfit",
    "InvincibleOutfit",
    "Joker Speed",
    "JokerCard",
    "JokerOutfit",
    "Killer Queen",
    "ReverseFlashOutfit",
    "Soft & Wet",
    "SpeedForce",
    "Spiderman",
    "Star Platinum",
    "SuperPunch",
    "TA4",
    "The World",
    "Tusk Act 4",
    "Wonder of U",
]

v4 = {
    "PSPlus": "PS Plus",
    "Spit": "Spit",
    "SMG": "SMG",
    "Mask": "Mask",
    "Food": "Food",
    "Char": "Char",
    "Armor": "Armor",
    "MaxArmor": "Max Armor",
    "Aimviewer": "Aimviewer",
    "2xWanted": "2x Wanted",
    "AnonymousMode": "Anonymous Mode",
    "RingTone": "Ring Tone",
}

v5 = os.environ.get("DISCORD_TOKEN", "").strip()
v6 = os.environ.get("MODERATION_API_SECRET", "").strip()
v7 = os.environ.get(
    "BACKEND_URL",
    "https://209-54-105-140.sslip.io",
).strip().rstrip("/")
v8 = os.environ.get("DISCORD_PUBLIC_KEY", "").strip()
v9 = int(os.environ.get("PORT", "8080"))

if not v5:
    raise RuntimeError("missing DISCORD_TOKEN")

if not v6:
    raise RuntimeError("missing MODERATION_API_SECRET")

if not v8:
    raise RuntimeError("missing DISCORD_PUBLIC_KEY")

class u0(Exception):
    def __init__(self, v):
        self.code = str(v)
        super().__init__(self.code)

def u1(v):
    return re.sub(r"[^a-z0-9]+", "", str(v).lower())

u2 = {u1(v): v for v in v3}
u3 = {}

for k, v in v4.items():
    u3[u1(k)] = k
    u3[u1(v)] = k

def u4(v):
    if isinstance(v, str) and v.lower() == "yes":
        return True
    return False

def u5(v):
    x = str(v).strip()

    if not x.isdigit():
        raise u0("1005")

    n = int(x)

    if n <= 0 or n > 10000000000000:
        raise u0("1005")

    return n

def u6(v):
    k = u1(v)
    x = u2.get(k)

    if not x:
        raise u0("1017")

    return x

def u7(v):
    k = u1(v)
    x = u3.get(k)

    if not x:
        raise u0("1018")

    return x

def u8(v):
    return v4.get(v, v)

def u9(v):
    if not isinstance(v, dict):
        return False
    return v.get("enabled") is True

class p0(discord.Client):
    def __init__(self):
        x = discord.Intents.none()
        x.guilds = True

        super().__init__(intents=x)

        self.tree = app_commands.CommandTree(
            self,
            allowed_contexts=app_commands.AppCommandContext(
                guild=True,
                dm_channel=True,
                private_channel=True,
            ),
            allowed_installs=app_commands.AppInstallationType(
                guild=True,
                user=True,
            ),
        )

        self.a = None
        self.b = None
        self.c = {}
        self.d = {}
        self.e = set()

    async def setup_hook(self):
        self.a = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=12)
        )

        await self.f()

        try:
            await self.tree.sync()
        except Exception:
            traceback.print_exc()
            raise RuntimeError("1012")

    async def close(self):
        if self.b:
            await self.b.cleanup()

        if self.a:
            await self.a.close()

        await super().close()

    async def on_ready(self):
        for g in list(self.guilds):
            if g.id != v0:
                await self.h(
                    {
                        "integration_type": 0,
                        "user": {
                            "id": str(g.owner_id or 0),
                            "username": str(g.owner or "unknown"),
                            "global_name": str(g.owner or "unknown"),
                            "avatar": None,
                            "discriminator": "0",
                        },
                        "scopes": ["bot", "applications.commands"],
                        "guild": {
                            "id": str(g.id),
                            "name": g.name,
                        },
                    },
                    "unauthorized guild joined",
                )

                try:
                    await g.leave()
                except Exception:
                    traceback.print_exc()

        print(
            f"connected as {self.user} | guilds={len(self.guilds)}"
        )

    async def on_guild_join(self, g):
        if g.id == v0:
            return

        await self.h(
            {
                "integration_type": 0,
                "user": {
                    "id": str(g.owner_id or 0),
                    "username": str(g.owner or "unknown"),
                    "global_name": str(g.owner or "unknown"),
                    "avatar": None,
                    "discriminator": "0",
                },
                "scopes": ["bot", "applications.commands"],
                "guild": {
                    "id": str(g.id),
                    "name": g.name,
                },
            },
            "unauthorized guild joined",
        )

        try:
            await g.leave()
        except Exception:
            traceback.print_exc()

    async def f(self):
        x = web.Application()
        x.router.add_get("/health", self.i)
        x.router.add_post("/discord-events", self.j)

        self.b = web.AppRunner(x)
        await self.b.setup()

        y = web.TCPSite(
            self.b,
            "0.0.0.0",
            v9,
        )

        await y.start()

    async def i(self, _):
        return web.json_response(
            {
                "ok": True,
                "ready": self.is_ready(),
            }
        )

    async def j(self, r):
        s = r.headers.get("X-Signature-Ed25519", "")
        t = r.headers.get("X-Signature-Timestamp", "")
        b = await r.read()

        try:
            VerifyKey(bytes.fromhex(v8)).verify(
                t.encode() + b,
                bytes.fromhex(s),
            )
        except (ValueError, BadSignatureError):
            return web.Response(status=401)

        try:
            x = json.loads(b.decode("utf-8"))
        except Exception:
            return web.Response(status=400)

        if x.get("type") == 0:
            return web.Response(status=204)

        e = x.get("event") or {}
        n = e.get("type")
        d = e.get("data") or {}

        if n == "APPLICATION_AUTHORIZED":
            asyncio.create_task(
                self.h(
                    d,
                    "application authorized",
                )
            )

        if n == "APPLICATION_DEAUTHORIZED":
            asyncio.create_task(
                self.h(
                    d,
                    "application deauthorized",
                )
            )

        return web.Response(status=204)

    async def k(self, n):
        x = self.get_channel(n)

        if x is None:
            try:
                x = await self.fetch_channel(n)
            except Exception as e:
                raise u0("1010") from e

        if not hasattr(x, "send"):
            raise u0("1010")

        return x

    async def l(self, n, e):
        x = await self.k(n)
        z = None

        for q in range(3):
            try:
                z = await x.send(
                    embed=e,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                break
            except Exception:
                if q == 2:
                    raise u0("1010")
                await asyncio.sleep(q + 1)

        return z

    async def m(self, method, path, body=None):
        if not self.a:
            raise u0("1002")

        try:
            async with self.a.request(
                method,
                f"{v7}{path}",
                headers={
                    "x-moderation-secret": v6,
                    "content-type": "application/json",
                },
                json=body,
            ) as r:
                text = await r.text()
        except asyncio.TimeoutError as e:
            raise u0("1002") from e
        except aiohttp.ClientError as e:
            raise u0("1002") from e

        try:
            data = json.loads(text)
        except Exception as e:
            raise u0("1004") from e

        if r.status == 401:
            raise u0("1003")

        if r.status >= 400 or data.get("ok") is not True:
            raise u0("1009")

        return data

    async def n(self, uid):
        x = await self.m(
            "GET",
            f"/moderation/access/{uid}",
        )

        a = x.get("access")

        if not isinstance(a, dict):
            raise u0("1008")

        return a

    async def o(self, uid, kind, action, name, i):
        body = {
            "userId": uid,
            "kind": kind,
            "action": action,
            "actor": {
                "discordId": str(i.user.id),
                "username": str(i.user),
                "displayName": getattr(
                    i.user,
                    "display_name",
                    str(i.user),
                ),
                "guildId": str(i.guild_id or 0),
                "command": (
                    i.command.name
                    if i.command
                    else "unknown"
                ),
            },
            "reason": (
                i.command.name
                if i.command
                else "unknown"
            ),
        }

        if name is not None:
            body["name"] = name

        x = await self.m(
            "POST",
            "/moderation/access/change",
            body,
        )

        if not x.get("requestId"):
            raise u0("1009")

        return x

    async def p(self, uid):
        now = time.monotonic()
        old = self.c.get(uid)

        if old and now - old[0] < 600:
            return old[1]

        if not self.a:
            raise u0("1002")

        try:
            async with self.a.post(
                "https://users.roblox.com/v1/users",
                json={
                    "userIds": [uid],
                    "excludeBannedUsers": False,
                },
            ) as r:
                x = await r.json(content_type=None)
        except Exception as e:
            raise u0("1006") from e

        data = x.get("data") if isinstance(x, dict) else None

        if not isinstance(data, list) or not data:
            raise u0("1006")

        y = data[0]
        avatar = await self.q(uid)

        z = {
            "id": uid,
            "name": str(y.get("name") or uid),
            "display_name": str(
                y.get("displayName")
                or y.get("name")
                or uid
            ),
            "avatar": avatar,
        }

        self.c[uid] = (now, z)

        return z

    async def q(self, uid):
        if not self.a:
            return None

        for n in range(3):
            try:
                async with self.a.get(
                    "https://thumbnails.roblox.com/v1/users/avatar-headshot",
                    params={
                        "userIds": str(uid),
                        "size": "150x150",
                        "format": "Png",
                        "isCircular": "false",
                    },
                ) as r:
                    x = await r.json(content_type=None)

                d = x.get("data") if isinstance(x, dict) else None

                if isinstance(d, list) and d:
                    image = d[0].get("imageUrl")
                    state = d[0].get("state")

                    if image and state == "Completed":
                        return str(image)
            except Exception:
                pass

            await asyncio.sleep(0.5)

        return None

    async def r(self, i):
        if (
            i.user.id in v2
            and (
                i.guild_id is None
                or i.guild_id == v0
            )
        ):
            return True

        asyncio.create_task(self.s(i))
        return False

    async def s(self, i):
        await self.wait_until_ready()

        x = discord.Embed(
            title="failed command usage",
            color=12735058,
            timestamp=datetime.now(timezone.utc),
        )

        try:
            x.set_author(
                name=str(i.user),
                icon_url=i.user.display_avatar.url,
            )
        except Exception:
            x.set_author(name=str(i.user))

        x.add_field(
            name="user",
            value=f"{i.user} ({i.user.id})",
            inline=False,
        )
        x.add_field(
            name="command",
            value=(
                f"/{i.command.name}"
                if i.command
                else "unknown"
            ),
            inline=True,
        )
        x.add_field(
            name="server",
            value=str(i.guild_id or "dm"),
            inline=True,
        )
        x.add_field(
            name="channel",
            value=str(i.channel_id or "unknown"),
            inline=True,
        )
        x.add_field(
            name="date/time",
            value=f"<t:{int(time.time())}:F>",
            inline=False,
        )

        try:
            await self.l(v1["failed"], x)
        except Exception:
            traceback.print_exc()

    async def h(self, d, action):
        await self.wait_until_ready()

        user = d.get("user") or {}
        guild = d.get("guild") or {}
        uid = str(user.get("id") or "unknown")
        username = str(
            user.get("global_name")
            or user.get("username")
            or "unknown"
        )
        avatar = user.get("avatar")
        icon = None

        if avatar and uid.isdigit():
            icon = (
                f"https://cdn.discordapp.com/avatars/"
                f"{uid}/{avatar}.png?size=128"
            )

        x = discord.Embed(
            title=action,
            color=15320064,
            timestamp=datetime.now(timezone.utc),
        )

        if icon:
            x.set_author(
                name=username,
                icon_url=icon,
            )
        else:
            x.set_author(name=username)

        t = d.get("integration_type")
        kind = (
            "user install"
            if t == 1
            else "server install"
            if t == 0
            else "unknown"
        )

        x.add_field(
            name="user",
            value=f"{username} ({uid})",
            inline=False,
        )
        x.add_field(
            name="type",
            value=kind,
            inline=True,
        )
        x.add_field(
            name="scopes",
            value=", ".join(
                str(q)
                for q in d.get("scopes", [])
            ) or "n/a",
            inline=True,
        )
        x.add_field(
            name="server",
            value=(
                f"{guild.get('name', 'n/a')} "
                f"({guild.get('id', 'n/a')})"
            ),
            inline=False,
        )
        x.add_field(
            name="date/time",
            value=f"<t:{int(time.time())}:F>",
            inline=False,
        )

        try:
            await self.l(v1["requests"], x)
        except Exception:
            traceback.print_exc()

    async def t(
        self,
        channel,
        category,
        action,
        i,
        roblox,
        items,
        requests,
    ):
        now = int(time.time())
        item_text = "\n".join(
            f"- {x}"
            for x in items
        ) or "n/a"

        x = discord.Embed(
            title=f"{category} {action}",
            description=(
                f"{action} **{', '.join(items)}** "
                f"{'to' if action in {'added', 'granted'} else 'from'} "
                f"**{roblox['name']}**"
            ),
            color=(
                1353760
                if action in {"added", "granted"}
                else 15787236
            ),
            timestamp=datetime.now(timezone.utc),
        )

        if roblox.get("avatar"):
            x.set_author(
                name=roblox["name"],
                icon_url=roblox["avatar"],
            )
        else:
            x.set_author(name=roblox["name"])

        x.add_field(
            name="by",
            value=f"{i.user} ({i.user.id})",
            inline=False,
        )
        x.add_field(
            name="roblox user",
            value=(
                f"{roblox['name']} "
                f"({roblox['id']})"
            ),
            inline=False,
        )
        x.add_field(
            name=category,
            value=item_text[:1024],
            inline=False,
        )
        x.add_field(
            name="command",
            value=(
                f"/{i.command.name}"
                if i.command
                else "unknown"
            ),
            inline=True,
        )
        x.add_field(
            name="date/time",
            value=f"<t:{now}:F>",
            inline=True,
        )
        x.add_field(
            name="request",
            value=(
                ", ".join(requests)[:1024]
                if requests
                else "n/a"
            ),
            inline=False,
        )

        if category == "gamepass":
            x.set_footer(
                text=f"checkmateee|gp|{roblox['id']}"
            )

        await self.l(channel, x)

    def v(self, uid):
        if uid not in self.d:
            self.d[uid] = asyncio.Lock()
        return self.d[uid]

    async def w(self):
        x = await self.k(v1["gamepasses"])
        ids = set()

        try:
            async for m in x.history(limit=None):
                if not m.embeds:
                    continue

                f = m.embeds[0].footer.text or ""

                if not f.startswith("checkmateee|gp|"):
                    continue

                raw = f.rsplit("|", 1)[-1]

                if raw.isdigit():
                    ids.add(int(raw))
        except Exception as e:
            raise u0("1010") from e

        counts = {
            k: 0
            for k in v4
        }

        sem = asyncio.Semaphore(8)

        async def one(uid):
            async with sem:
                try:
                    a = await self.n(uid)
                except Exception:
                    return

                gps = a.get("gamepasses") or {}

                for name in counts:
                    if u9(gps.get(name)):
                        counts[name] += 1

        await asyncio.gather(
            *(one(uid) for uid in ids)
        )

        return counts

bot = p0()

async def p1(i):
    if await bot.r(i):
        return True

    if not i.response.is_done():
        await i.response.send_message(
            "no.",
            ephemeral=True,
        )

    return False

async def p2(i):
    if not i.response.is_done():
        await i.response.defer(
            ephemeral=True,
            thinking=True,
        )

async def p3(
    i,
    *,
    content=None,
    embed=None,
    ephemeral=False,
):
    if ephemeral:
        await i.edit_original_response(
            content=content,
            embed=embed,
        )
        return

    await i.followup.send(
        content=content,
        embed=embed,
        ephemeral=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )

    try:
        await i.delete_original_response()
    except Exception:
        pass

async def p4(i, code):
    text = f'show this to ezzi, error "{code}"'

    try:
        if i.response.is_done():
            await i.edit_original_response(
                content=text,
                embed=None,
            )
        else:
            await i.response.send_message(
                text,
                ephemeral=True,
            )
    except Exception:
        traceback.print_exc()

def p5(a):
    return {
        name
        for name, record in (
            a.get("powers") or {}
        ).items()
        if u9(record)
    }

def p6(a):
    manual = a.get("gamepasses") or {}
    bought = a.get("purchasedGamepasses") or {}
    result = {}

    for name in v4:
        result[name] = (
            u9(manual.get(name))
            or u9(bought.get(name))
        )

    return result

def p7(a):
    manual = a.get("gamepasses") or {}

    return {
        name
        for name in v4
        if u9(manual.get(name))
    }

def p8(i):
    return (
        i.user.id in v2
        and (
            i.guild_id is None
            or i.guild_id == v0
        )
    )

async def p9(i, current, values):
    if not p8(i):
        return []

    q = u1(current)
    ranked = []

    for value in values:
        n = u1(value)
        score = (
            0
            if not q
            else 1
            if n.startswith(q)
            else 2
            if q in n
            else 3
        )

        if score < 3:
            ranked.append(
                (score, value.lower(), value)
            )

    if not q:
        ranked = [
            (0, value.lower(), value)
            for value in values
        ]

    ranked.sort()

    return [
        app_commands.Choice(
            name=value,
            value=value,
        )
        for _, _, value in ranked[:25]
    ]

@bot.tree.command(
    name="checkpowers",
    description="?",
)
@app_commands.describe(
    roblox_userid="?",
    ephemeral="?",
)
async def c0(
    i: discord.Interaction,
    roblox_userid: str,
    ephemeral: Literal["yes", "no"] = "no",
):
    await p2(i)
    uid = u5(roblox_userid)
    rbx = await bot.p(uid)
    a = await bot.n(uid)
    powers = sorted(
        p5(a),
        key=str.lower,
    )

    e = discord.Embed(
        title=f"{rbx['name']}'s Powers",
        description=(
            "\n".join(
                f"- {x}"
                for x in powers
            )
            if powers
            else "n/a"
        ),
    )

    if rbx.get("avatar"):
        e.set_author(
            name=rbx["name"],
            icon_url=rbx["avatar"],
        )
    else:
        e.set_author(name=rbx["name"])

    await p3(
        i,
        embed=e,
        ephemeral=u4(ephemeral),
    )

@bot.tree.command(
    name="add-power",
    description="?",
)
@app_commands.describe(
    roblox_userid="?",
    power="?",
    ephemeral="?",
)
async def c1(
    i: discord.Interaction,
    roblox_userid: str,
    power: str,
    ephemeral: Literal["yes", "no"] = "no",
):
    await p2(i)
    uid = u5(roblox_userid)
    name = u6(power)
    rbx = await bot.p(uid)

    async with bot.v(uid):
        a = await bot.n(uid)

        if name in p5(a):
            e = discord.Embed(
                description="failed. user already has that power",
                color=2500390,
            )

            await p3(
                i,
                embed=e,
                ephemeral=u4(ephemeral),
            )
            return

        x = await bot.o(
            uid,
            "power",
            "grant",
            name,
            i,
        )

        await bot.t(
            v1["powers"],
            "power",
            "added",
            i,
            rbx,
            [name],
            [x["requestId"]],
        )

    e = discord.Embed(
        description=(
            f"Added **{name}** "
            f"to **{rbx['name']}**"
        ),
        color=65331,
    )

    await p3(
        i,
        embed=e,
        ephemeral=u4(ephemeral),
    )

@c1.autocomplete("power")
async def c1a(
    i: discord.Interaction,
    current: str,
):
    return await p9(i, current, v3)

@bot.tree.command(
    name="remove-power",
    description="?",
)
@app_commands.describe(
    roblox_userid="?",
    power="?",
    ephemeral="?",
)
async def c2(
    i: discord.Interaction,
    roblox_userid: str,
    power: str,
    ephemeral: Literal["yes", "no"] = "no",
):
    await p2(i)
    uid = u5(roblox_userid)
    name = u6(power)
    rbx = await bot.p(uid)

    async with bot.v(uid):
        a = await bot.n(uid)

        if name not in p5(a):
            await p3(
                i,
                content="buddy doesnt have that power 😭",
                ephemeral=u4(ephemeral),
            )
            return

        x = await bot.o(
            uid,
            "power",
            "remove",
            name,
            i,
        )

        await bot.t(
            v1["powers"],
            "power",
            "removed",
            i,
            rbx,
            [name],
            [x["requestId"]],
        )

    e = discord.Embed(
        description=(
            f"removed **{name}** "
            f"from **{rbx['name']}**"
        ),
        color=12735058,
    )

    await p3(
        i,
        embed=e,
        ephemeral=u4(ephemeral),
    )

@c2.autocomplete("power")
async def c2a(
    i: discord.Interaction,
    current: str,
):
    return await p9(i, current, v3)

@bot.tree.command(
    name="giveallpowers",
    description="?",
)
@app_commands.describe(
    robloxuserid="?",
)
async def c3(
    i: discord.Interaction,
    robloxuserid: str,
):
    await p2(i)
    uid = u5(robloxuserid)
    rbx = await bot.p(uid)

    async with bot.v(uid):
        a = await bot.n(uid)
        owned = p5(a)
        missing = [
            x
            for x in v3
            if x not in owned
        ]

        if not missing:
            await p3(
                i,
                content="they already have all powers",
            )
            return

        requests = []

        for name in missing:
            x = await bot.o(
                uid,
                "power",
                "grant",
                name,
                i,
            )
            requests.append(x["requestId"])

        await bot.t(
            v1["powers"],
            "power",
            "added",
            i,
            rbx,
            missing,
            requests,
        )

    await p3(
        i,
        content="👍",
    )

@bot.tree.command(
    name="removeallpowers",
    description="?",
)
@app_commands.describe(
    robloxuserid="?",
)
async def c4(
    i: discord.Interaction,
    robloxuserid: str,
):
    await p2(i)
    uid = u5(robloxuserid)
    rbx = await bot.p(uid)

    async with bot.v(uid):
        a = await bot.n(uid)
        owned = sorted(
            p5(a),
            key=str.lower,
        )

        if not owned:
            await p3(
                i,
                content="0 powers to this guys name",
            )
            return

        requests = []

        for name in owned:
            x = await bot.o(
                uid,
                "power",
                "remove",
                name,
                i,
            )
            requests.append(x["requestId"])

        await bot.t(
            v1["powers"],
            "power",
            "removed",
            i,
            rbx,
            owned,
            requests,
        )

    await p3(
        i,
        content="👍",
    )

@bot.tree.command(
    name="powerlist",
    description="?",
)
async def c5(i: discord.Interaction):
    e = discord.Embed(
        title="power list",
        description="\n".join(
            f"- {x}"
            for x in v3
        ),
        color=15320064,
    )

    e.set_footer(
        text="Powers are sold **ONLY BY ezzi.**"
    )

    await i.response.send_message(
        embed=e,
        allowed_mentions=discord.AllowedMentions.none(),
    )

@bot.tree.command(
    name="checkgamepasses",
    description="?",
)
@app_commands.describe(
    roblox_user="?",
    ephemeral="?",
)
async def c6(
    i: discord.Interaction,
    roblox_user: str,
    ephemeral: Literal["yes", "no"] = "no",
):
    await p2(i)
    uid = u5(roblox_user)
    rbx = await bot.p(uid)
    a = await bot.n(uid)
    gps = p6(a)

    e = discord.Embed(
        title=f"{rbx['name']}'s gamepasses",
        description="\n".join(
            f"- {u8(name).lower()} : "
            f"{str(gps[name]).lower()}"
            for name in v4
        ),
        color=15329769,
    )

    if rbx.get("avatar"):
        e.set_author(
            name=rbx["name"],
            icon_url=rbx["avatar"],
        )
    else:
        e.set_author(name=rbx["name"])

    await p3(
        i,
        embed=e,
        ephemeral=u4(ephemeral),
    )

@bot.tree.command(
    name="add-gamepass",
    description="?",
)
@app_commands.describe(
    robloxuserid="?",
    gamepass="?",
    ephemeral="?",
)
async def c7(
    i: discord.Interaction,
    robloxuserid: str,
    gamepass: str,
    ephemeral: Literal["yes", "no"] = "no",
):
    await p2(i)
    uid = u5(robloxuserid)
    name = u7(gamepass)
    rbx = await bot.p(uid)

    async with bot.v(uid):
        a = await bot.n(uid)

        if p6(a).get(name):
            await p3(
                i,
                content="user already has that",
                ephemeral=True,
            )
            return

        x = await bot.o(
            uid,
            "gamepass",
            "grant",
            name,
            i,
        )

        await bot.t(
            v1["gamepasses"],
            "gamepass",
            "added",
            i,
            rbx,
            [u8(name)],
            [x["requestId"]],
        )

    e = discord.Embed(
        description=(
            f"added **{u8(name)}** "
            f"to **{rbx['name']}**"
        ),
        color=1353760,
    )

    await p3(
        i,
        embed=e,
        ephemeral=u4(ephemeral),
    )

@c7.autocomplete("gamepass")
async def c7a(
    i: discord.Interaction,
    current: str,
):
    return await p9(
        i,
        current,
        list(v4.values()),
    )

@bot.tree.command(
    name="remove-gamepass",
    description="?",
)
@app_commands.describe(
    robloxuserid="?",
    gamepass="?",
    ephemeral="?",
)
async def c8(
    i: discord.Interaction,
    robloxuserid: str,
    gamepass: str,
    ephemeral: Literal["yes", "no"] = "no",
):
    await p2(i)
    uid = u5(robloxuserid)
    name = u7(gamepass)
    rbx = await bot.p(uid)

    async with bot.v(uid):
        a = await bot.n(uid)

        if name not in p7(a):
            await p3(
                i,
                content="they dont have it",
                ephemeral=u4(ephemeral),
            )
            return

        x = await bot.o(
            uid,
            "gamepass",
            "remove",
            name,
            i,
        )

        await bot.t(
            v1["gamepasses"],
            "gamepass",
            "removed",
            i,
            rbx,
            [u8(name)],
            [x["requestId"]],
        )

    e = discord.Embed(
        description=(
            f"removed **{u8(name)}** "
            f"from **{rbx['name']}**"
        ),
        color=15787236,
    )

    await p3(
        i,
        embed=e,
        ephemeral=u4(ephemeral),
    )

@c8.autocomplete("gamepass")
async def c8a(
    i: discord.Interaction,
    current: str,
):
    return await p9(
        i,
        current,
        list(v4.values()),
    )

@bot.tree.command(
    name="addallgamepasses",
    description="?",
)
@app_commands.describe(
    robloxuserid="?",
)
async def c9(
    i: discord.Interaction,
    robloxuserid: str,
):
    await p2(i)
    uid = u5(robloxuserid)
    rbx = await bot.p(uid)

    async with bot.v(uid):
        a = await bot.n(uid)
        effective = p6(a)
        missing = [
            name
            for name in v4
            if not effective.get(name)
        ]

        if not missing:
            await p3(
                i,
                content="they already have all gps",
            )
            return

        requests = []

        for name in missing:
            x = await bot.o(
                uid,
                "gamepass",
                "grant",
                name,
                i,
            )
            requests.append(x["requestId"])

        await bot.t(
            v1["gamepasses"],
            "gamepass",
            "added",
            i,
            rbx,
            [u8(x) for x in missing],
            requests,
        )

    await p3(
        i,
        content="👍",
    )

@bot.tree.command(
    name="removeallgamepasses",
    description="?",
)
@app_commands.describe(
    robloxuserid="?",
)
async def c10(
    i: discord.Interaction,
    robloxuserid: str,
):
    await p2(i)
    uid = u5(robloxuserid)
    rbx = await bot.p(uid)

    async with bot.v(uid):
        a = await bot.n(uid)
        owned = sorted(
            p7(a),
            key=lambda x: u8(x).lower(),
        )

        if not owned:
            await p3(
                i,
                content="they dont have any",
            )
            return

        requests = []

        for name in owned:
            x = await bot.o(
                uid,
                "gamepass",
                "remove",
                name,
                i,
            )
            requests.append(x["requestId"])

        await bot.t(
            v1["gamepasses"],
            "gamepass",
            "removed",
            i,
            rbx,
            [u8(x) for x in owned],
            requests,
        )

    await p3(
        i,
        content="👍",
    )

@bot.tree.command(
    name="gamepasslist",
    description="?",
)
async def c11(i: discord.Interaction):
    await p2(i)
    counts = await bot.w()

    e = discord.Embed(
        title="available gamepasses",
        description="\n".join(
            f"- {u8(name)} / "
            f"**{counts.get(name, 0)}** users"
            for name in v4
        ),
    )

    await p3(
        i,
        embed=e,
    )

for command in bot.tree.get_commands():
    command.add_check(p1)

@bot.tree.error
async def c12(
    i: discord.Interaction,
    error: app_commands.AppCommandError,
):
    if isinstance(error, app_commands.CheckFailure):
        return

    original = getattr(
        error,
        "original",
        error,
    )

    code = (
        original.code
        if isinstance(original, u0)
        else "1099"
    )

    traceback.print_exception(
        type(original),
        original,
        original.__traceback__,
    )

    await p4(i, code)

bot.run(
    v5,
    log_handler=None,
)
