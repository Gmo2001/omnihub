def to_internal_id(prefix: str, external_id: str) -> str:
    """
    외부 ID(Google ID 등)에 접두어를 붙여 내부 ID로 변환합니다.
    이미 접두어가 있으면 그대로 반환합니다.
    예: '12345' -> 'fil_12345' (prefix='fil_')
    """
    if external_id.startswith(prefix):
        return external_id
    return f"{prefix}{external_id}"

def to_external_id(prefix: str, internal_id: str) -> str:
    """
    내부 ID에서 접두어를 제거하여 외부 API 호출용 ID로 변환합니다.
    접두어가 없으면 그대로 반환합니다.
    예: 'fil_12345' -> '12345' (prefix='fil_')
    """
    if internal_id.startswith(prefix):
        return internal_id[len(prefix):]
    return internal_id
