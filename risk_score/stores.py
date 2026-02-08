from __future__ import annotations

from typing import Any, Dict, Optional

from google.cloud import firestore, storage, bigquery


class Stores:
    """
    - main.py에서는 Stores(project_id=..., bq_dataset=..., ...) 형태로 생성하길 기대
    - 따라서 여기서 GCP 클라이언트를 내부에서 자동 생성하도록 통일
    - 테스트를 위해 필요하면 client를 주입할 수도 있게 Optional로 열어둠
    """

    def __init__(
        self,
        *,
        project_id: str,
        bq_dataset: str,
        bq_table: str,
        fs_users_col: str,
        fs_idem_col: str,
        firestore_client: Optional[firestore.Client] = None,
        storage_client: Optional[storage.Client] = None,
        bq_client: Optional[bigquery.Client] = None,
    ) -> None:
        self.firestore = firestore_client or firestore.Client(project=project_id)
        self.storage = storage_client or storage.Client(project=project_id)
        self.bq = bq_client or bigquery.Client(project=project_id)

        self.fs_users_col = fs_users_col
        self.fs_idempotency_col = fs_idem_col

        self.bq_dataset = bq_dataset
        self.bq_table = bq_table

    # -------------------------
    # Firestore: idempotency
    # -------------------------
    def claim_idempotency(self, idempotency_key: str) -> bool:
        """
        idempotency_key로 한번만 처리되도록 Firestore에 '도장'을 찍는다.
        이미 있으면 False, 새로 만들면 True.
        """
        ref = self.firestore.collection(self.fs_idempotency_col).document(idempotency_key)

        @firestore.transactional
        def _txn(tx: firestore.Transaction) -> bool:
            snap = ref.get(transaction=tx)
            if snap.exists:
                return False
            tx.set(ref, {"createdAt": firestore.SERVER_TIMESTAMP, "idempotencyKey": idempotency_key})
            return True

        tx = self.firestore.transaction()
        return _txn(tx)

    # -------------------------
    # GCS: download json
    # -------------------------
    def download_json_from_gcs(self, *, bucket: str, name: str, generation: Optional[str | int]) -> Dict[str, Any]:
        b = self.storage.bucket(bucket)
        blob = b.blob(name)

        # generation이 있으면 해당 세대(generation)로 고정해서 읽기
        if generation is not None and str(generation).strip() != "":
            blob = b.blob(name, generation=int(generation))

        text = blob.download_as_text()
        import json

        return json.loads(text)

    # -------------------------
    # Firestore: latest user doc
    # -------------------------
    def get_user_latest(self, user_id: str) -> Optional[Dict[str, Any]]:
        ref = self.firestore.collection(self.fs_users_col).document(user_id)
        snap = ref.get()
        if not snap.exists:
            return None
        return snap.to_dict() or {}

    def upsert_user_latest(self, user_id: str, payload: Dict[str, Any], *, merge: bool = True) -> None:
        """
        merge=True  -> 기존 필드 유지(부분 업데이트)
        merge=False -> 문서 교체(기존 불필요 필드 제거 목적)
        """
        ref = self.firestore.collection(self.fs_users_col).document(user_id)
        # 만약 문서가 없으면 생성하면서 history도 넣을 수 있게 set을 사용
        # (set은 문서가 없으면 생성, 있으면 업데이트/덮어쓰기)
        ref.set(payload, merge=merge)

    def add_user_history(self, user_id: str, payload: Dict[str, Any]) -> None:
        """
        user_id 문서 하위의 'history' 컬렉션에 문서를 추가한다.
        ID를 무작위가 아닌 'YYYYMMDD_HHMMSS_EventType' 형식으로 지정하여 가독성을 높인다.
        """
        # ID 생성: 2026-02-08T12:00:00Z -> 20260208_120000
        ts = str(payload.get("lastEventAt", "")).replace("-", "").replace(":", "").replace("T", "_").split(".")[0].replace("Z", "")
        evt = str(payload.get("eventType", "EVENT"))
        doc_id = f"{ts}_{evt}"
        
        parent_ref = self.firestore.collection(self.fs_users_col).document(user_id)
        # .add() 대신 .document(id).set() 사용
        parent_ref.collection("history").document(doc_id).set(payload)

    # -------------------------
    # BigQuery: append row
    # -------------------------
    def append_bq_event(self, row: Dict[str, Any], *, insert_id: str) -> None:
        table_id = f"{self.bq.project}.{self.bq_dataset}.{self.bq_table}"
        errors = self.bq.insert_rows_json(table_id, [row], row_ids=[insert_id])
        if errors:
            raise RuntimeError(f"BigQuery insert errors: {errors}")
