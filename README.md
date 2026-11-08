# INTERS 미장 → 국장 연계 지도

S&P 500과 나스닥 100 지도에서 미국 종목을 누르면 함께 볼 한국 종목과, 실제로 다음 날 한국 주가가 얼마나 따라 움직였는지(커플링)가 나오는 공개 웹페이지입니다. 서버 없이 GitHub Pages에 올라가서 누구나 링크로 열 수 있습니다.

## 어떻게 돌아가나

- **목적:** 전일 미장 흐름을 보고 국장을 매매하도록 돕는 화면입니다.
- **미장 마감 = 초기화:** 화~토 오전 6시 30분(한국 시간) 실행에서 화면 전체가 방금 끝난 미장 기준으로 새로 바뀝니다. 지도 색, 예상 반응, 국장 추천 테마가 그날 국장용으로 바뀝니다.
- **국장 마감 = 데이터 반영:** 월~금 오후 6시 30분 실행(외국인 매매 확정치가 나온 뒤)은 전일 미장과 그날 국장 한 쌍을 60일 상관계수·외국인 연동에 더할 뿐, 화면 기준(미장 날짜)은 그대로입니다.
- **실행 내용:** 두 번 모두 GitHub Actions가 Yahoo Finance에서 미국 518개(S&P 500 503개 + 나스닥 100에만 있는 15개)와 한국 연계 종목의 종가, 나스닥 100 종목의 시가총액을 받습니다.
- **한국 데이터:** 한국 종목 시세와 외국인 순매매·보유율은 네이버 금융(종목별 외국인·기관 매매 페이지, 최근 약 100거래일)에서 받습니다. 네이버에서 못 받은 종목은 Yahoo Finance 시세로 대신합니다.
- **계산:** 가장 최근 미장 등락률, 종목 쌍마다 최근 미국 거래일 60일 동안의 커플링, 예상 반응(반응 배율 × 미장 등락률), 그리고 국장 추천 테마를 계산합니다.
- **국장 추천 테마:** 미장에서 평균 +1% 이상 오른 연계 섹터 중 한국 종목과의 연동(상관계수 상위 5개 평균)이 0.25 이상인 곳을 "미국 평균 × 연동" 점수 순으로 보여 줍니다. 각 테마에는 재료와, 상관계수 0.3 이상인 한국 종목 중 예상 반응이 큰 종목이 붙습니다. 반대로 -1% 이하로 빠지고 연동이 높은 섹터는 "약세 주의"로 따로 보여 줍니다. 기준값은 `docs/index.html`의 `LK_RECO_US`, `LK_RECO_CORR`, `LK_PICK_CORR`에서 바꿀 수 있습니다.
- **게시:** 결과를 웹페이지와 함께 GitHub Pages에 올립니다. 결과 파일은 `data` 브랜치에 덮어써서 보관합니다. **`data` 브랜치는 지우거나 고치지 마세요.**
- **바로 반영:** `data/links.csv` 등을 고쳐서 저장하면 그때도 자동으로 다시 계산해 5분 안에 반영됩니다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `data/links.csv` | **미국 종목 ↔ 한국 종목 연결 목록 (여기에 추가·수정)** |
| `data/themes.csv` | 날짜별 섹터 재료 (선택) |
| `data/universe.csv` | 미국 종목 목록: 섹터, 연계 섹터, S&P 500 비중, 어느 지수에 속하는지 |
| `docs/index.html` | 웹페이지 |
| `link_scan.py` | 시세를 받아 커플링을 계산하는 스크립트 |
| `.github/workflows/pages.yml` | 자동 실행 일정과 순서 |

## 처음 설정하기 (한 번만)

1. **새 저장소:** GitHub 오른쪽 위 `+` → `New repository`. 이름은 `inters-link`처럼 짓고 **Public**으로 만듭니다.
2. **Pages 켜기:** `Settings` → `Pages` → `Build and deployment`의 `Source`를 **GitHub Actions**로 바꿉니다.
3. **파일 올리기:** 압축을 푼 폴더 **안의** 파일과 폴더를 끌어다 놓고 `Commit changes`를 누릅니다. `.github` 폴더가 안 올라가면 `Add file` → `Create new file`에서 이름을 `.github/workflows/pages.yml`로 하고 맨 아래 부록 내용을 붙여 넣습니다.
4. **첫 실행:** 파일을 올리면 자동으로 시작됩니다. `Actions` 탭에서 초록 체크가 뜰 때까지 5~10분 기다립니다. 안 시작되면 `연계 지도 자동 갱신` → `Run workflow`를 누릅니다.
5. **공유:** `Settings` → `Pages` 맨 위의 `https://아이디.github.io/inters-link/` 주소를 공유합니다. 종목을 고른 상태에서 페이지 맨 아래 `지금 보고 있는 종목 링크 복사`를 누르면 그 종목이 열린 채로 공유됩니다.

## 연계 종목 추가·수정하기

`data/links.csv`의 한 줄이 미국 종목 하나와 한국 종목 하나의 연결입니다.

| 열 | 내용 | 예 |
| --- | --- | --- |
| `us_ticker` | 미국 티커 (`data/universe.csv`에 있는 종목) | NVDA |
| `kr_name` | 한국 종목 이름 | SK하이닉스 |
| `kr_code` | 한국 종목코드 6자리 (앞의 0까지) | 000660 |
| `relation` | 공급망, 업황 공유, 투자 수혜, 정책·테마, 판매 채널, 같은 섹터 중 하나 | 공급망 |
| `note` | 한 줄 설명 | AI 가속기에 들어가는 HBM 공급 |
| `basis` | 근거: 소모임 자료, 기사, 같은 업종, 추론 중 하나 (다른 말도 됩니다) | 기사 |

**고치는 방법:** 저장소에서 `data/links.csv`를 열고 연필 아이콘(Edit)을 눌러 맨 끝에 줄을 추가한 뒤 `Commit changes`를 누릅니다. 엑셀로 열어 저장하면 종목코드 앞의 0이 사라질 수 있으니 GitHub 화면에서 고치는 것을 권합니다. 코스피·코스닥은 스크립트가 알아서 찾습니다.

## 두 지도 (S&P 500, 나스닥 100)

지도 오른쪽 위 버튼으로 전환합니다. S&P 500은 지수 비중만큼, 나스닥 100은 시가총액만큼 칸 크기가 정해집니다. 연계 목록은 두 지도가 같이 씁니다. 검색창에서 다른 지수에만 있는 종목(예: 나스닥 100의 SPCX)을 찾으면 그 지수로 자동으로 넘어갑니다. 주소 끝 `#idx=ndx&us=SPCX`처럼 지수와 종목이 함께 저장돼 링크로 공유됩니다.

**구성 종목이 바뀌면** `data/universe.csv`의 `in_sp500`, `in_ndx100` 열(Y/N)을 고치거나 줄을 추가합니다. 새 종목은 `sector`(정보기술, 산업재 등 11개 섹터 중 하나), `sub_industry`, `theme`(연계 섹터 이름)을 함께 적어 주세요. S&P 500 비중(`sp_weight`)은 가끔 us500.com 등에서 갱신하면 됩니다.

## 그날 재료 적기 (선택)

`data/themes.csv`에 `date,theme,reason,source` 형식으로 한 줄씩 적습니다. `date`는 **미국 거래일**(예: 2026-11-06), `theme`은 페이지의 연계 섹터 이름과 똑같이 적습니다. 그날 데이터가 게시될 때 해당 섹터에 재료가 표시됩니다.

## 지표 읽는 법

- **외국인 연동:** 미국 종목이 오른 날 다음 한국 거래일에 외국인이 그 한국 종목을 순매수한 정도(상관계수)입니다. 추천 테마 카드의 "외국인 확인"은 외국인 연동 0.2 이상이고 추천 종목들의 최근 5일 외국인 순매수가 플러스인 경우입니다.
- **외국인 5일:** 최근 5거래일 외국인 순매수 금액(순매매량 × 종가, 억 원)입니다.

- **상관계수:** 미국 종목이 오른 날 다음 날 한국 종목도 오르고 내린 날 내리는 정도입니다. 1에 가까울수록 같이 움직이고, 0이면 관계가 없습니다.
- **방향 일치율:** 다음 날 같은 방향으로 움직인 날의 비율입니다. 50%면 동전 던지기와 같습니다.
- **반응 배율:** 미국 종목이 1% 움직일 때 다음 날 한국 종목이 평균 몇 % 움직였는지입니다.

## 문제가 생기면

- **Actions에 빨간 X:** 실패한 실행 → `build` → 빨간 X 단계의 마지막 줄(`스캔 실패:`)을 확인합니다.
- **deploy 단계 오류:** 설정 2번(Source를 GitHub Actions로)이 빠진 경우입니다.
- **데이터 보관 단계 권한 오류(403):** `Settings` → `Actions` → `General` → `Workflow permissions`를 `Read and write permissions`로 바꿉니다.
- **갱신이 멈췄을 때:** 공개 저장소는 60일 동안 활동이 없으면 GitHub이 자동 실행을 멈출 수 있습니다. 알림 메일이 오면 `Actions` 탭의 `Enable workflow`로 다시 켭니다.

## 데이터 출처와 한계

- 주가: Yahoo Finance 종가. 개인 용도 전제의 데이터이므로 페이지 외에 데이터를 따로 게시하는 일은 피해 주세요.
- 구성 종목·섹터: 위키백과 S&P 500 구성 종목 목록과 나스닥 100 구성 종목(2026년 11월 5일 기준), S&P 500 지수 비중: us500.com. 가끔 갱신이 필요합니다.
- 한국 종목코드는 Bigdata.com 상장 정보로 회사 이름을 대조해 확인했습니다. 0126Z0(삼성에피스홀딩스), 0053F0(티앤이코리아)처럼 새 형식의 종목코드는 Yahoo Finance가 아직 시세를 주지 않을 수 있어, 그 경우 빈칸으로 나옵니다.
- 연계 목록: 인터즈 종목 선정 소모임 자료, 확인한 기사, 업종 분류를 바탕으로 정리. 근거가 `같은 업종`·`추론`인 줄은 직접 확인이 필요합니다.
- 동아리 내부 학습용이며 투자 권유가 아닙니다.

## 부록: `.github/workflows/pages.yml`

```yaml
name: 연계 지도 자동 갱신

on:
  schedule:
    - cron: "30 21 * * 1-5"     # 화~토 06:30 (한국 시간), 미장 마감 뒤
    - cron: "30 9 * * 1-5"      # 월~금 18:30 (한국 시간), 국장 마감·외국인 확정치 뒤
  workflow_dispatch: {}          # Actions 탭에서 'Run workflow'로 바로 실행
  push:
    branches: [main]             # 연계 종목(data/links.csv) 등을 고치면 바로 다시 계산

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: 패키지 설치
        run: pip install -r requirements.txt

      - name: 시세 받기와 커플링 계산
        run: python link_scan.py state

      - name: 데이터 보관
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          cd state
          git init -q -b data
          git add -A
          git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" commit -q -m "데이터 갱신 $(date -u +%F)"
          git push -q -f "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" data

      - name: 웹페이지 묶기
        run: |
          mkdir -p _site/data
          cp -r docs/. _site/
          cp state/link.json _site/data/

      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```
