from pathlib import Path


def test_release_documents_include_privacy_and_risk_boundaries() -> None:
    risk = Path("docs/07-risk-disclaimer.md").read_text(encoding="utf-8")
    privacy = Path("docs/06-privacy-and-data.md").read_text(encoding="utf-8")

    assert "不构成投资建议" in risk
    assert "本地" in privacy
    assert "token" not in privacy.lower() or "不" in privacy


def test_release_checklist_covers_packaged_launch_and_source_failure() -> None:
    checklist = Path("docs/release-checklist.md").read_text(encoding="utf-8")

    assert "Windows packaged launch" in checklist
    assert "provider failure" in checklist
