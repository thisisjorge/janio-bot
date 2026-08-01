# Segurança

Não abra uma issue pública contendo token, chave, cookie, dado pessoal ou
detalhe explorável. Revogue imediatamente qualquer segredo exposto.

Para relatar uma vulnerabilidade de forma privada, abra um aviso de segurança
em [GitHub Security Advisories](https://github.com/thisisjorge/janio-bot/security/advisories/new).
Inclua o impacto, os passos mínimos para reproduzir e, se possível, uma sugestão
de correção. Não publique detalhes antes da análise dos mantenedores.

Segredos ficam apenas no `.env` local ou em GitHub Actions Secrets. O arquivo
`.env` já está ignorado pelo Git.

O comando de música aceita busca e URLs do YouTube, mas rejeita outros hosts e
esquemas para reduzir risco de SSRF. Reproduza somente conteúdo que você tem
direito de usar e respeite os termos do provedor.
