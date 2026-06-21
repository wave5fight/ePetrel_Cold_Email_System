import random
import re

def parse_spintax(text):
    """递归解析 {A|B|C} 格式的 Spintax 文本"""
    pattern = re.compile(r'\{([^{}]+)\}')
    while True:
        match = next((item for item in pattern.finditer(text) if '|' in item.group(1)), None)
        if match is None:
            break
        options = match.group(1).split('|')
        text = text.replace(match.group(0), random.choice(options), 1)
    return text
