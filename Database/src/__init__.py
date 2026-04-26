"""ax_nilm Database 모듈 — 영속성 계층.

- ORM models: ``Database.src.models``
- Repository 구현체: ``Database.src.repositories``
- 엔진/세션 부트스트랩: ``Database.src.db``

Repository 인터페이스(Protocol)에만 의존하도록 다운스트림(API_Server 등)을
유도. 직접 SQLAlchemy 모델/세션 import 는 본 모듈 내부 또는 ETL 스크립트
한정.
"""
