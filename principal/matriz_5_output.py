import re

def traduzir_para_humano(thought_tokens: list) -> str:
    output = " ".join(thought_tokens)
    output = re.sub(r'\s+([.,!?;])', r'\1', output)
    output = re.sub(r'^([.,!?;]\s*)', '', output) 
    return output.capitalize()