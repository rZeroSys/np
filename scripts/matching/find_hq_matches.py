import pandas as pd
import requests
import csv
import os

API_KEY = os.environ.get("GOOGLE_API_KEY", "")
URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

df = pd.read_csv("/Users/forrestmiller/Desktop/building type by org/matching_groups.csv", low_memory=False)
orgs = df['hq_org'].unique()

match_file = open("/Users/forrestmiller/Desktop/building type by org/hq_matches.csv", 'w', newline='')
nomatch_file = open("/Users/forrestmiller/Desktop/building type by org/hq_no_match.csv", 'w', newline='')

mw = csv.writer(match_file)
mw.writerow(['hq_org','hq_address','matched_address','distance_meters','rank','id_building','bldg_sqft','org_owner','org_tenant'])

nw = csv.writer(nomatch_file)
nw.writerow(['hq_org','hq_address','closest_address'])

matches = 0
no_matches = 0

print(f"Processing {len(orgs)} orgs (max 5 candidates each)...")
print("-" * 60)

for i, org in enumerate(orgs):
    org_df = df[df['hq_org'] == org].sort_values('rank').head(5)
    hq = org_df.iloc[0]['hq_address']
    found = False

    print(f"\n[{i+1}/{len(orgs)}] {org}")
    print(f"    HQ: {hq}")

    for _, row in org_df.iterrows():
        rank = int(row['rank'])
        bldg = row['loc_address']

        try:
            r = requests.get(URL, params={"origins":hq,"destinations":bldg,"key":API_KEY,"mode":"walking"}, timeout=10).json()
            if r.get('status')=='OK' and r['rows'][0]['elements'][0].get('status')=='OK':
                dist = r['rows'][0]['elements'][0]['distance']['value']
                print(f"    #{rank}: {dist}m - {bldg[:50]}")

                if dist <= 20:
                    mw.writerow([org,hq,bldg,dist,rank,row['id_building'],row.get('bldg_sqft'),row.get('org_owner'),row.get('org_tenant')])
                    match_file.flush()
                    matches += 1
                    found = True
                    print(f"    >>> MATCH! <<<")
                    break
            else:
                print(f"    #{rank}: API error - {bldg[:50]}")
        except Exception as e:
            print(f"    #{rank}: Error {e}")

    if not found:
        nw.writerow([org,hq,org_df.iloc[0]['loc_address']])
        nomatch_file.flush()
        no_matches += 1
        print(f"    --- no match ---")

match_file.close()
nomatch_file.close()

print("\n" + "=" * 60)
print(f"DONE! {matches} matches, {no_matches} no match")
print(f"Results saved to hq_matches.csv and hq_no_match.csv")
