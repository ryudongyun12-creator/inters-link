# -*- coding: utf-8 -*-
"""
INTERS 미장 → 국장 연계 지도: 하루 두 번 갱신 (미장 마감 뒤, 국장 마감 뒤)

1) data/universe.csv 의 미국 종목(S&P 500 + 나스닥 100)과 data/links.csv 의 한국 종목 종가를 Yahoo Finance에서 받습니다.
2) 가장 최근에 마감한 미국장 등락률과 가장 최근에 마감한 국장 등락률을 구합니다.
   예상 반응 = 반응 배율 × 가장 최근 미국 등락률 (다음 국장 참고치)
3) 연결된 종목 쌍마다 최근 미국 거래일 60일 동안의 커플링(상관계수·방향 일치율·반응 배율)을 계산합니다.
4) 한국 종목 시세와 외국인 순매매는 네이버 금융(외국인·기관 매매 페이지)에서 받고, 미장이 움직인 다음 날
   외국인이 그 종목을 사고팔았는지(외국인 연동)도 계산합니다. 네이버가 막히면 시세만 Yahoo로 받습니다.

    python link_scan.py state      # state/link.json 저장
"""

import csv
import datetime as dt
import io
import json
import re
import os
import sys
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

WINDOW = 60       # 커플링을 재는 미국 거래일 수
MIN_DAYS = 20     # 이보다 겹친 날이 적으면 계산하지 않음
CHUNK = 100
HERE = os.path.dirname(os.path.abspath(__file__))


def log(m):
    print(m, flush=True)


def read_csv(name):
    with open(os.path.join(HERE, "data", name), encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def download(symbols):
    """{심볼: 종가 Series} — 받지 못한 심볼은 빠짐."""
    import yfinance as yf

    out = {}
    for i in range(0, len(symbols), CHUNK):
        batch = symbols[i:i + CHUNK]
        data = None
        for attempt in range(4):
            try:
                data = yf.download(batch, period="9mo", interval="1d", auto_adjust=True,
                                   group_by="ticker", threads=True, progress=False)
                if data is not None and not data.empty:
                    break
            except Exception as e:
                log(f"  다운로드 오류({type(e).__name__}), 재시도")
            time.sleep(10 * (attempt + 1))
        if data is None or data.empty:
            continue
        if isinstance(data.columns, pd.MultiIndex):
            have = set(data.columns.get_level_values(0))
            frames = {s: data[s] for s in batch if s in have}
        else:
            frames = {batch[0]: data}
        for s, d in frames.items():
            c = d["Close"].dropna() if "Close" in d else pd.Series(dtype=float)
            if len(c) > 5:
                c.index = pd.to_datetime(c.index).strftime("%Y-%m-%d")
                out[s] = c[~c.index.duplicated()]
        log(f"  {min(i + CHUNK, len(symbols))}/{len(symbols)} 받음 (누적 {len(out)})")
        time.sleep(1)
    return out


NAVER_PAGES = 5   # 외국인 매매 페이지 1쪽 = 약 20거래일
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _num(x):
    s = str(x).replace(",", "").replace("+", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return np.nan


ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
DATE_RE = re.compile(r"^(\d{4})[.\-/](\d{2})[.\-/](\d{2})$")
DIAG = {"done": False}
FLOW_START = (dt.date.today() - dt.timedelta(days=200)).strftime("%Y%m%d")
FLOW_END = dt.date.today().strftime("%Y%m%d")


def _frame(rows, cols):
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=["date"] + cols).drop_duplicates("date").sort_values("date").set_index("date")
    return d if len(d) > 5 else None


def _src_krx(code, requests):
    """1순위: 한국거래소 투자자별 거래실적(pykrx). 외국인 순매수 금액(원)이 그대로 나옴."""
    from pykrx import stock

    df = stock.get_market_trading_value_by_date(FLOW_START, FLOW_END, code)
    if df is None or df.empty:
        return None, "KRX 0줄"
    col = next((c for c in df.columns if "외국인" in str(c)), None)
    if col is None:
        return None, f"KRX 열 없음 {list(df.columns)[:6]}"
    rows = [(pd.Timestamp(i).strftime("%Y-%m-%d"), np.nan, float(v) / 1e8, np.nan) for i, v in df[col].items()]
    return _frame(rows, ["close", "f_val", "f_hold"]), f"KRX {len(rows)}줄"


def _src_sisejson(code, requests):
    """2순위: 네이버 일별 시세 API. 종가와 외국인 지분율(소진율) → 지분율 변화로 외국인 매매를 대신 잼."""
    url = (f"https://api.finance.naver.com/siseJson.naver?symbol={code}&requestType=1"
           f"&startTime={FLOW_START}&endTime={FLOW_END}&timeframe=day")
    r = requests.get(url, headers={**UA, "Referer": "https://finance.naver.com/"}, timeout=20)
    txt = r.content.decode("utf-8", errors="ignore")
    if not re.search(r'"\d{8}"', txt):
        txt = r.content.decode("euc-kr", errors="ignore")
    rows = []
    for ds, rest in re.findall(r'\[\s*"(\d{8})"\s*,([^\]]*)\]', txt):
        v = [_num(x) for x in rest.split(",")]
        if len(v) >= 6:
            rows.append((f"{ds[:4]}-{ds[4:6]}-{ds[6:]}", v[3], np.nan, v[5]))
    return _frame(rows, ["close", "f_val", "f_hold"]), f"일별시세API 응답 {r.status_code}, {len(rows)}줄"


def _src_pc(code, requests):
    """3순위: 네이버 PC 외국인·기관 매매 페이지. 날짜 칸을 찾고 그 뒤 칸 순서로 읽음."""
    rows, note = [], ""
    for page in range(1, NAVER_PAGES + 1):
        url = f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}"
        r = requests.get(url, headers={**UA, "Referer": f"https://finance.naver.com/item/main.naver?code={code}"}, timeout=20)
        html = r.content.decode("euc-kr", errors="ignore")
        if "외국인" not in html:
            html = r.content.decode("utf-8", errors="ignore")
        got = []
        for tr in ROW_RE.findall(html):
            cells = [TAG_RE.sub("", c).replace("&nbsp;", " ").strip() for c in CELL_RE.findall(tr)]
            k = next((i for i, c in enumerate(cells) if DATE_RE.match(c)), None)
            if k is None or len(cells) - k < 9:
                continue
            y, m, d = DATE_RE.match(cells[k]).groups()
            after = cells[k + 1:]
            close, fnet, hold = _num(after[0]), _num(after[5]), _num(after[7])
            got.append((f"{y}-{m}-{d}", close, fnet * close / 1e8 if np.isfinite(fnet) else np.nan, hold))
        if page == 1:
            title = re.search(r"<title>(.*?)</title>", html, re.S)
            note = (f"PC 응답 {r.status_code}, {len(r.content):,}바이트, 제목 '{(title.group(1).strip() if title else '')[:30]}', "
                    f"'외국인' {'있음' if '외국인' in html else '없음'}, 날짜 {len(re.findall(r'\d{4}\.\d{2}\.\d{2}', html))}개, 1쪽 {len(got)}줄")
        if not got:
            break
        rows += got
        time.sleep(0.25)
    return _frame(rows, ["close", "f_val", "f_hold"]), note


def korea_flow(code):
    """외국인 수급(가능하면 시세도): 출처를 차례로 시도. (DataFrame[close, f_val(억 원), f_hold(%)], 출처) 또는 (None, '')"""
    import requests

    notes = []
    for name, fn in (("KRX", _src_krx), ("네이버 일별시세", _src_sisejson), ("네이버 PC", _src_pc)):
        try:
            d, note = fn(code, requests)
        except Exception as e:
            d, note = None, f"{name} 오류 {type(e).__name__}: {str(e)[:60]}"
        notes.append(note)
        if d is not None and (d["f_val"].notna().sum() > 5 or d["f_hold"].notna().sum() > 5):
            if not DIAG["done"]:
                log(f"[외국인 수급 진단] {code}: " + " / ".join(notes) + f" → 성공({name})")
                DIAG["done"] = True
            return d, name
    if not DIAG["done"]:
        log(f"[외국인 수급 진단] {code}: " + " / ".join(notes) + " → 실패")
        DIAG["done"] = True
    return None, ""


def market_caps(symbols):
    """나스닥 100 지도 칸 크기용 시가총액 (받지 못하면 빠짐)."""
    import yfinance as yf

    caps = {}
    for s in symbols:
        for attempt in range(2):
            try:
                fi = yf.Ticker(s).fast_info
                v = getattr(fi, "market_cap", None) or fi["market_cap"]
                if v and float(v) > 0:
                    caps[s] = float(v)
                break
            except Exception:
                time.sleep(2)
        time.sleep(0.2)
    return caps


def r2(x, n=2):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def main():
    state = sys.argv[1] if len(sys.argv) > 1 else "state"
    sp = read_csv("universe.csv")
    links = [r for r in read_csv("links.csv") if r.get("us_ticker") and r.get("kr_name")]
    themes = read_csv("themes.csv")
    log(f"미국 {len(sp)}개, 연계 {len(links)}줄")

    # 미국
    ysym = {r["ticker"]: r["ticker"].replace(".", "-") for r in sp}
    us_px = download(sorted(set(ysym.values())))
    us_ret = pd.DataFrame({t: us_px[s].pct_change() * 100 for t, s in ysym.items() if s in us_px})
    log(f"미국 시세 {us_ret.shape[1]}개")
    ndx = [r for r in sp if r.get("in_ndx100") == "Y"]
    caps = market_caps([ysym[r["ticker"]] for r in ndx])
    log(f"나스닥 100 시가총액 {len(caps)}/{len(ndx)}개")

    # 한국: 외국인 수급은 KRX → 네이버 일별시세 → 네이버 PC 순서로, 시세는 거기서 받거나 Yahoo로
    codes = sorted({r["kr_code"].zfill(6) if r["kr_code"].isdigit() else r["kr_code"] for r in links if r["kr_code"]})
    kr_close, kr_flow, srcs = {}, {}, {}
    for k, c in enumerate(codes, start=1):
        d, src = korea_flow(c)
        if d is not None:
            kr_flow[c] = d
            srcs[src] = srcs.get(src, 0) + 1
            if d["close"].notna().sum() > 5:
                kr_close[c] = d["close"].dropna()
        if k % 25 == 0:
            log(f"  한국 {k}/{len(codes)} (외국인 {len(kr_flow)}, 출처 {srcs})")
        time.sleep(0.3)
    log(f"외국인 수급 출처별 종목 수: {srcs or '없음'}")
    left = [c for c in codes if c not in kr_close]
    if left:
        log(f"시세를 Yahoo로 받을 종목 {len(left)}개")
        ypx = download([c + ".KS" for c in left])
        left2 = [c for c in left if c + ".KS" not in ypx]
        ypx.update(download([c + ".KQ" for c in left2]) if left2 else {})
        for c in left:
            s = ypx.get(c + ".KS", ypx.get(c + ".KQ"))
            if s is not None:
                kr_close[c] = s
        # Yahoo에도 없는 종목(새 형식 종목코드 등)은 네이버 일별 시세로
        import requests
        for c in [c for c in left if c not in kr_close]:
            try:
                d, _ = _src_sisejson(c, requests)
                if d is not None and d["close"].notna().sum() > 5:
                    kr_close[c] = d["close"].dropna()
            except Exception:
                pass
    kr_ret = pd.DataFrame({c: s.sort_index().pct_change() * 100 for c, s in kr_close.items()})
    # 외국인 흐름: 순매수 금액(억 원)이 있으면 그것, 없으면 지분율 변화(%p)
    fser = {}
    for c, d in kr_flow.items():
        fser[c] = d["f_val"] if d["f_val"].notna().sum() > 5 else d["f_hold"].diff()
    kr_fval = pd.DataFrame(fser).sort_index()
    log(f"한국 시세 {kr_ret.shape[1]}/{len(codes)}개, 외국인 {len(kr_flow)}개, 시세 못 받은 종목코드: {[c for c in codes if c not in kr_close]}")
    if us_ret.empty or kr_ret.empty:
        raise RuntimeError("시세를 받지 못했습니다.")

    # 거래일 (종목의 절반 이상이 거래한 날)
    us_days = [d for d in us_ret.index if us_ret.loc[d].notna().mean() > 0.5]
    kr_days = [d for d in kr_ret.index if kr_ret.loc[d].notna().mean() > 0.5]
    us_ret, kr_ret = us_ret.loc[us_days].sort_index(), kr_ret.loc[kr_days].sort_index()
    kr_days = list(kr_ret.index)
    nxt = {}
    for d in us_ret.index:
        later = [k for k in kr_days if k > d]
        if later:
            nxt[d] = later[0]
    usable = [d for d in us_ret.index if d in nxt]
    if not usable:
        raise RuntimeError("미국 거래일 다음의 한국 거래일이 없습니다.")
    d_us = list(us_ret.index)[-1]            # 가장 최근에 마감한 미국장
    d_kr = kr_days[-1]                        # 가장 최근에 마감한 국장
    reacted = d_kr > d_us                     # 그 미국장에 대한 국장 반응이 이미 나왔는지
    nd = dt.date.fromisoformat(d_us) + dt.timedelta(days=1)
    while nd.weekday() >= 5:
        nd += dt.timedelta(days=1)
    next_kr = d_kr if reacted else nd.isoformat()   # 예상 반응이 가리키는 국장 날짜 (휴장일은 반영 안 함)
    win = usable[-WINDOW:]
    log(f"기준: 미국 {d_us} 마감, 한국 {d_kr} 마감, 예상 반응 대상 국장 {next_kr}, 커플링 기간 {win[0]} ~ {win[-1]} ({len(win)}일)")

    # 미국 종목 표
    us_rows = []
    for r in sp:
        v = us_ret.at[d_us, r["ticker"]] if r["ticker"] in us_ret else np.nan
        w = float(r["sp_weight"]) if r.get("sp_weight") else None
        cap = None
        if r.get("in_ndx100") == "Y":
            # 시가총액을 못 받으면 S&P 비중으로 어림 (S&P 전체 약 68조 달러), 그것도 없으면 500억 달러
            cap = caps.get(ysym[r["ticker"]]) or (w * 6.8e11 if w else 5e10)
        us_rows.append([r["ticker"], r["company"], r["sector"], r["sub_industry"], r["theme"],
                        w, r2(cap / 1e9, 4) if cap else None, r2(v),
                        "Yahoo Finance 종가" if np.isfinite(v) else "시세 없음",
                        r.get("in_sp500") == "Y", r.get("in_ndx100") == "Y"])

    # 연계 쌍 표
    kr_last = {c: kr_ret.at[d_kr, c] for c in kr_ret.columns}
    # 종목별 외국인 요약 (가장 최근 한국 마감까지)
    fsum = {}
    for c, d in kr_flow.items():
        v = d["f_val"].dropna()
        h = d["f_hold"].dropna()
        fsum[c] = (v.iloc[-1] if len(v) else np.nan, v.iloc[-5:].sum() if len(v) else np.nan,
                   h.iloc[-1] if len(h) else np.nan, (h.iloc[-1] - h.iloc[-6]) if len(h) >= 6 else np.nan)
    f_date = max((d.dropna(how="all", subset=["f_val", "f_hold"]).index[-1] for d in kr_flow.values()), default=None)
    us_last = {t: us_ret.at[d_us, t] for t in us_ret.columns}
    link_rows = []
    for i, r in enumerate(links, start=1):
        t, c = r["us_ticker"], (r["kr_code"].zfill(6) if r["kr_code"].isdigit() else r["kr_code"])
        corr = hit = beta = fcorr = fhit = None
        n = 0
        if t in us_ret and c in kr_ret:
            x = us_ret.loc[win, t].to_numpy(dtype=float)
            y = np.array([kr_ret.at[nxt[d], c] for d in win], dtype=float)
            m = ~(np.isnan(x) | np.isnan(y))
            x, y = x[m], y[m]
            n = int(len(x))
            if n >= MIN_DAYS and np.std(x) > 0 and np.std(y) > 0:
                corr = float(np.corrcoef(x, y)[0, 1])
                nz = (x != 0) & (y != 0)
                hit = float((np.sign(x[nz]) == np.sign(y[nz])).mean() * 100) if nz.any() else None
                beta = float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))
        if t in us_ret and c in kr_fval:
            # 외국인 연동: 미국 하루 등락 vs 다음 한국 거래일 외국인 순매수 금액
            x = us_ret.loc[win, t].to_numpy(dtype=float)
            y = np.array([kr_fval.at[nxt[d], c] if nxt[d] in kr_fval.index else np.nan for d in win], dtype=float)
            m = ~(np.isnan(x) | np.isnan(y))
            x, y = x[m], y[m]
            if len(x) >= MIN_DAYS and np.std(x) > 0 and np.std(y) > 0:
                fcorr = float(np.corrcoef(x, y)[0, 1])
                nz = (x != 0) & (y != 0)
                fhit = float((np.sign(x[nz]) == np.sign(y[nz])).mean() * 100) if nz.any() else None
        u = us_last.get(t, np.nan)
        expected = beta * u if (beta is not None and np.isfinite(u)) else None
        fs = fsum.get(c, (np.nan,) * 4)
        link_rows.append([f"{t}-{i}", t, r["kr_name"], c, r["relation"], r["note"], r["basis"],
                          r2(expected) if expected is not None else None, r2(kr_last.get(c, np.nan)),
                          r2(corr), r2(hit, 0) if hit is not None else None, r2(beta), n,
                          r2(fcorr), r2(fhit, 0) if fhit is not None else None,
                          r2(fs[0], 1), r2(fs[1], 1), r2(fs[2], 2), r2(fs[3], 2)])

    # 연계 섹터 전체 목록 + 그날(미국 거래일) 재료가 적혀 있으면 함께
    reason = {r["theme"]: (r["reason"], r.get("source", "")) for r in themes if r.get("date") == d_us and r.get("reason")}
    order = list(dict.fromkeys(r["theme"] for r in sp))
    th_rows = [[t, *reason.get(t, ("", ""))] for t in order]
    now = dt.datetime.now(ZoneInfo("Asia/Seoul"))
    out = {
        "meta": {"us_date": d_us, "kr_date": d_kr, "next_kr_date": next_kr, "reacted": bool(reacted),
                 "window_start": win[0], "window_end": win[-1],
                 "window_days": len(win), "generated_kst": now.strftime("%Y-%m-%d %H:%M"), "price_source": "Yahoo Finance(미국)·네이버 금융(한국)", "flow_date": f_date,
                 "timestamp": now.timestamp()},
        "us": {"cols": ["ticker", "company", "sector", "sub_industry", "theme", "weight", "ndx_cap", "change_pct",
                        "value_source", "in_sp", "in_ndx"], "rows": us_rows},
        "links": {"cols": ["link_id", "ticker", "kr_name", "kr_code", "relation", "note", "basis",
                           "expected_pct", "kr_last_pct", "corr", "hit_rate", "beta", "n_days",
                           "f_corr", "f_hit", "f_net_1d", "f_net_5d", "f_hold", "f_hold_chg5"], "rows": link_rows},
        "themes": {"cols": ["theme", "reason", "reason_source"], "rows": th_rows},
    }
    os.makedirs(state, exist_ok=True)
    path = os.path.join(state, "link.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    os.replace(path + ".tmp", path)
    measured = sum(1 for r in link_rows if r[9] is not None)
    log(f"외국인 연동 측정 {sum(1 for r in link_rows if r[13] is not None)}쌍, 외국인 기준일 {f_date}")
    log(f"완료: 미국 등락률 {sum(1 for r in us_rows if r[7] is not None)}개, 커플링 측정 {measured}/{len(link_rows)}쌍")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"스캔 실패: {type(e).__name__}: {e}")
        sys.exit(1)
