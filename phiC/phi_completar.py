import os
from huggingface_hub import hf_hub_download

# Configuração do seu proxy
proxy_url = "http://servidor.seti:Rxtzef19@proxy01.seti.parana:8080"
os.environ['http_proxy'] = proxy_url
os.environ['https_proxy'] = proxy_url

# Pasta onde está o seu modelo fundido
diretorio_destino = "./app/models/phi_completo_merged"

# Lista de arquivos de código necessários para o Phi-3
arquivos_necessarios = [
    "modeling_phi3.py",
    "configuration_phi3.py",
    "tokenizer_config.json" # Garante que as definições de tokens especiais estejam lá
]

print("Baixando arquivos de arquitetura faltantes...")

for arquivo in arquivos_necessarios:
    try:
        hf_hub_download(
            repo_id="microsoft/Phi-3-mini-4k-instruct",
            filename=arquivo,
            local_dir=diretorio_destino,
            local_dir_use_symlinks=False
        )
        print(f"✅ {arquivo} baixado com sucesso.")
    except Exception as e:
        print(f"❌ Erro ao baixar {arquivo}: {e}")

print("\nAgora tente rodar o comando ct2-transformers-converter novamente.")