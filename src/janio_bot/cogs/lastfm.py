import discord
from discord.ext import commands
from janio_bot.services.lastfm import lastfm_service
from janio_bot.database import Database

class LastfmCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    @commands.group(name="lastfm", invoke_without_command=True)
    async def lastfm(self, ctx: commands.Context) -> None:
        await ctx.send("Use `j!lastfm login <usuario> <senha>` na minha DM para linkar sua conta!")

    @lastfm.command(name="login")
    async def login(self, ctx: commands.Context, username: str, password: str) -> None:
        if not isinstance(ctx.channel, discord.DMChannel):
            await ctx.message.delete()
            await ctx.send("⚠️ Por segurança, envie esse comando apenas na minha DM (mensagem direta)!", delete_after=10)
            return

        async with ctx.typing():
            try:
                session_key = await lastfm_service.generate_session_key(username, password)
                await self.db.set_lastfm_session(ctx.author.id, session_key)
                await ctx.send("✅ Conta do Last.fm vinculada com sucesso! Agora você fará scrobble automático nas calls de voz.")
            except Exception as e:
                await ctx.send(f"❌ Erro ao logar no Last.fm. Verifique seu usuário e senha. ({e})")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LastfmCog(bot, bot.database)) # type: ignore
