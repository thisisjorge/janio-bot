# Hospedagem

## Opção gratuita permanente: este PC

O projeto inclui scripts para iniciar o bot automaticamente no login do
Windows. Depois de configurar `.env`:

```powershell
.\scripts\install-windows-task.ps1
```

O PC precisa permanecer ligado e conectado. Os logs ficam em
`logs/janio-bot.log`.

## Zaroz Cloud

O [catálogo oficial do Zaroz](https://zaroz.cloud/en/catalog/b62b5feb-a9b6-481e-9809-79aaf0649885)
anuncia teste grátis, Python 3.12+, armazenamento persistente, reinício
automático e um plano Micro com 1 GB de RAM e 2 GB de disco. A página pública
não informa a duração do teste; confirme no checkout se a oferta disponível na
conta é realmente de 365 dias e custa `€0`.

Os termos dizem que testes podem mudar ou ser retirados e que pedidos podem
renovar automaticamente. Antes de concluir:

1. confirme preço atual `€0`, duração e data final;
2. não cadastre cartão se a intenção for custo zero;
3. desative renovação paga, se ela vier habilitada;
4. exporte backups consistentes do banco.

Para copiar o SQLite manualmente, pare o bot primeiro e então copie todo o
diretório `data/`. Não copie somente `janio.sqlite3` enquanto o processo estiver
ativo, porque transações recentes podem estar nos arquivos WAL. No Zaroz,
prefira também os snapshots/slots de backup oferecidos pelo serviço.

### Configuração do serviço

- Runtime: Python 3.12 ou superior
- Build/install: `python -m pip install .`
- Start command: `python -m janio_bot`
- Diretório persistente: `data/`

Variáveis obrigatórias:

```text
DISCORD_TOKEN=<segredo configurado somente no painel>
JANIO_MODE=community
DATABASE_PATH=data/janio.sqlite3
SYNC_COMMANDS=true
```

Opcional durante desenvolvimento:

```text
TEST_GUILD_ID=<id do servidor de teste>
```

Sem `TEST_GUILD_ID`, os comandos são sincronizados globalmente.

Para o modo `league`, troque `JANIO_MODE` e configure `RIOT_API_KEY` se quiser
usar `/lol jogador`.

Não envie `.env` ao provedor. Cadastre cada segredo no painel de variáveis.

### Música

Antes de considerar o deploy concluído, confira no console:

```sh
ffmpeg -version
deno --version
```

O catálogo lista Deno como runtime compatível, mas não documenta publicamente
se FFmpeg e Deno coexistem no ambiente Python. Sem os dois, comandos gerais
funcionam, mas a música por YouTube não está validada. O `Dockerfile` do projeto
inclui ambos para provedores que aceitam imagens Docker.
