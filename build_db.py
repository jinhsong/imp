#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
전파인증(적합성평가) 데이터(.xls = euc-kr HTML 테이블) → 검색용 JSON 변환기.

RRA 검색결과 다운로드 파일은 실제로는 euc-kr 로 인코딩된 HTML <table> 입니다.
이 스크립트는 그 표를 읽어 index.html 이 브라우저에서 바로 검색할 수 있는
rra_db.json 으로 변환합니다.

  - 파생모델명 셀의 <br> 구분 다중 모델을 각각 배열로 펼칩니다.
  - 모델명/파생모델/기자재명칭/상호를 합친 소문자 검색문자열(_s)을 미리 만들어 둡니다.

사용법:
  python3 build_db.py                      # data/Device_list.xls → rra_db.json
  python3 build_db.py 입력.xls 출력.json
"""
import sys
import json
import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser

# 입력 파일 헤더 순서 (파일의 <th> 순서와 동일해야 함)
FIELDS = ["no", "company", "equipment", "model", "country",
          "date", "status", "certNo", "maker", "derivRaw"]


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_td = False
        self.in_thead = False
        self.cur = []          # 현재 셀 텍스트 조각
        self.row = []          # 현재 행의 셀들
        self.rows = []         # 모든 데이터 행
        self.deriv_breaks = False

    def handle_starttag(self, tag, attrs):
        if tag == "thead":
            self.in_thead = True
        elif tag == "td":
            self.in_td = True
            self.cur = []
        elif tag == "br" and self.in_td:
            self.cur.append("\n")   # <br> → 줄바꿈으로 보존 (파생모델 구분)

    def handle_endtag(self, tag):
        if tag == "thead":
            self.in_thead = False
        elif tag == "td":
            self.in_td = False
            self.row.append("".join(self.cur).strip())
        elif tag == "tr":
            if not self.in_thead and self.row:
                self.rows.append(self.row)
            self.row = []

    def handle_data(self, data):
        if self.in_td:
            self.cur.append(data)


def clean(s: str) -> str:
    s = html.unescape(s or "")
    # 셀 내부의 연속 공백/개행 정리 (단, 파생모델 구분 개행은 split 후 처리)
    return s.strip()


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "data/Device_list.xls"
    out = sys.argv[2] if len(sys.argv) > 2 else "rra_db.json"

    with open(src, "rb") as f:
        text = f.read().decode("euc-kr", "replace")

    p = TableParser()
    p.feed(text)

    records = []
    for cells in p.rows:
        if len(cells) < len(FIELDS):
            continue
        rec = {FIELDS[i]: clean(cells[i]) for i in range(len(FIELDS))}
        # 셀 내부 다중 공백 정리 (개행 기준 분리는 derivRaw 에서만)
        for k in ("company", "equipment", "model", "country", "status", "certNo", "maker"):
            rec[k] = re.sub(r"\s+", " ", rec[k]).strip()
        # 파생모델: 개행으로 분리
        derivs = [re.sub(r"\s+", " ", d).strip() for d in rec.pop("derivRaw").split("\n")]
        rec["derivModels"] = [d for d in derivs if d]
        # 검색 인덱스 문자열 (모델 + 파생 + 기자재 + 상호), 소문자
        idx = " ".join([rec["model"]] + rec["derivModels"]
                       + [rec["equipment"], rec["company"]])
        rec["_s"] = idx.lower()
        records.append(rec)

    db = {
        "source": src,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(records),
        "records": records,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))

    derv = sum(len(r["derivModels"]) for r in records)
    print("입력 :", src)
    print("출력 :", out)
    print("레코드:", len(records), "건  /  파생모델 합계:", derv, "개")


if __name__ == "__main__":
    main()
