import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import Api

app = Api()
res = app.calculate_advanced_radar_metrics()
print(res)
