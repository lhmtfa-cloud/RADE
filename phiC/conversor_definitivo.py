import os
import shutil
import torch
import ctranslate2
from transformers import AutoModelForCausalLM, AutoTokenizer

proxy_url = "http://servidor.seti:Rxtzef19@proxy01.seti.parana:8080"
os.environ['http_proxy'] = proxy_url
os.environ['https_proxy'] = proxy_url

caminho_origem = os.path.abspath("./app/models/phi_completo_merged")
caminho_temp = os.path.abspath("./app/models/phi_temp_f16")
caminho_destino_ct2 = os.path.abspath("./app/models/phi_ct2")

if not os.path.exists(caminho_origem):
    raise FileNotFoundError(f"ERRO: A pasta não foi encontrada em: {caminho_origem}")

model = AutoModelForCausalLM.from_pretrained(
    caminho_origem,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    device_map="auto",
    local_files_only=True 
)
tokenizer = AutoTokenizer.from_pretrained(
    caminho_origem, 
    trust_remote_code=True,
    local_files_only=True
)

for name, module in model.named_modules():
    if "rotary_emb" in name.lower():
        if not hasattr(module, "long_factor"):
            module.long_factor = None
        if not hasattr(module, "short_factor"):
            module.short_factor = None

model = model.to(torch.float16)


os.makedirs(caminho_temp, exist_ok=True)
model.save_pretrained(caminho_temp)
tokenizer.save_pretrained(caminho_temp)

for arquivo in os.listdir(caminho_origem):
    if arquivo.endswith(".py") or arquivo.endswith(".json"):
        caminho_arquivo_origem = os.path.join(caminho_origem, arquivo)
        caminho_arquivo_destino = os.path.join(caminho_temp, arquivo)
        if not os.path.exists(caminho_arquivo_destino):
            shutil.copy(caminho_arquivo_origem, caminho_arquivo_destino)

converter = ctranslate2.converters.TransformersConverter(
    caminho_temp,
    load_as_float16=True,
    trust_remote_code=True
)

try:
    converter.convert(
        caminho_destino_ct2,
        quantization="float16",
        force=True
    )
    print(f"\n🚀 SUCESSO ABSOLUTO! O modelo foi salvo em: {caminho_destino_ct2}")
except Exception as e:
    print(f"❌ Erro na conversão: {e}")