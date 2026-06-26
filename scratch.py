from app.scoring import combine_signals, classify
print(classify(combine_signals(0.95, 0.90)))  # -> ('likely_ai', ~0.93)
print(classify(combine_signals(0.10, 0.15)))  # -> ('likely_human', ~0.88)
print(classify(combine_signals(0.55, 0.60)))  # -> ('uncertain', ~0.89... wait, check)