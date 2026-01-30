import os
os.environ['GOOGLE_CLOUD_PROJECT'] = 'jnu-rise-edu-147'

from google.cloud import aiplatform

aiplatform.init(project='jnu-rise-edu-147', location='us-central1')

print("Matching Engine Endpoint 목록:")
print("="*80)

endpoints = aiplatform.MatchingEngineIndexEndpoint.list()

if not endpoints:
    print("❌ Endpoint가 하나도 없습니다!")
else:
    for i, ep in enumerate(endpoints, 1):
        print(f"\n[{i}] Endpoint")
        print(f"  Display Name: {ep.display_name}")
        print(f"  Resource Name: {ep.resource_name}")
        print(f"  Public Endpoint: {ep.public_endpoint_domain_name if hasattr(ep, 'public_endpoint_domain_name') else 'N/A'}")
        
        # Check deployed indexes
        print(f"  Deployed Indexes:")
        if hasattr(ep, 'deployed_indexes') and ep.deployed_indexes:
            for dep_idx in ep.deployed_indexes:
                print(f"    - ID: {dep_idx.id}")
                print(f"      Index: {dep_idx.index if hasattr(dep_idx, 'index') else 'N/A'}")
        else:
            print("    (없음)")

print("\n" + "="*80)
