#!/usr/bin/env python3

import sys
import subprocess
import argparse
import csv
import json
import requests


# ============================================================
# Auto-install required packages if missing
# ============================================================

def install_package(package_name):
    print(f"[+] Installing missing package: {package_name}")
    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--user",
        "--upgrade",
        package_name
    ])


try:
    import requests
except ImportError:
    install_package("requests")
    import requests


# ============================================================
# Configuration Section
# ============================================================

# Option 1:
# Paste your Log Analytics Workspace ID / Customer ID here.
# Example:
# WORKSPACE_ID = "00000000-0000-0000-0000-000000000000"
#
# If you leave it blank, pass it while running the script:
# python3 sentinel_log_export.py --workspace-id "<WORKSPACE_ID>"

WORKSPACE_ID = "Your workspace ID for the log analytics workspace"


# ============================================================
# Embedded KQL Query
# Modify this query as per your requirement.
# ============================================================

KQL_QUERY = r"""
Your KQL query which you want to use to export logs
"""


# ============================================================
# Functions
# ============================================================

def check_az_login():
    print("[+] Checking Azure CLI login status...")

    try:
        result = subprocess.run(
            ["az", "account", "show", "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )

        account = json.loads(result.stdout)
        print(f"[+] Azure account detected: {account.get('user', {}).get('name', 'Unknown')}")
        print(f"[+] Subscription: {account.get('name', 'Unknown')}")

    except subprocess.CalledProcessError:
        print("[!] Azure CLI is not logged in.")
        print("[!] In Azure Cloud Shell, please run:")
        print("    az login")
        sys.exit(1)


def get_access_token():
    print("[+] Getting access token using Azure CLI...")

    try:
        result = subprocess.run(
            [
                "az",
                "account",
                "get-access-token",
                "--resource",
                "https://api.loganalytics.io",
                "-o",
                "json"
            ],
            capture_output=True,
            text=True,
            check=True
        )

        token_data = json.loads(result.stdout)
        return token_data["accessToken"]

    except subprocess.CalledProcessError as error:
        print("[!] Failed to get Azure access token.")
        print(error.stderr)
        sys.exit(1)


def run_kql_query(workspace_id, access_token):
    print("[+] Running KQL query against Log Analytics workspace...")

    url = f"https://api.loganalytics.azure.com/v1/workspaces/{workspace_id}/query"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "query": KQL_QUERY,
        "timespan": "P1D"
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        print("[!] Query failed.")
        print(f"[!] HTTP Status Code: {response.status_code}")
        print("[!] Response:")
        print(response.text)
        sys.exit(1)

    return response.json()


def export_results_to_csv(query_result, output_file):
    print("[+] Exporting results to CSV...")

    tables = query_result.get("tables", [])

    if not tables:
        print("[!] No tables returned from query.")
        return

    table = tables[0]
    columns = table.get("columns", [])
    rows = table.get("rows", [])

    if not rows:
        print("[!] Query completed successfully, but no rows were returned.")
        return

    column_names = [column["name"] for column in columns]

    with open(output_file, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(column_names)

        for row in rows:
            writer.writerow(row)

    print("[+] Export completed successfully.")
    print(f"[+] Rows exported: {len(rows)}")
    print(f"[+] Output file created: {output_file}")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Export Microsoft Sentinel / Log Analytics logs using embedded KQL query."
    )

    parser.add_argument(
        "--workspace-id",
        required=False,
        help="Log Analytics Workspace ID / Customer ID."
    )

    parser.add_argument(
        "--output",
        required=False,
        default="sentinel_logs_export.csv",
        help="CSV output file name. Default: sentinel_logs_export.csv"
    )

    args = parser.parse_args()

    workspace_id = args.workspace_id if args.workspace_id else WORKSPACE_ID

    if not workspace_id:
        print("[!] Workspace ID is missing.")
        print("[!] Either edit WORKSPACE_ID inside the script or run:")
        print("    python3 sentinel_log_export.py --workspace-id '<YOUR_WORKSPACE_ID>'")
        sys.exit(1)

    check_az_login()
    access_token = get_access_token()
    query_result = run_kql_query(workspace_id, access_token)
    export_results_to_csv(query_result, args.output)


if __name__ == "__main__":
    main()