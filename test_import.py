import sys
from main import Api

api = Api()
for path in ["test_naive.gpx", "test_aware.gpx", "./local_tracks/594207408_ACTIVITY.fit"]:
    print(f"Testing {path}...")
    res = api.import_track(file_path=path, duplicate_action="replace")
    print(f"Result: {res}")
    if not res.get("ok"):
        print(f"FAILED: {res}")
        sys.exit(1)
print("All imports successful.")
