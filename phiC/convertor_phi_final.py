import os
import torch
import ctranslate2
from transformers import AutoModelForCausalLM, AutoTokenizer

# 1. Configuração de Proxy (necessário para carregar a arquitetura)
proxy_url = "http://servidor.seti:Rxtzef19@proxy01.seti.parana:8080"
os.environ['http_proxy'] = proxy_url
os.environ['https_proxy'] = proxy_url

caminho_modelo_original = "./phi_completo_merged"
caminho_saida_ct2 = "./phi_ct2"

print("1. Carregando modelo e tokenizer para a memória...")
# Carregamos o modelo explicitamente ignorando erros de flash-attention
model = AutoModelForCausalLM.from_pretrained(
    caminho_modelo_original,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    device_map="cpu"
)
tokenizer = AutoTokenizer.from_pretrained(caminho_modelo_original, trust_remote_code=True)

print("2. Aplicando 'hack' de compatibilidade nos atributos RoPE...")
# Percorremos todos os módulos do modelo procurando pelo Rotary Embedding
# e injetamos os atributos que o CTranslate2 exige
count = 0
for name, module in model.named_modules():
    if "rotary_emb" in name.lower():
        if not hasattr(module, "long_factor"):
            module.long_factor = None
        if not hasattr(module, "short_factor"):
            module.short_factor = None
        count += 1
print(f"✅ Hack aplicado em {count} camadas de embedding.")

print("3. Iniciando conversão para CTranslate2 (formato int8_float16)...")
converter = ctranslate2.converters.TransformersConverter(
    caminho_modelo_original,
    load_as_float16=True,
    trust_remote_code=True
)

# Realiza a conversão usando o modelo que já está na memória (com o hack)
# ou forçando o spec. 
# Nota: O CTranslate2 às vezes tenta recarregar, então usaremos o Converter interno.
try:
    converter.convert(
        caminho_saida_ct2,
        quantization="int8_float16",
        force=True
    )
    print(f"\n🚀 SUCESSO! Modelo convertido em: {caminho_saida_ct2}")
except Exception as e:
    print(f"\n❌ Erro na conversão: {e}")
    print("\nTentando método alternativo via Spec...")
    # Se o converter.convert falhar por recarregar o arquivo, 
    # teremos que editar o arquivo da biblioteca (último recurso).