import re
from collections import Counter

def analyze_text(text):
    text = re.sub(r'[^\w\s]', '', text).lower()
    word_count = len(text.split())
    
    if word_count == 0:
        most_frequent_word = ''
    else:
        most_frequent_word = Counter(text.split()).most_common(1)[0][0]
        
    frequency_map = {word: count for word, count in Counter(text.split()).items() if len(word) >= 3}
    
    return {
        'total_word_count': word_count,
        'most_frequent_word': most_frequent_word,
        'frequency_map': frequency_map
    }