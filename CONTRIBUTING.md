# Como contribuir

Este projeto foi pensado para o Bruno e outras pessoas aprenderem GitHub fazendo.

1. Faça um fork do repositório.
2. Clone seu fork: `git clone URL_DO_SEU_FORK`.
3. Crie uma branch: `git switch -c feat/minha-melhoria`.
4. Instale o ambiente: `pip install -e ".[dev]"`.
5. Faça a alteração e rode `ruff check .`, `mypy` e `pytest`.
6. Crie o commit: `git add . && git commit -m "feat: descreva a melhoria"`.
7. Envie a branch: `git push -u origin feat/minha-melhoria`.
8. Abra um Pull Request no GitHub e explique o que mudou.

Nunca envie `.env`, tokens do Discord, chaves da Riot, cookies ou banco SQLite.

## Convenção simples de commits

- `feat:` recurso novo
- `fix:` correção
- `docs:` documentação
- `test:` testes
- `refactor:` mudança interna sem alterar comportamento

## Antes do Pull Request

```powershell
ruff check .
mypy
pytest
```
