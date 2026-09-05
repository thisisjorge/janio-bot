import discord

class Colors:
    PRIMARY = discord.Color.blurple()
    SUCCESS = discord.Color.brand_green()
    ERROR = discord.Color.brand_red()
    WARNING = discord.Color.gold()
    INFO = discord.Color.teal()

def make_embed(title: str, description: str, color: discord.Color = Colors.PRIMARY) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)

def make_error_embed(description: str) -> discord.Embed:
    return discord.Embed(title="⚠️ Erro", description=description, color=Colors.ERROR)

def make_success_embed(description: str) -> discord.Embed:
    return discord.Embed(title="✅ Sucesso", description=description, color=Colors.SUCCESS)
