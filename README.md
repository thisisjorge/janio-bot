# Janio Bot

Bot de Discord em Python com dois modos de execução:

- pontos virtuais por servidor, bônus diário e ranking;
- no modo `community`: previsões com duas opções, pote proporcional,
  cancelamento e registro interno;
- no modo `league`: builds, runas, Riot ID e ranks;
- aviso configurável a cada 3 minutos e 30 segundos;
- fila de música em canal de voz.

> Os pontos não podem ser comprados, vendidos, transferidos, sacados ou trocados
> por prêmio. O recurso é uma brincadeira de previsões, sem valor real.

## Modos e política da Riot

A [política atual da Riot](https://developer.riotgames.com/policies/general)
proíbe betting/gambling em produtos do ecossistema. Como redução de risco, o
Janio Bot não carrega previsões com pontos e integrações de LoL na mesma
instância:

- `JANIO_MODE=community` habilita `/aposta` e não carrega `/lol`;
- `JANIO_MODE=league` habilita `/lol` e não carrega `/aposta`.

Essa separação técnica não equivale a uma aprovação da Riot. Para oferecer os
dois conjuntos, use duas aplicações Discord, dois tokens, dois processos/deploys
e caminhos de banco distintos. Não use marca ou dados de LoL na instância
`community` sem orientação da Riot. Um produto público que use dados da Riot
deve ser registrado e auditado no Developer Portal.

## Como os dados de LoL funcionam

Não existe uma API pública da Zoe para reutilizar. O código público da
[Zoe Discord Bot](https://github.com/Zoe-Discord-Bot/Zoe-Discord-Bot) está
arquivado e usa a API oficial da Riot por meio da biblioteca Java R4J.

O Janio Bot usa:

- [Riot Games API](https://developer.riotgames.com/) para `/lol jogador`;
- [Riot Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon) para
  catálogo, versão e imagens;
- [MetaBot.GG](https://metabot.gg/pt_BR/ai) para dados agregados de builds e
  runas atuais, sempre com o link de atribuição no embed.

Data Dragon não oferece uma relação confiável de “melhor build por campeão”.
Por isso o bot chama o resultado de **build observada**, não de recomendação
oficial.

## Requisitos

- Python 3.11 ou superior;
- FFmpeg no `PATH` para música;
- Deno 2.3+ ou Node.js 22+ para suporte completo do YouTube;
- uma aplicação no Discord Developer Portal;
- chave da Riot apenas se quiser usar `/lol jogador`.

No Windows deste projeto, Python 3.11, FFmpeg e Node.js 24 já foram detectados.
O container Docker já inclui FFmpeg e Deno.

## Configuração rápida

### 1. Criar o bot no Discord

1. Abra o [Discord Developer Portal](https://discord.com/developers/applications).
2. Clique em **New Application** e dê o nome `Janio Bot`.
3. Entre em **Bot**, crie o bot e use **Reset Token**.
4. Copie `.env.example` para `.env`.
5. Cole o token em `DISCORD_TOKEN`. Não envie esse token no chat ou no GitHub.
6. Em **Installation**, habilite os escopos `bot` e `applications.commands`.
7. Permissões recomendadas: View Channels, Send Messages, Embed Links, Read
   Message History, Connect e Speak.
8. Em **Bot > Privileged Gateway Intents**, habilite **Message Content Intent**.
9. Instale a aplicação no servidor.

O **Message Content Intent** é necessário para os comandos de texto com `!`.
Os slash commands continuam disponíveis mesmo que esse intent seja desabilitado.

### 2. Preparar o ambiente

PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edite `.env`. Os comandos são sempre registrados globalmente. Para que as
alterações também apareçam imediatamente em um servidor de desenvolvimento,
ative o modo desenvolvedor do Discord, copie o ID do servidor e preencha
`TEST_GUILD_ID`.

### 3. Iniciar

```powershell
python -m janio_bot
```

Ou com Docker:

```powershell
docker compose up --build -d
docker compose logs -f
```

### Rodar gratuitamente neste Windows

Depois de configurar `.env`, instale a tarefa de inicialização automática:

```powershell
.\scripts\install-windows-task.ps1
```

O bot inicia imediatamente e volta a iniciar a cada login do Windows, sem custo
de hospedagem. O PC precisa permanecer ligado e conectado à internet. Os logs
ficam em `logs/janio-bot.log`. Para remover:

```powershell
.\scripts\uninstall-windows-task.ps1
```

## Comandos

Cada comando pode ser usado como slash command ou como comando de texto com `!`:

| Grupo | Slash | Texto |
|---|---|---|
| Geral | `/janio`, `/ping` | `!janio`, `!ping`, `!ajuda` |
| Pontos | `/pontos saldo`, `/pontos diario`, `/pontos ranking`, `/pontos dar` | `!pontos saldo`, `!pontos diario`, `!pontos ranking`, `!pontos dar` |
| Previsões | `/aposta criar`, `/aposta apostar`, `/aposta ver`, `/aposta abertas`, `/aposta fechar`, `/aposta resolver`, `/aposta cancelar` | os mesmos nomes após `!aposta` |
| League | `/lol build`, `/lol runas`, `/lol jogador` | `!lol build`, `!lol runas`, `!lol jogador` |
| Aviso | `/aviso configurar`, `/aviso ativar`, `/aviso desativar`, `/aviso status`, `/aviso testar` | os mesmos nomes após `!aviso` |
| Música | `/musica tocar`, `/musica fila`, `/musica pausar`, `/musica continuar`, `/musica pular`, `/musica parar`, `/musica sair` | os mesmos nomes após `!musica` |

Use `!ajuda` para ver os comandos comuns e `!ajuda moderacao` para ver os
comandos que exigem **Manage Server**. Quando um argumento tem espaços, coloque-o
entre aspas. Exemplo:

```text
!aposta criar "A equipe azul vence?" "Sim" "Não" 10
!musica tocar minha música favorita
```

O grupo `/aposta` existe somente no modo `community`; o grupo `/lol`, somente no
modo `league`.

Ao trocar o modo de uma aplicação já instalada, defina `SYNC_COMMANDS=true` na
primeira inicialização para remover os comandos antigos e sincronizar os novos.
Comandos globais podem levar algum tempo para propagar. É preferível não
reutilizar a mesma aplicação Discord entre os dois modos.

Criar, fechar, resolver ou cancelar previsão e configurar o aviso exigem
**Manage Server**. Cada pessoa pode apostar uma vez por mercado. Se ninguém
escolher a opção vencedora, o bot devolve todas as apostas.

### Exemplo de previsão

```text
/aposta criar
  titulo: A equipe azul vence o amistoso?
  opcao_a: Sim
  opcao_b: Não
  duracao_minutos: 10

/aposta apostar mercado:1 opcao:A valor:250
/aposta fechar mercado:1
/aposta resolver mercado:1 vencedora:A
```

### Aviso de 3 minutos e 30 segundos

O aviso não começa sozinho porque o bot precisa saber qual canal deve receber
as mensagens. Depois de instalar o bot, uma pessoa com **Manage Server** deve
configurá-lo uma vez:

```text
/aviso configurar canal:#geral intervalo_segundos:210 mensagem:Lembrete: confira a próxima partida!
```

O bot bloqueia menções como `@everyone` nessa mensagem.

## Variáveis de ambiente

| Nome | Obrigatória | Padrão |
|---|---:|---|
| `DISCORD_TOKEN` | sim | — |
| `JANIO_MODE` | não | `community` |
| `TEST_GUILD_ID` | não | vazio; sync somente global |
| `RIOT_API_KEY` | só para `/lol jogador` | — |
| `DATABASE_PATH` | não | `data/janio.sqlite3` |
| `DEFAULT_POINTS` | não | `1000` |
| `DAILY_POINTS` | não | `250` |
| `DEFAULT_ANNOUNCEMENT_INTERVAL_SECONDS` | não | `210` |
| `DEFAULT_ANNOUNCEMENT_MESSAGE` | não | `Hora do palpite!` |
| `FFMPEG_PATH` | não | `ffmpeg` |
| `SYNC_COMMANDS` | não | `true` |
| `LOG_LEVEL` | não | `INFO` |

Chaves de desenvolvimento da Riot expiram e bots públicos precisam seguir o
processo de registro/production key. Consulte a
[documentação do portal](https://developer.riotgames.com/docs/portal).

## Testes e qualidade

```powershell
ruff check .
mypy
pytest --cov=janio_bot
```

Os testes cobrem saldo, corrida de gastos simultâneos, apostas duplicadas,
mercado fechado, cancelamento, ausência de vencedores, arredondamento do pote,
agendamento, rotas da Riot e parsing das APIs externas.

## GitHub

Leia [CONTRIBUTING.md](CONTRIBUTING.md). A CI roda lint, tipos, testes e build
do Docker em cada Pull Request. `.env` e o banco local ficam fora do Git.

As opções de execução gratuita e o checklist específico do Zaroz estão em
[HOSTING.md](HOSTING.md).

## Avisos legais

Janio Bot isn't endorsed by Riot Games and doesn't reflect the views or
opinions of Riot Games or anyone officially involved in producing or managing
Riot Games properties. Riot Games, and all associated properties are
trademarks or registered trademarks of Riot Games, Inc.

Os dados de build vêm do MetaBot.GG e carregam atribuição para a página
específica. Música deve ser usada somente com conteúdo que você tem direito de
reproduzir e de acordo com os termos do provedor.
