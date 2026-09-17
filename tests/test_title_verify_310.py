"""Title switch verify: overlap is file text, not model spelling. No live calls."""

from sentence_reading.title_verify import overlap_file, parse_extract, pick_hit, verify_windows


def test_truncated_json_still_yields_title():
    raw = (
        '{"title": "Mitigating Deactivation in Dry Methane Reforming", '
        '"authors": ["Bahari, M.B.", "Jal'
    )
    parsed = parse_extract(raw)
    assert parsed["title"].startswith("Mitigating Deactivation")
    assert "Bahari, M.B." in parsed["authors"]


def test_overlap_uses_file_not_misspelled_model_names():
    blob = "Bahari Mamat Jalil Hassan wrote the review"
    hit_authors = [
        {"family": "Bahari", "given": "M. B."},
        {"family": "Other", "given": "Name"},
    ]
    assert overlap_file(hit_authors, blob) == ["bahari"]


def test_highest_overlap_hit_keeps_extracted_title():
    blob = "Wang Littlewood Marks Stair Weitz coking methane"
    calls = {"n": 0}

    def extract(_chunk):
        calls["n"] += 1
        if calls["n"] < 3:
            return {"title": "", "authors": [], "stop": "section"}
        return {
            "title": "Coking Can Enhance Product Yields",
            "authors": ["Wang, X."],
            "stop": "",
        }

    def search(_title, _author):
        return [
            {
                "score": 20,
                "doi": "10.1000/low",
                "authors": [{"family": "Wang", "given": "X."}],
            },
            {
                "score": 60,
                "doi": "10.1000/high",
                "authors": [{"family": "Wang", "given": "X."}, {"family": "Marks", "given": "T."}],
            },
            {
                "score": 90,
                "doi": "10.1000/miss",
                "authors": [{"family": "Nobody", "given": "Z."}],
            },
        ]

    windows = [(1, "section one text here " * 5), (1, "section two text here " * 5), (1, "title window " * 5)]
    out = verify_windows(windows, blob, extract=extract, search=search)
    assert out["ok"] is True
    assert out["title"] == "Coking Can Enhance Product Yields"
    assert out["doi"] == "10.1000/high"
    assert out["windows"] == 3
    picked = pick_hit("Coking Can Enhance Product Yields", ["Wang, X."], blob, search=search)
    assert picked["doi"] == "10.1000/high"
