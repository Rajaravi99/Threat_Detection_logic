
import os
import requests
import pandas as pd
from azure.identity import AzureCliCredential

# =========================
# CONFIGURATION
# =========================
#
# Follow this process to run this script:
# 1. Please edit the variables according to your microsoft azure workspaces
# 2. open azure clude shell
# 3. In the tool bar click on mange files and upload this script
# 4. you can check if the script is uploaded or not by using command "ls -l ~", you can check the directry where your script is saved.
# 5. install python using command "pip install --user azure-identity requests pandas openpyxl" and check if python is installed or not by "python3 --version"
# 6. Once you are sure python is installed run the script using command "python3 /home/your user_name/this_script.py"
# 7. Once it is successfully run the xlsx file will be saved into the same directry with whatever filename you mention in the script.
# 8. Again click on manage files and use download your xlsx file by giving proper path and detailes, and then you are done.
#
SUBSCRIPTION_ID = "Your_Subscription_ID"
RESOURCE_GROUP = "Your_Resource_group_NAME"
WORKSPACE_NAME = "Your_workspace_NAME"

# Use a current supported Sentinel REST API version
API_VERSION = "2025-09-01" #or any supported Microsoft API version endpoint

# Save to clouddrive so the file persists in Cloud Shell
OUTPUT_FILE = os.path.expanduser("/home/ravi-nandan_ray/Challhoub_Analytics_Rules.xlsx")


def get_access_token():
    """
    Uses the Azure identity already signed in to Azure Cloud Shell.
    """
    credential = AzureCliCredential()
    token = credential.get_token("https://management.azure.com/.default")
    return token.token


def safe_join(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value


def flatten_rule(rule):
    props = rule.get("properties", {}) or {}
    incident_cfg = props.get("incidentConfiguration", {}) or {}
    grouping_cfg = incident_cfg.get("groupingConfiguration", {}) or {}

    return {
        "RuleId": rule.get("name"),
        "RuleKind": rule.get("kind"),
        "DisplayName": props.get("displayName"),
        "Description": props.get("description"),
        "Enabled": props.get("enabled"),
        "Severity": props.get("severity"),
        "Query": props.get("query"),
        "QueryFrequency": props.get("queryFrequency"),
        "QueryPeriod": props.get("queryPeriod"),
        "TriggerOperator": props.get("triggerOperator"),
        "TriggerThreshold": props.get("triggerThreshold"),
        "SuppressionEnabled": props.get("suppressionEnabled"),
        "SuppressionDuration": props.get("suppressionDuration"),
        "Tactics": safe_join(props.get("tactics")),
        "Techniques": safe_join(props.get("techniques")),
        "CreatedUtc": props.get("createdUtc"),
        "LastModifiedUtc": props.get("lastModifiedUtc"),
        "TemplateName": props.get("alertRuleTemplateName"),
        "TemplateVersion": props.get("templateVersion"),
        "CreateIncident": incident_cfg.get("createIncident"),
        "IncidentGroupingEnabled": grouping_cfg.get("enabled"),
        "ReopenClosedIncident": grouping_cfg.get("reopenClosedIncident"),
        "GroupingLookbackDuration": grouping_cfg.get("lookbackDuration"),
        "GroupingMatchingMethod": grouping_cfg.get("matchingMethod"),
        "EntityMappings": str(props.get("entityMappings")),
        "EventGroupingSettings": str(props.get("eventGroupingSettings")),
        "CustomDetails": str(props.get("customDetails")),
        "AlertDetailsOverride": str(props.get("alertDetailsOverride")),
        "ResourceId": rule.get("id"),
        "Etag": rule.get("etag"),
    }


def get_all_rules(token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.OperationalInsights/workspaces/{WORKSPACE_NAME}"
        f"/providers/Microsoft.SecurityInsights/alertRules"
        f"?api-version={API_VERSION}"
    )

    records = []

    while url:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()

        for rule in data.get("value", []):
            records.append(flatten_rule(rule))

        url = data.get("nextLink")

    return records


def export_to_excel(records, output_file):
    df = pd.DataFrame(records)

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="SentinelRules", index=False)

        ws = writer.book["SentinelRules"]

        # Basic formatting: freeze top row and auto-width
        ws.freeze_panes = "A2"
        for column_cells in ws.columns:
            max_len = 0
            col_letter = column_cells[0].column_letter
            for cell in column_cells:
                try:
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                except Exception:
                    pass
            ws.column_dimensions[col_letter].width = min(max_len + 2, 60)

    print(f"Exported {len(df)} rules to: {output_file}")


if __name__ == "__main__":
    try:
        token = get_access_token()
        rules = get_all_rules(token)
        export_to_excel(rules, OUTPUT_FILE)
    except Exception as e:
        print(f"Error: {e}")
        raise
