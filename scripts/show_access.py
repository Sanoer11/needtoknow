import json

company = json.load(open("data/company.json"))

for user in company["users"]:
    my_groups = set(user["groups"])
    print(f"\n{user['name']} ({user['role']}) - groups: {sorted(my_groups)}")

    for doc in company["documents"]:
        for sec in doc["sections"]:
            allowed = my_groups & set(sec["acl"])   # groups in common
            mark = "YES" if allowed else " - "
            print(f"  [{mark}] {doc['title']} > {sec['section']}")