# src/utils/logger.py
import logging
from pathlib import Path

def setup_logger(name="Oxidizer"):
    logger = logging.getLogger(name)
    
    # 이미 핸들러가 세팅되어 있다면 중복 추가 방지
    if logger.hasHandlers():
        return logger
        
    # 전체 로거의 기본 레벨은 DEBUG로 설정 (핸들러에서 필터링)
    logger.setLevel(logging.DEBUG)
    
    # 로그 파일이 저장될 logs/ 디렉토리 생성
    project_root = Path(__file__).resolve().parent.parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "oxidizer_debug.log"
    
    # 1. 터미널 출력용 콘솔 핸들러 (INFO 레벨 이상만 출력)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    # 터미널에는 지저분한 시간/파일 정보 없이 깔끔하게 메시지만 출력
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    
    # 2. 파일 저장용 파일 핸들러 (DEBUG 레벨 이상 모두 기록)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    # 파일에는 나중에 디버깅하기 좋도록 시간, 로그 레벨, 발생한 파일명과 라인 번호까지 상세히 기록
    file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # 로거에 두 핸들러 부착
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# 프로젝트 전역에서 사용할 공용 로거 객체
logger = setup_logger()