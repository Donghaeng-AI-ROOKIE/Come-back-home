"""PDF 34편을 페이지 단위로 추출하고 행동 관련 문장 후보를 만든다.

원문 PDF는 저장소 밖 Downloads 폴더에 둔다. 이 스크립트는 페이지 텍스트와
후보 문장을 로컬 실험 디렉터리에 생성하며, PDF 파일 자체를 복사하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path


ROOTS = (
    Path("/Users/damisoda/Downloads/치매"),
)
HERE = Path(__file__).resolve().parent

KEYWORDS_KO = (
    "배회", "실종", "길찾기", "방향", "경로", "보행", "걷", "이동", "직진",
    "되돌", "멈", "머무", "숨", "도움", "요청", "발견", "물가", "익사",
    "위험", "횡단", "교통", "버스", "지하철", "소음", "불안", "고착", "회피",
    "이탈", "탈출", "루틴", "낯선", "익숙", "랜드마크", "공간기억", "탐색",
)
KEYWORDS_EN = (
    "wander", "missing", "wayfind", "navigation", "route", "walk", "gait",
    "elop", "escape", "flee", "hide", "remain", "stay", "stop", "continue",
    "straight", "backtrack", "help", "assist", "found", "location", "water",
    "drown", "hazard", "danger", "road", "cross", "traffic", "transport",
    "bus", "train", "subway", "noise", "anxiety", "distress", "stereotyp",
    "routine", "familiar", "unfamiliar", "landmark", "spatial", "search",
)
CONDITION_MARKERS = (
    "when ", "while ", "after ", "before ", "during ", "if ", "under ",
    "because ", "associated with", "more likely", "less likely", "tended to",
    "characterized by", "in response to", "in the presence of",
    "때 ", "경우", "하면", "할 때", "에서", "때문", "따라", "높을수록",
    "낮을수록", "관련", "경향", "반응",
)
BEHAVIOR_MARKERS = KEYWORDS_KO + KEYWORDS_EN


@dataclass(frozen=True)
class Paper:
    paper_id: str
    population: str
    region: str
    category: str
    path: Path


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def slug(index: int, path: Path) -> str:
    pop = "DEM" if "치매" in nfc(str(path)) else "DEV"
    return f"{pop}-{index:02d}"


def discover() -> list[Paper]:
    paths = sorted((p for root in ROOTS for p in root.rglob("*.pdf")),
                   key=lambda p: nfc(str(p)))
    papers = []
    for index, path in enumerate(paths, 1):
        parts = [nfc(x) for x in path.parts]
        population = "dementia"   # 코퍼스는 치매 단독 (2026-08-03)
        region = "domestic" if "국내" in parts else "international"
        title = nfc(path.stem)
        m = re.match(r"^\[([^\]]+)\]", title)
        category = m.group(1) if m else "기타"
        papers.append(Paper(slug(index, path), population, region, category, path))
    return papers


def extract_pages(path: Path) -> tuple[list[str], str | None]:
    proc = subprocess.run(
        # Poppler 기본 reading-order가 2단 논문에서 열을 순서대로 이어 주는 반면
        # -layout은 좌우 열 문장을 한 줄에 섞어 인용을 훼손할 수 있다.
        ["pdftotext", "-enc", "UTF-8", str(path), "-"],
        capture_output=True,
        check=False,
    )
    error = None
    if proc.returncode:
        error = proc.stderr.decode("utf-8", "replace").strip()
    text = proc.stdout.decode("utf-8", "replace")
    pages = [nfc(page).strip() for page in text.split("\f")]
    if pages and not pages[-1]:
        pages.pop()
    return pages, error


def sentences(text: str) -> list[str]:
    compact = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    compact = re.sub(r"[ \t]+", " ", compact)
    # PDF의 줄바꿈은 대부분 문장 경계가 아니라 지면 폭에 따른 soft wrap이다.
    # 이를 문장 경계로 취급하면 인용이 반쪽으로 잘리므로 공백으로 합친다.
    compact = re.sub(r"\s*\n+\s*", " ", compact)
    parts = re.split(r"(?<=[.!?。])\s+", compact)
    out = []
    for part in parts:
        part = part.strip()
        if 35 <= len(part) <= 900:
            out.append(part)
    return out


def candidate_score(sentence: str) -> tuple[int, list[str]]:
    lower = sentence.lower()
    hits = [kw for kw in BEHAVIOR_MARKERS if kw.lower() in lower]
    cond = sum(1 for marker in CONDITION_MARKERS if marker.lower() in lower)
    score = min(len(set(hits)), 4) + min(cond, 2)
    if re.search(r"\b(p\s*[<=>]|odds ratio|OR\s*=|r\s*=|%|n\s*=)\b", sentence,
                 re.IGNORECASE):
        score += 1
    return score, sorted(set(hits), key=lambda x: x.lower())


def main(output: Path) -> None:
    pages_dir = output / "corpus" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "corpus" / "manifest.jsonl"
    candidates_path = output / "candidates.jsonl"

    with manifest_path.open("w", encoding="utf-8") as manifest, \
            candidates_path.open("w", encoding="utf-8") as candidates:
        for paper in discover():
            pages, error = extract_pages(paper.path)
            page_path = pages_dir / f"{paper.paper_id}.jsonl"
            chars = 0
            nonempty = 0
            candidate_count = 0
            with page_path.open("w", encoding="utf-8") as page_file:
                for page_no, text in enumerate(pages, 1):
                    chars += len(text)
                    nonempty += bool(text.strip())
                    page_file.write(json.dumps({
                        "paper_id": paper.paper_id,
                        "pdf_page": page_no,
                        "text": text,
                    }, ensure_ascii=False) + "\n")
                    for sentence_no, sentence in enumerate(sentences(text), 1):
                        score, hits = candidate_score(sentence)
                        if score < 2:
                            continue
                        candidate_count += 1
                        candidates.write(json.dumps({
                            "candidate_id": f"{paper.paper_id}-P{page_no:04d}-S{sentence_no:03d}",
                            "paper_id": paper.paper_id,
                            "population": paper.population,
                            "category": paper.category,
                            "title": nfc(paper.path.stem),
                            "source_path": nfc(str(paper.path)),
                            "pdf_page": page_no,
                            "sentence": sentence,
                            "score": score,
                            "keyword_hits": hits,
                        }, ensure_ascii=False) + "\n")
            manifest.write(json.dumps({
                "paper_id": paper.paper_id,
                "population": paper.population,
                "region": paper.region,
                "category": paper.category,
                "title": nfc(paper.path.stem),
                "source_path": nfc(str(paper.path)),
                "sha256": sha256(paper.path),
                "pages": len(pages),
                "nonempty_pages": nonempty,
                "extracted_chars": chars,
                "candidate_count": candidate_count,
                "extract_error": error,
            }, ensure_ascii=False) + "\n")
            print(f"{paper.paper_id}: pages={len(pages)} chars={chars} "
                  f"candidates={candidate_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    main(args.output)
