# v089 원문·최초 실패·연속 참조 진단

없는 부모 ID를 출력한 규칙: 448
최초 비정상 단계가 있는 연속 graph: 303

| 군 | 규칙 위치(0부터) | 직전 유효 | 관측 | 성공 | 실패 | 미관측 |
|---|---:|---:|---:|---:|---:|---:|
| atom_alias__atom_alias | 0 | 32 | 32 | 32 | 0 | 0 |
| atom_alias__atom_alias | 1 | 32 | 32 | 29 | 3 | 0 |
| atom_alias__atom_alias | 2 | 29 | 29 | 29 | 0 | 0 |
| atom_alias__atom_alias | 3 | 27 | 27 | 27 | 0 | 0 |
| atom_alias__atom_alias | 4 | 14 | 14 | 14 | 0 | 0 |
| atom_alias__atom_tagged | 0 | 32 | 32 | 31 | 1 | 0 |
| atom_alias__atom_tagged | 1 | 31 | 31 | 13 | 18 | 0 |
| atom_alias__atom_tagged | 2 | 13 | 13 | 6 | 7 | 0 |
| atom_alias__atom_tagged | 3 | 6 | 6 | 5 | 1 | 0 |
| atom_alias__atom_tagged | 4 | 0 | 0 | 0 | 0 | 0 |
| atom_alias__long | 0 | 32 | 32 | 32 | 0 | 0 |
| atom_alias__long | 1 | 32 | 32 | 14 | 18 | 0 |
| atom_alias__long | 2 | 14 | 14 | 6 | 8 | 0 |
| atom_alias__long | 3 | 6 | 6 | 0 | 6 | 0 |
| atom_alias__long | 4 | 0 | 0 | 0 | 0 | 0 |
| atom_alias__short | 0 | 32 | 32 | 32 | 0 | 0 |
| atom_alias__short | 1 | 32 | 32 | 14 | 18 | 0 |
| atom_alias__short | 2 | 14 | 14 | 6 | 8 | 0 |
| atom_alias__short | 3 | 6 | 6 | 5 | 1 | 0 |
| atom_alias__short | 4 | 0 | 0 | 0 | 0 | 0 |
| atom_tagged__atom_alias | 0 | 32 | 32 | 19 | 13 | 0 |
| atom_tagged__atom_alias | 1 | 19 | 19 | 10 | 9 | 0 |
| atom_tagged__atom_alias | 2 | 10 | 10 | 7 | 3 | 0 |
| atom_tagged__atom_alias | 3 | 6 | 6 | 3 | 3 | 0 |
| atom_tagged__atom_alias | 4 | 1 | 1 | 0 | 1 | 0 |
| atom_tagged__atom_tagged | 0 | 32 | 32 | 30 | 2 | 0 |
| atom_tagged__atom_tagged | 1 | 30 | 30 | 30 | 0 | 0 |
| atom_tagged__atom_tagged | 2 | 30 | 30 | 30 | 0 | 0 |
| atom_tagged__atom_tagged | 3 | 28 | 28 | 26 | 2 | 0 |
| atom_tagged__atom_tagged | 4 | 12 | 12 | 12 | 0 | 0 |
| atom_tagged__long | 0 | 32 | 32 | 32 | 0 | 0 |
| atom_tagged__long | 1 | 32 | 32 | 30 | 2 | 0 |
| atom_tagged__long | 2 | 30 | 30 | 27 | 3 | 0 |
| atom_tagged__long | 3 | 25 | 25 | 22 | 3 | 0 |
| atom_tagged__long | 4 | 10 | 10 | 6 | 4 | 0 |
| atom_tagged__short | 0 | 32 | 32 | 29 | 3 | 0 |
| atom_tagged__short | 1 | 29 | 29 | 20 | 9 | 0 |
| atom_tagged__short | 2 | 20 | 20 | 14 | 6 | 0 |
| atom_tagged__short | 3 | 12 | 12 | 12 | 0 | 0 |
| atom_tagged__short | 4 | 5 | 5 | 4 | 1 | 0 |
| long__atom_alias | 0 | 32 | 32 | 29 | 3 | 0 |
| long__atom_alias | 1 | 29 | 29 | 21 | 8 | 0 |
| long__atom_alias | 2 | 21 | 21 | 10 | 11 | 0 |
| long__atom_alias | 3 | 10 | 10 | 8 | 2 | 0 |
| long__atom_alias | 4 | 0 | 0 | 0 | 0 | 0 |
| long__atom_tagged | 0 | 32 | 32 | 32 | 0 | 0 |
| long__atom_tagged | 1 | 32 | 32 | 31 | 1 | 0 |
| long__atom_tagged | 2 | 31 | 31 | 24 | 7 | 0 |
| long__atom_tagged | 3 | 22 | 22 | 19 | 3 | 0 |
| long__atom_tagged | 4 | 8 | 8 | 4 | 4 | 0 |
| long__long | 0 | 32 | 32 | 32 | 0 | 0 |
| long__long | 1 | 32 | 32 | 32 | 0 | 0 |
| long__long | 2 | 32 | 32 | 28 | 4 | 0 |
| long__long | 3 | 26 | 26 | 21 | 5 | 0 |
| long__long | 4 | 11 | 11 | 7 | 4 | 0 |
| long__short | 0 | 32 | 32 | 32 | 0 | 0 |
| long__short | 1 | 32 | 32 | 27 | 5 | 0 |
| long__short | 2 | 27 | 27 | 17 | 10 | 0 |
| long__short | 3 | 15 | 15 | 14 | 1 | 0 |
| long__short | 4 | 5 | 5 | 1 | 4 | 0 |
| short__atom_alias | 0 | 32 | 32 | 30 | 2 | 0 |
| short__atom_alias | 1 | 30 | 30 | 20 | 10 | 0 |
| short__atom_alias | 2 | 20 | 20 | 11 | 9 | 0 |
| short__atom_alias | 3 | 10 | 10 | 9 | 1 | 0 |
| short__atom_alias | 4 | 3 | 3 | 0 | 3 | 0 |
| short__atom_tagged | 0 | 32 | 32 | 30 | 2 | 0 |
| short__atom_tagged | 1 | 30 | 30 | 30 | 0 | 0 |
| short__atom_tagged | 2 | 30 | 30 | 20 | 10 | 0 |
| short__atom_tagged | 3 | 18 | 18 | 15 | 3 | 0 |
| short__atom_tagged | 4 | 5 | 5 | 0 | 5 | 0 |
| short__long | 0 | 32 | 32 | 32 | 0 | 0 |
| short__long | 1 | 32 | 32 | 29 | 3 | 0 |
| short__long | 2 | 29 | 29 | 24 | 5 | 0 |
| short__long | 3 | 24 | 24 | 19 | 5 | 0 |
| short__long | 4 | 11 | 11 | 5 | 6 | 0 |
| short__short | 0 | 32 | 32 | 32 | 0 | 0 |
| short__short | 1 | 32 | 32 | 30 | 2 | 0 |
| short__short | 2 | 30 | 30 | 24 | 6 | 0 |
| short__short | 3 | 22 | 22 | 21 | 1 | 0 |
| short__short | 4 | 11 | 11 | 6 | 5 | 0 |

risk set은 직전까지 모든 의미/지원 계약이 유효한 경로만 포함한다.
규칙 오류 수와 최초 오류 graph 수를 합산하지 않는다. 전송/미관측은 논리 오답과 별도다.
응답 사용량 합은 wall-clock 또는 API 청구액이 아니다.
원응답과 모델이 생성한 history는 사후 수정하지 않는다.
