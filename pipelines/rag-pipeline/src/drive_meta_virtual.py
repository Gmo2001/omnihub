
import os
import hashlib
import random
import time

class VirtualMetaGenerator:
    def __init__(self, config_path=None):
        self.config = {}
        # Config (Optional)
        if config_path and os.path.exists(config_path):
            import json
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except:
                pass
        
        self.owners = self.config.get("owners", [{"name": "Admin", "email": "admin@example.com"}])
        self.folders = self.config.get("folders", ["/General"])
        self.statuses = self.config.get("statuses", ["active"])
        self.types_map = self.config.get("file_types_map", {})
        
        # New defaults for rules
        self.depts = ["Engineering", "Marketing", "Sales", "HR", "Legal", "General"]
        self.folder_years = ["2023", "2024", "2025"]

    def _get_deterministic_seed(self, **kwargs):
        """
        Prioritized source for stable seed:
        1. drive_file_id (if available, best)
        2. source_uri (stable URL)
        3. parent_doc_id
        4. filename (weakest, but fallback)
        """
        raw_key = ""
        if kwargs.get("drive_file_id"):
            raw_key = kwargs["drive_file_id"]
        elif kwargs.get("source_uri"):
            raw_key = kwargs["source_uri"]
        elif kwargs.get("parent_doc_id"):
            raw_key = kwargs["parent_doc_id"]
        else:
            raw_key = kwargs.get("filename", "unknown")

        # Stable hash (SHA256) -> int for random seed
        hash_hex = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
        return int(hash_hex, 16)

    def generate(self, filename, **kwargs):
        """
        kwargs keys: 
           drive_file_id, source_uri, parent_doc_id (for seeding)
           existing_meta (dict): partial info like tags, securityLevel
        """
        seed = self._get_deterministic_seed(filename=filename, **kwargs)
        rng = random.Random(seed)
        
        existing_meta = kwargs.get("existing_meta") or {}
        
        # 1. Basic Fields
        owner = rng.choice(self.owners)
        status = rng.choice(self.statuses)

        # 2. Path Generation (Rule Based)
        # /Dept/{department}/{Tag}/{Year}
        dept = existing_meta.get("department")
        if not dept or dept not in self.depts:
            dept = rng.choice(self.depts)
        
        # Security Prefix (Deterministic based on seed + security)
        security = existing_meta.get("securityLevel", "medium")
        path_prefix = ""
        if security == "high":
            # 50% chance to be in Restricted root or just Dept restricted
            if rng.choice([True, False]):
                path_prefix = "/Restricted"

        # Tag component
        tags = existing_meta.get("tags", [])
        tag_folder = "Misc"
        if tags:
            # Sorted to be deterministic, pick first or RNG choice
            sorted_tags = sorted(tags)
            tag_folder = sorted_tags[0] # Primary tag
            # Capitalize
            tag_folder = tag_folder.capitalize()

        # Year component
        year = rng.choice(self.folder_years)

        # Construct Folder Path
        # e.g. /Engineering/Specs/2024
        folder_path = f"{path_prefix}/{dept}/{tag_folder}/{year}".replace("//", "/")
        
        # Related Paths (Deterministic variations)
        related_paths = []
        # Parent
        parent_path = os.path.dirname(folder_path)
        if parent_path and parent_path != "/":
            related_paths.append(parent_path)
        
        # Sibling or archived
        related_paths.append(f"{path_prefix}/{dept}/Archived/{year}".replace("//", "/"))
        
        # remove duplicates and self
        related_paths = [p for p in set(related_paths) if p != folder_path]

        # 3. Dates
        now_ts = int(time.time())
        day_seconds = 86400
        days_ago = rng.randint(0, 365 * 2) # Last 2 years
        updated_at_ms = (now_ts - (days_ago * day_seconds)) * 1000

        # 4. Size
        size_bytes = existing_meta.get("sizeBytes", 0)
        try:
            size_kb = int(size_bytes) // 1024
        except:
            size_kb = 0
        
        if size_kb == 0:
            size_kb = rng.randint(10, 20480) # 10KB ~ 20MB

        # 5. URLs
        # If we have a real drive ID, use it. Else make one up based on seed for consistency
        drive_id = kwargs.get("drive_file_id")
        if not drive_id:
             # Fake ID: 32 chars alphanumeric from seed
             # but let's just use part of the hash we already made
             chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
             # re-seed RNG just to be safe or use current state
             fake_id = "".join(rng.choices(chars, k=33))
             drive_id = fake_id
        
        drive_url = f"https://drive.google.com/file/d/{drive_id}/view"

        # 6. Ext
        ext = os.path.splitext(filename)[1].lstrip(".").lower()
        if not ext: ext = "pdf"
        mime = self.types_map.get(ext, "application/octet-stream")

        return {
            "driveUrl": drive_url,
            "folderPath": folder_path,
            "actualPath": folder_path, 
            "owner": owner, 
            "updatedAt": updated_at_ms,
            "sizeKB": size_kb,
            "status": status,
            "ext": ext,
            "mimeType": mime,
            "relatedFolderPaths": related_paths
        }
