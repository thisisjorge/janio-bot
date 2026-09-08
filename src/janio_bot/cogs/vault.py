import re
import os
import httpx
import discord
from discord import app_commands
from discord.ext import commands

from janio_bot.bot import JanioBot
from janio_bot.ui import make_embed, make_error_embed, make_success_embed, Colors
from janio_bot.services.drive_service import drive_vault_service

def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

class VaultCog(
    commands.Cog,
    name="musicvault",
    description="Gerenciamento do cofre de músicas do Janiobot no Google Drive."
):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    @commands.group(name="musicvault", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def musicvault(self, ctx: commands.Context) -> None:
        await ctx.send("Use `j!musicvault list`, `info`, `remove` ou `stats`.")

    @musicvault.command(name="list", description="Lista as músicas armazenadas no cofre do Drive.")
    @commands.has_permissions(administrator=True)
    async def list_vault(self, ctx: commands.Context) -> None:
        async with ctx.typing():
            items = await drive_vault_service.list_vault()
        
        if not items:
            await ctx.send(embed=make_error_embed("O cofre está vazio."))
            return
            
        lines = []
        for item in items:
            name = item.get('name', 'Desconhecido')
            size = int(item.get('size', 0)) / (1024 * 1024)
            app_props = item.get('appProperties', {})
            video_id = app_props.get('youtubeVideoId', 'N/A')
            lines.append(f"• **{name}** (`{video_id}`) - {size:.2f} MB")
            
        embed = make_embed(
            title="☁️ Músicas no Cofre (Google Drive)",
            description="\n".join(lines) if len(lines) <= 20 else "\n".join(lines[:20]) + f"\n\n*...e mais {len(lines) - 20} arquivos.*",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @musicvault.command(name="info", description="Busca informações de uma música no cofre pelo link do YouTube.")
    @commands.has_permissions(administrator=True)
    async def info_vault(self, ctx: commands.Context, url: str) -> None:
        async with ctx.typing():
            match = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
            if not match:
                await ctx.send(embed=make_error_embed("URL do YouTube inválida."))
                return
            
        video_id = match.group(1)
        items = await drive_vault_service.list_vault()
        for item in items:
            if item.get('appProperties', {}).get('youtubeVideoId') == video_id:
                name = item.get('name')
                size = int(item.get('size', 0)) / (1024 * 1024)
                
                embed = make_embed(
                    title="☁️ Informações do Cofre",
                    description=f"**Arquivo:** {name}\n**ID do YouTube:** `{video_id}`\n**Tamanho:** {size:.2f} MB",
                    color=Colors.SUCCESS
                )
                await ctx.send(embed=embed)
                return
                
        await ctx.send(embed=make_error_embed("Esta música não está no cofre."))

    @musicvault.command(name="remove", description="Remove uma música do cofre pelo link do YouTube.")
    @commands.has_permissions(administrator=True)
    async def remove_vault(self, ctx: commands.Context, url: str) -> None:
        async with ctx.typing():
            match = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
            if not match:
                await ctx.send(embed=make_error_embed("URL do YouTube inválida."))
                return
            
        video_id = match.group(1)
        success = await drive_vault_service.remove_by_video_id(video_id)
        
        if success:
            await ctx.send(embed=make_success_embed(f"A música do vídeo `{video_id}` foi removida do cofre com sucesso."))
        else:
            await ctx.send(embed=make_error_embed("A música não foi encontrada no cofre ou ocorreu um erro ao deletar."))

    @musicvault.command(name="stats", description="Mostra estatísticas do cofre.")
    @commands.has_permissions(administrator=True)
    async def stats_vault(self, ctx: commands.Context) -> None:
        async with ctx.typing():
            items = await drive_vault_service.list_vault()
        
        total_size = sum(int(item.get('size', 0)) for item in items) / (1024 * 1024)
        count = len(items)
        
        embed = make_embed(
            title="📊 Estatísticas do Cofre (Google Drive)",
            description=f"**Total de Músicas:** {count}\n**Espaço Utilizado:** {total_size:.2f} MB",
            color=Colors.PRIMARY
        )
        await ctx.send(embed=embed)


class AddMusicCog(commands.Cog):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    @commands.command(name="addmusic", description="Adiciona uma música exclusiva ao cofre do Google Drive.")
    @commands.has_permissions(administrator=True)
    async def add_music(self, ctx: commands.Context, url: str) -> None:
        if not ctx.message.attachments:
            await ctx.send(embed=make_error_embed("Você precisa anexar o arquivo MP3 da música na mesma mensagem!"))
            return
            
        arquivo = ctx.message.attachments[0]
        
        if not arquivo.content_type or not arquivo.content_type.startswith('audio/'):
            await ctx.send(embed=make_error_embed("O arquivo anexado deve ser um áudio válido (ex: MP3)."))
            return

        async with ctx.typing():
            match = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
            if not match:
                await ctx.send(embed=make_error_embed("URL do YouTube inválida."))
                return
            
        video_id = match.group(1)
        
        # 1. Verifica duplicata no Drive
        items = await drive_vault_service.list_vault()
        for item in items:
            if item.get('appProperties', {}).get('youtubeVideoId') == video_id:
                await ctx.send(embed=make_error_embed(f"⚠️ Essa música (ID: `{video_id}`) já existe no cofre."))
                return

        # 2. Puxa Metadata do YouTube (oEmbed)
        title = "Unknown Title"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json", timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title", title)
        except Exception:
            pass

        # 3. Baixa arquivo temporário
        temp_path = f"/tmp/janiobot/upload_{video_id}.mp3"
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        await arquivo.save(temp_path)
        
        # 4. Faz upload pro Google Drive
        success = await drive_vault_service.upload_file(temp_path, video_id, title)
        
        # 5. Cleanup temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if success:
            embed = make_embed(
                title="✅ Música adicionada ao cofre",
                description=f"🎵 **{title}**\n☁️ Google Drive\n💾 {arquivo.size / (1024*1024):.2f} MB",
                color=Colors.SUCCESS
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(embed=make_error_embed("Erro ao realizar o upload para o Google Drive. Verifique os logs do bot."))

async def setup(bot: JanioBot) -> None:
    await bot.add_cog(VaultCog(bot))
    await bot.add_cog(AddMusicCog(bot))
