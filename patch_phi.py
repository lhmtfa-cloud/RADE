import os

path = "phi_completo_merged/modeling_phi3.py"

with open(path, "r", encoding="utf-8") as f:
    linhas = f.readlines()

nova_lista = []
for linha in linhas:
    nova_lista.append(linha)
    # Quando encontrar a linha do inv_freq, injetamos as outras duas logo abaixo
    if "self.inv_freq = inv_freq" in linha:
        # Detecta a indentação automaticamente
        indent = linha[:linha.find("self")]
        if "long_factor" not in "".join(linhas): # Evita duplicar se rodar 2x
            nova_lista.append(f"{indent}self.long_factor = None\n")
            nova_lista.append(f"{indent}self.short_factor = None\n")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(nova_lista)

print("✅ Atributos injetados com sucesso no arquivo modeling_phi3.py!")