# backend

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