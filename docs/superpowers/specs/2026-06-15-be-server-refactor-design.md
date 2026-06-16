# BE Server Refactor Design

## Goal

BE 서버의 큰 service 파일을 작은 책임 단위로 나누고, 게임 정책을 객체로 주입할 수 있게 만들어 게임 진행 로직을 간결하게 유지한다.

## Current State

- `app/be/services/game.py`는 record DTO, repository protocol, domain error, helper 함수, `GameService`를 한 파일에 담고 있다.
- `app/be/services/match.py`는 snapshot DTO, repository protocol, `MatchConnectionManager`, message handler, timer, broadcaster helper를 한 파일에 담고 있다.
- 기존 endpoint, repository, test는 `from app.be.services.game import GameService`와 같은 public import 경로에 의존한다.
- 따라서 리팩터링은 package `__init__.py`에서 기존 import surface를 보존하면서 내부 파일만 나누는 방식으로 진행한다.

## File Boundary Policy

- 핵심 class, service, manager, policy는 파일당 하나를 원칙으로 한다.
- 작은 dataclass DTO와 type alias는 `records.py`, `snapshots.py`, `timers.py`처럼 역할별로 묶을 수 있다.
- Protocol과 error class는 책임이 명확하면 별도 파일로 분리한다.
- endpoint와 repository의 외부 import 경로는 가능한 한 유지하고, 내부 import만 새 하위 모듈을 사용하도록 점진적으로 정리한다.

## Target Structure

```text
app/be/services/game/
  __init__.py
  errors.py
  records.py
  repository_protocol.py
  room_membership_policy.py
  service.py
  session_credential_policy.py
  session_participant_policy.py

app/be/services/match/
  __init__.py
  broadcasters.py
  connection_manager.py
  message_handler.py
  repository_protocol.py
  service.py
  snapshots.py
  timers.py
```

## Game Policy Design

`GameService` keeps orchestration responsibility and delegates pure rules to policy objects.

- `RoomMembershipPolicy` decides whether a started room is safe to abort when a user moves lobby rooms.
- `SessionParticipantPolicy` builds anonymized user participants and the AI guest participant from active room members.
- `SessionCredentialPolicy` issues and hashes `game_session_token` credentials with the default TTL.

Default policies are injected by constructor defaults so current dependency providers do not need to know every policy. Tests can still pass custom policies to verify behavior without a database.

## Match Split Design

`MatchService` remains the snapshot service. Process-local WebSocket state and message orchestration move out of the snapshot service module.

- `connection_manager.py` owns `MatchConnectionManager` and the process-level `match_connection_manager`.
- `message_handler.py` owns `handle_match_message`, payload parsing, and AppException mapping.
- `timers.py` owns timer dataclasses and timeout calculation.
- `broadcasters.py` owns round finished/started message derivation and broadcast sequencing.
- `snapshots.py` owns match snapshot DTOs.

## Compatibility

The following imports must continue to work:

```python
from app.be.services.game import GameService, GameSessionStartResult
from app.be.services.match import MatchSnapshotResult, match_connection_manager
```

The package `__init__.py` files re-export the existing public names so endpoint and test churn stays low.

## Testing

- Add a focused service-level test proving `GameService` can receive a custom participant policy.
- Run the new test before implementation and confirm it fails because policy injection does not exist yet.
- After implementation, run targeted game and match tests:
  - `pytest test/test_game_session_entry.py test/test_game_rooms_api.py test/test_lobby_websocket.py`
  - `pytest test/test_match_websocket.py test/test_match_repository.py test/test_match_progress.py test/test_match_vote.py`
- If import churn causes broader risk, run full `pytest`.
