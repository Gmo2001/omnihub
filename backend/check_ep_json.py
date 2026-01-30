import os
os.environ['GOOGLE_CLOUD_PROJECT'] = 'jnu-rise-edu-147'

from google.cloud import aiplatform
import json

aiplatform.init(project='jnu-rise-edu-147', location='us-central1')

endpoints = aiplatform.MatchingEngineIndexEndpoint.list()

result = {
    "total_endpoints": len(endpoints),
    "endpoints": []
}

for ep in endpoints:
    ep_info = {
        "display_name": ep.display_name,
        "resource_name": ep.resource_name,
        "deployed_indexes": []
    }
    
    if hasattr(ep, 'deployed_indexes') and ep.deployed_indexes:
        for dep_idx in ep.deployed_indexes:
            dep_info = {
                "id": dep_idx.id if hasattr(dep_idx, 'id') else 'N/A',
                "index": dep_idx.index if hasattr(dep_idx, 'index') else 'N/A'
            }
            ep_info["deployed_indexes"].append(dep_info)
    
    result["endpoints"].append(ep_info)

with open("endpoint_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(json.dumps(result, indent=2, ensure_ascii=False))
