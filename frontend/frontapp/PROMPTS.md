# OmniHub Frontend Prototype - Development History

이 문서는 "Frontend-only OmniHub Prototype" 프로젝트를 진행하며 사용된 프롬프트와 그에 따른 주요 코드 변경 사항을 기록합니다. 향후 프로젝트 재구축 시 가이드라인으로 활용할 수 있습니다.

---

## 1. 초기 보안 기능 구현 (Initial Access Control)

**요청 내용:**
> "외부 연동(GCP/Firestore/Drive API/BigQuery) 없이 배포했을 때 접근 제어를 위해 앱 시작 화면에 비밀번호를 입력해야만 메인 기능이 보이도록 수정해줘. 비번: asdf1234, 필드명: '비밀번호 입력'"

**구현 내역 (`components/App.tsx`):**
1.  **상태 관리 추가:** `isAuthenticated`, `passwordInput`, `loginError` 상태 변수 추가.
2.  **조건부 렌더링:**
    *   데이터 로딩(`isDataReady`) 완료 후, `!isAuthenticated` 상태일 때 로그인 화면을 표시.
    *   로그인 성공 시 `isAuthenticated`를 `true`로 변경하여 메인 UI로 진입.
3.  **UI 디자인:**
    *   기존 앱의 다크 테마와 어울리는 'System Access' 컨셉의 디자인 적용.
    *   배경 노이즈 효과, Glassmorphism 패널, 입력 오류 시 'Shake' 애니메이션 추가.

---

## 2. UI 디자인 톤 조정 및 레이아웃 최적화 (UI Refinement)

**요청 내용:**
> "기존 OmniHub 데모의 UI 색상 팔레트와 레이아웃 크기를 참고하여, 디자인 톤을 조정하고 컴포넌트 크기 비율을 최적화해줘. 차트/그래프 가독성을 높이고 시각적 통일성 강화."

**구현 내역:**

1.  **로그 패널 최적화 (`components/EventLogPanel.tsx`):**
    *   패널 높이를 `h-40`(160px)에서 `h-32`(128px)로 축소하여 상단 메인 콘텐츠(그래프 등) 영역 확보.
    *   터미널 스타일의 폰트 사이즈와 패딩을 줄여 정보 밀도(Density) 향상.

2.  **옴니허브 탭 레이아웃 (`components/OmniHubTab.tsx`):**
    *   좌측 패널 너비를 400px -> 360px로 조정하여 그래프 영역 확장.
    *   RAG(검색 결과) 카드의 배경색과 대비를 높여 가독성 개선.
    *   입력창 및 버튼 스타일을 전체 테마에 맞게 다듬음.

3.  **보안 대시보드 (`components/SecurityTab.tsx`):**
    *   차트 영역 높이 확보.
    *   KPI 카드 디자인에 일관된 Glassmorphism(투명도+블러) 효과 적용.
    *   위험도 그래프의 그라데이션 색상을 상태(`SAFE`/`WATCH`/`ALERT`)에 따라 동적으로 변경.

4.  **그래프 시각화 스타일 (`components/GraphVisualizer.tsx`):**
    *   노드 색상을 기존 파스텔 톤에서 고대비 **Neon** 컬러(Green, Blue, Amber)로 변경.
    *   배경에 미세한 그리드 패턴을 추가하여 '설계도/시스템' 느낌 강화.

---

## 3. 그래프 물리 엔진 최적화 (Physics Simulation Tuning)

**요청 내용:**
> "Refactor the GraphVisualizer component to integrate the physics simulation logic directly... preventing excessive 'bouncing' or 'teleporting'... adjust strength of forces to keep nodes generally centered."

**구현 내역 (`components/GraphVisualizer.tsx`):**

1.  **물리 엔진 파라미터 튜닝:**
    *   **Velocity Decay (0.45):** 마찰력을 높여 노드가 너무 빠르게 튀어 나가는 현상 방지.
    *   **Alpha Decay (0.02):** 시뮬레이션이 적절한 속도로 안정화되도록 조정.
2.  **중앙 정렬 강화:**
    *   `d3.forceCenter(0, 0)`를 추가하여 그래프의 무게 중심을 캔버스 중앙(0,0)으로 고정.
    *   `d3.forceX`, `d3.forceY`의 강도(Strength)를 0.04로 설정하여, 부드럽게 중앙으로 모이되 뭉치지 않도록 조정.
3.  **충돌 처리:**
    *   `forceCollide` 반경과 강도를 조정하여 노드 간 겹침 방지 및 자연스러운 배치 유도.

---

## 4. 개발 히스토리 문서화 (Documentation)

**요청 내용:**
> "지금까지 내가 요청했던 프롬프트들과 네가 수행한 작업 내역을 순서대로 정리해서 PROMPTS.md 라는 파일로 새로 만들어줘."

**구현 내역:**
*   현재 보고 계신 `PROMPTS.md` 파일 생성.

---

## 기술 스택 (Tech Stack)
*   **Framework:** React 19
*   **Styling:** Tailwind CSS (via CDN)
*   **Visualization:** D3.js (Force Graph), Recharts (Charts)
*   **Icons:** Lucide React
