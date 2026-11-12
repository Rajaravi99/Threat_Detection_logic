import json
import subprocess

# 1. Configuration
SUBSCRIPTION_ID = "cd9863f7-ea88-4e01-a99b-739f9f9e0e40"
RESOURCE_GROUP = "rg-testsent-nlwe002"
WORKSPACE_NAME = "log-testsentdevops-nlwe003"

DRY_RUN = True
API_VERSION = "2025-09-01"

BASE_URL = (
    f"https://azure.com{SUBSCRIPTION_ID}"
    f"/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.OperationalInsights"
    f"/workspaces/{WORKSPACE_NAME}/providers/Microsoft.SecurityInsights/alertRules"
)

def run_az_rest(method, url, body=None):
  cmd = ["az", "rest", "--method", method, "--uri", url]
  if body:
    cmd.extend(["--body", json.dumps(body)])
  result = subprocess.run(cmd, capture_output=True, text=True)
  if result.returncode != 0:
    print(f"Azure CLI Error:\n{result.stderr}")
    raise SystemExit(1)
  return json.loads(result.stdout) if result.stdout else None

# 2. Fetch rules (uses your existing Cloud Shell login automatically)
print("Fetching detection rules...")
response = run_az_rest("GET", f"{BASE_URL}?api-version={API_VERSION}")
rules = response.get("value", [])
print(f"Found {len(rules)} rules.\n")

# 3. Process and rename
for rule in rules:
  rule_id = rule["name"]
  rule_kind = rule.get("kind")
  props = rule.get("properties", {})
  old_name = props.get("displayName")

  if rule_kind == "Fusion" or not old_name:
    continue

  # --- YOUR NAMING LOGIC ---
  new_name = old_name.replace("OldText", "NewText")
  # -------------------------

  if old_name == new_name:
    continue

  print(f"Match: '{old_name}'  -->  '{new_name}'")

  if DRY_RUN:
    continue

  props["displayName"] = new_name
  payload = {"kind": rule_kind, "etag": rule.get("etag"), "properties": props}

  try:
    run_az_rest("PUT", f"{BASE_URL}/{rule_id}?api-version={API_VERSION}", payload)
    print("  [OK] Updated")
  except subprocess.CalledProcessError as e:
    print(f"  [ERROR] {e.stderr.strip()}")

if DRY_RUN:
  print("\n--- DRY RUN COMPLETE: No changes were made. ---")
  print("Change DRY_RUN = False in the script to apply updates.")