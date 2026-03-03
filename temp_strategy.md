Oxidizer 세부 구현 및 평가 전략 (SOTA 논문 융합 아키텍처)

본 문서는 Oxidizer 프로젝트의 핵심 엔진 구동 방식, LLM 프롬프팅 아키텍처, 대용량 파일 처리 전략, 그리고 정량적/정성적 평가 방법에 대한 세부 명세서입니다.

본 전략은 단순히 LLM에 의존하는 것을 넘어, NDSS 유저 스터디 논문(Translating C To Rust: Lessons from a User Study) 등에서 도출된 **'인간의 변환 통찰력(Human Insight)'**과 최신 C-to-Rust 변환 관련 SOTA 논문 5편의 핵심 방법론을 파이프라인의 각 단계에 완벽히 융합(Integration)하는 것을 목표로 합니다.
1. LLM 프롬프팅 아키텍처: DFG 및 Multi-Step 기반 통찰력 주입

단순히 "C 코드를 Rust로 변환하라"는 Zero-shot 접근의 한계(타입 불일치, 환각)를 극복하기 위해, Oxidizer는 LLM을 '정적 분석기'와 '코드 변환기'로 분리하여 활용하는 2단계(2-Step) 다단계 전략을 사용합니다.
Step 1. DFG 기반 의도 파악 및 타입 분석 (Semantic Analysis)

    💡 융합 논문: Optimizing Type Migration (DFG Approach)

코드를 변환하기 전, 원본 C 코드와 C2Rust 초기 결과물을 LLM에 제공하여 변수와 포인터의 **데이터 흐름 그래프(DFG, Data Flow Graph)**적 맥락과 '의미적 의도(Semantic Intent)'를 분석하고 JSON 형태로 추출합니다.

    Type Migration: char*가 단순 포인터인지, 문자열(String)인지, 바이트 버퍼(Vec<u8>)인지 파악.

    Enum Indicators: 다중 대여(Multiple Borrowing)가 발생하는 전역 변수나 매개변수를 식별하여, 안전한 Rust enum이나 RefCell 적용 대상인지 마킹.

    API Mapping: malloc, memcpy, puts 등 C 표준 라이브러리 함수의 역할을 파악하여 대체할 Rust Std API 제안.

Step 2. 관용적 안전 코드로의 승격 (Idiomatic Refinement)

    💡 융합 논문: NDSS User Study (Semantic Lifting) & SACTOR (Unidiomatic to Idiomatic)

Step 1에서 추출된 DFG 분석 결과(JSON)를 컨텍스트(Context)로 제공하며, 인간 개발자의 통찰력(Human Insight) 규칙을 강제하여 실제 Safe Rust 코드를 생성합니다.

    Semantic Lifting 적용: 분석된 의도에 따라 Raw Pointer(*mut T)를 고수준 타입(Vec<T>, String, 슬라이스 &[T])으로 승격.

    Borrow Checker 해결 전략 (Cloning & Elision): 소유권 충돌이 예상되는 경우, 인간 개발자가 취하는 방식인 .clone()을 통한 데이터 복제(Cloning)나 이터레이터(Iterator)를 활용한 포인터 생략(Elision) 기법을 지시.

    Zero Unsafe: 최종 출력물에서 unsafe 블록을 완전히 제거하도록 강제.

2. 컴파일 피드백 루프 (Few-Shot Guided Auto-Repair)

    💡 융합 논문: SafeTrans (Few-shot guided repair)

생성된 Rust 코드가 컴파일(cargo check)에 실패할 경우, 단순 에러 로그만 넘기는 방식(Basic Repair)은 복구율이 현저히 낮습니다. Oxidizer는 단순 재시도가 아닌 에러 코드 맞춤형 Few-shot 가이드를 주입하여 수정을 유도합니다.

    피드백 매핑 예시:

        E0382 (Use of moved value): "소유권이 이동되었습니다. 타입이 Clone을 지원한다면 .clone()을 사용하거나, 소유권 이동 대신 참조(& 또는 &mut)를 전달하도록 함수 시그니처를 수정하세요. [Few-shot 예제 코드 제공]"

        E0133 (Use of unsafe code): "안전한 함수 내에서 unsafe 연산이 발생했습니다. Raw 포인터 역참조를 안전한 슬라이스 인덱싱이나 이터레이터로 대체하세요. [Few-shot 예제 코드 제공]"

3. 대규모 프로젝트 변환 전략 (Skeleton-Guided Divide & Conquer)

    💡 융합 논문: EvoC2Rust (Skeleton-guided Framework)

수천 줄의 코드나 다수의 모듈/함수가 포함된 대용량 파일 변환 시 발생하는 LLM의 문맥 소실(Context Length Limit) 문제를 해결하기 위해 분할 정복 방식을 도입합니다.

    Skeleton Extraction (뼈대 추출): 파이썬 파서 또는 정규식을 통해 C 코드에서 매크로, 전역 변수, 구조체(struct), 열거형(enum), 그리고 함수 시그니처(Header)를 우선 파싱하여, 함수 내부가 비어있는 '컴파일 가능한 Rust 뼈대(Skeleton)'를 선제적으로 구축해 Global Context를 확보합니다.

    Function-level Translation (함수 단위 분할 변환): 전체 코드를 함수 단위로 분할한 뒤, LLM에게 [Global Context 뼈대] + [Target Function 1개]를 묶어 반복적으로 변환을 요청(API 호출)합니다.

    AST Merge (결과 병합): 개별적으로 변환된 안전한 Rust 함수들을 파이썬 엔진이 다시 조립하여 하나의 완전한 .rs 파일로 완성합니다.

4. 평가 및 검증 전략 (FFI 기반 End-to-End 검증)

    💡 융합 논문: SACTOR (FFI Verification) & SafeTrans (Vulnerability Mitigation)

제안된 파이프라인의 성능을 객관적으로 입증하기 위해 3단계 데이터셋 검증을 수행합니다.
검증 단계	데이터셋	활용 목적	핵심 평가 지표 (Metrics)
Phase 1	CRUST-bench	파이프라인 MVP 동작 및 에러 복구율 확인	

- 초기 컴파일 성공률 (Compile Rate)

- unsafe 키워드 제거율 (%)
Phase 2	simcrat	C 표준 라이브러리 매핑 및 파일 I/O 평가	

- C API -> Rust Std API 변환 성공률

- 의미적 동등성 (Semantic Equivalence)
Phase 3	Syzygy_Zopfli	대규모 실무 프로젝트(압축 알고리즘) 일반화 검증	- FFI 기반 기능 테스트 통과율 (Test Pass Rate)

    FFI(Foreign Function Interface) 기반 검증 자동화: 변환된 Rust 코드를 FFI를 통해 원본 C 테스트 스위트에 임베딩합니다. 원본 C 프로젝트의 Test Case(입력값)를 주입하여, 실행 결과(출력값 및 상태 코드)가 100% 일치하는지 교차 검증합니다.

    보안 취약점 완화 검증: 원본 C 코드에 존재하는 오버플로우 등의 취약점 유발 입력을 주입했을 때, 변환된 Rust 코드가 메모리를 훼손하지 않고 안전하게 패닉(Panic) 방어해 내는지(취약점 완화 여부) 입증합니다.

5. 결과 시각화 및 웹 대시보드 구축 (UI / Frontend)

단순 CLI 출력을 넘어, 변환 결과와 성능 지표를 직관적으로 확인할 수 있는 Python 기반 가벼운 웹 대시보드(Streamlit)를 구축합니다.

    주요 기능:

        Metrics Dashboard: 전체 코드 라인 수 변화, unsafe 블록 감소율, 토큰 소모량(비용 최적화 모니터링), 소요 시간, 컴파일 통과 여부 시각화.

        Code Diff Viewer: 원본 unsafe 코드(좌)와 Oxidizer가 정제한 Safe Rust 코드(우)를 나란히 배치하고, 변경(리팩토링)된 부분을 하이라이트 표시 (Monaco Editor 연동).

        DFG & Intent Log Tracker: Step 1에서 LLM이 분석한 변수/포인터의 'Semantic Intent JSON(타입 변환 맵)'을 화면에 시각화하여, 파이프라인 엔진의 추론 과정을 투명하게 공개.