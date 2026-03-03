# Oxidizer 세부 구현 및 평가 전략 (Implementation & Evaluation Strategy)

본 문서는 Oxidizer 프로젝트의 핵심 엔진 구동 방식, LLM 프롬프팅 아키텍처, 대용량 파일 처리 전략, 그리고 정량적/정성적 평가 방법에 대한 세부 명세서입니다. 본 전략은 NDSS 유저 스터디 논문(*Translating C To Rust: Lessons from a User Study*) 등 최신 연구에서 도출된 '인간의 변환 통찰력(Human Insight)'을 자동화 파이프라인에 통합하는 것을 목표로 합니다.

---

## 1. LLM 프롬프팅 아키텍처: 2-Step Chain-of-Thought
단순히 "C 코드를 Rust로 변환하라"는 Zero-shot 접근은 환각(Hallucination)과 비효율적 코드를 유발합니다. Oxidizer는 LLM을 '정적 분석기'와 '코드 변환기'로 분리하여 활용하는 2단계(2-Step) 전략을 사용합니다.

### Step 1. Semantic Analysis (의도 파악 및 분석)
코드를 변환하기 전, 원본 C 코드와 C2Rust 초기 결과물을 LLM에 제공하여 변수와 포인터의 '의미적 의도(Semantic Intent)'를 분석하고 JSON 형태로 추출합니다.
* **분석 목표 1 (Type Lifting):** `char*`가 단순 포인터인지, 문자열(`String`)인지, 바이트 버퍼(`Vec<u8>`)인지 파악.
* **분석 목표 2 (Aliasing):** 다중 가변 참조(Multiple mutable pointers) 등 Rust의 소유권(Borrow Checker) 규칙을 위반할 가능성이 있는 패턴 식별.
* **분석 목표 3 (API Mapping):** `malloc`, `memcpy`, `puts` 등 C 표준 라이브러리 함수의 역할을 파악하여 대체할 Rust Std API 제안.

### Step 2. Idiomatic Translation (관용적 변환)
Step 1에서 추출된 JSON 분석 결과를 컨텍스트(Context)로 제공하며 실제 Safe Rust 코드를 생성합니다.
* **Semantic Lifting 적용:** 분석된 의도에 따라 Raw Pointer(`*mut T`)를 고수준 타입(`Vec<T>`, `String`, 슬라이스 `&[T]`)으로 승격.
* **Borrow Checker 해결 전략 (Cloning & Elision):** 소유권 충돌이 예상되는 경우, 인간 개발자가 취하는 방식인 `.clone()`을 통한 데이터 복제(Cloning)나 이터레이터(Iterator)를 활용한 포인터 생략(Elision) 기법을 강제.
* **Zero Unsafe:** 최종 출력물에서 `unsafe` 블록을 완전히 제거하도록 지시.

---

## 2. 컴파일 피드백 루프 (Auto-Repair via Compiler Feedback)
생성된 Rust 코드가 컴파일(`cargo check`)에 실패할 경우, 단순 재시도가 아닌 **에러 코드 맞춤형 Few-shot 가이드**를 주입하여 수정을 유도합니다.

* **피드백 매핑 예시:**
  * `E0382 (Use of moved value):` "소유권이 이동되었습니다. 타입이 Clone을 지원한다면 `.clone()`을 사용하거나, 소유권 이동 대신 참조(`&` 또는 `&mut`)를 전달하도록 함수 시그니처를 수정하세요."
  * `E0133 (Use of unsafe code):` "안전한 함수 내에서 unsafe 연산이 발생했습니다. Raw 포인터 역참조를 안전한 슬라이스 인덱싱이나 이터레이터로 대체하세요."

---

## 3. 대규모 프로젝트 변환 전략 (Divide & Conquer)
수천 줄의 코드나 다수의 함수가 포함된 대용량 파일 변환 시 발생하는 LLM의 문맥 소실(Context Length Limit) 문제를 해결하기 위해 분할 정복 방식을 도입합니다.

1. **Skeleton Extraction (뼈대 추출):** 파이썬 파서 또는 정규식을 통해 전역 변수, 구조체(`struct`), 열거형(`enum`), 그리고 함수 시그니처(Header)를 우선 추출하여 'Global Context'를 구축.
2. **Function-level Translation (함수 단위 분할 변환):** 전체 코드를 함수 단위로 분할한 뒤, LLM에게 `[Global Context] + [Target Function 1개]`를 묶어 반복적으로 API 호출 진행.
3. **AST Merge (결과 병합):** 개별적으로 변환된 안전한 Rust 함수들을 파이썬 엔진이 다시 조립하여 하나의 완전한 `.rs` 파일로 완성.

---

## 4. 평가 및 검증 전략 (Evaluation & Metrics)
제안된 파이프라인의 성능을 객관적으로 입증하기 위해 3단계 데이터셋 검증을 수행합니다.

| 검증 단계 | 데이터셋 | 활용 목적 | 핵심 평가 지표 (Metrics) |
| :--- | :--- | :--- | :--- |
| **Phase 1** | `CRUST-bench` | MVP 동작 확인 및 프롬프트 최적화 | - `unsafe` 키워드 제거율 (%)<br>- 초기 컴파일 성공률 (Compile Rate) |
| **Phase 2** | `simcrat` | C 표준 라이브러리 매핑 및 파일 I/O 평가 | - C API -> Rust Std API 변환 성공률<br>- 의미적 동등성 (Semantic Equivalence) |
| **Phase 3** | `Syzygy_Zopfli` | 대규모 실무 프로젝트(압축 알고리즘) 일반화 검증 | - **기능 테스트 통과율 (Test Pass Rate)**: C 원본과 변환된 Rust 코드의 I/O 일치 여부 |

* **기능 검증 자동화:** 변환된 Rust 프로젝트에 원본 C 프로젝트의 Test Case(입력값)를 주입하고, 실행 결과(출력값 및 상태 코드)가 100% 일치하는지 파이썬 스크립트로 교차 검증.

---

## 5. 결과 시각화 및 웹 대시보드 구축 (UI / Frontend)
단순 CLI 출력을 넘어, 변환 결과와 성능 지표를 직관적으로 확인할 수 있는 Python 기반 가벼운 웹 대시보드(Streamlit)를 구축합니다.

* **주요 기능:**
  1. **Metrics Dashboard:** 전체 코드 라인 수 변화, `unsafe` 블록 감소율, 소요 시간, 컴파일 통과 여부 시각화.
  2. **Code Diff Viewer:** 원본 `unsafe` 코드(좌)와 Oxidizer가 정제한 `Safe Rust` 코드(우)를 나란히 배치하고, 변경(리팩토링)된 부분을 하이라이트 표시 (Monaco Editor 연동).
  3. **Insight Log Tracker:** Step 1에서 LLM이 분석한 변수/포인터의 'Semantic Intent JSON'을 화면에 출력하여, 엔진의 추론 과정을 투명하게 공개.
