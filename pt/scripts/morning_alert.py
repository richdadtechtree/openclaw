from pathlib import Path
import sys
sys.path.append(str(Path("/home/ubuntu/pt_system")))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.send_telegram import send_message
send_message(
    "좋은 아침입니다.\n"
    "오늘은 운동 가능 시간, 식사 계획, 컨디션을 간단히 남겨주세요.\n"
    "예: 오늘 하체 운동 예정, 컨디션 보통, 수면 7시간"
)
