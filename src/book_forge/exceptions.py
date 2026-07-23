"""Book-forge 예외 계층."""


class BookForgeError(Exception):
    """모든 Book-forge 예외의 기본 클래스."""


class ConfigurationError(BookForgeError):
    """설정 파일/환경변수 오류."""


class MissingAPIKeyError(ConfigurationError):
    """필수 API 키가 설정되지 않음."""


class UnsupportedProviderError(ConfigurationError):
    """지원하지 않는 LLM_PROVIDER 값."""


class LLMProviderError(BookForgeError):
    """LLM 호출 실패 (provider 무관 공통)."""


class TocParseError(BookForgeError):
    """LLM이 생성한 목차에서 ```toc 매니페스트 블록을 파싱하지 못함."""
