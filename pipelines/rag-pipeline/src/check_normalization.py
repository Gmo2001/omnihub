import json
import random

# 파일 경로
FILE_PATH = "canonical_content.jsonl"
SAMPLE_SIZE = 100

print(f"[*] {FILE_PATH} 파일에서 무작위로 {SAMPLE_SIZE}개의 데이터를 샘플링하여 검증합니다.\n")

try:
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    total_lines = len(lines)
    if total_lines == 0:
        print("[!] 파일이 비어있습니다.")
        exit()
        
    print(f" - 총 문서 수: {total_lines}개")
    
    # 샘플링
    sample_count = min(total_lines, SAMPLE_SIZE)
    samples = random.sample(lines, sample_count)
    
    print(f" - 샘플링 수: {sample_count}개")
    print("-" * 60)

    pass_count = 0
    fail_count = 0
    
    for idx, line in enumerate(samples):
        try:
            data = json.loads(line)
            
            # 필수 필드 검사
            missing_fields = []
            if 'summary' not in data: missing_fields.append('summary')
            if 'securityLevel' not in data: missing_fields.append('securityLevel')
            if 'sizeBytes' not in data: missing_fields.append('sizeBytes')
            if 'mimeType' not in data: missing_fields.append('mimeType')
            
            if missing_fields:
                fail_count += 1
                if fail_count <= 5: # 실패 사례는 5개까지만 상세 출력
                    print(f"[FAIL] ID: {data.get('fileId', 'Unknown')} | 누락된 필드: {', '.join(missing_fields)}")
            else:
                pass_count += 1
                
        except json.JSONDecodeError:
            fail_count += 1
            print(f"[FAIL] JSON 파싱 오류 발생 (Line Sample Index: {idx})")

    print("-" * 60)
    print(f"[결과 요약]")
    print(f"✅ 성공: {pass_count}건")
    if fail_count > 0:
        print(f"❌ 실패: {fail_count}건")
        print(" -> 데이터 일부에 문제가 있습니다. 수정이 필요합니다.")
    else:
        print("✨ 완벽합니다! 모든 샘플 데이터에 필수 메타데이터가 포함되어 있습니다.")
        
    # 샘플 1개 자세히 보여주기
    if samples:
        print("\n[참고] 랜덤 샘플 데이터 1건 예시:")
        sample_data = json.loads(samples[0])
        # 내용이 너무 길면 줄임
        if 'content' in sample_data and len(sample_data['content']) > 100:
            sample_data['content'] = sample_data['content'][:100] + "... (생략)"
        print(json.dumps(sample_data, ensure_ascii=False, indent=2))

except FileNotFoundError:
    print("[!] 파일을 찾을 수 없습니다.")