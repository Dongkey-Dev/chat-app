# 실시간 채팅 애플리케이션
### 시작
0. docker, docker-compose가 필요합니다.
1. 해당 프로젝트의 루트 경로에서 docker-compose up --build를 실행합니다.
2. http://localhost:8000/client 주소로 접속합니다.
3. 접속 버튼을 누른 뒤, 채팅방 생성, 접속, 채팅 메세지 전송이 가능합니다.

## 기능

### 1. 실시간 채팅

- **WebSocket 기반 실시간 채팅**: FastAPI의 `WebSocket`을 사용해 클라이언트 간 실시간 채팅을 구현했습니다. 클라이언트가 채팅방에 접속하면 `WebSocket` 연결이 이루어지며, 사용자가 메시지를 전송하면 이를 같은 방에 있는 모든 사용자에게 전송할 수 있도록 하였습니다.
- **메시지 저장 및 전송**: 채팅 메시지와 방정보는 MongoDB에 저장되며, 새로운 사용자가 채팅방에 참여할 때 기존의 채팅 기록을 MongoDB에서 불러와 모든 이전 메시지를 확인할 수 있도록 했습니다.
- **Redis를 활용한 접속자 관리**: 서버의 확장성을 고려해 Redis를 통해 각 방에 접속한 사용자의 수를 관리했습니다.

---

### 2. 30분 내 접속자 수 기준으로 채팅 목록 정렬

- **접속자 수 관리**: Redis에 각 방의 접속자 수를 저장하고, 30분 내 접속한 유저의 수를 Redis의 `zset`을 통해 관리했습니다.
- **정렬 구현**: `zset`에 기록된 접속자 수를 기준으로 채팅 목록을 내림차순으로 정렬하여 클라이언트에 전송했습니다.
- **30분 내 접속자 수 계산**: 유저 연결이 끊어질때, `zset`의 해당 유저 `score`를 현재 `timestamp`로 갱신하고 사용자가 방목록을 조회할때마다 30분 전의 `timestamp score`에 대해 삭제하여 30분 기간의 접속자 수를 구현하였습니다.

### Todo:
- **30분 내 접속자 수 계산 로직 최적화**: 

    asis : 유저가 매 5초마다 방목록 조회 요청을 보내며, 요청을 받을때마다 30분 내 접속자 수를 계산합니다.

    tobe : 서버에서 자체적으로 일정한 주기로 계산을 하여 저장을 하고, 유저가 요청을 보낼때 캐싱되어 있는 방목록을 내려줍니다.
- **방목록 조회 방식**: 

    asis : 방에 대한 정보를 REST Api를 통해 내려주고 있어 실시간이 아닙니다.

    tobe : websocket을 통해 변동사항마다 실시간으로 업데이트를 내려줄 수 있습니다.

---

### 3. 채팅 목록에 최근 메시지 노출

- **MongoDB 기반 메시지 저장 및 조회**: 각 채팅방의 메시지를 MongoDB에 저장하여 관리했습니다.
- **실시간 업데이트**: 클라이언트 측에서는 WebSocket을 통해 새로운 메시지가 도착할 때마다 목록의 최신 메시지를 자동으로 갱신할 수 있도록 구현했습니다.

---

### 4. 데이터베이스 관리

- **MongoDB와 Redis 사용**: 
  - **MongoDB**는 메시지 저장 및 방 목록 관리와 같은 영구적인 데이터를 처리하는 데 사용했습니다.
  - **Redis**는 실시간 접속자 수, 참여자 관리와 같은 휘발성 데이터를 처리하는 데 사용했습니다.
- **확장성 고려**: MongoDB를 통해 메시지와 방 목록 데이터를 저장하는 구조로 확장성을 고려했으며, 분산 서버 구조의 확장을 고려해 Redis를 통해 접속자 수와 같은 데이터를 처리했습니다.

---

### 5. 사용자 관리

- **회원가입 및 로그인 없이 ID 생성**: 사용자가 별도의 회원가입 없이 접속할 때마다 자동으로 ID가 발급되어 채팅에 참여할 수 있도록 설정했습니다.

### Todo:
- **사용자 관리**: 현재는 임의로 랜덤 문자열을 유저 ID로 할당하지만, RDB를 도입해 유저 정보를 관리할 수 있습니다.

---
### 6. 인프라 확장성 고려

- **수평 확장을 고려한 구조**: 웹소켓 서버의 수평 확장을 고려해 연결 단위를 유저 단위로 하였습니다. 이를 통해 트래픽에 따라 능동적으로 원할하게 서버를 확장 및 축소가 가능합니다.

---

## 회고

소켓 프로그래밍에 대한 경험이 많지 않았지만, 이번 기회에 소켓프로그래밍을 경험해 보았습니다. 소켓을 이용하면 상당히 많은 부분을 실시간으로 서비스가 가능하지만, 그만큼 서버와 프론트측 모두 많은 리소스가 들어가니 실시간성과 준실시간성을 유저 경험을 기준으로 분리를 잘 해야합니다.