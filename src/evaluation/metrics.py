# src/evaluation/metrics.py
import re

class MetricsCollector:
    """
    원본 C 코드와 변환된 Rust 코드를 비교하여,
    안전성(Safety), 변환율(LOC), 노력(Repair Attempts) 등의 핵심 지표를 정량적으로 추출합니다.
    """

    def __init__(self):
        pass

    def _count_loc(self, code: str) -> int:
        """공백 및 주석을 제외한 유효 코드 라인 수(Lines of Code)를 계산합니다."""
        if not code:
            return 0
        lines = code.splitlines()
        # 단순 공백 줄 제거
        valid_lines = [line for line in lines if line.strip()]
        return len(valid_lines)

    def analyze_safety(self, rust_code: str) -> dict:
        """
        최종 Rust 코드 내에 남아있는 unsafe 요소와 Raw Pointer를 카운트합니다.
        (목표치: 0에 가까울수록 안전한 변환)
        """
        # unsafe 키워드 개수 (unsafe fn, unsafe { ... })
        unsafe_keywords = len(re.findall(r'\bunsafe\b', rust_code))
        
        # Raw Pointer 사용 횟수 (*mut T, *const T)
        raw_mut = len(re.findall(r'\*mut\s+', rust_code))
        raw_const = len(re.findall(r'\*const\s+', rust_code))
        
        return {
            "unsafe_blocks": unsafe_keywords,
            "raw_mut_pointers": raw_mut,
            "raw_const_pointers": raw_const,
            "total_unsafe_elements": unsafe_keywords + raw_mut + raw_const
        }

    def analyze_translation_ratio(self, c_code: str, rust_code: str) -> dict:
        """
        C와 Rust 코드의 라인 수를 비교하여 코드 확장 비율을 측정합니다.
        보통 안전하고 관용적인 Rust 코드는 C 코드보다 길이가 다소 길어집니다.
        """
        c_loc = self._count_loc(c_code)
        rust_loc = self._count_loc(rust_code)
        
        ratio = (rust_loc / c_loc) if c_loc > 0 else 0.0
        
        return {
            "c_loc": c_loc,
            "rust_loc": rust_loc,
            "expansion_ratio": round(ratio, 2)
        }

    def generate_report(self, c_code: str, rust_code: str, repair_attempts: int, duration_sec: float = 0.0) -> dict:
        """
        모든 지표를 취합하여 최종 분석 리포트 딕셔너리를 반환합니다.
        이 데이터는 추후 터미널 대시보드 렌더링에 사용됩니다.
        """
        report = {}
        report.update(self.analyze_safety(rust_code))
        report.update(self.analyze_translation_ratio(c_code, rust_code))
        
        report["repair_attempts"] = repair_attempts
        report["duration_seconds"] = round(duration_sec, 2)
        
        # 완전 안전성 확보 여부 (Boolean)
        report["is_fully_safe"] = (report["total_unsafe_elements"] == 0)
        
        return report