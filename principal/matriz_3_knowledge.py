import re
import random
from collections import Counter, defaultdict

def treinar_conhecimento(text: str) -> dict:
    transitions = defaultdict(Counter)
    tokens = re.findall(r"[\w']+|[.,!?;]", text.lower())
    for i in range(len(tokens) - 2):
        state = (tokens[i], tokens[i+1])
        next_state = tokens[i+2]
        transitions[state][next_state] += 1
    return transitions

def gerar_pensamento(start_state: tuple, transitions: dict, max_length: int = 30) -> list:
    if start_state not in transitions:
        return list(start_state)

    current_state = start_state
    thought = list(start_state)
    
    for _ in range(max_length):
        next_options = transitions.get(current_state)
        if not next_options:
            break 
        
        choices = list(next_options.keys())
        weights = list(next_options.values())
        next_word = random.choices(choices, weights=weights, k=1)[0]
        
        thought.append(next_word)
        
        if next_word in [".", "!", "?"]:
            break
            
        current_state = (current_state[1], next_word)
        
    return thought