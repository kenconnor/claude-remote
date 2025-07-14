#!/usr/bin/env python3

import re
from pathlib import Path
from datetime import datetime

def test_question_detection():
    """Test the question detection logic"""
    
    # Sample Claude response with questions
    sample_logs = """
I'd be happy to help you create a Python calculator! However, I need some clarification to make sure I build exactly what you need:

1. What specific arithmetic operations should it support? (addition, subtraction, multiplication, division, or more advanced operations like exponents, square roots?)

2. Should this be a command-line interface or a GUI application?

3. Do you need error handling for invalid inputs?

Let me know your preferences and I'll create the calculator accordingly.
"""

    # Question detection patterns
    question_patterns = [
        r'(?:質問|Question|クエスチョン)[:：]?\s*(.+)',
        r'(?:確認|Confirm|コンファーム)[:：]?\s*(.+)', 
        r'(?:詳細|Details|詳しく)[:：]?\s*(.+)',
        r'(?:どの|Which|どちら).*[？?]',
        r'(?:何|What|なに).*[？?]',
        r'(?:いつ|When|どこ|Where|なぜ|Why|どうやって|How).*[？?]',
        r'(?:してください|お聞かせください|教えてください|please|Please).*[？?]?',
        r'(?:必要です|required|需要|ください).*(?:情報|information|詳細|details)',
    ]
    
    questions = []
    
    # Extract questions using patterns
    for pattern in question_patterns:
        matches = re.findall(pattern, sample_logs, re.IGNORECASE | re.MULTILINE)
        questions.extend(matches)
    
    # Direct question detection (lines ending with ? or ？)
    for line in sample_logs.split('\n'):
        line = line.strip()
        if line and (line.endswith('?') or line.endswith('？')):
            if len(line) > 10 and len(line) < 200:
                questions.append(line)
    
    # Remove duplicates
    unique_questions = []
    for q in questions:
        q = q.strip()
        if q and len(q) > 5 and q not in unique_questions:
            unique_questions.append(q)
    
    print(f"Detected {len(unique_questions)} questions:")
    for i, q in enumerate(unique_questions, 1):
        print(f"{i}. {q}")
    
    return unique_questions

if __name__ == "__main__":
    test_question_detection()