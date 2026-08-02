from __future__ import annotations

import asyncio
import json
import os
import re
import time
import traceback
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Literal

import aiohttp
import discord
from aiohttp import web
from discord import app_commands
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

AUTHORIZED_GUILD_ID = 1533574360085037278

LOG_CHANNEL_IDS = {
    "gamepasses": 1533574360529375466,
    "exclusive": 1533574657985347704,
    "powers": 1533574669775540335,
    "corrupt": 1533574681553272872,
    "applications": 1533575613418307827,
    "denied": 1533585424927297706,
}

AUTHORIZED_DISCORD_USER_IDS = frozenset(
    {
        1187698029973733388,
        1248180512665767978,
        1266390756973609042,
    }
)

POWER_PACKAGES = OrderedDict(
    [
        ("Batman", ("[Batarang]", "BatmanOutfit", "GrappleHook", "Glide")),
        ("[DooM]", ("[DooM]",)),
        ("[Genjutsu]", ("[Genjutsu]",)),
        ("[Grimiore]", ("[Grimiore]",)),
        ("[Light Magic]", ("[Light Magic]",)),
        ("[Mjolnir]", ("[Mjolnir]",)),
        ("[River]", ("[River]",)),
        ("AdminBat", ("AdminBat",)),
        ("Cards", ("Cards",)),
        ("Catwoman", ("Cat Speed", "CatwomanWhip")),
        ("Dash Punch", ("Dash Punch",)),
        ("Escape", ("Escape",)),
        ("FirePower", ("FirePower",)),
        ("Flash", ("FlashTransformation", "SpeedForce")),
        ("Ghost", ("Ghost", "Ghost Ray")),
        (
            "Green Goblin",
            ("GoblinGlider", "GoblinGrenade", "GreenGoblinOutfit"),
        ),
        (
            "Green Lantern",
            ("Energy Hammer", "EnergyBeam", "Flight", "GreenLanternOutfit"),
        ),
        ("Invincible", ("InvincibleOutfit", "Fly", "SuperPunch")),
        ("Joker", ("Joker Speed", "JokerCard", "JokerOutfit")),
        ("Killer Queen", ("Killer Queen",)),
        ("Reverse Flash", ("ReverseFlashOutfit",)),
        ("Soft & Wet", ("Soft & Wet",)),
        ("Spiderman", ("Spiderman",)),
        ("Star Platinum", ("Star Platinum",)),
        ("Tusk Act 4", ("TA4", "Tusk Act 4")),
        ("The World", ("The World",)),
        ("Wonder of U", ("Wonder of U",)),
    ]
)

GAMEPASS_NAMES = OrderedDict(
    [
        ("PSPlus", "PS Plus"),
        ("Spit", "Spit"),
        ("SMG", "SMG"),
        ("Mask", "Mask"),
        ("Food", "Food"),
        ("Char", "Char"),
        ("Armor", "Armor"),
        ("MaxArmor", "Max Armor"),
        ("Aimviewer", "Aimviewer"),
        ("2xWanted", "2x Wanted"),
        ("AnonymousMode", "Anonymous Mode"),
        ("RingTone", "Ring Tone"),
    ]
)


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing {name}")
    return value


DISCORD_TOKEN = required_environment("DISCORD_TOKEN")
MODERATION_API_SECRET = required_environment("MODERATION_API_SECRET")
DISCORD_PUBLIC_KEY = required_environment("DISCORD_PUBLIC_KEY")
BACKEND_URL = os.environ.get(
    "BACKEND_URL",
    "https://209-54-105-140.sslip.io",
).strip().rstrip("/")
RAILWAY_PORT = int(os.environ.get("PORT", "8080"))

try:
    DISCORD_SIGNATURE_VERIFIER = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
except (ValueError, TypeError) as verification_error:
    raise RuntimeError("invalid DISCORD_PUBLIC_KEY") from verification_error


class CheckmateFault(Exception):
    def __init__(self, code: str):
        self.code = str(code)
        super().__init__(self.code)


def normalize_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


POWER_NAME_ALIASES: dict[str, str] = {}
POWER_COMPONENT_TO_PACKAGE: dict[str, str] = {}
ALL_POWER_COMPONENTS: tuple[str, ...] = tuple(
    component
    for package_components in POWER_PACKAGES.values()
    for component in package_components
)
ALL_POWER_COMPONENT_SET = frozenset(ALL_POWER_COMPONENTS)

for power_package_name, power_package_components in POWER_PACKAGES.items():
    POWER_NAME_ALIASES[normalize_name(power_package_name)] = power_package_name
    for power_component_name in power_package_components:
        POWER_NAME_ALIASES[normalize_name(power_component_name)] = power_package_name
        POWER_COMPONENT_TO_PACKAGE[power_component_name] = power_package_name

GAMEPASS_NAME_ALIASES: dict[str, str] = {}
for gamepass_storage_name, gamepass_display_name in GAMEPASS_NAMES.items():
    GAMEPASS_NAME_ALIASES[normalize_name(gamepass_storage_name)] = gamepass_storage_name
    GAMEPASS_NAME_ALIASES[normalize_name(gamepass_display_name)] = gamepass_storage_name


def option_is_ephemeral(value: str) -> bool:
    return str(value).lower() == "yes"


def parse_roblox_user_id(value: Any) -> int:
    normalized_value = str(value).strip()
    if not normalized_value.isdigit():
        raise CheckmateFault("3003")
    user_id = int(normalized_value)
    if user_id <= 0 or user_id > 9_007_199_254_740_991:
        raise CheckmateFault("3003")
    return user_id


def resolve_power_package(value: Any) -> str:
    package_name = POWER_NAME_ALIASES.get(normalize_name(value))
    if not package_name:
        raise CheckmateFault("3001")
    return package_name


def resolve_gamepass_name(value: Any) -> str:
    storage_name = GAMEPASS_NAME_ALIASES.get(normalize_name(value))
    if not storage_name:
        raise CheckmateFault("3002")
    return storage_name


def access_record_enabled(value: Any) -> bool:
    if value is True:
        return True
    return isinstance(value, dict) and value.get("enabled") is True


def enabled_power_components(access_data: dict[str, Any]) -> set[str]:
    power_records = access_data.get("powers")
    if not isinstance(power_records, dict):
        return set()
    return {
        str(power_name)
        for power_name, power_record in power_records.items()
        if access_record_enabled(power_record)
    }


def displayed_power_names(access_data: dict[str, Any]) -> list[str]:
    owned_components = enabled_power_components(access_data)
    displayed_names: list[str] = []
    for package_name, package_components in POWER_PACKAGES.items():
        if any(component in owned_components for component in package_components):
            displayed_names.append(package_name)
    displayed_names.extend(
        sorted(
            owned_components.difference(ALL_POWER_COMPONENT_SET),
            key=str.lower,
        )
    )
    return displayed_names


def package_names_for_components(components: set[str] | list[str]) -> list[str]:
    component_set = set(components)
    package_names: list[str] = []
    for package_name, package_components in POWER_PACKAGES.items():
        if any(component in component_set for component in package_components):
            package_names.append(package_name)
    package_names.extend(
        sorted(
            component_set.difference(ALL_POWER_COMPONENT_SET),
            key=str.lower,
        )
    )
    return package_names


def enabled_gamepass_sources(access_data: dict[str, Any]) -> dict[str, bool]:
    source_names = (
        "gamepasses",
        "purchasedGamepasses",
        "giftedGamepasses",
    )
    enabled_sources: dict[str, bool] = {}
    for gamepass_storage_name in GAMEPASS_NAMES:
        enabled_sources[gamepass_storage_name] = any(
            isinstance(access_data.get(source_name), dict)
            and access_record_enabled(
                access_data[source_name].get(gamepass_storage_name)
            )
            for source_name in source_names
        )
    return enabled_sources


def manually_enabled_gamepasses(access_data: dict[str, Any]) -> set[str]:
    manual_records = access_data.get("gamepasses")
    if not isinstance(manual_records, dict):
        return set()
    return {
        gamepass_storage_name
        for gamepass_storage_name in GAMEPASS_NAMES
        if access_record_enabled(manual_records.get(gamepass_storage_name))
    }


def command_name(interaction: discord.Interaction) -> str:
    if interaction.command:
        return str(interaction.command.name)
    return "unknown"


def interaction_context(interaction: discord.Interaction) -> str:
    if interaction.guild_id is None:
        return "dm/private"
    guild_name = interaction.guild.name if interaction.guild else "unknown"
    return f"{guild_name} ({interaction.guild_id})"


def user_avatar_url(user: discord.abc.User) -> str | None:
    try:
        return user.display_avatar.url
    except Exception:
        return None


def ranked_autocomplete_choices(
    current: str,
    values: list[str],
) -> list[app_commands.Choice[str]]:
    normalized_current = normalize_name(current)
    ranked_values: list[tuple[int, str, str]] = []
    for value in values:
        normalized_value = normalize_name(value)
        if not normalized_current:
            score = 0
        elif normalized_value.startswith(normalized_current):
            score = 0
        elif normalized_current in normalized_value:
            score = 1
        else:
            continue
        ranked_values.append((score, value.lower(), value))
    ranked_values.sort()
    return [
        app_commands.Choice(name=value, value=value)
        for _, _, value in ranked_values[:25]
    ]


class CheckmateClient(discord.Client):
    def __init__(self) -> None:
        discord_intents = discord.Intents.none()
        discord_intents.guilds = True
        super().__init__(intents=discord_intents)
        self.command_tree = app_commands.CommandTree(
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
        self.api_session: aiohttp.ClientSession | None = None
        self.web_runner: web.AppRunner | None = None
        self.roblox_user_cache: dict[int, tuple[float, dict[str, Any]]] = {}
        self.user_operation_locks: dict[int, asyncio.Lock] = {}
        self.known_roblox_user_ids: set[int] = set()
        self.webhook_event_cache: OrderedDict[str, float] = OrderedDict()

    async def setup_hook(self) -> None:
        self.api_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            connector=aiohttp.TCPConnector(limit=50),
        )
        await self.start_web_server()
        try:
            await self.command_tree.sync()
        except Exception as synchronization_error:
            traceback.print_exc()
            raise RuntimeError("command sync failed") from synchronization_error

    async def close(self) -> None:
        if self.web_runner:
            await self.web_runner.cleanup()
        if self.api_session:
            await self.api_session.close()
        await super().close()

    async def on_ready(self) -> None:
        for connected_guild in list(self.guilds):
            if connected_guild.id == AUTHORIZED_GUILD_ID:
                continue
            try:
                await self.log_application_event(
                    {
                        "integration_type": 0,
                        "user": {
                            "id": str(connected_guild.owner_id or 0),
                            "username": str(connected_guild.owner or "unknown"),
                            "global_name": str(connected_guild.owner or "unknown"),
                            "avatar": None,
                        },
                        "scopes": ["bot", "applications.commands"],
                        "guild": {
                            "id": str(connected_guild.id),
                            "name": connected_guild.name,
                        },
                    },
                    "unauthorized server install",
                    None,
                )
            except Exception:
                traceback.print_exc()
            try:
                await connected_guild.leave()
            except Exception:
                traceback.print_exc()
        print(
            f"connected as {self.user} | guilds={len(self.guilds)} | "
            f"commands={len(self.command_tree.get_commands())}"
        )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if guild.id == AUTHORIZED_GUILD_ID:
            return
        try:
            await self.log_application_event(
                {
                    "integration_type": 0,
                    "user": {
                        "id": str(guild.owner_id or 0),
                        "username": str(guild.owner or "unknown"),
                        "global_name": str(guild.owner or "unknown"),
                        "avatar": None,
                    },
                    "scopes": ["bot", "applications.commands"],
                    "guild": {
                        "id": str(guild.id),
                        "name": guild.name,
                    },
                },
                "unauthorized server install",
                None,
            )
        except Exception:
            traceback.print_exc()
        try:
            await guild.leave()
        except Exception:
            traceback.print_exc()

    async def start_web_server(self) -> None:
        web_application = web.Application(client_max_size=1_048_576)
        web_application.router.add_get("/health", self.health_endpoint)
        web_application.router.add_post(
            "/discord-events",
            self.discord_events_endpoint,
        )
        self.web_runner = web.AppRunner(web_application)
        await self.web_runner.setup()
        web_site = web.TCPSite(
            self.web_runner,
            "0.0.0.0",
            RAILWAY_PORT,
        )
        await web_site.start()

    async def health_endpoint(self, _: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "ready": self.is_ready(),
                "guilds": len(self.guilds),
            }
        )

    async def discord_events_endpoint(
        self,
        request: web.Request,
    ) -> web.Response:
        request_signature = request.headers.get("X-Signature-Ed25519", "")
        request_timestamp = request.headers.get("X-Signature-Timestamp", "")
        request_body = await request.read()
        try:
            DISCORD_SIGNATURE_VERIFIER.verify(
                request_timestamp.encode("utf-8") + request_body,
                bytes.fromhex(request_signature),
            )
        except (ValueError, BadSignatureError):
            return web.Response(status=401)
        try:
            webhook_payload = json.loads(request_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return web.Response(status=400)
        if webhook_payload.get("type") == 0:
            return web.Response(
                status=204,
                headers={"Content-Type": "application/json"},
            )
        if webhook_payload.get("type") == 1:
            asyncio.create_task(
                self.process_discord_webhook_event(webhook_payload)
            )
        return web.Response(status=204)

    async def process_discord_webhook_event(
        self,
        webhook_payload: dict[str, Any],
    ) -> None:
        event_body = webhook_payload.get("event")
        if not isinstance(event_body, dict):
            return
        event_type = str(event_body.get("type") or "")
        event_timestamp = str(event_body.get("timestamp") or "")
        event_data = event_body.get("data")
        if not isinstance(event_data, dict):
            event_data = {}
        event_user = event_data.get("user")
        event_user_id = (
            str(event_user.get("id") or "unknown")
            if isinstance(event_user, dict)
            else "unknown"
        )
        event_guild = event_data.get("guild")
        event_guild_id = (
            str(event_guild.get("id") or "none")
            if isinstance(event_guild, dict)
            else "none"
        )
        event_key = (
            f"{event_type}|{event_timestamp}|{event_user_id}|{event_guild_id}"
        )
        current_time = time.monotonic()
        while self.webhook_event_cache:
            oldest_key, oldest_time = next(iter(self.webhook_event_cache.items()))
            if current_time - oldest_time <= 600:
                break
            self.webhook_event_cache.pop(oldest_key, None)
        if event_key in self.webhook_event_cache:
            return
        self.webhook_event_cache[event_key] = current_time
        try:
            if event_type == "APPLICATION_AUTHORIZED":
                await self.log_application_event(
                    event_data,
                    "application authorized",
                    event_timestamp,
                )
            elif event_type == "APPLICATION_DEAUTHORIZED":
                await self.log_application_event(
                    event_data,
                    "application deauthorized",
                    event_timestamp,
                )
        except Exception:
            traceback.print_exc()

    def interaction_is_authorized(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id not in AUTHORIZED_DISCORD_USER_IDS:
            return False
        if interaction.guild_id is None:
            return True
        return interaction.guild_id == AUTHORIZED_GUILD_ID

    def operation_lock(self, roblox_user_id: int) -> asyncio.Lock:
        operation_lock = self.user_operation_locks.get(roblox_user_id)
        if operation_lock is None:
            operation_lock = asyncio.Lock()
            self.user_operation_locks[roblox_user_id] = operation_lock
        return operation_lock

    async def fetch_log_channel(
        self,
        channel_category: str,
    ) -> discord.abc.Messageable:
        channel_id = LOG_CHANNEL_IDS[channel_category]
        log_channel = self.get_channel(channel_id)
        if log_channel is None:
            try:
                log_channel = await self.fetch_channel(channel_id)
            except Exception as channel_error:
                raise CheckmateFault("2101") from channel_error
        if not hasattr(log_channel, "send"):
            raise CheckmateFault("2101")
        channel_guild = getattr(log_channel, "guild", None)
        if channel_guild and channel_guild.id != AUTHORIZED_GUILD_ID:
            raise CheckmateFault("2101")
        return log_channel

    async def send_log_embed(
        self,
        channel_category: str,
        log_embed: discord.Embed,
    ) -> discord.Message:
        log_channel = await self.fetch_log_channel(channel_category)
        for send_attempt in range(3):
            try:
                return await log_channel.send(
                    embed=log_embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except Exception as send_error:
                if send_attempt == 2:
                    raise CheckmateFault("2102") from send_error
                await asyncio.sleep(send_attempt + 1)
        raise CheckmateFault("2102")

    def queue_denied_usage_log(
        self,
        interaction: discord.Interaction,
    ) -> None:
        async def denied_log_task() -> None:
            try:
                await self.log_denied_usage(interaction)
            except Exception:
                traceback.print_exc()

        asyncio.create_task(denied_log_task())

    async def log_denied_usage(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await self.wait_until_ready()
        denied_embed = discord.Embed(
            title="failed command usage",
            color=12735058,
            timestamp=datetime.now(timezone.utc),
        )
        denied_avatar = user_avatar_url(interaction.user)
        if denied_avatar:
            denied_embed.set_author(
                name=str(interaction.user),
                icon_url=denied_avatar,
            )
        else:
            denied_embed.set_author(name=str(interaction.user))
        denied_embed.add_field(
            name="user",
            value=f"{interaction.user} ({interaction.user.id})",
            inline=False,
        )
        denied_embed.add_field(
            name="command",
            value=f"/{command_name(interaction)}",
            inline=True,
        )
        denied_embed.add_field(
            name="server",
            value=str(interaction.guild_id or "dm/private"),
            inline=True,
        )
        denied_embed.add_field(
            name="channel",
            value=str(interaction.channel_id or "unknown"),
            inline=True,
        )
        denied_embed.add_field(
            name="date/time",
            value=f"<t:{int(time.time())}:F>",
            inline=False,
        )
        await self.send_log_embed("denied", denied_embed)

    async def log_application_event(
        self,
        event_data: dict[str, Any],
        event_action: str,
        event_timestamp: str | None,
    ) -> None:
        await self.wait_until_ready()
        event_user = event_data.get("user")
        if not isinstance(event_user, dict):
            event_user = {}
        event_guild = event_data.get("guild")
        if not isinstance(event_guild, dict):
            event_guild = {}
        event_user_id = str(event_user.get("id") or "unknown")
        event_username = str(
            event_user.get("global_name")
            or event_user.get("username")
            or "unknown"
        )
        event_avatar_hash = event_user.get("avatar")
        event_avatar_url = None
        if event_avatar_hash and event_user_id.isdigit():
            event_avatar_url = (
                f"https://cdn.discordapp.com/avatars/{event_user_id}/"
                f"{event_avatar_hash}.png?size=128"
            )
        application_embed = discord.Embed(
            title=event_action,
            color=15320064,
            timestamp=datetime.now(timezone.utc),
        )
        if event_avatar_url:
            application_embed.set_author(
                name=event_username,
                icon_url=event_avatar_url,
            )
        else:
            application_embed.set_author(name=event_username)
        integration_type = event_data.get("integration_type")
        installation_type = (
            "user install"
            if integration_type == 1
            else "server install"
            if integration_type == 0
            else "unknown"
        )
        application_embed.add_field(
            name="user",
            value=f"{event_username} ({event_user_id})",
            inline=False,
        )
        application_embed.add_field(
            name="type",
            value=installation_type,
            inline=True,
        )
        application_embed.add_field(
            name="scopes",
            value=", ".join(
                str(scope_name)
                for scope_name in event_data.get("scopes", [])
            )
            or "n/a",
            inline=True,
        )
        application_embed.add_field(
            name="server",
            value=(
                f"{event_guild.get('name', 'n/a')} "
                f"({event_guild.get('id', 'n/a')})"
            ),
            inline=False,
        )
        application_embed.add_field(
            name="event time",
            value=event_timestamp or "n/a",
            inline=False,
        )
        application_embed.add_field(
            name="logged at",
            value=f"<t:{int(time.time())}:F>",
            inline=False,
        )
        await self.send_log_embed("applications", application_embed)

    async def log_access_change(
        self,
        channel_category: str,
        access_category: str,
        access_action: str,
        interaction: discord.Interaction,
        roblox_user: dict[str, Any],
        displayed_items: list[str],
        request_ids: list[str],
    ) -> None:
        action_preposition = (
            "to" if access_action in {"added", "granted"} else "from"
        )
        item_description = ", ".join(displayed_items)
        change_embed = discord.Embed(
            title=f"{access_category} {access_action}",
            description=(
                f"{access_action} **{item_description}** {action_preposition} "
                f"**{roblox_user['name']}**"
            ),
            color=(
                1353760
                if access_action in {"added", "granted"}
                else 15787236
            ),
            timestamp=datetime.now(timezone.utc),
        )
        if roblox_user.get("avatar"):
            change_embed.set_author(
                name=roblox_user["name"],
                icon_url=roblox_user["avatar"],
            )
        else:
            change_embed.set_author(name=roblox_user["name"])
        change_embed.add_field(
            name="by",
            value=f"{interaction.user} ({interaction.user.id})",
            inline=False,
        )
        change_embed.add_field(
            name="roblox user",
            value=f"{roblox_user['name']} ({roblox_user['id']})",
            inline=False,
        )
        change_embed.add_field(
            name=access_category,
            value="\n".join(f"- {item}" for item in displayed_items)[:1024],
            inline=False,
        )
        change_embed.add_field(
            name="command",
            value=f"/{command_name(interaction)}",
            inline=True,
        )
        change_embed.add_field(
            name="context",
            value=interaction_context(interaction),
            inline=True,
        )
        change_embed.add_field(
            name="date/time",
            value=f"<t:{int(time.time())}:F>",
            inline=False,
        )
        change_embed.add_field(
            name="request",
            value=", ".join(request_ids)[:1024] or "n/a",
            inline=False,
        )
        change_embed.set_footer(
            text=f"checkmateee|user|{roblox_user['id']}"
        )
        await self.send_log_embed(channel_category, change_embed)

    async def backend_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.api_session:
            raise CheckmateFault("2001")
        request_headers = {
            "x-moderation-secret": MODERATION_API_SECRET,
            "accept": "application/json",
        }
        request_arguments: dict[str, Any] = {"headers": request_headers}
        if payload is not None:
            request_headers["content-type"] = "application/json"
            request_arguments["json"] = payload
        final_status = 0
        final_text = ""
        maximum_attempts = 3 if method.upper() == "GET" else 1
        for request_attempt in range(maximum_attempts):
            try:
                async with self.api_session.request(
                    method,
                    f"{BACKEND_URL}{path}",
                    **request_arguments,
                ) as backend_response:
                    final_status = backend_response.status
                    final_text = await backend_response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as request_error:
                if request_attempt == maximum_attempts - 1:
                    raise CheckmateFault("2001") from request_error
                await asyncio.sleep(request_attempt + 1)
                continue
            if final_status >= 500 and request_attempt < maximum_attempts - 1:
                await asyncio.sleep(request_attempt + 1)
                continue
            break
        if final_status in {401, 403}:
            raise CheckmateFault("2002")
        if final_status >= 500:
            raise CheckmateFault("2001")
        try:
            backend_data = json.loads(final_text)
        except json.JSONDecodeError as response_error:
            raise CheckmateFault("2003") from response_error
        if not isinstance(backend_data, dict):
            raise CheckmateFault("2003")
        if final_status >= 400 or backend_data.get("ok") is not True:
            raise CheckmateFault("2004")
        return backend_data

    async def get_access(self, roblox_user_id: int) -> dict[str, Any]:
        self.known_roblox_user_ids.add(roblox_user_id)
        backend_data = await self.backend_request(
            "GET",
            f"/moderation/access/{roblox_user_id}",
        )
        access_data = backend_data.get("access")
        if not isinstance(access_data, dict):
            raise CheckmateFault("2005")
        return access_data

    async def change_access(
        self,
        roblox_user_id: int,
        access_kind: str,
        access_action: str,
        access_name: str,
        interaction: discord.Interaction,
    ) -> str:
        interaction_user = interaction.user
        interaction_guild_id = str(interaction.guild_id or 0)
        discord_user_id = str(interaction_user.id)
        discord_username = str(interaction_user)
        change_payload = {
            "userId": roblox_user_id,
            "kind": access_kind,
            "action": access_action,
            "name": access_name,
            "actor": {
                "discordId": discord_user_id,
                "discordUserId": discord_user_id,
                "username": discord_username,
                "discordUsername": discord_username,
                "displayName": getattr(
                    interaction_user,
                    "display_name",
                    discord_username,
                ),
                "guildId": interaction_guild_id,
                "discordGuildId": interaction_guild_id,
                "command": command_name(interaction),
            },
            "reason": f"discord command /{command_name(interaction)}",
        }
        backend_data = await self.backend_request(
            "POST",
            "/moderation/access/change",
            change_payload,
        )
        request_id = backend_data.get("requestId")
        if not request_id:
            raise CheckmateFault("2006")
        return str(request_id)

    async def lookup_roblox_user(
        self,
        roblox_user_id: int,
    ) -> dict[str, Any]:
        self.known_roblox_user_ids.add(roblox_user_id)
        current_time = time.monotonic()
        cached_user = self.roblox_user_cache.get(roblox_user_id)
        if cached_user and current_time - cached_user[0] < 600:
            return cached_user[1]
        if not self.api_session:
            raise CheckmateFault("2202")
        roblox_data: dict[str, Any] | None = None
        for request_attempt in range(3):
            try:
                async with self.api_session.post(
                    "https://users.roblox.com/v1/users",
                    json={
                        "userIds": [roblox_user_id],
                        "excludeBannedUsers": False,
                    },
                ) as roblox_response:
                    if roblox_response.status != 200:
                        raise aiohttp.ClientResponseError(
                            roblox_response.request_info,
                            roblox_response.history,
                            status=roblox_response.status,
                        )
                    roblox_data = await roblox_response.json(content_type=None)
                break
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                json.JSONDecodeError,
            ) as roblox_error:
                if request_attempt == 2:
                    raise CheckmateFault("2202") from roblox_error
                await asyncio.sleep(request_attempt + 1)
        returned_users = (
            roblox_data.get("data")
            if isinstance(roblox_data, dict)
            else None
        )
        if not isinstance(returned_users, list) or not returned_users:
            raise CheckmateFault("2201")
        returned_user = returned_users[0]
        if not isinstance(returned_user, dict):
            raise CheckmateFault("2201")
        roblox_username = str(returned_user.get("name") or "").strip()
        if not roblox_username:
            raise CheckmateFault("2201")
        avatar_url = await self.lookup_roblox_avatar(roblox_user_id)
        normalized_user = {
            "id": roblox_user_id,
            "name": roblox_username,
            "display_name": str(
                returned_user.get("displayName") or roblox_username
            ),
            "avatar": avatar_url,
        }
        self.roblox_user_cache[roblox_user_id] = (
            current_time,
            normalized_user,
        )
        return normalized_user

    async def lookup_roblox_avatar(
        self,
        roblox_user_id: int,
    ) -> str | None:
        if not self.api_session:
            return None
        for request_attempt in range(3):
            try:
                async with self.api_session.get(
                    "https://thumbnails.roblox.com/v1/users/avatar-headshot",
                    params={
                        "userIds": str(roblox_user_id),
                        "size": "150x150",
                        "format": "Png",
                        "isCircular": "false",
                    },
                ) as avatar_response:
                    avatar_data = await avatar_response.json(content_type=None)
                avatar_records = (
                    avatar_data.get("data")
                    if isinstance(avatar_data, dict)
                    else None
                )
                if isinstance(avatar_records, list) and avatar_records:
                    avatar_record = avatar_records[0]
                    if (
                        isinstance(avatar_record, dict)
                        and avatar_record.get("state") == "Completed"
                        and avatar_record.get("imageUrl")
                    ):
                        return str(avatar_record["imageUrl"])
            except Exception:
                pass
            await asyncio.sleep(0.5 * (request_attempt + 1))
        return None

    async def rollback_access_changes(
        self,
        roblox_user_id: int,
        access_kind: str,
        original_action: str,
        completed_names: list[str],
        interaction: discord.Interaction,
    ) -> None:
        rollback_action = "remove" if original_action == "grant" else "grant"
        rollback_failed = False
        for completed_name in reversed(completed_names):
            try:
                await self.change_access(
                    roblox_user_id,
                    access_kind,
                    rollback_action,
                    completed_name,
                    interaction,
                )
            except Exception:
                rollback_failed = True
                traceback.print_exc()
        if rollback_failed:
            raise CheckmateFault("2301")

    async def perform_access_changes(
        self,
        roblox_user_id: int,
        access_kind: str,
        access_action: str,
        access_names: list[str],
        interaction: discord.Interaction,
    ) -> tuple[list[str], list[str]]:
        completed_names: list[str] = []
        request_ids: list[str] = []
        try:
            for access_name in access_names:
                request_id = await self.change_access(
                    roblox_user_id,
                    access_kind,
                    access_action,
                    access_name,
                    interaction,
                )
                completed_names.append(access_name)
                request_ids.append(request_id)
        except Exception as change_error:
            if completed_names:
                try:
                    await self.rollback_access_changes(
                        roblox_user_id,
                        access_kind,
                        access_action,
                        completed_names,
                        interaction,
                    )
                except CheckmateFault as rollback_error:
                    raise rollback_error from change_error
            raise
        return completed_names, request_ids

    async def perform_logged_access_changes(
        self,
        roblox_user_id: int,
        access_kind: str,
        access_action: str,
        access_names: list[str],
        interaction: discord.Interaction,
        log_channel_category: str,
        log_access_category: str,
        log_access_action: str,
        roblox_user: dict[str, Any],
        displayed_items: list[str],
    ) -> list[str]:
        completed_names, request_ids = await self.perform_access_changes(
            roblox_user_id,
            access_kind,
            access_action,
            access_names,
            interaction,
        )
        try:
            await self.log_access_change(
                log_channel_category,
                log_access_category,
                log_access_action,
                interaction,
                roblox_user,
                displayed_items,
                request_ids,
            )
        except Exception as log_error:
            try:
                await self.rollback_access_changes(
                    roblox_user_id,
                    access_kind,
                    access_action,
                    completed_names,
                    interaction,
                )
            except CheckmateFault as rollback_error:
                raise rollback_error from log_error
            raise
        return request_ids

    async def collect_logged_roblox_user_ids(self) -> set[int]:
        collected_user_ids = set(self.known_roblox_user_ids)
        gamepass_log_channel = await self.fetch_log_channel("gamepasses")
        try:
            async for logged_message in gamepass_log_channel.history(limit=None):
                for logged_embed in logged_message.embeds:
                    footer_text = logged_embed.footer.text or ""
                    footer_match = re.search(
                        r"checkmateee(?:\|gp\||\|user\|)(\d+)",
                        footer_text,
                    )
                    if footer_match:
                        collected_user_ids.add(int(footer_match.group(1)))
                    for embed_field in logged_embed.fields:
                        if embed_field.name.lower() != "roblox user":
                            continue
                        field_match = re.search(r"\((\d+)\)", embed_field.value)
                        if field_match:
                            collected_user_ids.add(int(field_match.group(1)))
        except Exception as history_error:
            raise CheckmateFault("2103") from history_error
        return collected_user_ids

    async def count_gamepasses(self) -> dict[str, int]:
        candidate_user_ids = await self.collect_logged_roblox_user_ids()
        gamepass_counts = {
            gamepass_storage_name: 0
            for gamepass_storage_name in GAMEPASS_NAMES
        }
        access_semaphore = asyncio.Semaphore(6)

        async def count_user_gamepasses(roblox_user_id: int) -> None:
            async with access_semaphore:
                access_data = await self.get_access(roblox_user_id)
                effective_gamepasses = enabled_gamepass_sources(access_data)
                for gamepass_storage_name, is_enabled in effective_gamepasses.items():
                    if is_enabled:
                        gamepass_counts[gamepass_storage_name] += 1

        await asyncio.gather(
            *(
                count_user_gamepasses(roblox_user_id)
                for roblox_user_id in candidate_user_ids
            )
        )
        return gamepass_counts


checkmate_client = CheckmateClient()
checkmate_tree = checkmate_client.command_tree


async def require_checkmate_access(
    interaction: discord.Interaction,
) -> bool:
    if checkmate_client.interaction_is_authorized(interaction):
        return True
    checkmate_client.queue_denied_usage_log(interaction)
    return False


async def defer_command_response(
    interaction: discord.Interaction,
    ephemeral: bool = False,
) -> None:
    interaction.extras["checkmate_response_ephemeral"] = ephemeral
    if not interaction.response.is_done():
        await interaction.response.defer(
            ephemeral=ephemeral,
            thinking=True,
        )


async def complete_command_response(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    ephemeral: bool = False,
) -> None:
    interaction.extras["checkmate_response_ephemeral"] = ephemeral
    if interaction.response.is_done():
        await interaction.edit_original_response(
            content=content,
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return
    await interaction.response.send_message(
        content=content,
        embed=embed,
        ephemeral=ephemeral,
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def force_ephemeral_response(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
) -> None:
    if not interaction.response.is_done():
        interaction.extras["checkmate_response_ephemeral"] = True
        await interaction.response.send_message(
            content=content,
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    original_is_ephemeral = bool(
        interaction.extras.get("checkmate_response_ephemeral", False)
    )

    if original_is_ephemeral:
        await interaction.edit_original_response(
            content=content,
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    await interaction.edit_original_response(
        content="command failed",
        embed=None,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    await interaction.followup.send(
        content=content,
        embed=embed,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def send_error_response(
    interaction: discord.Interaction,
    error_code: str,
) -> None:
    await force_ephemeral_response(
        interaction,
        content=f'show this to ezzi, error "{error_code}"',
    )


def set_roblox_author(
    embed: discord.Embed,
    roblox_user: dict[str, Any],
) -> None:
    if roblox_user.get("avatar"):
        embed.set_author(
            name=roblox_user["name"],
            icon_url=roblox_user["avatar"],
        )
    else:
        embed.set_author(name=roblox_user["name"])


@checkmate_tree.command(name="checkpowers", description="?")
@app_commands.describe(roblox_userid="?", ephemeral="?")
async def check_powers_command(
    interaction: discord.Interaction,
    roblox_userid: str,
    ephemeral: Literal["yes", "no"] = "no",
) -> None:
    response_is_ephemeral = option_is_ephemeral(ephemeral)
    await defer_command_response(interaction, response_is_ephemeral)
    roblox_user_id = parse_roblox_user_id(roblox_userid)
    roblox_user, access_data = await asyncio.gather(
        checkmate_client.lookup_roblox_user(roblox_user_id),
        checkmate_client.get_access(roblox_user_id),
    )
    power_names = displayed_power_names(access_data)
    powers_embed = discord.Embed(
        title=f"{roblox_user['name']}'s Powers",
        description=(
            "\n".join(f"- {power_name}" for power_name in power_names)
            if power_names
            else "n/a"
        ),
    )
    set_roblox_author(powers_embed, roblox_user)
    await complete_command_response(
        interaction,
        embed=powers_embed,
        ephemeral=response_is_ephemeral,
    )


@checkmate_tree.command(name="add-power", description="?")
@app_commands.describe(roblox_userid="?", power="?", ephemeral="?")
async def add_power_command(
    interaction: discord.Interaction,
    roblox_userid: str,
    power: str,
    ephemeral: Literal["yes", "no"] = "no",
) -> None:
    response_is_ephemeral = option_is_ephemeral(ephemeral)
    await defer_command_response(interaction, response_is_ephemeral)
    roblox_user_id = parse_roblox_user_id(roblox_userid)
    package_name = resolve_power_package(power)
    roblox_user = await checkmate_client.lookup_roblox_user(roblox_user_id)
    async with checkmate_client.operation_lock(roblox_user_id):
        access_data = await checkmate_client.get_access(roblox_user_id)
        owned_components = enabled_power_components(access_data)
        package_components = list(POWER_PACKAGES[package_name])
        missing_components = [
            component
            for component in package_components
            if component not in owned_components
        ]
        if not missing_components:
            duplicate_embed = discord.Embed(
                description="failed. user already has that power",
                color=2500390,
            )
            await complete_command_response(
                interaction,
                embed=duplicate_embed,
                ephemeral=response_is_ephemeral,
            )
            return
        await checkmate_client.perform_logged_access_changes(
            roblox_user_id,
            "power",
            "grant",
            missing_components,
            interaction,
            "powers",
            "power",
            "added",
            roblox_user,
            [package_name],
        )
    success_embed = discord.Embed(
        description=f"Added **{package_name}** to **{roblox_user['name']}**",
        color=65331,
    )
    await complete_command_response(
        interaction,
        embed=success_embed,
        ephemeral=response_is_ephemeral,
    )


@add_power_command.autocomplete("power")
async def add_power_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if not checkmate_client.interaction_is_authorized(interaction):
        return []
    return ranked_autocomplete_choices(current, list(POWER_PACKAGES.keys()))


@checkmate_tree.command(name="remove-power", description="?")
@app_commands.describe(roblox_userid="?", power="?", ephemeral="?")
async def remove_power_command(
    interaction: discord.Interaction,
    roblox_userid: str,
    power: str,
    ephemeral: Literal["yes", "no"] = "no",
) -> None:
    response_is_ephemeral = option_is_ephemeral(ephemeral)
    await defer_command_response(interaction, response_is_ephemeral)
    roblox_user_id = parse_roblox_user_id(roblox_userid)
    package_name = resolve_power_package(power)
    roblox_user = await checkmate_client.lookup_roblox_user(roblox_user_id)
    async with checkmate_client.operation_lock(roblox_user_id):
        access_data = await checkmate_client.get_access(roblox_user_id)
        owned_components = enabled_power_components(access_data)
        removable_components = [
            component
            for component in POWER_PACKAGES[package_name]
            if component in owned_components
        ]
        if not removable_components:
            await complete_command_response(
                interaction,
                content="buddy doesnt have that power 😭",
                ephemeral=response_is_ephemeral,
            )
            return
        await checkmate_client.perform_logged_access_changes(
            roblox_user_id,
            "power",
            "remove",
            removable_components,
            interaction,
            "powers",
            "power",
            "removed",
            roblox_user,
            [package_name],
        )
    success_embed = discord.Embed(
        description=f"removed **{package_name}** from **{roblox_user['name']}**",
        color=12735058,
    )
    await complete_command_response(
        interaction,
        embed=success_embed,
        ephemeral=response_is_ephemeral,
    )


@remove_power_command.autocomplete("power")
async def remove_power_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if not checkmate_client.interaction_is_authorized(interaction):
        return []
    return ranked_autocomplete_choices(current, list(POWER_PACKAGES.keys()))


@checkmate_tree.command(name="giveallpowers", description="?")
@app_commands.describe(robloxuserid="?")
async def give_all_powers_command(
    interaction: discord.Interaction,
    robloxuserid: str,
) -> None:
    await defer_command_response(interaction, False)
    roblox_user_id = parse_roblox_user_id(robloxuserid)
    roblox_user = await checkmate_client.lookup_roblox_user(roblox_user_id)
    async with checkmate_client.operation_lock(roblox_user_id):
        access_data = await checkmate_client.get_access(roblox_user_id)
        owned_components = enabled_power_components(access_data)
        missing_components = [
            component
            for component in ALL_POWER_COMPONENTS
            if component not in owned_components
        ]
        if not missing_components:
            await complete_command_response(
                interaction,
                content="they already have all powers",
            )
            return
        await checkmate_client.perform_logged_access_changes(
            roblox_user_id,
            "power",
            "grant",
            missing_components,
            interaction,
            "powers",
            "power",
            "added",
            roblox_user,
            package_names_for_components(missing_components),
        )
    await complete_command_response(interaction, content="👍")


@checkmate_tree.command(name="removeallpowers", description="?")
@app_commands.describe(robloxuserid="?")
async def remove_all_powers_command(
    interaction: discord.Interaction,
    robloxuserid: str,
) -> None:
    await defer_command_response(interaction, False)
    roblox_user_id = parse_roblox_user_id(robloxuserid)
    roblox_user = await checkmate_client.lookup_roblox_user(roblox_user_id)
    async with checkmate_client.operation_lock(roblox_user_id):
        access_data = await checkmate_client.get_access(roblox_user_id)
        owned_components = sorted(
            enabled_power_components(access_data),
            key=str.lower,
        )
        if not owned_components:
            await complete_command_response(
                interaction,
                content="0 powers to this guys name",
            )
            return
        await checkmate_client.perform_logged_access_changes(
            roblox_user_id,
            "power",
            "remove",
            owned_components,
            interaction,
            "powers",
            "power",
            "removed",
            roblox_user,
            displayed_power_names(access_data),
        )
    await complete_command_response(interaction, content="👍")


@checkmate_tree.command(name="powerlist", description="?")
async def power_list_command(interaction: discord.Interaction) -> None:
    power_list_embed = discord.Embed(
        title="power list",
        description="\n".join(
            f"- {power_name}" for power_name in POWER_PACKAGES
        ),
        color=15320064,
    )
    power_list_embed.set_footer(text="Powers are sold **ONLY BY ezzi.**")
    await complete_command_response(interaction, embed=power_list_embed)


@checkmate_tree.command(name="checkgamepasses", description="?")
@app_commands.describe(roblox_user="?", ephemeral="?")
async def check_gamepasses_command(
    interaction: discord.Interaction,
    roblox_user: str,
    ephemeral: Literal["yes", "no"] = "no",
) -> None:
    response_is_ephemeral = option_is_ephemeral(ephemeral)
    await defer_command_response(interaction, response_is_ephemeral)
    roblox_user_id = parse_roblox_user_id(roblox_user)
    roblox_profile, access_data = await asyncio.gather(
        checkmate_client.lookup_roblox_user(roblox_user_id),
        checkmate_client.get_access(roblox_user_id),
    )
    gamepass_states = enabled_gamepass_sources(access_data)
    gamepasses_embed = discord.Embed(
        title=f"{roblox_profile['name']}'s gamepasses",
        description="\n".join(
            f"- {GAMEPASS_NAMES[gamepass_name].lower()} : "
            f"{str(gamepass_states[gamepass_name]).lower()}"
            for gamepass_name in GAMEPASS_NAMES
        ),
        color=15329769,
    )
    set_roblox_author(gamepasses_embed, roblox_profile)
    await complete_command_response(
        interaction,
        embed=gamepasses_embed,
        ephemeral=response_is_ephemeral,
    )


@checkmate_tree.command(name="add-gamepass", description="?")
@app_commands.describe(robloxuserid="?", gamepass="?", ephemeral="?")
async def add_gamepass_command(
    interaction: discord.Interaction,
    robloxuserid: str,
    gamepass: str,
    ephemeral: Literal["yes", "no"] = "no",
) -> None:
    response_is_ephemeral = option_is_ephemeral(ephemeral)
    await defer_command_response(interaction, response_is_ephemeral)
    roblox_user_id = parse_roblox_user_id(robloxuserid)
    gamepass_storage_name = resolve_gamepass_name(gamepass)
    gamepass_display_name = GAMEPASS_NAMES[gamepass_storage_name]
    roblox_user = await checkmate_client.lookup_roblox_user(roblox_user_id)
    async with checkmate_client.operation_lock(roblox_user_id):
        access_data = await checkmate_client.get_access(roblox_user_id)
        if enabled_gamepass_sources(access_data)[gamepass_storage_name]:
            await force_ephemeral_response(
                interaction,
                content="user already has that",
            )
            return
        await checkmate_client.perform_logged_access_changes(
            roblox_user_id,
            "gamepass",
            "grant",
            [gamepass_storage_name],
            interaction,
            "gamepasses",
            "gamepass",
            "added",
            roblox_user,
            [gamepass_display_name],
        )
    success_embed = discord.Embed(
        description=(
            f"added **{gamepass_display_name}** to **{roblox_user['name']}**"
        ),
        color=1353760,
    )
    await complete_command_response(
        interaction,
        embed=success_embed,
        ephemeral=response_is_ephemeral,
    )


@add_gamepass_command.autocomplete("gamepass")
async def add_gamepass_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if not checkmate_client.interaction_is_authorized(interaction):
        return []
    return ranked_autocomplete_choices(current, list(GAMEPASS_NAMES.values()))


@checkmate_tree.command(name="remove-gamepass", description="?")
@app_commands.describe(robloxuserid="?", gamepass="?", ephemeral="?")
async def remove_gamepass_command(
    interaction: discord.Interaction,
    robloxuserid: str,
    gamepass: str,
    ephemeral: Literal["yes", "no"] = "no",
) -> None:
    response_is_ephemeral = option_is_ephemeral(ephemeral)
    await defer_command_response(interaction, response_is_ephemeral)
    roblox_user_id = parse_roblox_user_id(robloxuserid)
    gamepass_storage_name = resolve_gamepass_name(gamepass)
    gamepass_display_name = GAMEPASS_NAMES[gamepass_storage_name]
    roblox_user = await checkmate_client.lookup_roblox_user(roblox_user_id)
    async with checkmate_client.operation_lock(roblox_user_id):
        access_data = await checkmate_client.get_access(roblox_user_id)
        manual_gamepasses = manually_enabled_gamepasses(access_data)
        effective_gamepasses = enabled_gamepass_sources(access_data)
        if gamepass_storage_name not in manual_gamepasses:
            if effective_gamepasses[gamepass_storage_name]:
                raise CheckmateFault("2401")
            await complete_command_response(
                interaction,
                content="they dont have it",
                ephemeral=response_is_ephemeral,
            )
            return
        await checkmate_client.perform_logged_access_changes(
            roblox_user_id,
            "gamepass",
            "remove",
            [gamepass_storage_name],
            interaction,
            "gamepasses",
            "gamepass",
            "removed",
            roblox_user,
            [gamepass_display_name],
        )
    success_embed = discord.Embed(
        description=(
            f"removed **{gamepass_display_name}** from **{roblox_user['name']}**"
        ),
        color=15787236,
    )
    await complete_command_response(
        interaction,
        embed=success_embed,
        ephemeral=response_is_ephemeral,
    )


@remove_gamepass_command.autocomplete("gamepass")
async def remove_gamepass_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if not checkmate_client.interaction_is_authorized(interaction):
        return []
    return ranked_autocomplete_choices(current, list(GAMEPASS_NAMES.values()))


@checkmate_tree.command(name="addallgamepasses", description="?")
@app_commands.describe(robloxuserid="?")
async def add_all_gamepasses_command(
    interaction: discord.Interaction,
    robloxuserid: str,
) -> None:
    await defer_command_response(interaction, False)
    roblox_user_id = parse_roblox_user_id(robloxuserid)
    roblox_user = await checkmate_client.lookup_roblox_user(roblox_user_id)
    async with checkmate_client.operation_lock(roblox_user_id):
        access_data = await checkmate_client.get_access(roblox_user_id)
        effective_gamepasses = enabled_gamepass_sources(access_data)
        missing_gamepasses = [
            gamepass_storage_name
            for gamepass_storage_name in GAMEPASS_NAMES
            if not effective_gamepasses[gamepass_storage_name]
        ]
        if not missing_gamepasses:
            await complete_command_response(
                interaction,
                content="they already have all gps",
            )
            return
        await checkmate_client.perform_logged_access_changes(
            roblox_user_id,
            "gamepass",
            "grant",
            missing_gamepasses,
            interaction,
            "gamepasses",
            "gamepass",
            "added",
            roblox_user,
            [
                GAMEPASS_NAMES[gamepass_storage_name]
                for gamepass_storage_name in missing_gamepasses
            ],
        )
    await complete_command_response(interaction, content="👍")


@checkmate_tree.command(name="removeallgamepasses", description="?")
@app_commands.describe(robloxuserid="?")
async def remove_all_gamepasses_command(
    interaction: discord.Interaction,
    robloxuserid: str,
) -> None:
    await defer_command_response(interaction, False)
    roblox_user_id = parse_roblox_user_id(robloxuserid)
    roblox_user = await checkmate_client.lookup_roblox_user(roblox_user_id)
    async with checkmate_client.operation_lock(roblox_user_id):
        access_data = await checkmate_client.get_access(roblox_user_id)
        removable_gamepasses = sorted(
            manually_enabled_gamepasses(access_data),
            key=lambda gamepass_name: GAMEPASS_NAMES[gamepass_name].lower(),
        )
        if not removable_gamepasses:
            await complete_command_response(
                interaction,
                content="they dont have any",
            )
            return
        await checkmate_client.perform_logged_access_changes(
            roblox_user_id,
            "gamepass",
            "remove",
            removable_gamepasses,
            interaction,
            "gamepasses",
            "gamepass",
            "removed",
            roblox_user,
            [
                GAMEPASS_NAMES[gamepass_storage_name]
                for gamepass_storage_name in removable_gamepasses
            ],
        )
    await complete_command_response(interaction, content="👍")


@checkmate_tree.command(name="gamepasslist", description="?")
async def gamepass_list_command(interaction: discord.Interaction) -> None:
    await defer_command_response(interaction, False)
    gamepass_counts = await checkmate_client.count_gamepasses()
    gamepass_list_embed = discord.Embed(
        title="available gamepasses",
        description="\n".join(
            f"- {gamepass_display_name} / "
            f"**{gamepass_counts[gamepass_storage_name]}** users"
            for gamepass_storage_name, gamepass_display_name in GAMEPASS_NAMES.items()
        ),
    )
    await complete_command_response(interaction, embed=gamepass_list_embed)


for registered_command in checkmate_tree.get_commands():
    registered_command.add_check(require_checkmate_access)


@checkmate_tree.error
async def checkmate_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    if isinstance(error, app_commands.CheckFailure):
        return
    original_error = getattr(error, "original", error)
    error_code = (
        original_error.code
        if isinstance(original_error, CheckmateFault)
        else "9999"
    )
    traceback.print_exception(
        type(original_error),
        original_error,
        original_error.__traceback__,
    )
    try:
        await send_error_response(interaction, error_code)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    checkmate_client.run(
        DISCORD_TOKEN,
        log_handler=None,
    )
