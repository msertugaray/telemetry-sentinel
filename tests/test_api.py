"""API entegrasyon testleri (FastAPI TestClient).

Dosya yükleme -> analiz -> sonuç zincirini ve güvenlik senaryolarını (G1–G6)
uçtan uca dener. FastAPI kurulu değilse bu dosya atlanır.
"""

import pytest
from conftest import make_csv, t

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app, raise_server_exceptions=False)


def upload(content, name="kesinti.csv"):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return client.post("/api/analyze", files={"file": (name, content, "text/csv")})


def test_ana_sayfa_ve_ornek_dosya():
    assert client.get("/").status_code == 200
    sample = client.get("/ornek.csv")
    assert sample.status_code == 200
    assert sample.text.startswith("otobus,sensor,baslangic,bitis")


def test_filo_bilgisi():
    data = client.get("/api/fleet").json()
    assert data["otobusler"] and data["sensorler"]


def test_ornek_dosya_analiz_edilir():
    response = upload(client.get("/ornek.csv").content)
    assert response.status_code == 200
    assert response.json()["findings"]


def test_basarili_analiz():
    response = upload(make_csv(("B1", "S1", t(2), t(9))))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["record_count"] == 1
    assert body["findings"][0]["message"] == (
        "00:00:02–00:00:09 arası sorun B1 otobüsünün S1 sensöründe."
    )
    assert body["summary"] == {"istasyon": 0, "otobus": 0, "sensor": 1}


def test_kesinti_yok_mesaji():
    body = upload(make_csv()).json()
    assert body["findings"] == []
    assert body["message"] == "Kesinti bulunamadı."


def test_hatali_satirlar_422():
    response = upload(make_csv(("B9", "S1", t(2), t(9))))
    assert response.status_code == 422
    assert response.json()["errors"] == ["2. satır: tanımsız otobüs 'B9'"]


@pytest.mark.parametrize("name", ["rapor.pdf", "program.exe", "veri", "veri.csv.exe"])
def test_g1_csv_olmayan_uzanti(name):
    assert upload(make_csv(), name=name).status_code == 415


def test_g2_uzantisi_degistirilmis_ikili_dosya():
    response = upload(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", name="resim.csv")
    assert response.status_code == 400
    assert "metin" in response.json()["errors"][0]


def test_g3_buyuk_dosya(monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 100)
    assert upload("x" * 101).status_code == 413


def test_g4_script_calismaz():
    response = upload(make_csv(("<script>alert(1)</script>", "S1", t(2), t(9))))
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")


def test_g5_dosya_adi_ile_diske_yazilmaz(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    upload(make_csv(("B1", "S1", t(2), t(9))), name="../../etc/passwd.csv")
    assert list(tmp_path.iterdir()) == []


def test_g6_beklenmeyen_hatada_teknik_doküm_yok(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("gizli iç detay")

    monkeypatch.setattr(main, "analyze", broken)
    response = upload(make_csv(("B1", "S1", t(2), t(9))))
    assert response.status_code == 500
    assert "gizli" not in response.text
    assert "Traceback" not in response.text


def test_turkce_excel_kodlamasi():
    text = "otobus;sensor;baslangic;bitis\r\nB1;S1;00:00:02;00:00:09\r\n"
    assert upload(text.encode("cp1254")).status_code == 200
