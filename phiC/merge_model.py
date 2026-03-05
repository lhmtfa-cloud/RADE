import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# ==========================================
# CONFIGURAÇÃO DE PROXY CORPORATIVO
# ==========================================
proxy_url = "http://servidor.seti:Rxtzef19@proxy01.seti.parana:8080"
os.environ['http_proxy'] = proxy_url
os.environ['https_proxy'] = proxy_url
os.environ['HTTP_PROXY'] = proxy_url
os.environ['HTTPS_PROXY'] = proxy_url

# Desativa a verificação de certificado SSL caso o proxy corporativo o bloqueie
os.environ['CURL_CA_BUNDLE'] = ""
os.environ['REQUESTS_CA_BUNDLE'] = ""
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ==========================================

# Caminhos
modelo_base_id = "microsoft/Phi-3-mini-4k-instruct"
caminho_lora = "./app/models/phi"  
caminho_saida = "./app/models/phi_completo_merged"

print("1. Carregando modelo base...")
modelo_base = AutoModelForCausalLM.from_pretrained(
    modelo_base_id, 
    torch_dtype=torch.float16, 
    trust_remote_code=True,
    resume_download=True
)
tokenizer = AutoTokenizer.from_pretrained(modelo_base_id, trust_remote_code=True)

print("2. Aplicando o Adapter LoRA...")
modelo_com_lora = PeftModel.from_pretrained(modelo_base, caminho_lora)

print("3. Fundindo os pesos (Merge)...")
modelo_final = modelo_com_lora.merge_and_unload()

print(f"4. Salvando o modelo completo em: {caminho_saida}")
modelo_final.save_pretrained(caminho_saida)
tokenizer.save_pretrained(caminho_saida)

print("Finalizado com sucesso!")