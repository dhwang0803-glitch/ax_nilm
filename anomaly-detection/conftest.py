import sys
import types
from pathlib import Path

_pkg_dir = Path(__file__).parent

# anomaly-detection/ 폴더를 'anomaly_detection' 패키지로 등록
# 폴더명 하이픈 때문에 직접 import 불가 → 모듈 별칭으로 해결
pkg = types.ModuleType("anomaly_detection")
pkg.__path__ = [str(_pkg_dir)]
pkg.__package__ = "anomaly_detection"
sys.modules["anomaly_detection"] = pkg

sys.path.insert(0, str(_pkg_dir))
