"""临时冒烟测试 — 验证后删除"""
from gap_calculator import GapCalculator
from datetime import datetime, timedelta
import json

t0 = datetime(2025, 6, 1, 8, 0, 0)
records = []
dist = 0.0
alt = 100.0
for i in range(100):
    ts = t0 + timedelta(seconds=i * 10)
    dist += 30.0
    alt += 1.5
    records.append({
        'altitude': alt,
        'distance': dist,
        'heart_rate': 140 + (i % 10),
        'timestamp': ts,
    })

gc = GapCalculator(smooth_window=5)
result = gc.calculate(records)

print("source:", result["source"])
print("smoothed_altitude[:5]:", result["smoothed_altitude"][:5])
print("grade_curve[:5]:", result["grade_curve"][:5])
print("gap_curve[:5]:", result["gap_curve"][:5])
print("efficiency_curve[:5]:", result["efficiency_curve"][:5])

valid_gaps = [g for g in result["gap_curve"] if g is not None]
valid_grades = [g for g in result["grade_curve"] if g is not None]
print("valid GAP points:", len(valid_gaps))
print("valid grade points:", len(valid_grades))
if valid_grades:
    print("avg grade:", sum(valid