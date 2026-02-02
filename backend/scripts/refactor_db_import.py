
import os
import re

TARGET_DIRS = [
    "backend/app/rag/steps",
    "backend/app/routers",
    "backend/app/services",
    "backend/app",
    "backend/app/utils"
]

def refactor_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = content
    
    # Pattern: from app.core.gcp_clients import ... db ...
    # We want to replace 'db' with 'get_firestore_client' in imports
    
    # 1. Imports Replacement (More robust regex)
    # Matches: from app.core.gcp_clients import A, db, B
    import_pattern = r"from app\.core\.gcp_clients import ([^\n]+)"
    
    def replace_import(match):
        imports = match.group(1)
        if "db" not in imports:
            return match.group(0)
            
        parts = [p.strip() for p in imports.split(",")]
        new_parts = []
        has_get_fs = "get_firestore_client" in parts
        
        for p in parts:
            if p == "db":
                if not has_get_fs:
                    new_parts.append("get_firestore_client")
                    has_get_fs = True
            else:
                new_parts.append(p)
                
        return f"from app.core.gcp_clients import {', '.join(new_parts)}"

    new_content = re.sub(import_pattern, replace_import, new_content)

    # 2. Assignment replacement (Class Init)
    new_content = new_content.replace("self.db = db", "self.db = get_firestore_client()")
    new_content = new_content.replace("self.db=db", "self.db = get_firestore_client()")
    
    # 3. Global usage replacement safely
    patterns = [
        (r'(?<!self\.)db\.collection\(', 'get_firestore_client().collection('),
        (r'(?<!self\.)db\.batch\(', 'get_firestore_client().batch('),
        (r'(?<!self\.)db\.transaction\(', 'get_firestore_client().transaction('),
        (r'(?<!self\.)db\.document\(', 'get_firestore_client().document('), # Sometimes used for ref
    ]
    
    for pat, repl in patterns:
        new_content = re.sub(pat, repl, new_content)

    if new_content != content:
        print(f"Refactoring: {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

def main():
    root_dir = os.path.abspath(".")
    for target in TARGET_DIRS:
        full_path = os.path.join(root_dir, target)
        if not os.path.exists(full_path):
            continue
            
        for root, _, files in os.walk(full_path):
            for file in files:
                if file.endswith(".py"):
                    refactor_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
