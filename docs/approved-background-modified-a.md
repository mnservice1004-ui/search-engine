# 확정 배경: 수정 A안

사용자가 확정한 화면은 `http://127.0.0.1:5037/?revision=a-whole-sky`의 **수정 A안**이다. 이전 A안 또는 별도 hero-atmosphere 구현을 기준으로 삼지 않는다.

- 실제 실행 모드: `variant=A`, `look=sunset-wide`, 재생 속도 `3.5`.
- 태양 크기·가장자리, 하늘 전체 석양빛과 구름 명암, 독립적인 나뭇잎 움직임은 5037 실행본 그대로다.
- 기본 홈페이지는 `public/qa/layer-engine.js`, `public/qa/layer-home.js`를 불러온다. 경로의 qa 명칭은 기존 실행본과의 동일성을 위해 유지한다.
- 기존 비교 페이지와 `look` 매개변수는 비교용으로 남아 있지만 기본값이나 승인 기준이 아니다.
- 파일별 원본 SHA-256은 `approved-background-modified-a.json`에 기록했다. 테스트가 이를 대조한다. Windows Git의 CRLF 체크아웃은 텍스트 파일에 한해 LF로 정규화하여 비교하며 이미지 바이트는 그대로 비교한다.
- 이후 민원 상세 안내를 이 배경 위에 통합하되, 이번 기준 확정 커밋에는 새 상세 안내 5개를 포함하지 않는다.
- 운영 DB, 사진 원본 폴더, 전체 임시 실험 폴더, 직원용 자료, 관계없는 삭제·untracked 파일은 게시하지 않는다.

자산은 사용자가 제공한 사진과 기존 승인 시뮬레이션 자산이다. 새 외부 이미지를 다운로드하거나 원본을 재압축하지 않았다. 두 JPEG는 기존 EXIF가 있으나 GPS 태그는 없음을 확인했다. `original.jpg`는 이미 추적된 `public/images/hero-dongtan.jpg`와 동일한 파일이다.
