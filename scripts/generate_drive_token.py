import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# Escopos necessários para ler, escrever e gerenciar arquivos criados pelo app
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def main():
    print("=" * 50)
    print("Gerador de Token do Google Drive para o Janiobot")
    print("=" * 50)
    print("\nSiga estes passos:")
    print("1. Crie as credenciais OAuth 2.0 (ID do cliente) no Google Cloud Console.")
    print("2. Baixe o arquivo JSON das credenciais.")
    print("3. Salve-o nesta pasta com o nome 'client_secret.json'.\n")
    
    if not os.path.exists('client_secret.json'):
        print("ERRO: 'client_secret.json' não encontrado!")
        print("Por favor, coloque o arquivo nesta pasta e rode o script novamente.")
        return

    print("Iniciando fluxo de autenticação...")
    print("Uma aba do navegador será aberta. Faça login com a conta Google do BOT.")
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            'client_secret.json', SCOPES)
        creds = flow.run_local_server(port=0)
        
        print("\n" + "=" * 50)
        print("AUTENTICAÇÃO BEM-SUCEDIDA!")
        print("=" * 50)
        print("Copie os valores abaixo e coloque no seu arquivo .env:\n")
        
        # Acessa os dados raw para extrair o Client ID e Secret do client_secret.json
        with open('client_secret.json', 'r') as f:
            client_data = json.load(f)
            web_data = client_data.get('installed', client_data.get('web', {}))
            client_id = web_data.get('client_id', '')
            client_secret = web_data.get('client_secret', '')
            
        print(f"GOOGLE_CLIENT_ID={client_id}")
        print(f"GOOGLE_CLIENT_SECRET={client_secret}")
        print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
        
        print("\n" + "=" * 50)
        print("ATENÇÃO: Nunca compartilhe o GOOGLE_REFRESH_TOKEN com ninguém!")
        print("Você pode excluir o 'client_secret.json' depois de copiar os dados acima.")
        print("=" * 50)
        
    except Exception as e:
        print(f"\nOcorreu um erro durante a autenticação: {e}")

if __name__ == '__main__':
    main()
