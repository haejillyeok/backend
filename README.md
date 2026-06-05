# backend

## 로컬 개발 환경

이 프로젝트는 로컬 런타임과 인프라 실행을 위해 `mise`를 사용합니다.

### mise 설정

아직 셸에 mise 활성화 설정이 없다면 아래 명령어를 실행합니다.

```bash
echo 'eval "$(mise activate zsh)"' >> ~/.zshrc
source ~/.zshrc
```

프로젝트 진입 시 실행되는 mise hook을 사용하기 위해 experimental 설정을 켜고,
현재 프로젝트 설정을 신뢰하도록 등록합니다.

```bash
mise settings set experimental true
mise trust
```

프로젝트에 설정된 Python 버전을 설치합니다.

```bash
mise install
```

### 로컬 인프라

프로젝트 디렉터리에 진입하면 mise가 `.mise.toml`의 enter hook을 실행해서
pgvector를 포함한 PostgreSQL을 자동으로 실행합니다.

```bash
cd /path/to/backend
```

인프라 명령어는 수동으로도 실행할 수 있습니다.

```bash
mise run infra-up
mise run infra-down
mise run infra-logs
```

PostgreSQL은 `localhost:5432`에서 실행됩니다.

```bash
./
├── app
│   ├── __init__.py
│   ├── api
│   │   ├── __init__.py
│   │   ├── endpoint
│   │   │   ├── __init__.py
│   │   │   └── health.py
│   │   ├── v1
│   │   │   ├── __init__.py
│   │   │   └── router.py
│   │   └── v2
│   │       ├── __init__.py
│   │       └── router.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── logging_config.py
│   ├── dependencies
│   │   ├── __init__.py
│   │   └── services.py
│   ├── repository
│   │   ├── __init__.py
│   │   └── base.py
│   ├── schemas
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── request
│   │   │   └── __init__.py
│   │   └── response
│   │       └── __init__.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── v1
│   │   │   └── __init__.py
│   │   └── v2
│   │       └── __init__.py
│   └── utils
│       └── __init__.py
├── docs
│   ├── api.md
│   ├── architecture.md
│   └── development.md
└── test
    └── __init__.py
```
