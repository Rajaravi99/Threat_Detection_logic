# The process to run this script is as follows:
# 1. Ensure you have the Azure CLI installed and are logged in with `az login`.
# 2. Make sure you have the required Python packages installed. You can install them using pip:
#    ```
#    pip install azure-identity azure-mgmt-monitor
#    ```
# 3. Run the script in an environment where you have access to the Azure subscription and resource group.
# 4. Replace the `AZURE_SUBSCRIPTION_ID` and `SENTINEL_RESOURCE_GROUP` variables with your actual Azure subscription ID and the resource group name where your DCRs are located.

import os
import json
import csv
import importlib
from azure.identity import DefaultAzureCredential
from azure.identity import DefaultAzureCredential
from azure.mgmt.monitor import MonitorManagementClient

 # REPLACE THESE VALUES WITH YOUR AZURE DETAILS
AZURE_SUBSCRIPTION_ID = "put your subscription id here"
SENTINEL_RESOURCE_GROUP = "put your resource group name here"
# This automatically checks for your local 'az login' session
credential = DefaultAzureCredential() 
monitor_client = MonitorManagementClient(credential, AZURE_SUBSCRIPTION_ID)

def extract_dcrs_from_resource_group(AZURE_SUBSCRIPTION_ID, resource_group_name):
    print(f"Connecting to Subscription: {AZURE_SUBSCRIPTION_ID} via Cloud Shell Identity...")
    
    # Authenticate implicitly using Cloud Shell's managed context
    credential = DefaultAzureCredential()
    monitor_client = MonitorManagementClient(credential, AZURE_SUBSCRIPTION_ID)
    
    print(f"Fetching DCRs from '{resource_group_name}'...")
    dcr_iterable = monitor_client.data_collection_rules.list_by_resource_group(resource_group_name)
    
    dcrs_extracted = []
    
    for dcr in dcr_iterable:
        dcr_data = {
            "name": dcr.name,
            "id": dcr.id,
            "location": dcr.location,
            "immutable_id": dcr.immutable_id,
            "kind": dcr.kind,
            "data_sources": dcr.data_sources.as_dict() if dcr.data_sources else None,
            "destinations": dcr.destinations.as_dict() if dcr.destinations else None,
            "data_flows": [flow.as_dict() for flow in dcr.data_flows] if dcr.data_flows else []
        }
        dcrs_extracted.append(dcr_data)
        print(f" -> Extracted: {dcr.name}")
        
    return dcrs_extracted

if __name__ == "__main__":
    
    extracted_rules = extract_dcrs_from_resource_group(AZURE_SUBSCRIPTION_ID, SENTINEL_RESOURCE_GROUP)
    # print(f"{extracted_rules}")
    
    # output_filename = f"DCRs_{SENTINEL_RESOURCE_GROUP}.json"
    # with open(output_filename, "w") as f:
    #     json.dump(extracted_rules, f, indent=4)
        
    # print(f"\nSuccess! Total {len(extracted_rules)} DCRs saved to {output_filename}")

    with open(f"DCRs_{SENTINEL_RESOURCE_GROUP}.csv", "w", newline="") as csvfile:
        fieldnames = ["name", "id", "location", "immutable_id", "kind", "data_sources", "destinations", "data_flows"]
        print(f'{fieldnames}\n')
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for dcr in extracted_rules:
            writer.writerow(dcr)
