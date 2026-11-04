"""The packaged control page must survive cleanup and normal Git packaging."""

from pathlib import Path
import re
import subprocess

from fastapi.testclient import TestClient

from host_services.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_control_page_and_referenced_assets_are_served():
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assets = re.findall(r'(?:src|href)="(/assets/[^"?#]+)', page.text)
        assert assets, "The packaged page must reference its compiled assets"
        for asset in assets:
            response = client.get(asset)
            assert response.status_code == 200, asset
            assert response.content, asset
            assert "text/html" not in response.headers["content-type"], asset
        notice = client.get("/THIRD_PARTY_NOTICES.txt")
        assert notice.status_code == 200
        assert "Vue" in notice.text


def test_control_page_assets_and_notice_are_not_hidden_from_packaging():
    files = sorted((ROOT / "kiosk" / "dist").rglob("*"))
    files = [p.relative_to(ROOT).as_posix() for p in files if p.is_file()]
    assert "kiosk/dist/index.html" in files
    assert "kiosk/dist/THIRD_PARTY_NOTICES.txt" in files
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", *files],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1, result.stdout or result.stderr
