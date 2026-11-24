from ragdesk.evaluation.run import _load, evaluate


async def test_bundled_eval_meets_quality_bar() -> None:
    report = await evaluate(_load(None, "corpus.jsonl"), _load(None, "questions.jsonl"), k=3)
    assert report.recall >= 0.9, report.misses
    assert report.mrr >= 0.85
    assert report.abstention >= 0.66
